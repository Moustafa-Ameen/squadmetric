"""P3 multi-horizon initial-squad optimization and continuation tournament.

Opening-squad challengers use only information available for the GW1 deadline.
Projected screening never uses outcomes.  Promotion evidence comes from running
the resulting legal squads through the unchanged full-season benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from fpl_intelligence.backtest_transfer_strategy import (
    INITIAL_BUDGET,
    build_initial_squad,
    select_starting_xi,
    validate_squad,
)
from fpl_intelligence.chip_simulation import CHIP_MODE_BEAM
from fpl_intelligence.preseason import (
    IDENTITY_SAFE_INITIAL_SQUAD_MODE,
    IDENTITY_SAFE_INITIAL_SQUAD_VERSION,
    build_identity_safe_preseason_pool,
)
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.season_benchmark import (
    HISTORICAL_PLAYER_GW_PATH,
    DeterministicTransferStrategy,
    SeasonBenchmarkResult,
    get_git_commit,
    run_season_benchmark,
    train_future_gameweek_predictions,
    train_gameweek_predictions,
)
from fpl_intelligence.squad_optimizer import (
    MAX_PLAYERS_PER_TEAM,
    POSITION_QUOTAS,
    position_group,
)
from fpl_intelligence.step4_models import load_historical_player_gameweeks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "initial_squad_tournaments"
P3_SCHEMA_VERSION = "pdc-p3-initial-squad-championship-v1"
P3_OPTIMIZER_VERSION = "p3-opening-milp-v1"
P3_HORIZONS = (3, 5, 8)
P3_BASELINE_NAME = IDENTITY_SAFE_INITIAL_SQUAD_MODE
CHECKPOINT_FILES = {
    "candidates": "checkpoint_projected_candidates.csv",
    "squads": "checkpoint_candidate_squads.csv",
    "projected_plan": "checkpoint_projected_plan.csv",
    "continuation": "checkpoint_full_season_continuation.csv",
    "decisions": "checkpoint_gameweek_decisions.csv",
}


@dataclass(frozen=True)
class OpeningSquadConfig:
    """One deterministic multi-objective opening-squad policy."""

    name: str
    horizon: int
    decay: float
    depth_weight: float
    value_weight: float
    uncertainty_penalty: float
    unmatched_penalty: float
    promoted_team_penalty: float
    transfer_pressure_penalty: float
    minimum_spend: float
    captain_weight: float = 1.0
    wildcard_scenario_gameweek: int | None = None
    reliable_start_threshold: float = 0.0
    minimum_reliable_players: int = 0


P3_CONFIGS = {
    "horizon_3_attack": OpeningSquadConfig(
        name="horizon_3_attack",
        horizon=3,
        decay=0.90,
        depth_weight=0.03,
        value_weight=0.01,
        uncertainty_penalty=0.05,
        unmatched_penalty=0.03,
        promoted_team_penalty=0.01,
        transfer_pressure_penalty=0.01,
        minimum_spend=98.5,
        wildcard_scenario_gameweek=4,
    ),
    "horizon_5_balanced": OpeningSquadConfig(
        name="horizon_5_balanced",
        horizon=5,
        decay=0.92,
        depth_weight=0.08,
        value_weight=0.03,
        uncertainty_penalty=0.10,
        unmatched_penalty=0.06,
        promoted_team_penalty=0.03,
        transfer_pressure_penalty=0.04,
        minimum_spend=97.0,
        wildcard_scenario_gameweek=6,
    ),
    "horizon_8_flexible": OpeningSquadConfig(
        name="horizon_8_flexible",
        horizon=8,
        decay=0.94,
        depth_weight=0.17,
        value_weight=0.06,
        uncertainty_penalty=0.16,
        unmatched_penalty=0.10,
        promoted_team_penalty=0.05,
        transfer_pressure_penalty=0.08,
        minimum_spend=95.5,
    ),
}

# P7 keeps the validated eight-Gameweek policy as the default, but exposes
# deterministic risk alternatives from the same projections and legality model.
GW1_DECISION_PROFILES = {
    "maximum_points": replace(
        P3_CONFIGS["horizon_8_flexible"],
        name="gw1_maximum_points",
        uncertainty_penalty=0.0,
        depth_weight=0.04,
        unmatched_penalty=0.04,
        promoted_team_penalty=0.02,
        transfer_pressure_penalty=0.03,
        reliable_start_threshold=0.0,
        minimum_reliable_players=0,
    ),
    "balanced": replace(
        P3_CONFIGS["horizon_8_flexible"],
        name="gw1_balanced",
        reliable_start_threshold=0.35,
        minimum_reliable_players=13,
    ),
    "safe": replace(
        P3_CONFIGS["horizon_8_flexible"],
        name="gw1_safe_depth",
        uncertainty_penalty=0.35,
        depth_weight=0.24,
        value_weight=0.08,
        unmatched_penalty=0.18,
        promoted_team_penalty=0.08,
        transfer_pressure_penalty=0.12,
        minimum_spend=94.0,
        reliable_start_threshold=0.55,
        minimum_reliable_players=14,
    ),
}


@dataclass(frozen=True)
class OpeningProjectionBundle:
    """Point-in-time candidate data and GW1-GW8 projections."""

    season: str
    candidates: pd.DataFrame
    projections: dict[int, pd.DataFrame]
    prior_season: str | None
    data_cutoff: str
    projection_hash: str


@dataclass(frozen=True)
class OpeningSquadCandidate:
    """A legal optimized squad with projected decision diagnostics."""

    name: str
    version: str
    squad: pd.DataFrame
    projected_metrics: dict[str, Any]
    horizon_lineups: dict[int, tuple[int, ...]]
    horizon_captains: dict[int, int]


@dataclass(frozen=True)
class InitialSquadTournamentResult:
    """P3 projected screening, continuation evidence, and acceptance result."""

    candidates: pd.DataFrame
    squads: pd.DataFrame
    projected_plan: pd.DataFrame
    continuation: pd.DataFrame
    decisions: pd.DataFrame
    acceptance: pd.DataFrame
    selected_candidate: str | None
    passed: bool
    output_dir: Path | None = None


def build_opening_projection_bundle(
    players: pd.DataFrame,
    season: str,
    *,
    model_name: str = "Ridge Regression",
    minutes_mode: str = "binary",
    feature_mode: str = "baseline",
    projection_mode: str = "total_points",
) -> OpeningProjectionBundle:
    """Build GW1-GW8 projections from a GW1-safe snapshot."""

    prior_season = _previous_season(players, season)
    candidates = build_identity_safe_preseason_pool(
        players,
        season=season,
        prior_season=prior_season,
    )
    model_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
    gw1, _ = train_gameweek_predictions(
        players,
        season,
        1,
        model_name=model_name,
        minutes_mode=minutes_mode,
        feature_mode=feature_mode,
        projection_mode=projection_mode,
        _model_context_cache=model_cache,
    )
    future = train_future_gameweek_predictions(
        players,
        season,
        1,
        model_name=model_name,
        minutes_mode=minutes_mode,
        feature_mode=feature_mode,
        projection_mode=projection_mode,
        horizons=tuple(range(1, 8)),
        _model_context_cache=model_cache,
    )
    projections = {1: _projection_frame(gw1, candidates)}
    for gameweek in range(2, 9):
        projections[gameweek] = _projection_frame(
            future.get(gameweek, pd.DataFrame()),
            candidates,
        )
    _assert_opening_cutoff(candidates, projections)
    projection_hash = _dataframe_collection_hash(projections)
    return OpeningProjectionBundle(
        season=season,
        candidates=candidates,
        projections=projections,
        prior_season=prior_season,
        data_cutoff=f"{season}:GW00",
        projection_hash=projection_hash,
    )


def build_live_opening_projection_bundle(
    projected_players: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> OpeningProjectionBundle:
    """Adapt live GW1-GW8 projections to the same reviewed P3 optimizer contract."""

    if not projected_players:
        raise ValueError("Live opening-squad projections are empty")
    candidate_rows = []
    projection_rows: dict[int, list[dict[str, Any]]] = {
        gameweek: [] for gameweek in range(1, 9)
    }
    for player in projected_players:
        player_id = int(player["element_id"])
        prior_source = str(player.get("prior_source") or "unknown")
        unmatched = (
            "new_player" in prior_source
            or "unmatched" in prior_source
            or prior_source in {"unknown", "current_season"}
        )
        candidate_rows.append(
            {
                "player_id": player_id,
                "player_name": player.get("name") or player.get("web_name"),
                "position": player.get("position"),
                "position_group": position_group(player.get("position")),
                "team": player.get("team"),
                "team_name": player.get("team_name") or player.get("team"),
                "price": float(player.get("price") or 0.0),
                "prior_matched": not unmatched,
                "unmatched_player": unmatched,
                "promoted_team": bool(player.get("promoted_team", False)),
                "identity_value_score": 0.0,
                "prior_source": prior_source,
                "status": player.get("status"),
                "chance_of_playing_next_round": player.get(
                    "chance_of_playing_next_round"
                ),
                "availability_probability": float(
                    player.get("availability_probability")
                    if player.get("availability_probability") is not None
                    else 0.5
                ),
                "start_likelihood": float(
                    player.get("start_likelihood")
                    if player.get("start_likelihood") is not None
                    else 0.4
                ),
                "launch_evidence_confidence": float(
                    player.get("launch_evidence_confidence") or 0.0
                ),
                "launch_evidence_type": player.get("launch_evidence_type"),
                "launch_evidence_source": player.get("launch_evidence_source"),
            }
        )
        by_gameweek = {
            int(row["gameweek"]): row
            for row in player.get("projections", [])
            if row.get("gameweek") is not None
        }
        for gameweek in range(1, 9):
            row = by_gameweek.get(gameweek, {})
            fixtures = row.get("fixtures", [])
            fixture_start_probabilities = [
                float(fixture.get("start_likelihood") or 0.0)
                for fixture in fixtures
                if fixture.get("start_likelihood") is not None
            ]
            start_probability = (
                max(fixture_start_probabilities)
                if fixture_start_probabilities
                else float(player.get("start_likelihood") or 0.4)
            )
            projection_rows[gameweek].append(
                {
                    "player_id": player_id,
                    "projected_points": float(row.get("projected_points") or 0.0),
                    "start_probability": min(1.0, max(0.0, start_probability)),
                }
            )
    candidates = pd.DataFrame(candidate_rows)
    projections = {
        gameweek: pd.DataFrame(rows)
        for gameweek, rows in projection_rows.items()
    }
    projection_hash = _dataframe_collection_hash(projections)
    return OpeningProjectionBundle(
        season=str(metadata.get("season") or "unknown"),
        candidates=candidates,
        projections=projections,
        prior_season=None,
        data_cutoff=str(metadata.get("data_cutoff") or "unknown"),
        projection_hash=projection_hash,
    )


def optimize_opening_squad(
    bundle: OpeningProjectionBundle,
    config: OpeningSquadConfig,
) -> OpeningSquadCandidate:
    """Jointly optimize squad, legal XI, and captain over a configured horizon."""

    if config.horizon not in P3_HORIZONS:
        raise ValueError(f"P3 horizon must be one of {P3_HORIZONS}")
    candidates = bundle.candidates.drop_duplicates("player_id").reset_index(drop=True).copy()
    n_players = len(candidates)
    gameweeks = tuple(range(1, config.horizon + 1))
    n_horizons = len(gameweeks)
    projection_matrix = np.column_stack(
        [
            candidates["player_id"]
            .map(
                bundle.projections[gameweek].set_index("player_id")[
                    "projected_points"
                ]
            )
            .fillna(0.0)
            .to_numpy(dtype=float)
            for gameweek in gameweeks
        ]
    )
    start_matrix = np.column_stack(
        [
            candidates["player_id"]
            .map(
                bundle.projections[gameweek].set_index("player_id")[
                    "start_probability"
                ]
            )
            .fillna(0.4)
            .clip(0.0, 1.0)
            .to_numpy(dtype=float)
            for gameweek in gameweeks
        ]
    )
    mean_start_probability = start_matrix.mean(axis=1)
    weights = np.array(
        [config.decay ** (gameweek - 1) for gameweek in gameweeks],
        dtype=float,
    )
    uncertainty = np.sqrt(start_matrix * (1.0 - start_matrix))
    risk_adjusted = projection_matrix - config.uncertainty_penalty * (
        projection_matrix.clip(min=0.0) * uncertainty
    )
    weighted_average = (risk_adjusted * weights).sum(axis=1) / weights.sum()
    autosub_matrix = config.depth_weight * risk_adjusted * start_matrix
    autosub_support = (autosub_matrix * weights).sum(axis=1)
    late_window = risk_adjusted[:, max(0, n_horizons - 3) :].mean(axis=1)
    transfer_pressure = np.maximum(0.0, risk_adjusted[:, 0] - late_window)
    price = pd.to_numeric(candidates["price"], errors="coerce").fillna(0.0).to_numpy()
    squad_support = (
        autosub_support
        + config.value_weight * weighted_average / np.maximum(price, 3.5)
        - config.unmatched_penalty
        * candidates["unmatched_player"].astype(float).to_numpy()
        - config.promoted_team_penalty
        * candidates["promoted_team"].astype(float).to_numpy()
        - config.transfer_pressure_penalty * transfer_pressure
    )

    x_offset = 0
    y_offset = n_players
    captain_offset = n_players + n_horizons * n_players
    variable_count = n_players + 2 * n_horizons * n_players
    objective = np.zeros(variable_count, dtype=float)
    objective[x_offset : x_offset + n_players] = -squad_support
    for horizon_index, weight in enumerate(weights):
        y_start = y_offset + horizon_index * n_players
        c_start = captain_offset + horizon_index * n_players
        objective[y_start : y_start + n_players] = -weight * (
            risk_adjusted[:, horizon_index] - autosub_matrix[:, horizon_index]
        )
        objective[c_start : c_start + n_players] = (
            -weight * config.captain_weight * risk_adjusted[:, horizon_index]
        )
    # Stable tie-break: lower FPL IDs win otherwise-identical solutions.
    ids = pd.to_numeric(candidates["player_id"], errors="raise").to_numpy(dtype=float)
    objective[x_offset : x_offset + n_players] += ids * 1e-10

    matrix_rows: list[int] = []
    matrix_columns: list[int] = []
    matrix_values: list[float] = []
    lower: list[float] = []
    upper: list[float] = []

    def add_constraint(coefficients: np.ndarray, minimum: float, maximum: float) -> None:
        row_index = len(lower)
        nonzero = np.flatnonzero(coefficients)
        matrix_rows.extend([row_index] * len(nonzero))
        matrix_columns.extend(int(value) for value in nonzero)
        matrix_values.extend(float(coefficients[value]) for value in nonzero)
        lower.append(minimum)
        upper.append(maximum)

    positions = candidates["position_group"].astype(str)
    teams = candidates["team"].astype(str)
    for position, required in POSITION_QUOTAS.items():
        coefficients = np.zeros(variable_count)
        coefficients[:n_players] = positions.eq(position).astype(float)
        add_constraint(coefficients, required, required)
    budget_coefficients = np.zeros(variable_count)
    budget_coefficients[:n_players] = price
    add_constraint(
        budget_coefficients,
        config.minimum_spend,
        INITIAL_BUDGET,
    )
    for team in sorted(teams.unique()):
        coefficients = np.zeros(variable_count)
        coefficients[:n_players] = teams.eq(team).astype(float)
        add_constraint(coefficients, -np.inf, MAX_PLAYERS_PER_TEAM)
    if config.minimum_reliable_players:
        reliable = mean_start_probability >= config.reliable_start_threshold
        coefficients = np.zeros(variable_count)
        coefficients[:n_players] = reliable.astype(float)
        add_constraint(
            coefficients,
            config.minimum_reliable_players,
            np.inf,
        )

    for horizon_index in range(n_horizons):
        y_start = y_offset + horizon_index * n_players
        c_start = captain_offset + horizon_index * n_players
        xi_total = np.zeros(variable_count)
        xi_total[y_start : y_start + n_players] = 1.0
        add_constraint(xi_total, 11, 11)
        captain_total = np.zeros(variable_count)
        captain_total[c_start : c_start + n_players] = 1.0
        add_constraint(captain_total, 1, 1)
        formation_bounds = {
            "GK": (1, 1),
            "DEF": (3, 5),
            "MID": (2, 5),
            "FWD": (1, 3),
        }
        for position, (minimum, maximum) in formation_bounds.items():
            coefficients = np.zeros(variable_count)
            coefficients[y_start : y_start + n_players] = positions.eq(position).astype(
                float
            )
            add_constraint(coefficients, minimum, maximum)
        for player_index in range(n_players):
            xi_link = np.zeros(variable_count)
            xi_link[y_start + player_index] = 1.0
            xi_link[x_offset + player_index] = -1.0
            add_constraint(xi_link, -np.inf, 0)
            captain_link = np.zeros(variable_count)
            captain_link[c_start + player_index] = 1.0
            captain_link[y_start + player_index] = -1.0
            add_constraint(captain_link, -np.inf, 0)

    constraint_matrix = coo_matrix(
        (matrix_values, (matrix_rows, matrix_columns)),
        shape=(len(lower), variable_count),
    ).tocsr()
    constraints = LinearConstraint(
        constraint_matrix,
        np.array(lower, dtype=float),
        np.array(upper, dtype=float),
    )
    upper_bounds = np.ones(variable_count)
    if "availability_probability" in candidates:
        unavailable = (
            pd.to_numeric(
                candidates["availability_probability"], errors="coerce"
            ).fillna(0.5)
            <= 0.0
        ).to_numpy()
        upper_bounds[:n_players][unavailable] = 0.0
    result = milp(
        c=objective,
        integrality=np.ones(variable_count),
        bounds=Bounds(np.zeros(variable_count), upper_bounds),
        constraints=constraints,
        options={"time_limit": 30.0},
    )
    if not result.success or result.x is None:
        raise ValueError(f"P3 opening-squad MILP failed: {result.message}")

    selected_mask = result.x[:n_players] > 0.5
    squad = candidates.loc[selected_mask].copy().reset_index(drop=True)
    violations = validate_squad(squad)
    if violations:
        raise AssertionError("P3 optimizer produced an invalid squad: " + "; ".join(violations))
    lineups: dict[int, tuple[int, ...]] = {}
    captains: dict[int, int] = {}
    for horizon_index, gameweek in enumerate(gameweeks):
        y_start = y_offset + horizon_index * n_players
        c_start = captain_offset + horizon_index * n_players
        lineups[gameweek] = tuple(
            int(value)
            for value in candidates.loc[
                result.x[y_start : y_start + n_players] > 0.5,
                "player_id",
            ].sort_values()
        )
        captain_ids = candidates.loc[
            result.x[c_start : c_start + n_players] > 0.5,
            "player_id",
        ]
        if len(captain_ids) != 1:
            raise AssertionError("P3 optimizer did not select exactly one captain")
        captains[gameweek] = int(captain_ids.iloc[0])

    metrics = evaluate_opening_squad(bundle, squad)
    metrics.update(
        {
            "objective_value": float(-result.fun),
            "configured_horizon": config.horizon,
            "wildcard_scenario_gameweek": config.wildcard_scenario_gameweek,
            "cost": round(float(squad["price"].sum()), 1),
            "bank": round(INITIAL_BUDGET - float(squad["price"].sum()), 1),
            "unmatched_players": int(squad["unmatched_player"].sum()),
            "promoted_team_players": int(squad["promoted_team"].sum()),
            "mean_transfer_pressure": round(
                float(np.mean(transfer_pressure[selected_mask])),
                4,
            ),
            "mean_start_probability": round(
                float(np.mean(mean_start_probability[selected_mask])),
                4,
            ),
            "reliable_players": int(
                (
                    mean_start_probability[selected_mask]
                    >= config.reliable_start_threshold
                ).sum()
            ),
            "reliable_start_threshold": config.reliable_start_threshold,
            "autosub_activation_probability": config.depth_weight,
            "projection_hash": bundle.projection_hash,
            "data_cutoff": bundle.data_cutoff,
        }
    )
    return OpeningSquadCandidate(
        name=config.name,
        version=P3_OPTIMIZER_VERSION,
        squad=squad,
        projected_metrics=metrics,
        horizon_lineups=lineups,
        horizon_captains=captains,
    )


def build_opening_candidates(
    players: pd.DataFrame,
    bundle: OpeningProjectionBundle,
) -> list[OpeningSquadCandidate]:
    """Build the identity-safe baseline and 3/5/8-GW challengers."""

    champion = build_initial_squad(
        players,
        season=bundle.season,
        prior_season=bundle.prior_season,
        minutes_floor=None,
    )
    output = [
        _wrap_existing_squad(
            P3_BASELINE_NAME,
            IDENTITY_SAFE_INITIAL_SQUAD_VERSION,
            champion,
            bundle,
        ),
    ]
    output.extend(optimize_opening_squad(bundle, config) for config in P3_CONFIGS.values())
    return output


def evaluate_opening_squad(
    bundle: OpeningProjectionBundle,
    squad: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate a legal squad on point-in-time projected XI/captain outcomes."""

    violations = validate_squad(squad)
    if violations:
        raise ValueError("Cannot evaluate invalid opening squad: " + "; ".join(violations))
    gameweek_scores: dict[int, float] = {}
    start_probabilities: list[float] = []
    for gameweek, frame in sorted(bundle.projections.items()):
        points = frame.set_index("player_id")["projected_points"].to_dict()
        starts = frame.set_index("player_id")["start_probability"].to_dict()
        lineup = select_starting_xi(squad, points)
        captain = max(
            lineup.starting_ids,
            key=lambda player_id: (float(points.get(player_id, 0.0)), -player_id),
        )
        gameweek_scores[gameweek] = float(
            sum(float(points.get(player_id, 0.0)) for player_id in lineup.starting_ids)
            + float(points.get(captain, 0.0))
        )
        start_probabilities.extend(
            float(starts.get(player_id, 0.4)) for player_id in squad["player_id"]
        )
    return {
        "projected_points_3": round(sum(gameweek_scores.get(gw, 0.0) for gw in range(1, 4)), 4),
        "projected_points_5": round(sum(gameweek_scores.get(gw, 0.0) for gw in range(1, 6)), 4),
        "projected_points_8": round(sum(gameweek_scores.get(gw, 0.0) for gw in range(1, 9)), 4),
        "mean_start_probability": round(float(np.mean(start_probabilities)), 4),
    }


def run_initial_squad_tournament(
    *,
    seasons: tuple[str, ...] = ("2023-24", "2024-25", "2025-26"),
    players: pd.DataFrame | None = None,
    output_dir: Path | None = None,
    chip_mode: str = CHIP_MODE_BEAM,
    candidate_names: tuple[str, ...] | None = None,
    benchmark_runner: Callable[..., SeasonBenchmarkResult] = run_season_benchmark,
    generated_at: str | None = None,
) -> InitialSquadTournamentResult:
    """Run every opening-squad candidate through full-season continuation."""

    historical = (
        load_historical_player_gameweeks(HISTORICAL_PLAYER_GW_PATH)
        if players is None
        else players.copy()
    )
    dataset_hash = (
        _file_hash(HISTORICAL_PLAYER_GW_PATH)
        if players is None
        else _frame_hash(historical)
    )
    portfolio = get_production_portfolio()
    strategy = DeterministicTransferStrategy()
    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    destination = output_dir or (
        DEFAULT_OUTPUT_ROOT / f"{_filesystem_timestamp(timestamp)}-{uuid.uuid4().hex[:8]}"
    )
    checkpoint = _load_or_create_checkpoint(destination)
    candidate_rows = checkpoint["candidates"].to_dict("records")
    squad_rows = [checkpoint["squads"]] if not checkpoint["squads"].empty else []
    projected_plan_rows = checkpoint["projected_plan"].to_dict("records")
    continuation_rows = checkpoint["continuation"].to_dict("records")
    decision_rows = [checkpoint["decisions"]] if not checkpoint["decisions"].empty else []
    completed = {
        (str(row["season"]), str(row["candidate"]))
        for row in continuation_rows
    }
    reusable_squads: dict[tuple[str, str], str] = {}
    decision_sources: dict[tuple[str, str], pd.DataFrame] = {}
    if not checkpoint["squads"].empty:
        for (season, candidate), squad in checkpoint["squads"].groupby(
            ["season", "candidate"],
            sort=False,
        ):
            key = (str(season), str(candidate))
            if key in completed:
                reusable_squads[
                    (str(season), _opening_squad_hash(squad))
                ] = str(candidate)
    if not checkpoint["decisions"].empty:
        for (season, candidate), rows in checkpoint["decisions"].groupby(
            ["season", "candidate"],
            sort=False,
        ):
            decision_sources[(str(season), str(candidate))] = rows.copy()
    selected_names = set(candidate_names or ())

    for season in seasons:
        # Reuse expensive model outputs across opening-squad candidates within a
        # season, then release them before the next season.
        prediction_cache: dict[Any, Any] = {}
        captain_cache: dict[Any, Any] = {}
        future_cache: dict[Any, Any] = {}
        print(f"Building P3 opening squads for {season}...")
        bundle = build_opening_projection_bundle(
            historical,
            season,
            model_name=portfolio.projections.transfer_model,
        )
        candidates = build_opening_candidates(historical, bundle)
        if selected_names:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.name == P3_BASELINE_NAME or candidate.name in selected_names
            ]
        for candidate in candidates:
            key = (season, candidate.name)
            if key in completed:
                print(f"  Resuming after completed {candidate.name}.")
                continue
            candidate_rows.append(
                {
                    "season": season,
                    "candidate": candidate.name,
                    "version": candidate.version,
                    **candidate.projected_metrics,
                }
            )
            candidate_squad = candidate.squad.copy()
            candidate_squad["season"] = season
            candidate_squad.insert(0, "candidate", candidate.name)
            squad_rows.append(candidate_squad)
            projected_plan_rows.extend(
                _projected_plan_rows(bundle, candidate)
            )
            squad_hash = _opening_squad_hash(candidate.squad)
            reusable_candidate = reusable_squads.get((season, squad_hash))
            if reusable_candidate is not None:
                print(
                    f"  Reusing deterministic continuation from {reusable_candidate} "
                    f"for {candidate.name} (identical opening squad)."
                )
                source_key = (season, reusable_candidate)
                source_row = next(
                    row
                    for row in continuation_rows
                    if (str(row["season"]), str(row["candidate"])) == source_key
                )
                continuation_row = dict(source_row)
                continuation_row["candidate"] = candidate.name
                continuation_rows.append(continuation_row)
                reused_decisions = decision_sources[source_key].copy()
                reused_decisions["candidate"] = candidate.name
                if "initial_squad_mode" in reused_decisions:
                    reused_decisions["initial_squad_mode"] = candidate.name
                if "initial_squad_version" in reused_decisions:
                    reused_decisions["initial_squad_version"] = candidate.version
                decision_rows.append(reused_decisions)
                decision_sources[key] = reused_decisions
                reusable_squads[(season, squad_hash)] = candidate.name
                completed.add(key)
                _write_checkpoint(
                    destination,
                    candidates=pd.DataFrame(candidate_rows),
                    squads=pd.concat(squad_rows, ignore_index=True, sort=False),
                    projected_plan=pd.DataFrame(projected_plan_rows),
                    continuation=pd.DataFrame(continuation_rows),
                    decisions=pd.concat(decision_rows, ignore_index=True, sort=False),
                )
                continue
            print(f"  Continuing {candidate.name} through the complete season...")
            result = benchmark_runner(
                historical,
                season,
                strategy,
                model_name=portfolio.projections.transfer_model,
                model_version=portfolio.version,
                chip_mode=chip_mode,
                projection_portfolio=portfolio.projections,
                prediction_cache=prediction_cache,
                captain_prediction_cache=captain_cache,
                future_prediction_cache=future_cache,
                initial_squad_override=candidate.squad,
                initial_squad_mode=candidate.name,
                initial_squad_version=candidate.version,
            )
            continuation_rows.append(
                {
                    "season": season,
                    "candidate": candidate.name,
                    "realistic_points": result.realistic_total_points,
                    "hindsight_points": result.total_points,
                    "transfers": result.transfers_made,
                    "hit_cost": result.total_hit_cost,
                    "chips_used": result.chips_used,
                    "initial_bank": result.initial_bank,
                    "final_bank": result.final_bank,
                    "initial_squad_hash": result.rows["initial_squad_hash"].iloc[0],
                }
            )
            decisions = result.rows.copy()
            decisions.insert(0, "candidate", candidate.name)
            decision_rows.append(decisions)
            decision_sources[key] = decisions
            reusable_squads[(season, squad_hash)] = candidate.name
            completed.add(key)
            _write_checkpoint(
                destination,
                candidates=pd.DataFrame(candidate_rows),
                squads=pd.concat(squad_rows, ignore_index=True, sort=False),
                projected_plan=pd.DataFrame(projected_plan_rows),
                continuation=pd.DataFrame(continuation_rows),
                decisions=pd.concat(decision_rows, ignore_index=True, sort=False),
            )

    candidate_frame = pd.DataFrame(candidate_rows)
    squad_frame = pd.concat(squad_rows, ignore_index=True, sort=False)
    projected_plan = pd.DataFrame(projected_plan_rows)
    continuation = pd.DataFrame(continuation_rows)
    decisions = pd.concat(decision_rows, ignore_index=True, sort=False)
    acceptance = evaluate_tournament_acceptance(continuation)
    passed_rows = acceptance[acceptance["passed"]]
    selected_candidate = (
        None
        if passed_rows.empty
        else str(
            passed_rows.sort_values(
                ["aggregate_delta", "candidate"],
                ascending=[False, True],
            ).iloc[0]["candidate"]
        )
    )
    _write_tournament(
        destination,
        candidate_frame,
        squad_frame,
        projected_plan,
        continuation,
        decisions,
        acceptance,
        selected_candidate=selected_candidate,
        timestamp=timestamp,
        portfolio_version=portfolio.version,
        seasons=seasons,
        chip_mode=chip_mode,
        dataset_hash=dataset_hash,
    )
    return InitialSquadTournamentResult(
        candidates=candidate_frame,
        squads=squad_frame,
        projected_plan=projected_plan,
        continuation=continuation,
        decisions=decisions,
        acceptance=acceptance,
        selected_candidate=selected_candidate,
        passed=selected_candidate is not None,
        output_dir=destination,
    )


def _opening_squad_hash(squad: pd.DataFrame) -> str:
    """Return the benchmark-compatible identity of an opening squad."""

    columns = [
        column
        for column in ("player_id", "team", "position", "price")
        if column in squad
    ]
    records = squad[columns].copy().sort_values("player_id").to_dict("records")
    payload = json.dumps(records, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def evaluate_tournament_acceptance(
    continuation: pd.DataFrame,
    *,
    minimum_improved_seasons: int = 2,
    maximum_regression_points: float = 50.0,
    maximum_regression_fraction: float = 0.03,
) -> pd.DataFrame:
    """Apply per-season P3 promotion gates with no aggregate masking."""

    champion = continuation[continuation["candidate"] == P3_BASELINE_NAME][
        ["season", "realistic_points"]
    ].rename(columns={"realistic_points": "champion_points"})
    if champion["season"].duplicated().any() or champion.empty:
        raise ValueError(
            f"Continuation rows require one {P3_BASELINE_NAME} baseline per season"
        )
    rows = []
    for candidate, frame in continuation[
        continuation["candidate"] != P3_BASELINE_NAME
    ].groupby("candidate", sort=True):
        comparison = frame.merge(champion, on="season", validate="one_to_one")
        comparison["delta"] = (
            comparison["realistic_points"] - comparison["champion_points"]
        )
        regression_limit = np.maximum(
            maximum_regression_points,
            comparison["champion_points"] * maximum_regression_fraction,
        )
        improved = int((comparison["delta"] > 0).sum())
        severe = comparison["delta"] < -regression_limit
        rows.append(
            {
                "candidate": candidate,
                "seasons_evaluated": int(len(comparison)),
                "improved_seasons": improved,
                "regressed_seasons": int((comparison["delta"] < 0).sum()),
                "worst_season_delta": float(comparison["delta"].min()),
                "aggregate_delta": float(comparison["delta"].sum()),
                "severe_regressions": int(severe.sum()),
                "passed": bool(
                    improved >= minimum_improved_seasons and not severe.any()
                ),
                "per_season_deltas": json.dumps(
                    {
                        str(row.season): float(row.delta)
                        for row in comparison.itertuples(index=False)
                    },
                    sort_keys=True,
                ),
            }
        )
    return pd.DataFrame(rows)


def _wrap_existing_squad(
    name: str,
    version: str,
    squad: pd.DataFrame,
    bundle: OpeningProjectionBundle,
) -> OpeningSquadCandidate:
    metrics = evaluate_opening_squad(bundle, squad)
    metrics.update(
        {
            "objective_value": None,
            "configured_horizon": 0,
            "cost": round(float(squad["price"].sum()), 1),
            "bank": round(INITIAL_BUDGET - float(squad["price"].sum()), 1),
            "unmatched_players": int(
                squad["player_id"]
                .map(bundle.candidates.set_index("player_id")["unmatched_player"])
                .fillna(True)
                .sum()
            ),
            "promoted_team_players": int(
                squad["player_id"]
                .map(bundle.candidates.set_index("player_id")["promoted_team"])
                .fillna(False)
                .sum()
            ),
            "projection_hash": bundle.projection_hash,
            "data_cutoff": bundle.data_cutoff,
        }
    )
    return OpeningSquadCandidate(
        name=name,
        version=version,
        squad=squad.copy(),
        projected_metrics=metrics,
        horizon_lineups={},
        horizon_captains={},
    )


def _projected_plan_rows(
    bundle: OpeningProjectionBundle,
    candidate: OpeningSquadCandidate,
) -> list[dict[str, Any]]:
    rows = []
    for gameweek, frame in sorted(bundle.projections.items()):
        points = frame.set_index("player_id")["projected_points"].to_dict()
        starts = frame.set_index("player_id")["start_probability"].to_dict()
        lineup = select_starting_xi(candidate.squad, points)
        captain_order = sorted(
            lineup.starting_ids,
            key=lambda player_id: (float(points.get(player_id, 0.0)), -player_id),
            reverse=True,
        )
        rows.append(
            {
                "season": bundle.season,
                "candidate": candidate.name,
                "gameweek": gameweek,
                "starting_ids": "+".join(str(value) for value in lineup.starting_ids),
                "bench_ids": "+".join(str(value) for value in lineup.bench_ids),
                "formation": lineup.formation,
                "captain_id": captain_order[0],
                "vice_captain_id": captain_order[1],
                "projected_xi_points": round(
                    sum(
                        float(points.get(player_id, 0.0))
                        for player_id in lineup.starting_ids
                    ),
                    4,
                ),
                "projected_captain_points": round(
                    float(points.get(captain_order[0], 0.0)),
                    4,
                ),
                "mean_squad_start_probability": round(
                    float(
                        np.mean(
                            [
                                float(starts.get(int(player_id), 0.4))
                                for player_id in candidate.squad["player_id"]
                            ]
                        )
                    ),
                    4,
                ),
                "data_cutoff": bundle.data_cutoff,
                "projection_hash": bundle.projection_hash,
            }
        )
    return rows


def _projection_frame(frame: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    base = candidates[["player_id"]].drop_duplicates().copy()
    if frame.empty:
        base["projected_points"] = 0.0
        base["start_probability"] = 0.4
        return base
    points_column = (
        "expected_points_adjusted"
        if "expected_points_adjusted" in frame
        else "predicted_points"
    )
    probability_column = next(
        (
            column
            for column in (
                "probability_start",
                "probability_60_plus_minutes",
                "probability_60_plus_minutes_v2",
            )
            if column in frame
        ),
        None,
    )
    selected_columns = ["player_id", points_column]
    if probability_column:
        selected_columns.append(probability_column)
    selected = frame[selected_columns].drop_duplicates("player_id").copy()
    selected = selected.rename(columns={points_column: "projected_points"})
    selected["start_probability"] = (
        pd.to_numeric(selected[probability_column], errors="coerce").fillna(0.4)
        if probability_column
        else 0.4
    )
    if probability_column:
        selected = selected.drop(columns=probability_column)
    output = base.merge(selected, on="player_id", how="left", validate="one_to_one")
    output["projected_points"] = pd.to_numeric(
        output["projected_points"], errors="coerce"
    ).fillna(0.0)
    output["start_probability"] = pd.to_numeric(
        output["start_probability"], errors="coerce"
    ).fillna(0.4).clip(0.0, 1.0)
    return output


def _assert_opening_cutoff(
    candidates: pd.DataFrame,
    projections: dict[int, pd.DataFrame],
) -> None:
    if "feature_cutoff_gameweek" in candidates:
        cutoff = pd.to_numeric(
            candidates["feature_cutoff_gameweek"], errors="coerce"
        ).dropna()
        if not cutoff.empty and float(cutoff.max()) > 0:
            raise AssertionError("P3 opening candidates contain post-GW1 feature state")
    if sorted(projections) != list(range(1, 9)):
        raise AssertionError("P3 requires a complete GW1-GW8 projection contract")


def _previous_season(players: pd.DataFrame, season: str) -> str | None:
    previous = sorted(
        str(value)
        for value in players["season"].dropna().unique()
        if str(value) < str(season)
    )
    return previous[-1] if previous else None


def _dataframe_collection_hash(frames: dict[int, pd.DataFrame]) -> str:
    digest = hashlib.sha256()
    for gameweek, frame in sorted(frames.items()):
        digest.update(str(gameweek).encode("utf-8"))
        ordered = frame.sort_values("player_id").reset_index(drop=True)
        digest.update(pd.util.hash_pandas_object(ordered, index=False).values.tobytes())
    return digest.hexdigest()


def _write_tournament(
    destination: Path,
    candidates: pd.DataFrame,
    squads: pd.DataFrame,
    projected_plan: pd.DataFrame,
    continuation: pd.DataFrame,
    decisions: pd.DataFrame,
    acceptance: pd.DataFrame,
    *,
    selected_candidate: str | None,
    timestamp: str,
    portfolio_version: str,
    seasons: tuple[str, ...],
    chip_mode: str,
    dataset_hash: str,
) -> None:
    if (destination / "run_manifest.json").exists():
        raise FileExistsError(f"Completed P3 output already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "projected_candidates": candidates,
        "candidate_squads": squads,
        "projected_plan": projected_plan,
        "full_season_continuation": continuation,
        "gameweek_decisions": decisions,
        "acceptance": acceptance,
    }
    manifest_artifacts: dict[str, Any] = {}
    for name, frame in artifacts.items():
        path = destination / f"{name}.csv"
        frame.to_csv(path, index=False)
        manifest_artifacts[name] = {
            "path": str(path),
            "rows": int(len(frame)),
            "sha256": _file_hash(path),
        }
    manifest = {
        "schema_version": P3_SCHEMA_VERSION,
        "optimizer_version": P3_OPTIMIZER_VERSION,
        "generated_at": timestamp,
        "run_id": uuid.uuid4().hex,
        "commit_hash": get_git_commit(),
        "portfolio_version": portfolio_version,
        "seasons": list(seasons),
        "chip_mode": chip_mode,
        "historical_dataset_sha256": dataset_hash,
        "selected_candidate": selected_candidate,
        "passed": selected_candidate is not None,
        "configs": {name: asdict(config) for name, config in P3_CONFIGS.items()},
        "artifacts": manifest_artifacts,
        "warnings": [
            "Projected screening is point-in-time safe but is not promotion evidence.",
            "Only full-season realistic continuation determines P3 acceptance.",
            (
                "No challenger is promoted unless at least two seasons improve "
                "without a severe regression."
            ),
        ],
    }
    (destination / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for filename in CHECKPOINT_FILES.values():
        (destination / filename).unlink(missing_ok=True)
    print("\nP3 full-season continuation")
    print(continuation.to_string(index=False))
    print("\nP3 acceptance")
    print(acceptance.to_string(index=False))
    print(f"\nSelected candidate: {selected_candidate or 'none'}")
    print(f"Artifacts: {destination}")


def _load_or_create_checkpoint(destination: Path) -> dict[str, pd.DataFrame]:
    if (destination / "run_manifest.json").exists():
        raise FileExistsError(f"Completed P3 output already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    checkpoint_count = 0
    for key, filename in CHECKPOINT_FILES.items():
        path = destination / filename
        if path.exists():
            frames[key] = pd.read_csv(path)
            checkpoint_count += 1
        else:
            frames[key] = pd.DataFrame()
    if checkpoint_count not in {0, len(CHECKPOINT_FILES)}:
        raise ValueError(
            f"Incomplete P3 checkpoint set in {destination}; expected "
            f"{len(CHECKPOINT_FILES)} files, found {checkpoint_count}"
        )
    return frames


def _write_checkpoint(
    destination: Path,
    *,
    candidates: pd.DataFrame,
    squads: pd.DataFrame,
    projected_plan: pd.DataFrame,
    continuation: pd.DataFrame,
    decisions: pd.DataFrame,
) -> None:
    frames = {
        "candidates": candidates,
        "squads": squads,
        "projected_plan": projected_plan,
        "continuation": continuation,
        "decisions": decisions,
    }
    for key, frame in frames.items():
        path = destination / CHECKPOINT_FILES[key]
        temporary = path.with_suffix(path.suffix + ".tmp")
        frame.to_csv(temporary, index=False)
        temporary.replace(path)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"empty").hexdigest()
    columns = sorted(frame.columns)
    sort_columns = [
        column
        for column in ("season", "gameweek", "player_id")
        if column in frame.columns
    ]
    ordered = frame[columns]
    if sort_columns:
        ordered = ordered.sort_values(sort_columns, kind="stable")
    values = pd.util.hash_pandas_object(ordered, index=False).values.tobytes()
    return hashlib.sha256(values).hexdigest()


def _filesystem_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the P3 initial-squad championship."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=["2023-24", "2024-25", "2025-26"],
    )
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=tuple(P3_CONFIGS),
    )
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    run_initial_squad_tournament(
        seasons=tuple(args.seasons),
        candidate_names=tuple(args.candidates or ()),
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
