"""Auditable points-loss and rank-reference analysis for completed simulations.

The audit separates exact score accounting from hindsight diagnostics.  It
never turns an unavailable counterfactual into an estimated loss and never
adds overlapping hindsight regret buckets into a fictional alternative score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fpl_intelligence.backtest_transfer_strategy import (
    VALID_FORMATIONS,
    LineupSelection,
    position_group,
    resolve_active_lineup,
)
from fpl_intelligence.season_benchmark import HISTORICAL_PLAYER_GW_PATH
from fpl_intelligence.step4_models import load_historical_player_gameweeks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RANK_REFERENCE_PATH = (
    PROJECT_ROOT / "data" / "reference" / "historical_top1_boundaries.json"
)
DEFAULT_RECOVERY_2023_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "simulations"
    / "performance-recovery-production-v3-2023-24"
)
DEFAULT_RECOVERY_TOURNAMENT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "initial_squad_tournaments"
    / "performance-recovery-2024-2025"
)
DEFAULT_POST_RECOVERY_AUDIT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "points_loss_audits"
    / "post-recovery-production-v1"
)
RECOVERY_TOURNAMENT_CANDIDATE = "horizon_8_flexible"
AUDIT_SCHEMA_VERSION = "pdc-post-recovery-points-loss-audit-v2"
AUDIT_ARTIFACTS = {
    "gameweeks": "points_loss_gameweeks.csv",
    "buckets": "points_loss_buckets.csv",
    "rank_evaluation": "rank_reference_evaluation.csv",
    "chip_counterfactuals": "chip_counterfactual_audit.csv",
    "decision_opportunities": "decision_opportunities.csv",
    "chip_usage": "chip_usage.csv",
}


@dataclass(frozen=True)
class PointsLossAudit:
    """Complete P2 audit outputs."""

    gameweeks: pd.DataFrame
    buckets: pd.DataFrame
    rank_evaluation: pd.DataFrame
    chip_counterfactuals: pd.DataFrame
    decision_opportunities: pd.DataFrame
    chip_usage: pd.DataFrame
    manifest: dict[str, Any]


def audit_simulation(
    simulation_dir: Path,
    *,
    historical_path: Path = HISTORICAL_PLAYER_GW_PATH,
    rank_reference_path: Path = DEFAULT_RANK_REFERENCE_PATH,
    generated_at: str | None = None,
    write: bool = True,
) -> PointsLossAudit:
    """Audit an isolated simulation directory and optionally persist P2 artifacts."""

    simulation_dir = Path(simulation_dir)
    decisions_path = simulation_dir / "gameweek_decisions.csv"
    summary_path = simulation_dir / "season_summary.csv"
    source_manifest_path = simulation_dir / "run_manifest.json"
    for path in (decisions_path, summary_path, source_manifest_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required simulation artifact is missing: {path}")

    decisions = pd.read_csv(decisions_path)
    season_summary = pd.read_csv(summary_path)
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_artifacts = {
        "gameweek_decisions_sha256": _file_hash(decisions_path),
        "season_summary_sha256": _file_hash(summary_path),
        "run_manifest_sha256": _file_hash(source_manifest_path),
    }
    return _audit_frames(
        decisions,
        season_summary,
        output_dir=simulation_dir,
        historical_path=historical_path,
        rank_reference_path=rank_reference_path,
        generated_at=generated_at,
        write=write,
        source_artifacts=source_artifacts,
        source_run_id=source_manifest.get("run_id"),
        source_simulation_key=source_manifest.get("simulation_key"),
    )


def audit_recovery_scorecard(
    *,
    cold_start_dir: Path = DEFAULT_RECOVERY_2023_DIR,
    tournament_dir: Path = DEFAULT_RECOVERY_TOURNAMENT_DIR,
    output_dir: Path = DEFAULT_POST_RECOVERY_AUDIT_DIR,
    candidate: str = RECOVERY_TOURNAMENT_CANDIDATE,
    historical_path: Path = HISTORICAL_PLAYER_GW_PATH,
    rank_reference_path: Path = DEFAULT_RANK_REFERENCE_PATH,
    generated_at: str | None = None,
    write: bool = True,
) -> PointsLossAudit:
    """Audit the accepted three-season post-recovery production scorecard."""

    decisions, season_summary, source_paths = load_recovery_scorecard(
        cold_start_dir=Path(cold_start_dir),
        tournament_dir=Path(tournament_dir),
        candidate=candidate,
    )
    source_artifacts = {
        f"{label}_sha256": _file_hash(path) for label, path in source_paths.items()
    }
    return _audit_frames(
        decisions,
        season_summary,
        output_dir=Path(output_dir),
        historical_path=historical_path,
        rank_reference_path=rank_reference_path,
        generated_at=generated_at,
        write=write,
        source_artifacts=source_artifacts,
        source_run_id="post-recovery-production-v1",
        source_simulation_key=candidate,
    )


def load_recovery_scorecard(
    *,
    cold_start_dir: Path,
    tournament_dir: Path,
    candidate: str = RECOVERY_TOURNAMENT_CANDIDATE,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    """Load the exact accepted 2023/24–2025/26 production paths."""

    paths = {
        "cold_start_decisions": Path(cold_start_dir) / "gameweek_decisions.csv",
        "cold_start_summary": Path(cold_start_dir) / "season_summary.csv",
        "cold_start_manifest": Path(cold_start_dir) / "run_manifest.json",
        "tournament_decisions": Path(tournament_dir) / "gameweek_decisions.csv",
        "tournament_continuation": Path(tournament_dir)
        / "full_season_continuation.csv",
        "tournament_manifest": Path(tournament_dir) / "run_manifest.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"Required recovery artifact is missing: {path}")

    cold_decisions = pd.read_csv(paths["cold_start_decisions"])
    cold_summary = pd.read_csv(paths["cold_start_summary"])
    tournament_decisions = pd.read_csv(paths["tournament_decisions"])
    continuation = pd.read_csv(paths["tournament_continuation"])
    if "candidate" not in tournament_decisions or "candidate" not in continuation:
        raise ValueError("Tournament artifacts do not identify candidate paths")
    selected_decisions = tournament_decisions[
        tournament_decisions["candidate"].astype(str).eq(candidate)
    ].drop(columns="candidate")
    selected_continuation = continuation[
        continuation["candidate"].astype(str).eq(candidate)
    ].drop(columns="candidate")
    if selected_decisions.empty or selected_continuation.empty:
        raise ValueError(f"Tournament candidate is unavailable: {candidate}")

    decisions = pd.concat(
        [cold_decisions, selected_decisions], ignore_index=True, sort=False
    ).sort_values(["season", "gameweek"], ignore_index=True)
    summary_columns = [
        column
        for column in ("season", "realistic_points", "hindsight_points")
        if column in cold_summary.columns and column in selected_continuation.columns
    ]
    season_summary = pd.concat(
        [cold_summary[summary_columns], selected_continuation[summary_columns]],
        ignore_index=True,
    ).sort_values("season", ignore_index=True)

    duplicates = decisions.duplicated(["season", "gameweek"], keep=False)
    if duplicates.any():
        keys = decisions.loc[duplicates, ["season", "gameweek"]].to_dict("records")
        raise ValueError(f"Recovery scorecard contains duplicate Gameweeks: {keys}")
    counts = decisions.groupby("season")["gameweek"].nunique()
    if set(counts.index.astype(str)) != {"2023-24", "2024-25", "2025-26"}:
        raise ValueError("Recovery scorecard must contain all three supported seasons")
    if not counts.eq(38).all():
        raise ValueError(f"Recovery scorecard is incomplete: {counts.to_dict()}")
    if season_summary["season"].astype(str).duplicated().any():
        raise ValueError("Recovery scorecard contains duplicate season summaries")
    return decisions, season_summary, paths


def _audit_frames(
    decisions: pd.DataFrame,
    season_summary: pd.DataFrame,
    *,
    output_dir: Path,
    historical_path: Path,
    rank_reference_path: Path,
    generated_at: str | None,
    write: bool,
    source_artifacts: dict[str, str],
    source_run_id: str | None,
    source_simulation_key: str | None,
) -> PointsLossAudit:
    """Build one audit from already-selected decision and summary rows."""

    players = load_historical_player_gameweeks(historical_path)
    references = load_rank_references(rank_reference_path)
    gameweeks = build_points_loss_gameweeks(decisions, players)
    buckets = build_loss_bucket_summary(gameweeks)
    rank_evaluation = evaluate_rank_references(season_summary, references)
    chip_counterfactuals = expand_chip_counterfactuals(decisions)
    chip_usage = build_chip_usage(decisions, gameweeks)
    decision_opportunities = build_decision_opportunities(gameweeks, chip_usage)
    _assert_season_reconciliation(gameweeks, season_summary)

    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "status": "complete",
        "generated_at": timestamp,
        "source_run_id": source_run_id,
        "source_simulation_key": source_simulation_key,
        "source_artifacts": {
            **source_artifacts,
            "historical_data_sha256": _file_hash(historical_path),
            "rank_reference_sha256": _file_hash(rank_reference_path),
        },
        "definitions": _audit_definitions(),
        "warnings": [
            (
                "Hindsight regret values are diagnostic upper bounds, "
                "not attainable production scores."
            ),
            "Loss buckets overlap and must not be summed into an alternative season total.",
            "Unavailable values are intentionally not inferred from player names or squad hashes.",
        ],
        "artifacts": {},
    }
    result = PointsLossAudit(
        gameweeks=gameweeks,
        buckets=buckets,
        rank_evaluation=rank_evaluation,
        chip_counterfactuals=chip_counterfactuals,
        decision_opportunities=decision_opportunities,
        chip_usage=chip_usage,
        manifest=manifest,
    )
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_audit(output_dir, result)
    return result


def build_points_loss_gameweeks(
    decisions: pd.DataFrame,
    players: pd.DataFrame,
) -> pd.DataFrame:
    """Build exact accounting and explicitly-labelled diagnostics by Gameweek."""

    required = {
        "season",
        "gameweek",
        "realistic_gross_points",
        "realistic_net_points",
        "realistic_cumulative_points",
        "hit_cost",
        "realistic_captain_id",
        "realistic_vice_captain_id",
        "realistic_vice_captain_fallback",
        "chip_used",
        "realistic_chip_realized_gain",
    }
    missing = sorted(required.difference(decisions.columns))
    if missing:
        raise ValueError(f"Decision rows are missing P2 columns: {', '.join(missing)}")
    required_players = {
        "season",
        "gameweek",
        "player_id",
        "position",
        "team",
        "price",
        "minutes",
        "next_gameweek_points",
    }
    missing_players = sorted(required_players.difference(players.columns))
    if missing_players:
        raise ValueError(
            f"Historical players are missing P2 columns: {', '.join(missing_players)}"
        )

    roster_by_season = {
        str(season): _season_roster(frame)
        for season, frame in players.groupby(players["season"].astype(str), sort=False)
    }
    output_rows: list[dict[str, Any]] = []
    for row in decisions.sort_values(["season", "gameweek"]).to_dict("records"):
        season = str(row["season"])
        gameweek = int(row["gameweek"])
        fixture_target = players[
            (players["season"].astype(str) == season)
            & (pd.to_numeric(players["gameweek"], errors="coerce") == gameweek)
        ].drop_duplicates("player_id")
        if fixture_target.empty:
            raise ValueError(f"No historical target rows for {season} GW{gameweek}")
        decision_squad_ids, decision_squad_source = _decision_squad_ids(row)
        target = _complete_target_for_squad(
            fixture_target,
            roster_by_season[season],
            decision_squad_ids,
            gameweek=gameweek,
        )
        target["player_id"] = pd.to_numeric(target["player_id"], errors="raise").astype(int)
        points = pd.to_numeric(
            target.set_index("player_id")["next_gameweek_points"], errors="coerce"
        ).fillna(0.0)
        gross = _number(row.get("realistic_gross_points"))
        hit_cost = _number(row.get("hit_cost"))
        net = _number(row.get("realistic_net_points"))
        expected_net = gross - hit_cost
        row_reconciliation_delta = net - expected_net

        active_ids, captain_source = _realistic_active_ids(row)
        captain_id = _optional_int(row.get("realistic_captain_id"))
        vice_id = _optional_int(row.get("realistic_vice_captain_id"))
        fallback = _bool(row.get("realistic_vice_captain_fallback"))
        effective_id = vice_id if fallback else captain_id
        effective_actual = _optional_number(
            row.get(
                "realistic_vice_captain_actual_points"
                if fallback
                else "realistic_captain_actual_points"
            )
        )
        captain_regret, captain_status = _captain_regret(
            active_ids,
            effective_id,
            points,
            chip_used=str(row.get("chip_used") or "none"),
            effective_actual=effective_actual,
        )
        lineup_regret, lineup_status, oracle_raw_points = _lineup_regret(
            row,
            target,
            points,
            squad_ids=decision_squad_ids,
        )
        bench_points, bench_status = _bench_points_left(row, points)
        transfer_delta, transfer_regret, transfer_status = _transfer_diagnostic(
            row,
            points,
        )
        regime = _fixture_regime(fixture_target)
        output_rows.append(
            {
                "season": season,
                "gameweek": gameweek,
                "realistic_gross_points": gross,
                "hit_cost": hit_cost,
                "realistic_net_points": net,
                "expected_net_points": expected_net,
                "row_reconciliation_delta": row_reconciliation_delta,
                "row_reconciliation_status": (
                    "exact" if abs(row_reconciliation_delta) < 1e-9 else "failed"
                ),
                "realistic_cumulative_points": _number(
                    row.get("realistic_cumulative_points")
                ),
                "chip_used": str(row.get("chip_used") or "none"),
                "chip_realized_gain": _number(
                    row.get("realistic_chip_realized_gain")
                ),
                "chip_expected_gain": _optional_number(row.get("chip_expected_gain")),
                "captain_effective_id": effective_id,
                "captain_regret": captain_regret,
                "captain_regret_status": captain_status,
                "captain_lineup_source": captain_source,
                "decision_squad_source": decision_squad_source,
                "lineup_regret": lineup_regret,
                "lineup_regret_status": lineup_status,
                "oracle_raw_xi_points": oracle_raw_points,
                "bench_points_left": bench_points,
                "bench_points_status": bench_status,
                "selected_transfer_one_week_delta": transfer_delta,
                "selected_transfer_regret": transfer_regret,
                "selected_transfer_status": transfer_status,
                "is_blank": regime["is_blank"],
                "is_double": regime["is_double"],
                "fixture_regime": regime["regime"],
                "initial_squad_regret_status": "unavailable",
                "chip_timing_regret_status": "unavailable",
                "profitable_hits_missed_status": "unavailable",
                "availability_minutes_loss_status": "unavailable",
                "projection_ranking_loss_status": "unavailable",
            }
        )
    output = pd.DataFrame(output_rows)
    output["calculated_cumulative_points"] = output.groupby("season", sort=False)[
        "realistic_net_points"
    ].cumsum()
    output["cumulative_reconciliation_delta"] = (
        output["realistic_cumulative_points"] - output["calculated_cumulative_points"]
    )
    output["cumulative_reconciliation_status"] = np.where(
        output["cumulative_reconciliation_delta"].abs() < 1e-9,
        "exact",
        "failed",
    )
    return output


def build_loss_bucket_summary(gameweeks: pd.DataFrame) -> pd.DataFrame:
    """Summarise every P2 bucket without pretending overlapping regret is additive."""

    rows: list[dict[str, Any]] = []
    for season, frame in gameweeks.groupby("season", sort=True):
        exact = bool(
            frame["row_reconciliation_status"].eq("exact").all()
            and frame["cumulative_reconciliation_status"].eq("exact").all()
        )
        rows.extend(
            [
                _bucket(
                    season,
                    "score_reconciliation",
                    float(frame["row_reconciliation_delta"].abs().sum()),
                    "exact" if exact else "failed",
                    "Absolute mismatch between persisted gross-minus-hits and net points.",
                ),
                _bucket(
                    season,
                    "initial_squad",
                    None,
                    "unavailable",
                    "Requires a legal alternative opening squad followed through the same season.",
                ),
                _bucket(
                    season,
                    "captain_and_vice",
                    _complete_sum(frame, "captain_regret", "captain_regret_status"),
                    _aggregate_status(frame["captain_regret_status"]),
                    (
                        "Hindsight best active-XI captain minus the effective captain; "
                        "doubled for Triple Captain."
                    ),
                ),
                _bucket(
                    season,
                    "starting_xi",
                    _complete_sum(frame, "lineup_regret", "lineup_regret_status"),
                    _aggregate_status(frame["lineup_regret_status"]),
                    "Hindsight legal XI raw points minus selected XI raw points.",
                ),
                _bucket(
                    season,
                    "bench_order_and_autosubs",
                    _complete_sum(frame, "bench_points_left", "bench_points_status"),
                    _aggregate_status(frame["bench_points_status"]),
                    (
                        "Actual points remaining on the ordered bench after autosubs; "
                        "diagnostic and overlapping."
                    ),
                ),
                _bucket(
                    season,
                    "transfer_selection_and_timing",
                    _complete_sum(
                        frame,
                        "selected_transfer_regret",
                        "selected_transfer_status",
                        accepted=("hindsight_partial", "not_applicable"),
                    ),
                    _aggregate_status(
                        frame["selected_transfer_status"],
                        accepted=("hindsight_partial", "not_applicable"),
                        available_label="hindsight_partial",
                    ),
                    (
                        "One-Gameweek downside of selected transfers only; missed "
                        "alternatives and long-term effects are unavailable."
                    ),
                ),
                _bucket(
                    season,
                    "bad_hits_taken",
                    float(
                        frame.loc[
                            frame["selected_transfer_one_week_delta"].fillna(0.0)
                            < frame["hit_cost"],
                            "hit_cost",
                        ].sum()
                    ),
                    "exact_accounting_partial_regret",
                    (
                        "Exact hit cost where the selected transfer failed to repay it "
                        "in that Gameweek; long-term value is excluded."
                    ),
                ),
                _bucket(
                    season,
                    "profitable_hits_missed",
                    None,
                    "unavailable",
                    "Requires legal point-in-time transfer counterfactuals for every Gameweek.",
                ),
                _bucket(
                    season,
                    "chip_timing_and_preparation",
                    None,
                    "unavailable",
                    (
                        "Selected realized gain is exact, but timing regret requires "
                        "legal cross-Gameweek chip replay."
                    ),
                ),
                _bucket(
                    season,
                    "blank_double_gameweek",
                    None,
                    "unavailable",
                    (
                        "Regime points are observable, but loss requires a legal "
                        "no-lookahead alternative decision path."
                    ),
                ),
                _bucket(
                    season,
                    "availability_and_minutes",
                    None,
                    "unavailable",
                    "Requires persisted player-level deadline projections and availability states.",
                ),
                _bucket(
                    season,
                    "projection_ranking",
                    None,
                    "unavailable",
                    "Requires persisted player-level projection ranks at every deadline.",
                ),
            ]
        )
    return pd.DataFrame(rows)


def load_rank_references(path: Path = DEFAULT_RANK_REFERENCE_PATH) -> pd.DataFrame:
    """Load the reviewed, source-backed historical rank reference table."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "pdc-p2-rank-reference-v1":
        raise ValueError("Unsupported historical rank-reference schema")
    rows = []
    for item in payload.get("seasons", []):
        row = dict(item)
        row["retrieved_at"] = payload.get("retrieved_at")
        row["source_urls"] = ";".join(
            source["url"] for source in item.get("sources", [])
        )
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate_rank_references(
    season_summary: pd.DataFrame,
    references: pd.DataFrame,
) -> pd.DataFrame:
    """Classify each simulated score against verified inside/outside bounds."""

    required = {"season", "realistic_points"}
    missing = sorted(required.difference(season_summary.columns))
    if missing:
        raise ValueError(f"Season summary is missing rank columns: {', '.join(missing)}")
    merged = season_summary[["season", "realistic_points"]].copy()
    merged["season"] = merged["season"].astype(str)
    merged = merged.merge(references, on="season", how="left", validate="one_to_one")
    rows = []
    for row in merged.to_dict("records"):
        score = _number(row["realistic_points"])
        status = str(row.get("status") or "unavailable")
        inside = _optional_number(row.get("known_inside_points"))
        outside = _optional_number(row.get("known_outside_points"))
        if status == "unavailable" or inside is None or outside is None:
            classification = "unavailable"
            minimum_gap = None
            inside_margin = None
        elif score >= inside:
            classification = "at_or_above_verified_inside_score"
            minimum_gap = score - inside
            inside_margin = score - inside
        elif score <= outside:
            classification = "below_verified_outside_score"
            minimum_gap = score - outside
            inside_margin = score - inside
        else:
            classification = "inside_unresolved_boundary_bracket"
            minimum_gap = 0.0
            inside_margin = score - inside
        rows.append(
            {
                "season": row["season"],
                "realistic_points": score,
                "reference_status": status,
                "total_managers": row.get("total_managers"),
                "top_one_percent_rank": row.get("top_one_percent_rank"),
                "known_inside_points": inside,
                "known_inside_rank": row.get("known_inside_rank"),
                "known_outside_points": outside,
                "known_outside_rank": row.get("known_outside_rank"),
                "classification": classification,
                "margin_to_known_inside_points": inside_margin,
                "minimum_margin_to_verified_boundary_evidence": minimum_gap,
                "retrieved_at": row.get("retrieved_at"),
                "source_urls": row.get("source_urls"),
                "note": row.get("note"),
            }
        )
    return pd.DataFrame(rows)


def expand_chip_counterfactuals(decisions: pd.DataFrame) -> pd.DataFrame:
    """Expand persisted expected chip branches without claiming realized outcomes."""

    rows: list[dict[str, Any]] = []
    if "chip_counterfactuals" not in decisions:
        return pd.DataFrame(
            columns=[
                "season",
                "gameweek",
                "chip_key",
                "status",
                "legal",
                "expected_gain",
                "realized_gain",
                "realized_gain_status",
                "reason",
            ]
        )
    for decision in decisions.to_dict("records"):
        raw = decision.get("chip_counterfactuals")
        if raw is None or (isinstance(raw, float) and np.isnan(raw)) or str(raw).strip() == "":
            continue
        try:
            counterfactuals = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid chip counterfactual JSON for {decision['season']} "
                f"GW{decision['gameweek']}"
            ) from exc
        selected_key = str(decision.get("chip_key") or "none")
        for branch in counterfactuals:
            branch_key = str(branch.get("chip_key") or "none")
            selected = branch_key == selected_key and str(branch.get("status")) == "selected"
            rows.append(
                {
                    "season": str(decision["season"]),
                    "gameweek": int(decision["gameweek"]),
                    "chip_key": branch_key,
                    "status": branch.get("status"),
                    "legal": branch.get("legal"),
                    "expected_gameweek_points": branch.get("expected_gameweek_points"),
                    "expected_horizon_points": branch.get("expected_horizon_points"),
                    "no_chip_horizon_points": branch.get("no_chip_horizon_points"),
                    "expected_gain": branch.get("expected_gain"),
                    "future_opportunity_cost": branch.get("future_opportunity_cost"),
                    "uncertainty_penalty": branch.get("uncertainty_penalty"),
                    "realized_gain": (
                        _number(decision.get("realistic_chip_realized_gain"))
                        if selected
                        else None
                    ),
                    "realized_gain_status": "exact_selected" if selected else "unavailable",
                    "reason": branch.get("reason"),
                }
            )
    return pd.DataFrame(rows)


def build_chip_usage(
    decisions: pd.DataFrame,
    gameweeks: pd.DataFrame,
) -> pd.DataFrame:
    """Describe selected chip timing and value without inventing replay regret."""

    selected = decisions[
        decisions["chip_used"].fillna("none").astype(str).str.lower().ne("none")
    ].copy()
    columns = [
        "season",
        "gameweek",
        "chip_used",
        "chip_key",
        "chip_slot",
        "fixture_regime",
        "expected_gain",
        "realized_gain",
        "realized_gain_status",
        "future_opportunity_cost",
        "uncertainty_penalty",
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    selected["season"] = selected["season"].astype(str)
    selected["gameweek"] = pd.to_numeric(selected["gameweek"], errors="raise").astype(int)
    regimes = gameweeks[["season", "gameweek", "fixture_regime"]].drop_duplicates()
    selected = selected.merge(
        regimes,
        on=["season", "gameweek"],
        how="left",
        validate="one_to_one",
    )
    selected["expected_gain"] = pd.to_numeric(
        selected.get("chip_expected_gain"), errors="coerce"
    )
    selected["realized_gain"] = pd.to_numeric(
        selected.get("realistic_chip_realized_gain"), errors="coerce"
    )
    selected["future_opportunity_cost"] = pd.to_numeric(
        selected.get("future_opportunity_cost"), errors="coerce"
    )
    selected["uncertainty_penalty"] = pd.to_numeric(
        selected.get("uncertainty_penalty"), errors="coerce"
    )
    selected["realized_gain_status"] = np.where(
        selected["chip_used"].astype(str).str.lower().eq("wildcard"),
        "not_measurable_same_gameweek",
        "exact_incremental_gameweek",
    )
    for column in ("chip_key", "chip_slot"):
        if column not in selected:
            selected[column] = None
    return selected[columns].sort_values(["season", "gameweek"], ignore_index=True)


def build_decision_opportunities(
    gameweeks: pd.DataFrame,
    chip_usage: pd.DataFrame,
) -> pd.DataFrame:
    """Build comparable diagnostics and structural chip-health checks by season."""

    rows: list[dict[str, Any]] = []
    for season, frame in gameweeks.groupby("season", sort=True):
        rows.extend(
            [
                _opportunity(
                    season,
                    "captaincy",
                    float(frame["captain_regret"].sum()),
                    "points",
                    _aggregate_status(
                        frame["captain_regret_status"],
                        accepted=(
                            "hindsight_upper_bound",
                            "hindsight_upper_bound_no_effective_captain",
                        ),
                    ),
                    int(frame["captain_regret"].notna().sum()),
                    "Hindsight upper bound; not an attainable forecast.",
                ),
                _opportunity(
                    season,
                    "starting_xi",
                    float(frame["lineup_regret"].sum()),
                    "points",
                    _aggregate_status(frame["lineup_regret_status"]),
                    int(frame["lineup_regret"].notna().sum()),
                    "Hindsight upper bound conditional on the owned active squad.",
                ),
                _opportunity(
                    season,
                    "selected_transfers",
                    float(frame["selected_transfer_regret"].sum()),
                    "points",
                    _aggregate_status(
                        frame["selected_transfer_status"],
                        accepted=("hindsight_partial", "not_applicable"),
                        available_label="hindsight_partial",
                    ),
                    int(frame["selected_transfer_regret"].notna().sum()),
                    "One-Gameweek downside of selected transfers; alternatives excluded.",
                ),
            ]
        )
        season_chips = chip_usage[chip_usage["season"].astype(str).eq(str(season))]
        selected_count = int(len(season_chips))
        zero_opportunity_cost = int(
            pd.to_numeric(
                season_chips["future_opportunity_cost"], errors="coerce"
            ).fillna(0.0).eq(0.0).sum()
        )
        free_hits = season_chips[
            season_chips["chip_used"].astype(str).str.lower().eq("freehit")
        ]
        zero_free_hits = int(
            pd.to_numeric(free_hits["realized_gain"], errors="coerce")
            .fillna(0.0)
            .eq(0.0)
            .sum()
        )
        rows.extend(
            [
                _opportunity(
                    season,
                    "chip_future_opportunity_cost",
                    zero_opportunity_cost / selected_count if selected_count else None,
                    "share",
                    "structural_diagnostic" if selected_count else "unavailable",
                    selected_count,
                    "Share of selected chips assigned zero value for saving the chip.",
                ),
                _opportunity(
                    season,
                    "free_hit_realization",
                    zero_free_hits,
                    "zero_gain_activations",
                    "exact_selected_outcomes" if len(free_hits) else "unavailable",
                    int(len(free_hits)),
                    "Count of selected Free Hits with zero incremental Gameweek points.",
                ),
            ]
        )
    return pd.DataFrame(rows)


def _captain_regret(
    active_ids: tuple[int, ...],
    effective_id: int | None,
    points: pd.Series,
    *,
    chip_used: str,
    effective_actual: float | None = None,
) -> tuple[float | None, str]:
    if not active_ids or effective_id is None:
        return None, "unavailable"
    best = max(float(points.get(player_id, 0.0)) for player_id in active_ids)
    effective = (
        float(effective_actual)
        if effective_actual is not None
        else float(points.get(effective_id, 0.0))
    )
    if effective_id not in active_ids and abs(effective) >= 1e-9:
        return None, "invalid_effective_captain"
    multiplier = 2.0 if chip_used.lower() in {"3xc", "triple_captain"} else 1.0
    status = (
        "hindsight_upper_bound"
        if effective_id in active_ids
        else "hindsight_upper_bound_no_effective_captain"
    )
    return max(0.0, best - effective) * multiplier, status


def _lineup_regret(
    row: dict[str, Any],
    target: pd.DataFrame,
    points: pd.Series,
    *,
    squad_ids: tuple[int, ...] | None = None,
) -> tuple[float | None, str, float | None]:
    if str(row.get("chip_used") or "none").lower() in {"bboost", "bench_boost"}:
        return 0.0, "not_applicable_bench_boost", None
    squad_ids = squad_ids or _parse_ids(row.get("squad_ids"))
    if len(squad_ids) != 15:
        return None, "unavailable_missing_squad_ids", None
    squad = target[target["player_id"].isin(squad_ids)].drop_duplicates("player_id").copy()
    if len(squad) != 15:
        return None, "unavailable_incomplete_squad_join", None
    try:
        oracle_lineup = _audit_oracle_lineup(squad, points.to_dict())
        oracle_active, _ = resolve_active_lineup(squad, target, oracle_lineup)
    except ValueError:
        return None, "unavailable_invalid_squad_shape", None
    oracle_raw = float(sum(float(points.get(player_id, 0.0)) for player_id in oracle_active))
    selected_raw = _optional_number(row.get("raw_starter_points"))
    if selected_raw is None:
        selected_ids, _ = _realistic_active_ids(row)
        if not selected_ids:
            return None, "unavailable_missing_selected_xi", oracle_raw
        selected_raw = float(sum(float(points.get(player_id, 0.0)) for player_id in selected_ids))
    return max(0.0, oracle_raw - selected_raw), "hindsight_upper_bound", oracle_raw


def _audit_oracle_lineup(
    squad: pd.DataFrame,
    actual_points: dict[int, float],
) -> LineupSelection:
    """Choose a hindsight XI without re-validating owned budget or club counts."""

    working = squad.copy()
    working["position_group"] = working["position"].map(position_group)
    if len(working) != 15 or working["player_id"].nunique() != 15:
        raise ValueError("Invalid owned squad shape")
    position_counts = working["position_group"].value_counts()
    if any(
        int(position_counts.get(position, 0)) != required
        for position, required in {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}.items()
    ):
        raise ValueError("Invalid owned squad position quotas")
    working["_actual"] = working["player_id"].map(actual_points).fillna(0.0)
    best: tuple[float, tuple[int, ...], tuple[int, int, int]] | None = None
    for formation in VALID_FORMATIONS:
        defender_count, midfielder_count, forward_count = formation
        quotas = {
            "GK": 1,
            "DEF": defender_count,
            "MID": midfielder_count,
            "FWD": forward_count,
        }
        selected_ids: list[int] = []
        for position, count in quotas.items():
            selected = working[working["position_group"].eq(position)].sort_values(
                ["_actual", "player_id"], ascending=[False, True]
            )
            selected_ids.extend(selected.head(count)["player_id"].astype(int).tolist())
        key = (
            float(sum(actual_points.get(player_id, 0.0) for player_id in selected_ids)),
            tuple(-player_id for player_id in sorted(selected_ids)),
            formation,
        )
        if best is None or key > best:
            best = key
    if best is None:
        raise ValueError("Could not construct hindsight XI")
    _, selected_key, formation = best
    starting_ids = tuple(-player_id for player_id in selected_key)
    bench = working[~working["player_id"].isin(starting_ids)].copy()
    bench["_is_goalkeeper"] = bench["position_group"].eq("GK")
    bench = bench.sort_values(
        ["_is_goalkeeper", "_actual", "player_id"],
        ascending=[True, False, True],
    )
    return LineupSelection(
        starting_ids=starting_ids,
        bench_ids=tuple(bench["player_id"].astype(int)),
        formation="-".join(str(value) for value in formation),
    )


def _bench_points_left(
    row: dict[str, Any],
    points: pd.Series,
) -> tuple[float | None, str]:
    if str(row.get("chip_used") or "none").lower() in {"bboost", "bench_boost"}:
        return 0.0, "included_by_bench_boost"
    bench_ids = _parse_ids(row.get("selected_bench_ids"))
    if len(bench_ids) != 4:
        return None, "unavailable_missing_ordered_bench"
    autosubs = set(_parse_ids(row.get("realistic_autosub_ids")))
    return (
        float(
            sum(
                float(points.get(player_id, 0.0))
                for player_id in bench_ids
                if player_id not in autosubs
            )
        ),
        "diagnostic_actual_points",
    )


def _transfer_diagnostic(
    row: dict[str, Any],
    points: pd.Series,
) -> tuple[float | None, float | None, str]:
    if not _bool(row.get("transfers_made")):
        return 0.0, 0.0, "not_applicable"
    incoming_id = _optional_int(row.get("incoming_id"))
    outgoing_id = _optional_int(row.get("outgoing_id"))
    if incoming_id is None or outgoing_id is None:
        return None, None, "unavailable_missing_transfer_ids"
    delta = float(points.get(incoming_id, 0.0)) - float(points.get(outgoing_id, 0.0))
    net_delta = delta - _number(row.get("hit_cost"))
    return delta, max(0.0, -net_delta), "hindsight_partial"


def _realistic_active_ids(row: dict[str, Any]) -> tuple[tuple[int, ...], str]:
    realistic = _parse_ids(row.get("realistic_starting_ids"))
    if realistic:
        return realistic, "realistic_starting_ids"
    legacy = _parse_ids(row.get("starting_ids"))
    if legacy:
        return legacy, "legacy_generic_starting_ids"
    return (), "unavailable"


def _decision_squad_ids(row: dict[str, Any]) -> tuple[tuple[int, ...], str]:
    starters = _parse_ids(row.get("selected_starting_ids"))
    bench = _parse_ids(row.get("selected_bench_ids"))
    active_squad = tuple(dict.fromkeys((*starters, *bench)))
    if len(starters) == 11 and len(bench) == 4 and len(active_squad) == 15:
        return active_squad, "selected_xi_plus_bench"
    persisted = _parse_ids(row.get("squad_ids"))
    if len(persisted) == 15:
        return persisted, "persisted_squad_ids"
    return (), "unavailable"


def _season_roster(players: pd.DataFrame) -> pd.DataFrame:
    """Prepare season-local identity history for zero-fixture joins."""

    roster = players.copy()
    roster["player_id"] = pd.to_numeric(roster["player_id"], errors="raise").astype(int)
    roster["gameweek"] = pd.to_numeric(roster["gameweek"], errors="coerce")
    return roster.sort_values(["player_id", "gameweek"])


def _complete_target_for_squad(
    fixture_target: pd.DataFrame,
    roster: pd.DataFrame,
    squad_ids: tuple[int, ...],
    *,
    gameweek: int,
) -> pd.DataFrame:
    """Add zero-point rows for owned players absent from that Gameweek table."""

    target = fixture_target.copy()
    target["player_id"] = pd.to_numeric(target["player_id"], errors="raise").astype(int)
    if not squad_ids:
        return target
    present = set(target["player_id"])
    missing_ids = set(squad_ids).difference(present)
    if not missing_ids:
        return target
    missing = (
        roster[
            roster["player_id"].isin(missing_ids)
            & (pd.to_numeric(roster["gameweek"], errors="coerce") <= gameweek)
        ]
        .drop_duplicates("player_id", keep="last")
        .copy()
    )
    if set(missing["player_id"]) != missing_ids:
        return target
    missing["gameweek"] = gameweek
    missing["minutes"] = 0.0
    missing["next_gameweek_points"] = 0.0
    return pd.concat([target, missing], ignore_index=True, sort=False).drop_duplicates(
        "player_id", keep="first"
    )


def _fixture_regime(target: pd.DataFrame) -> dict[str, Any]:
    opponent = target.get("opponent_team", pd.Series("", index=target.index)).astype(str)
    home_away = target.get("home_or_away", pd.Series("", index=target.index)).astype(str)
    is_blank = int(target["team"].astype(str).nunique() < 20)
    is_double = int(
        home_away.str.upper().eq("M").any() or opponent.str.contains(r"\+", regex=True).any()
    )
    if is_blank and is_double:
        regime = "blank_double"
    elif is_blank:
        regime = "blank"
    elif is_double:
        regime = "double"
    else:
        regime = "normal"
    return {"is_blank": is_blank, "is_double": is_double, "regime": regime}


def _assert_season_reconciliation(
    gameweeks: pd.DataFrame,
    season_summary: pd.DataFrame,
) -> None:
    failures = gameweeks[
        (gameweeks["row_reconciliation_status"] != "exact")
        | (gameweeks["cumulative_reconciliation_status"] != "exact")
    ]
    if not failures.empty:
        keys = failures[["season", "gameweek"]].to_dict("records")
        raise AssertionError(f"Gameweek score reconciliation failed: {keys}")
    calculated = (
        gameweeks.groupby("season", sort=True)["realistic_net_points"].sum().rename("calculated")
    )
    reported = season_summary.copy()
    reported["season"] = reported["season"].astype(str)
    reported = reported.set_index("season")["realistic_points"]
    aligned = pd.concat([calculated, reported.rename("reported")], axis=1)
    mismatched = aligned[(aligned["calculated"] - aligned["reported"]).abs() >= 1e-9]
    if not mismatched.empty or aligned.isna().any(axis=None):
        raise AssertionError(
            "Season score reconciliation failed: "
            + json.dumps(aligned.reset_index().to_dict("records"), default=str)
        )


def _write_audit(simulation_dir: Path, result: PointsLossAudit) -> None:
    artifacts = {
        "gameweeks": result.gameweeks,
        "buckets": result.buckets,
        "rank_evaluation": result.rank_evaluation,
        "chip_counterfactuals": result.chip_counterfactuals,
        "decision_opportunities": result.decision_opportunities,
        "chip_usage": result.chip_usage,
    }
    manifest = dict(result.manifest)
    manifest["artifacts"] = {}
    for key, frame in artifacts.items():
        path = simulation_dir / AUDIT_ARTIFACTS[key]
        frame.to_csv(path, index=False)
        manifest["artifacts"][key] = {
            "path": str(path),
            "rows": int(len(frame)),
            "sha256": _file_hash(path),
        }
    manifest_path = simulation_dir / "points_loss_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("\nPost-recovery points-loss audit")
    print(
        result.rank_evaluation[
            [
                "season",
                "realistic_points",
                "classification",
                "margin_to_known_inside_points",
            ]
        ].to_string(index=False)
    )
    print(f"\nAudit artifacts: {simulation_dir}")


def _bucket(
    season: str,
    bucket: str,
    value: float | None,
    status: str,
    definition: str,
    *,
    additive: bool = False,
) -> dict[str, Any]:
    return {
        "season": season,
        "bucket": bucket,
        "value": value,
        "status": status,
        "additive": additive,
        "definition": definition,
    }


def _opportunity(
    season: str,
    decision_area: str,
    value: float | int | None,
    unit: str,
    status: str,
    coverage_gameweeks: int,
    limitation: str,
) -> dict[str, Any]:
    return {
        "season": str(season),
        "decision_area": decision_area,
        "value": value,
        "unit": unit,
        "status": status,
        "coverage_gameweeks": coverage_gameweeks,
        "non_additive": True,
        "limitation": limitation,
    }


def _complete_sum(
    frame: pd.DataFrame,
    value_column: str,
    status_column: str,
    *,
    accepted: tuple[str, ...] = (
        "hindsight_upper_bound",
        "hindsight_upper_bound_no_effective_captain",
        "not_applicable_bench_boost",
        "included_by_bench_boost",
        "diagnostic_actual_points",
    ),
) -> float | None:
    if not frame[status_column].isin(accepted).all():
        return None
    return float(pd.to_numeric(frame[value_column], errors="coerce").fillna(0.0).sum())


def _aggregate_status(
    statuses: pd.Series,
    *,
    accepted: tuple[str, ...] = (
        "hindsight_upper_bound",
        "hindsight_upper_bound_no_effective_captain",
        "not_applicable_bench_boost",
        "included_by_bench_boost",
        "diagnostic_actual_points",
    ),
    available_label: str = "hindsight_upper_bound",
) -> str:
    return available_label if statuses.isin(accepted).all() else "partially_unavailable"


def _audit_definitions() -> dict[str, Any]:
    return {
        "realistic_net_points": "realistic_gross_points - hit_cost",
        "captain_regret": (
            "Best actual points among the post-autosub active XI minus effective "
            "captain actual points; multiplier two for Triple Captain."
        ),
        "lineup_regret": (
            "Actual-points-optimized legal XI after autosubs minus selected XI raw points."
        ),
        "selected_transfer_regret": (
            "max(0, outgoing actual points - incoming actual points + hit cost); "
            "one-Gameweek partial diagnostic only."
        ),
        "chip_future_opportunity_cost_zero_share": (
            "Selected chips with persisted future_opportunity_cost equal to zero "
            "divided by all selected chips. This is a structural planner diagnostic, "
            "not points regret."
        ),
        "free_hit_zero_gain_activations": (
            "Selected Free Hits whose exact incremental Gameweek points versus the "
            "persisted no-chip path equal zero."
        ),
        "rank_classification": (
            "Comparison with source-backed known-inside and known-outside score bounds; "
            "not an asserted exact points cutoff."
        ),
    }


def _parse_ids(value: Any) -> tuple[int, ...]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ()
    return tuple(int(part) for part in str(value).split("+") if part.strip())


def _number(value: Any) -> float:
    parsed = _optional_number(value)
    return 0.0 if parsed is None else parsed


def _optional_number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def _optional_int(value: Any) -> int | None:
    parsed = _optional_number(value)
    return None if parsed is None else int(parsed)


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value) if value is not None and not pd.isna(value) else False


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit score reconciliation, decision regret, and top-1% references."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--simulation-dir",
        type=Path,
        help="Directory containing gameweek_decisions.csv and season_summary.csv.",
    )
    source.add_argument(
        "--recovery-scorecard",
        action="store_true",
        help="Audit the accepted post-recovery three-season production scorecard.",
    )
    parser.add_argument(
        "--cold-start-dir",
        type=Path,
        default=DEFAULT_RECOVERY_2023_DIR,
    )
    parser.add_argument(
        "--tournament-dir",
        type=Path,
        default=DEFAULT_RECOVERY_TOURNAMENT_DIR,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_POST_RECOVERY_AUDIT_DIR,
    )
    parser.add_argument(
        "--candidate",
        default=RECOVERY_TOURNAMENT_CANDIDATE,
    )
    parser.add_argument(
        "--historical-data",
        type=Path,
        default=HISTORICAL_PLAYER_GW_PATH,
    )
    parser.add_argument(
        "--rank-reference",
        type=Path,
        default=DEFAULT_RANK_REFERENCE_PATH,
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    if args.recovery_scorecard:
        audit_recovery_scorecard(
            cold_start_dir=args.cold_start_dir,
            tournament_dir=args.tournament_dir,
            output_dir=args.output_dir,
            candidate=args.candidate,
            historical_path=args.historical_data,
            rank_reference_path=args.rank_reference,
        )
    else:
        audit_simulation(
            args.simulation_dir,
            historical_path=args.historical_data,
            rank_reference_path=args.rank_reference,
        )


if __name__ == "__main__":
    main()
