"""Diagnostic backtest for a simple model-driven transfer strategy.

This module is intentionally separate from the live planner. It answers a narrow
research question: what would a deterministic, model-driven one-transfer rule
have done across 2025-26 if it only used information available before each
gameweek? The score uses a projected legal starting XI, basic autosubs, and
an intentionally hindsight-optimal captain.

It is not an automatic transfer recommender for the app. The initial squad is a
reproducible heuristic, and the strategy uses a one-transfer-per-gameweek rule
with a 2.0-point net projected-gain threshold. Results are printed and optionally
written to ``data/processed`` for local inspection only.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from fpl_intelligence.preseason import build_identity_safe_preseason_pool
from fpl_intelligence.squad_optimizer import optimize_squad, optimize_starting_xi
from fpl_intelligence.step4_models import (
    FEATURE_COLUMNS,
    TEST_SEASON,
    build_minutes_classifier,
    build_ridge_model,
    load_historical_player_gameweeks,
)
from fpl_intelligence.step5_model_comparison import build_gradient_boosting_model
from fpl_intelligence.step6_backtest import get_training_data_for_gameweek

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = PROJECT_ROOT / "data" / "processed" / "backtest_transfer_strategy_results.csv"

INITIAL_BUDGET = 100.0
MAX_PLAYERS_PER_TEAM = 3
FREE_TRANSFER_CAP = 4
DEFAULT_GAIN_THRESHOLD = 2.0
LOOKAHEAD_DECISION_THRESHOLD = 1.0
MIN_PRESEASON_MINUTES = 900
POSITION_QUOTAS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
POSITION_ORDER = tuple(POSITION_QUOTAS)
VALID_FORMATIONS = (
    (3, 4, 3),
    (3, 5, 2),
    (4, 3, 3),
    (4, 4, 2),
    (4, 5, 1),
    (5, 2, 3),
    (5, 3, 2),
    (5, 4, 1),
)

MODEL_BUILDERS: dict[str, Callable[[], Pipeline]] = {
    "Ridge Regression": build_ridge_model,
    "Gradient Boosting Regressor": build_gradient_boosting_model,
}
MODEL_ALIASES = {
    "ridge": "Ridge Regression",
    "gradient": "Gradient Boosting Regressor",
    "gradient-boosting": "Gradient Boosting Regressor",
}


def _console_safe(value: Any) -> str:
    """Keep console output runnable on Windows code pages while preserving source data."""

    return str(value).encode("ascii", errors="replace").decode("ascii")


@dataclass(frozen=True)
class TransferDecision:
    outgoing_id: int | None
    incoming_id: int | None
    outgoing_name: str | None
    incoming_name: str | None
    projected_gain: float
    net_projected_gain: float
    hit_cost: int
    outgoing_price: float | None
    incoming_price: float | None

    @property
    def made(self) -> bool:
        return self.outgoing_id is not None and self.incoming_id is not None


@dataclass(frozen=True)
class BacktestResult:
    rows: pd.DataFrame
    initial_squad: pd.DataFrame
    final_squad: pd.DataFrame
    total_points: float
    baseline_points: float
    total_hit_cost: int
    transfers_made: int


@dataclass(frozen=True)
class LineupSelection:
    starting_ids: tuple[int, ...]
    bench_ids: tuple[int, ...]
    formation: str


@dataclass(frozen=True)
class GameweekScore:
    points: float
    raw_starter_points: float
    captain_id: int | None
    starting_ids: tuple[int, ...]
    bench_ids: tuple[int, ...]
    autosub_ids: tuple[int, ...]
    formation: str


def position_group(position: Any) -> str:
    """Map the historical position labels to the four FPL squad buckets."""

    value = str(position or "").upper()
    if value in {"GKP", "GOALKEEPER"}:
        return "GK"
    return "MID" if value == "AM" else value


def _formation_name(formation: tuple[int, int, int]) -> str:
    return "-".join(str(value) for value in formation)


def _is_legal_starting_xi(positions: list[str]) -> bool:
    counts = pd.Series(positions).value_counts().to_dict()
    outfield_count = len(positions) - counts.get("GK", 0)
    return (
        len(positions) == 11
        and counts.get("GK", 0) == 1
        and 3 <= counts.get("DEF", 0) <= 5
        and 2 <= counts.get("MID", 0) <= 5
        and 1 <= counts.get("FWD", 0) <= 3
        and outfield_count == 10
    )


def validate_squad(
    squad: pd.DataFrame,
    budget: float = INITIAL_BUDGET,
    max_players_per_team: int = MAX_PLAYERS_PER_TEAM,
) -> list[str]:
    """Return human-readable FPL roster violations for a 15-player squad."""

    violations: list[str] = []
    if len(squad) != 15:
        violations.append(f"squad has {len(squad)} players, expected 15")

    if squad["player_id"].duplicated().any():
        violations.append("squad contains duplicate player IDs")

    positions = squad["position"].map(position_group)
    for position, required in POSITION_QUOTAS.items():
        actual = int((positions == position).sum())
        if actual != required:
            violations.append(f"squad has {actual} {position}, expected {required}")

    team_counts = squad.groupby("team")["player_id"].size()
    over_limit = team_counts[team_counts > max_players_per_team]
    if not over_limit.empty:
        teams = ", ".join(f"{team} ({count})" for team, count in over_limit.items())
        violations.append(f"club limit exceeded: {teams}")

    total_price = float(squad["price"].sum()) if "price" in squad else float("inf")
    if total_price > budget + 1e-9:
        violations.append(f"squad costs GBP {total_price:.1f}m, above GBP {budget:.1f}m budget")

    return violations


def _normalise(series: pd.Series) -> pd.Series:
    maximum = pd.to_numeric(series, errors="coerce").max()
    if pd.isna(maximum) or maximum <= 0:
        return pd.Series(0.0, index=series.index)
    return pd.to_numeric(series, errors="coerce").fillna(0.0) / maximum


def build_preseason_scores(
    players: pd.DataFrame,
    season: str = TEST_SEASON,
    prior_season: str | None = "2024-25",
) -> pd.DataFrame:
    """Build a GW1 score without treating season-local IDs as identities."""

    scored = build_identity_safe_preseason_pool(
        players,
        season=season,
        prior_season=prior_season,
    )
    scored["preseason_value_score"] = scored["identity_value_score"]
    return scored


def _choose_cheapest_valid_squad(candidates: pd.DataFrame) -> pd.DataFrame:
    selected: list[pd.Series] = []
    team_counts: dict[str, int] = {}
    for position in POSITION_ORDER:
        pool = candidates[candidates["position_group"] == position].sort_values(
            ["price", "preseason_value_score", "player_id"],
            ascending=[True, False, True],
        )
        for _, candidate in pool.iterrows():
            if team_counts.get(candidate["team"], 0) >= MAX_PLAYERS_PER_TEAM:
                continue
            selected.append(candidate)
            team_counts[candidate["team"]] = team_counts.get(candidate["team"], 0) + 1
            selected_count = sum(position_group(row["position"]) == position for row in selected)
            if selected_count == POSITION_QUOTAS[position]:
                break

    squad = pd.DataFrame(selected).reset_index(drop=True)
    violations = validate_squad(squad, budget=float("inf"))
    if violations:
        raise ValueError(f"Could not construct a valid cheapest squad: {'; '.join(violations)}")
    return squad


def build_initial_squad(
    players: pd.DataFrame,
    season: str = TEST_SEASON,
    prior_season: str | None = "2024-25",
    minutes_floor: int | None = None,
) -> pd.DataFrame:
    """Select a legal identity-safe GW1 squad with the exact MILP optimizer."""

    candidates = build_preseason_scores(players, season=season, prior_season=prior_season)
    if minutes_floor is not None:
        candidates = candidates[
            ~candidates["prior_matched"]
            | (candidates["prior_minutes"] >= minutes_floor)
        ].copy()
    missing_positions = [
        position
        for position, required in POSITION_QUOTAS.items()
        if int((candidates["position_group"] == position).sum()) < required
    ]
    if missing_positions:
        raise ValueError(
            "The preseason minutes filter left too few candidates for: "
            + ", ".join(missing_positions)
        )
    squad = optimize_squad(candidates, prediction_column="preseason_value_score")
    violations = validate_squad(squad)
    if violations:
        raise ValueError(f"Initial squad is invalid: {'; '.join(violations)}")
    return squad


def train_gameweek_predictions(
    players: pd.DataFrame,
    gameweek: int,
    model_name: str = "Ridge Regression",
) -> pd.DataFrame:
    """Retrain points and minutes models using only rows before ``gameweek``."""

    if model_name not in MODEL_BUILDERS:
        raise ValueError(f"Unknown model {model_name!r}; choose from {', '.join(MODEL_BUILDERS)}")
    training = get_training_data_for_gameweek(players, gameweek)
    target = players[(players["season"] == TEST_SEASON) & (players["gameweek"] == gameweek)].copy()
    if target.empty:
        raise ValueError(f"No target rows for {TEST_SEASON} GW{gameweek}")
    current_training = training[training["season"] == TEST_SEASON]
    if not current_training.empty and int(current_training["gameweek"].max()) >= gameweek:
        raise AssertionError("Training data contains the target or a future gameweek")

    minutes_model = build_minutes_classifier()
    minutes_model.fit(training[FEATURE_COLUMNS], (training["minutes"] >= 60).astype(int))
    points_model = MODEL_BUILDERS[model_name]()
    points_model.fit(training[FEATURE_COLUMNS], training["next_gameweek_points"])

    target["predicted_points"] = points_model.predict(target[FEATURE_COLUMNS])
    target["probability_60_plus_minutes"] = minutes_model.predict_proba(
        target[FEATURE_COLUMNS]
    )[:, 1]
    target["expected_points_adjusted"] = (
        target["predicted_points"] * target["probability_60_plus_minutes"]
    ).clip(lower=0.0)
    target["decision_price"] = target["price_before_deadline"].fillna(target["price"])
    return target


def _latest_prices(players: pd.DataFrame, gameweek: int) -> dict[int, float]:
    # GW1 uses the opening snapshot. Before later deadlines, the latest safe
    # historical price is the previous completed-GW snapshot, not the target GW.
    cutoff = gameweek if gameweek == 1 else gameweek - 1
    rows = players[
        (players["season"] == TEST_SEASON) & (players["gameweek"] <= cutoff)
    ].sort_values(["player_id", "gameweek"])
    latest = rows.drop_duplicates("player_id", keep="last")
    return {int(row.player_id): float(row.price) for row in latest.itertuples()}


def _decision_price(row: pd.Series) -> float:
    value = row.get("decision_price")
    if value is not None and pd.notna(value):
        return float(value)
    return float(row["price"])


def choose_transfer(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    bank: float,
    free_transfers: int,
    gain_threshold: float = DEFAULT_GAIN_THRESHOLD,
) -> TransferDecision:
    """Choose the best legal single transfer using adjusted model projections."""

    projection_by_id = predictions.set_index("player_id")["expected_points_adjusted"].to_dict()
    candidates = predictions.copy()
    if "decision_price" not in candidates:
        candidates["decision_price"] = np.nan
    candidates["position_group"] = candidates["position"].map(position_group)
    squad_ids = set(int(value) for value in squad["player_id"])
    hit_cost = 0 if free_transfers > 0 else 4
    # Convert the small candidate pools once. The previous nested ``iterrows``
    # implementation rebuilt grouped frames and team counts for every possible
    # transfer, which made a two-horizon strategy unnecessarily expensive while
    # producing the same legal options and tie-break order.
    candidate_columns = [
        "player_id",
        "team",
        "price",
        "decision_price",
        "expected_points_adjusted",
        "player_name",
    ]
    candidates_by_position = {
        group: list(
            frame[candidate_columns].itertuples(index=False, name=None)
        )
        for group, frame in candidates.groupby("position_group", sort=False)
    }
    team_counts = squad.groupby("team")["player_id"].size().to_dict()
    options: list[tuple[float, float, int, int, str, float, str, float]] = []

    for outgoing_id_value, outgoing_position, outgoing_team, outgoing_price, outgoing_name in squad[
        ["player_id", "position", "team", "price", "player_name"]
    ].itertuples(index=False, name=None):
        outgoing_id = int(outgoing_id_value)
        outgoing_projection = float(projection_by_id.get(outgoing_id, 0.0))
        same_position = candidates_by_position.get(position_group(outgoing_position), [])
        remaining_team_counts = dict(team_counts)
        remaining_team_counts[outgoing_team] = (
            remaining_team_counts.get(outgoing_team, 0) - 1
        )
        for (
            incoming_id_value,
            incoming_team,
            incoming_price_value,
            decision_price,
            incoming_projection,
            incoming_name,
        ) in same_position:
            incoming_id = int(incoming_id_value)
            if incoming_id in squad_ids or incoming_id == outgoing_id:
                continue
            incoming_price = float(
                decision_price
                if decision_price is not None and pd.notna(decision_price)
                else incoming_price_value
            )
            if incoming_price > float(outgoing_price) + bank + 1e-9:
                continue
            if remaining_team_counts.get(incoming_team, 0) >= MAX_PLAYERS_PER_TEAM:
                continue
            projected_gain = float(incoming_projection) - outgoing_projection
            net_gain = projected_gain - hit_cost
            if net_gain <= gain_threshold:
                continue
            options.append(
                (
                    net_gain,
                    projected_gain,
                    -incoming_id,
                    -outgoing_id,
                    incoming_name,
                    incoming_price,
                    outgoing_name,
                    float(outgoing_price),
                )
            )

    if not options:
        return TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)

    (
        net_gain,
        projected_gain,
        neg_incoming_id,
        neg_outgoing_id,
        incoming_name,
        incoming_price,
        outgoing_name,
        outgoing_price,
    ) = max(options, key=lambda item: item[:4])
    outgoing_id = -neg_outgoing_id
    return TransferDecision(
        outgoing_id=outgoing_id,
        incoming_id=-neg_incoming_id,
        outgoing_name=str(outgoing_name),
        incoming_name=str(incoming_name),
        projected_gain=projected_gain,
        net_projected_gain=net_gain,
        hit_cost=hit_cost,
        outgoing_price=float(outgoing_price),
        incoming_price=float(incoming_price),
    )


def _empty_transfer_decision() -> TransferDecision:
    return TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)


def _projected_squad_points(squad: pd.DataFrame, predictions: pd.DataFrame) -> float:
    """Return projected points for the optimizer-selected XI of a squad."""

    if predictions.empty:
        return 0.0
    projections = predictions.set_index("player_id")["expected_points_adjusted"].to_dict()
    lineup = select_starting_xi(squad, projections)
    return float(sum(float(projections.get(player_id, 0.0)) for player_id in lineup.starting_ids))


def _hypothetical_transfer_squad(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    decision: TransferDecision,
) -> pd.DataFrame:
    """Apply a transfer to a hypothetical branch without changing live state."""

    if not decision.made:
        return squad.copy()
    incoming = predictions[predictions["player_id"] == decision.incoming_id].iloc[0].copy()
    incoming["price"] = _decision_price(incoming)
    updated = squad[squad["player_id"] != decision.outgoing_id].copy()
    updated = pd.concat([updated, pd.DataFrame([incoming])], ignore_index=True)
    violations = validate_squad(updated, budget=float("inf"))
    if violations:
        raise ValueError(
            "Hypothetical transfer produced an invalid squad: "
            + "; ".join(violations)
        )
    return updated


def _projected_branch_delta(
    before: pd.DataFrame,
    after: pd.DataFrame,
    prediction_frames: list[pd.DataFrame],
) -> float:
    return float(
        sum(
            _projected_squad_points(after, frame)
            - _projected_squad_points(before, frame)
            for frame in prediction_frames
            if not frame.empty
        )
    )


@dataclass(frozen=True)
class TwoGameweekLookaheadStrategy:
    """Compare a transfer-now branch with a one-week bank-and-wait branch."""

    decision_threshold: float = LOOKAHEAD_DECISION_THRESHOLD
    name: str = "two-gameweek-lookahead"
    version: str = "m5-lookahead-v1"
    requires_future_predictions: bool = True

    def decide(self, context: Any) -> TransferDecision:
        current = context.predictions
        best_now = choose_transfer(
            context.squad,
            current,
            bank=context.bank,
            free_transfers=context.free_transfers,
            gain_threshold=-float("inf"),
        )
        if not best_now.made:
            return _empty_transfer_decision()

        after_now = _hypothetical_transfer_squad(context.squad, current, best_now)
        future_frames = [
            context.future_predictions.get(context.gameweek + offset, pd.DataFrame())
            for offset in (1, 2)
        ]
        now_value = (
            _projected_branch_delta(
                context.squad,
                after_now,
                [current, *future_frames],
            )
            - best_now.hit_cost
        )

        next_predictions = future_frames[0]
        wait_value = 0.0
        if not next_predictions.empty:
            next_free_transfers = min(
                context.free_transfer_cap, context.free_transfers + 1
            )
            best_wait = choose_transfer(
                context.squad,
                next_predictions,
                bank=context.bank,
                free_transfers=next_free_transfers,
                gain_threshold=-float("inf"),
            )
            if best_wait.made:
                after_wait = _hypothetical_transfer_squad(
                    context.squad, next_predictions, best_wait
                )
                wait_value = (
                    _projected_branch_delta(
                        context.squad,
                        after_wait,
                        future_frames,
                    )
                    - best_wait.hit_cost
                )

        if now_value <= 0.0 or now_value - wait_value <= self.decision_threshold:
            return _empty_transfer_decision()

        return TransferDecision(
            outgoing_id=best_now.outgoing_id,
            incoming_id=best_now.incoming_id,
            outgoing_name=best_now.outgoing_name,
            incoming_name=best_now.incoming_name,
            projected_gain=now_value + best_now.hit_cost,
            net_projected_gain=now_value,
            hit_cost=best_now.hit_cost,
            outgoing_price=best_now.outgoing_price,
            incoming_price=best_now.incoming_price,
        )


def _apply_transfer(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    decision: TransferDecision,
) -> pd.DataFrame:
    if not decision.made:
        return squad.copy()
    incoming = predictions[predictions["player_id"] == decision.incoming_id].iloc[0]
    incoming = incoming.copy()
    incoming["price"] = _decision_price(incoming)
    updated = squad[squad["player_id"] != decision.outgoing_id].copy()
    updated = pd.concat([updated, pd.DataFrame([incoming])], ignore_index=True)
    updated["position_group"] = updated["position"].map(position_group)
    violations = validate_squad(updated)
    if violations:
        raise ValueError(f"Transfer produced an invalid squad: {'; '.join(violations)}")
    return updated


def select_starting_xi(
    squad: pd.DataFrame,
    projected_points: dict[int, float],
) -> LineupSelection:
    """Choose the optimizer's highest-projected legal formation and bench."""
    lineup = optimize_starting_xi(squad, projected_points)
    return LineupSelection(lineup.starting_ids, lineup.bench_ids, lineup.formation)


def score_gameweek(
    squad: pd.DataFrame,
    target: pd.DataFrame,
    projected_points: dict[int, float],
) -> GameweekScore:
    """Score a squad using XI-only points, basic autosubs, and hindsight captaincy."""

    lineup = select_starting_xi(squad, projected_points)
    target_rows = target.drop_duplicates("player_id").set_index("player_id")
    points = target_rows["next_gameweek_points"].to_dict()
    active_ids, autosub_ids = resolve_active_lineup(squad, target, lineup)

    captain_id = max(
        active_ids,
        key=lambda player_id: (
            float(points.get(player_id, 0)),
            float(projected_points.get(player_id, 0)),
            -player_id,
        ),
    )
    raw_starter_points = float(sum(float(points.get(player_id, 0)) for player_id in active_ids))
    total_points = raw_starter_points + float(points.get(captain_id, 0))
    return GameweekScore(
        points=total_points,
        raw_starter_points=raw_starter_points,
        captain_id=captain_id,
        starting_ids=tuple(active_ids),
        bench_ids=lineup.bench_ids,
        autosub_ids=tuple(autosub_ids),
        formation=lineup.formation,
    )


def resolve_active_lineup(
    squad: pd.DataFrame,
    target: pd.DataFrame,
    lineup: LineupSelection,
) -> tuple[list[int], tuple[int, ...]]:
    """Apply the benchmark's actual-minutes autosub rules to a lineup."""

    target_rows = target.drop_duplicates("player_id").set_index("player_id")
    minutes = target_rows["minutes"].to_dict()
    positions = {
        int(row.player_id): position_group(row.position) for row in squad.itertuples()
    }
    active_ids = list(lineup.starting_ids)
    used_bench: set[int] = set()
    autosub_ids: list[int] = []

    for starter_id in lineup.starting_ids:
        if float(minutes.get(starter_id, 0)) != 0:
            continue
        starter_position = positions[starter_id]
        for bench_id in lineup.bench_ids:
            if bench_id in used_bench or float(minutes.get(bench_id, 0)) <= 0:
                continue
            bench_position = positions[bench_id]
            if bench_position == "GK" and starter_position != "GK":
                continue
            if bench_position != "GK" and starter_position == "GK":
                continue
            proposed_positions = [
                positions[player_id] if player_id != starter_id else bench_position
                for player_id in active_ids
            ]
            if not _is_legal_starting_xi(proposed_positions):
                continue
            active_index = active_ids.index(starter_id)
            active_ids[active_index] = bench_id
            used_bench.add(bench_id)
            autosub_ids.append(bench_id)
            break

    return active_ids, tuple(autosub_ids)


def run_transfer_strategy_backtest(
    players: pd.DataFrame,
    model_name: str = "Ridge Regression",
    gain_threshold: float = DEFAULT_GAIN_THRESHOLD,
    verbose: bool = True,
) -> BacktestResult:
    """Run the no-lookahead transfer simulation from GW1 through GW38."""

    season_players = players[players["season"] == TEST_SEASON].copy()
    gameweeks = sorted(int(value) for value in season_players["gameweek"].unique())
    if not gameweeks or gameweeks[0] != 1:
        raise ValueError(f"Expected {TEST_SEASON} data starting at GW1")

    initial_squad = build_initial_squad(players)
    squad = initial_squad.copy()
    bank = 0.0
    free_transfers = 1
    result_rows: list[dict[str, Any]] = []
    strategy_points = 0.0
    baseline_points = 0.0
    total_hit_cost = 0
    transfers_made = 0
    preseason_projection = build_preseason_scores(players).set_index("player_id")[
        "preseason_value_score"
    ].to_dict()

    if verbose:
        print(f"Diagnostic transfer strategy backtest ({TEST_SEASON})")
        print(f"- Model: {model_name}; net projected-gain threshold: {gain_threshold:.1f} points")
        print(
            "- Refit boundary: before each target GW using prior seasons plus "
            "current-season history."
        )
        print(
            "- GW1 squad: deterministic prior-season value heuristic, GBP 100.0m, "
            "FPL roster limits."
        )

    for gameweek in gameweeks:
        target = season_players[season_players["gameweek"] == gameweek]
        prices = _latest_prices(players, gameweek)
        squad["price"] = squad["player_id"].map(prices).fillna(squad["price"])
        bank_before = bank
        free_transfers_before = free_transfers

        decision = TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)
        projected_points = preseason_projection
        if gameweek >= 2:
            predictions = train_gameweek_predictions(players, gameweek, model_name)
            projected_points = predictions.set_index("player_id")[
                "expected_points_adjusted"
            ].to_dict()
            decision = choose_transfer(
                squad,
                predictions,
                bank=bank,
                free_transfers=free_transfers,
                gain_threshold=gain_threshold,
            )
            if decision.made:
                squad = _apply_transfer(squad, predictions, decision)
                bank = round(bank + decision.outgoing_price - decision.incoming_price, 1)
                free_transfers = max(0, free_transfers - 1)
                total_hit_cost += decision.hit_cost
                transfers_made += 1

        strategy_score = score_gameweek(squad, target, projected_points)
        baseline_score = score_gameweek(initial_squad, target, projected_points)
        strategy_points_gw = strategy_score.points
        baseline_points_gw = baseline_score.points
        strategy_points += strategy_points_gw - decision.hit_cost
        baseline_points += baseline_points_gw
        result_rows.append(
            {
                "season": TEST_SEASON,
                "gameweek": gameweek,
                "strategy_points": strategy_points_gw,
                "baseline_points": baseline_points_gw,
                "strategy_raw_starter_points": strategy_score.raw_starter_points,
                "baseline_raw_starter_points": baseline_score.raw_starter_points,
                "hit_cost": decision.hit_cost,
                "strategy_net_points": strategy_points_gw - decision.hit_cost,
                "cumulative_strategy_points": strategy_points,
                "cumulative_baseline_points": baseline_points,
                "transfers_made": int(decision.made),
                "outgoing": decision.outgoing_name,
                "incoming": decision.incoming_name,
                "projected_gain": round(decision.projected_gain, 3),
                "net_projected_gain": round(decision.net_projected_gain, 3),
                "strategy_captain_id": strategy_score.captain_id,
                "baseline_captain_id": baseline_score.captain_id,
                "strategy_formation": strategy_score.formation,
                "baseline_formation": baseline_score.formation,
                "strategy_autosubs": "+".join(str(value) for value in strategy_score.autosub_ids),
                "baseline_autosubs": "+".join(str(value) for value in baseline_score.autosub_ids),
                "bank_before": round(bank_before, 1),
                "free_transfers_before": free_transfers_before,
            }
        )

        free_transfers = min(FREE_TRANSFER_CAP, free_transfers + 1)
        if verbose:
            transfer_text = (
                f"{_console_safe(decision.outgoing_name)} -> "
                f"{_console_safe(decision.incoming_name)}"
                if decision.made
                else "no transfer"
            )
            print(
                f"- GW{gameweek:02d}: {transfer_text}; actual {strategy_points_gw:.1f} pts"
                f"; captain {strategy_score.captain_id}; autosubs {len(strategy_score.autosub_ids)}"
                f"; hit -{decision.hit_cost}; bank GBP {bank:.1f}m; FT next {free_transfers}"
            )

    results = pd.DataFrame(result_rows)
    return BacktestResult(
        rows=results,
        initial_squad=initial_squad,
        final_squad=squad,
        total_points=round(strategy_points, 2),
        baseline_points=round(baseline_points, 2),
        total_hit_cost=total_hit_cost,
        transfers_made=transfers_made,
    )


def print_summary(result: BacktestResult, results_path: Path | None = RESULTS_PATH) -> None:
    print("\nSummary")
    print(f"- Model transfer strategy: {result.total_points:.1f} points")
    print(f"- No-transfers baseline: {result.baseline_points:.1f} points")
    print(
        f"- Difference versus baseline: "
        f"{result.total_points - result.baseline_points:+.1f} points"
    )
    print(f"- Transfers made: {result.transfers_made}")
    print(f"- Total hit costs: -{result.total_hit_cost} points")
    print("\nInitial GW1 squad")
    print(", ".join(_console_safe(name) for name in result.initial_squad["player_name"]))
    print("\nCaveats")
    print(
        "- This is a simplified deterministic diagnostic, not the live planner's "
        "recommendation engine."
    )
    print(
        f"- The GW1 squad excludes players below {MIN_PRESEASON_MINUTES} prior-season "
        "minutes, then uses prior-season output, value, and GW1 ownership."
    )
    print(
        "- The rule considers at most one transfer per gameweek and uses a "
        "projected-gain threshold."
    )
    print(
        "- It models a highest-projected legal formation, XI-only points, basic autosubs, "
        "and one captain doubled each gameweek."
    )
    print(
        "- Captaincy always picks the highest-scoring starter in hindsight. This is "
        "optimistic and treats captaincy as solved so the diagnostic tests transfers."
    )
    print(
        "- It still does not model chips, injuries/news, press conferences, price-change "
        "timing, selling-value rules, or manager behaviour."
    )
    print(
        "- Historical blanks, doubles, and missing player-gameweek rows are treated "
        "as zero points for that player-gameweek."
    )
    if results_path is not None:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        result.rows.to_csv(results_path, index=False)
        print(f"\nSaved local diagnostic rows to {results_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        choices=sorted(MODEL_ALIASES),
        default="ridge",
        help="points model to refit at each GW boundary (default: ridge)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_GAIN_THRESHOLD,
        help="minimum net projected gain required to make a transfer (default: 2.0)",
    )
    parser.add_argument(
        "--no-save-results",
        action="store_true",
        help="print the report without writing the optional local results CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    model_name = MODEL_ALIASES[args.model]
    result = run_transfer_strategy_backtest(
        load_historical_player_gameweeks(),
        model_name=model_name,
        gain_threshold=args.threshold,
    )
    print_summary(result, None if args.no_save_results else RESULTS_PATH)


if __name__ == "__main__":
    main()
