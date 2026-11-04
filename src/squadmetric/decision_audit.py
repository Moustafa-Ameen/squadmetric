"""Champion/challenger decision-quality diagnostics for recovery R1.

This module is deliberately downstream of the existing benchmark.  It does not
choose a model, alter transfers, or alter chips.  It makes the consequences of
those decisions measurable at player, captain, transfer, chip, Gameweek, and
season grain.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

DECISION_AUDIT_VERSION = "recovery-r1-decision-audit-v1"
RETURN_BANDS = ("zeros", "blanks", "tickers", "haulers")


@dataclass(frozen=True)
class ChampionChallengerGate:
    """Explicit production-promotion guardrails for a challenger."""

    minimum_improved_seasons: int = 2
    maximum_season_regression_points: float = 50.0
    maximum_season_regression_fraction: float = 0.03


@dataclass(frozen=True)
class ChampionChallengerReport:
    """Per-Gameweek, per-season, and gate outputs for two benchmark tracks."""

    per_gameweek: pd.DataFrame
    season_summary: pd.DataFrame
    regime_summary: pd.DataFrame
    passed: bool
    rejection_reasons: tuple[str, ...]
    audit_version: str = DECISION_AUDIT_VERSION


def build_prediction_audit(
    predictions: pd.DataFrame,
    target: pd.DataFrame,
) -> pd.DataFrame:
    """Attach realised points, ranks, and return bands to a prediction frame."""

    required_predictions = {"player_id", "expected_points_adjusted"}
    required_target = {"player_id", "next_gameweek_points"}
    missing_predictions = required_predictions.difference(predictions.columns)
    missing_target = required_target.difference(target.columns)
    if missing_predictions:
        raise ValueError(f"Predictions are missing columns: {sorted(missing_predictions)}")
    if missing_target:
        raise ValueError(f"Target is missing columns: {sorted(missing_target)}")

    prediction_columns = [
        column
        for column in ("player_id", "player_name", "position", "expected_points_adjusted")
        if column in predictions.columns
    ]
    target_columns = [
        column
        for column in ("player_id", "next_gameweek_points", "minutes", "position")
        if column in target.columns
    ]
    predicted = predictions[prediction_columns].drop_duplicates("player_id").copy()
    realised = target[target_columns].drop_duplicates("player_id").copy()
    if "position" in predicted and "position" in realised:
        realised = realised.drop(columns=["position"])
    output = predicted.merge(realised, on="player_id", how="inner", validate="one_to_one")
    output["predicted_points"] = pd.to_numeric(
        output["expected_points_adjusted"], errors="coerce"
    ).fillna(0.0)
    output["actual_points"] = pd.to_numeric(
        output["next_gameweek_points"], errors="coerce"
    ).fillna(0.0)
    output["absolute_error"] = (output["predicted_points"] - output["actual_points"]).abs()
    output["squared_error"] = (output["predicted_points"] - output["actual_points"]) ** 2
    output["predicted_rank"] = output["predicted_points"].rank(
        method="min", ascending=False
    ).astype(int)
    output["actual_rank"] = output["actual_points"].rank(method="min", ascending=False).astype(int)
    output["return_band"] = output["actual_points"].map(_return_band)
    return output


def summarise_prediction_audit(
    audit: pd.DataFrame,
    *,
    top_k: int = 10,
) -> pd.DataFrame:
    """Summarise point and ranking quality by position and realised return band."""

    required = {"predicted_points", "actual_points", "absolute_error", "squared_error"}
    missing = required.difference(audit.columns)
    if missing:
        raise ValueError(f"Prediction audit is missing columns: {sorted(missing)}")
    if top_k < 1:
        raise ValueError("top_k must be positive")

    segments: list[tuple[str, pd.Series]] = [("all", pd.Series(True, index=audit.index))]
    if "position" in audit:
        segments.extend(
            (f"position:{value}", audit["position"].astype(str).eq(value))
            for value in sorted(audit["position"].dropna().astype(str).unique())
        )
    if "return_band" in audit:
        segments.extend(
            (f"return_band:{value}", audit["return_band"].eq(value))
            for value in RETURN_BANDS
        )

    predicted_top = set(audit.nlargest(top_k, "predicted_points")["player_id"])
    actual_top = set(audit.nlargest(top_k, "actual_points")["player_id"])
    rows: list[dict[str, Any]] = []
    for segment, mask in segments:
        frame = audit[mask].copy()
        if frame.empty:
            continue
        frame_predicted_top = set(frame.nlargest(top_k, "predicted_points")["player_id"])
        frame_actual_top = set(frame.nlargest(top_k, "actual_points")["player_id"])
        rows.append(
            {
                "segment": segment,
                "row_count": int(len(frame)),
                "mae": float(frame["absolute_error"].mean()),
                "rmse": float(np.sqrt(frame["squared_error"].mean())),
                "bias": float((frame["predicted_points"] - frame["actual_points"]).mean()),
                "spearman_rank_correlation": _rank_correlation(
                    frame["predicted_points"], frame["actual_points"]
                ),
                "top_k_precision": _safe_ratio(
                    len(frame_predicted_top & frame_actual_top), len(frame_predicted_top)
                ),
                "top_k_recall": _safe_ratio(
                    len(frame_predicted_top & frame_actual_top), len(frame_actual_top)
                ),
                "global_top_k_precision": _safe_ratio(
                    len(predicted_top & actual_top), len(predicted_top)
                ),
                "global_top_k_recall": _safe_ratio(
                    len(predicted_top & actual_top), len(actual_top)
                ),
            }
        )
    return pd.DataFrame(rows)


def build_decision_audit(
    result_or_rows: Any,
    players: pd.DataFrame,
) -> pd.DataFrame:
    """Build Gameweek decision diagnostics from an existing benchmark result."""

    rows = result_or_rows.rows.copy() if hasattr(result_or_rows, "rows") else result_or_rows.copy()
    if not isinstance(rows, pd.DataFrame):
        raise TypeError("result_or_rows must contain a pandas DataFrame named rows")
    required_rows = {
        "season",
        "gameweek",
        "realistic_net_points",
        "net_points",
        "realistic_captain_id",
        "realistic_vice_captain_id",
        "realistic_captain_actual_points",
        "realistic_vice_captain_actual_points",
        "realistic_vice_captain_fallback",
        "starting_ids",
        "transfers_made",
        "chip_used",
    }
    missing = required_rows.difference(rows.columns)
    if missing:
        raise ValueError(f"Benchmark decision rows are missing columns: {sorted(missing)}")
    required_players = {"season", "gameweek", "player_id", "next_gameweek_points", "minutes"}
    missing = required_players.difference(players.columns)
    if missing:
        raise ValueError(f"Players are missing columns: {sorted(missing)}")

    output = rows.copy()
    regime = _gameweek_regimes(players)
    output = output.merge(regime, on=["season", "gameweek"], how="left", validate="one_to_one")
    metrics = []
    for row in output.itertuples(index=False):
        target = players[
            (players["season"].astype(str) == str(row.season))
            & (pd.to_numeric(players["gameweek"], errors="coerce") == int(row.gameweek))
        ].drop_duplicates("player_id")
        points = target.set_index("player_id")["next_gameweek_points"].to_dict()
        minutes = target.set_index("player_id")["minutes"].to_dict()
        active_ids = _parse_ids(row.starting_ids)
        captain_id = int(row.realistic_captain_id)
        vice_id = int(row.realistic_vice_captain_id)
        effective_id = vice_id if bool(row.realistic_vice_captain_fallback) else captain_id
        eligible_ids = tuple(dict.fromkeys((*active_ids, captain_id, vice_id)))
        best_actual = max(
            (float(points.get(player_id, 0.0)) for player_id in active_ids),
            default=0.0,
        )
        effective_actual = float(points.get(effective_id, 0.0))
        captain_rank = 1 + sum(
            float(points.get(player_id, 0.0)) > effective_actual for player_id in active_ids
        )
        metrics.append(
            {
                "captain_effective_id": effective_id,
                "captain_effective_actual_points": effective_actual,
                "best_legal_captain_points": best_actual,
                "captain_regret": max(0.0, best_actual - effective_actual),
                "captain_rank_by_actual_points": captain_rank,
                "captain_top_two": captain_rank <= 2,
                "captain_selected_played": float(minutes.get(captain_id, 0.0)) > 0,
                "captain_candidate_count": len(eligible_ids),
            }
        )
    return pd.concat([output.reset_index(drop=True), pd.DataFrame(metrics)], axis=1)


def build_champion_challenger_report(
    champion_results: Sequence[Any],
    challenger_results: Sequence[Any],
    players: pd.DataFrame,
    *,
    gate: ChampionChallengerGate | None = None,
) -> ChampionChallengerReport:
    """Compare two completed benchmark tracks without changing either track."""

    champion = _combined_decision_audit(champion_results, players)
    challenger = _combined_decision_audit(challenger_results, players)
    keys = ["season", "gameweek"]
    merged = champion.merge(
        challenger,
        on=keys,
        how="outer",
        suffixes=("_champion", "_challenger"),
        indicator=True,
    )
    if not merged["_merge"].eq("both").all():
        missing = merged.loc[merged["_merge"] != "both", keys].to_dict("records")
        raise ValueError(f"Champion and challenger Gameweeks do not align: {missing}")
    merged = merged.drop(columns="_merge")
    merged["realistic_delta"] = (
        merged["realistic_net_points_challenger"]
        - merged["realistic_net_points_champion"]
    )
    merged["hindsight_delta"] = merged["net_points_challenger"] - merged["net_points_champion"]
    merged["captain_regret_delta"] = (
        merged["captain_regret_challenger"] - merged["captain_regret_champion"]
    )
    merged["captain_changed"] = (
        merged["realistic_captain_id_champion"] != merged["realistic_captain_id_challenger"]
    )
    merged["transfer_changed"] = (
        merged["incoming_champion"].fillna("") != merged["incoming_challenger"].fillna("")
    ) | (
        merged["outgoing_champion"].fillna("") != merged["outgoing_challenger"].fillna("")
    )
    merged["chip_changed"] = merged["chip_used_champion"].fillna("none") != merged[
        "chip_used_challenger"
    ].fillna("none")
    if not merged["regime_champion"].eq(merged["regime_challenger"]).all():
        raise ValueError("Champion and challenger regime classifications do not align")
    merged["regime"] = merged["regime_champion"]
    for column in ("is_blank", "is_double"):
        if not merged[f"{column}_champion"].eq(merged[f"{column}_challenger"]).all():
            raise ValueError(f"Champion and challenger {column} classifications do not align")
        merged[column] = merged[f"{column}_champion"]

    season_summary = _group_comparison(merged, ["season"])
    regime_summary = _group_comparison(merged, ["season", "regime"])
    decision_gate = gate or ChampionChallengerGate()
    reasons: list[str] = []
    improved_seasons = int((season_summary["realistic_delta"] > 0).sum())
    if improved_seasons < decision_gate.minimum_improved_seasons:
        reasons.append(
            f"Only {improved_seasons} validation seasons improved; "
            f"required {decision_gate.minimum_improved_seasons}."
        )
    severe_regressions = season_summary[
        season_summary["realistic_delta"]
        < -np.maximum(
            decision_gate.maximum_season_regression_points,
            season_summary["champion_realistic_points"]
            * decision_gate.maximum_season_regression_fraction,
        )
    ]
    for row in severe_regressions.itertuples(index=False):
        reasons.append(
            f"{row.season} realistic regression {row.realistic_delta:.1f} exceeds the "
            "season guardrail."
        )
    return ChampionChallengerReport(
        per_gameweek=merged,
        season_summary=season_summary,
        regime_summary=regime_summary,
        passed=not reasons,
        rejection_reasons=tuple(reasons),
    )


def _combined_decision_audit(results: Sequence[Any], players: pd.DataFrame) -> pd.DataFrame:
    frames = [build_decision_audit(result, players) for result in results]
    if not frames:
        raise ValueError("At least one benchmark result is required")
    return pd.concat(frames, ignore_index=True)


def _group_comparison(frame: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    grouped = frame.groupby(by, dropna=False, sort=True)
    summary = grouped.agg(
        gameweeks=("gameweek", "size"),
        champion_realistic_points=("realistic_net_points_champion", "sum"),
        challenger_realistic_points=("realistic_net_points_challenger", "sum"),
        champion_hindsight_points=("net_points_champion", "sum"),
        challenger_hindsight_points=("net_points_challenger", "sum"),
        champion_captain_regret=("captain_regret_champion", "sum"),
        challenger_captain_regret=("captain_regret_challenger", "sum"),
        captain_changes=("captain_changed", "sum"),
        transfer_changes=("transfer_changed", "sum"),
        chip_changes=("chip_changed", "sum"),
    ).reset_index()
    summary["realistic_delta"] = (
        summary["challenger_realistic_points"] - summary["champion_realistic_points"]
    )
    summary["hindsight_delta"] = (
        summary["challenger_hindsight_points"] - summary["champion_hindsight_points"]
    )
    summary["captain_regret_delta"] = (
        summary["challenger_captain_regret"] - summary["champion_captain_regret"]
    )
    return summary


def _gameweek_regimes(players: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (season, gameweek), frame in players.groupby(["season", "gameweek"], sort=True):
        opponent = frame["opponent_team"].astype(str)
        rows.append(
            {
                "season": season,
                "gameweek": int(gameweek),
                "is_blank": int(frame["team"].nunique() < 20),
                "is_double": int(
                    frame["home_or_away"].astype(str).str.upper().eq("M").any()
                    or opponent.str.contains(r"\+", regex=True).any()
                ),
            }
        )
    return pd.DataFrame(rows).assign(
        regime=lambda frame: np.select(
            [
                frame["is_blank"].eq(1) & frame["is_double"].eq(1),
                frame["is_blank"].eq(1),
                frame["is_double"].eq(1),
            ],
            ["blank_double", "blank", "double"],
            default="normal",
        )
    )


def _parse_ids(value: Any) -> tuple[int, ...]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ()
    return tuple(int(part) for part in str(value).split("+") if part.strip())


def _return_band(value: Any) -> str:
    points = float(value)
    if points <= 0:
        return "zeros"
    if points <= 2:
        return "blanks"
    if points <= 4:
        return "tickers"
    return "haulers"


def _rank_correlation(predicted: pd.Series, actual: pd.Series) -> float:
    if len(predicted) < 2 or predicted.nunique() < 2 or actual.nunique() < 2:
        return 0.0
    value = predicted.corr(actual, method="spearman")
    return 0.0 if pd.isna(value) else float(value)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0
