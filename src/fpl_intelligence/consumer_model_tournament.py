"""P4 consumer-specific champion/challenger tournament.

Each challenger changes one decision consumer or policy at a time. Screening
runs are chips-disabled and cannot promote a candidate. Full runs use the
accepted chip-aware beam, fixed opening squads, realistic captaincy, and the
same historical rules/data cutoffs as the production champion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from fpl_intelligence.chip_simulation import CHIP_MODE_BEAM, CHIP_MODE_NONE
from fpl_intelligence.decision_audit import (
    ChampionChallengerGate,
    build_champion_challenger_report,
)
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.projection_portfolio import ProjectionPortfolio
from fpl_intelligence.season_benchmark import (
    HISTORICAL_PLAYER_GW_PATH,
    DeterministicTransferStrategy,
    get_git_commit,
    run_season_benchmark,
)
from fpl_intelligence.season_rules import build_historical_season_rules
from fpl_intelligence.simulate_seasons import (
    CONTROL_INITIAL_SQUAD_POLICY,
    DEFAULT_SEASONS,
    PRODUCTION_INITIAL_SQUAD_POLICY,
    _initial_squad_for_preset,
)
from fpl_intelligence.step4_models import load_historical_player_gameweeks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "consumer_tournaments"
P4_SCHEMA_VERSION = "pdc-p4-consumer-model-tournament-v1"
P4_CHAMPION = "production_champion"
P4_STAGES = ("screening", "full")

Consumer = Literal[
    "champion",
    "transfer",
    "captain",
    "chip",
    "lineup",
    "minutes_availability",
    "initial_squad",
    "hit",
    "projection_engine",
]


@dataclass(frozen=True)
class ConsumerCandidate:
    name: str
    consumer: Consumer
    version: str
    portfolio: ProjectionPortfolio
    minutes_mode: str = "binary"
    feature_mode: str = "baseline"
    projection_mode: str = "total_points"
    hit_policy: str = "current_gw"
    initial_squad_policy: str = PRODUCTION_INITIAL_SQUAD_POLICY

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["portfolio"] = self.portfolio.as_dict()
        return value


@dataclass(frozen=True)
class CandidateSeasonRun:
    candidate: ConsumerCandidate
    season: str
    rows: pd.DataFrame
    realistic_points: float
    hindsight_points: float
    transfers: int
    hit_cost: int
    chips_used: int
    initial_squad_hash: str


@dataclass(frozen=True)
class P4TournamentResult:
    stage: str
    summary: pd.DataFrame
    acceptance: pd.DataFrame
    decisions: pd.DataFrame
    per_gameweek: pd.DataFrame
    regime_summary: pd.DataFrame
    output_dir: Path


def candidate_catalog() -> dict[str, ConsumerCandidate]:
    """Return stable, one-change-at-a-time P4 candidates."""

    champion_portfolio = get_production_portfolio("r2_validated").projections
    ridge = "Ridge Regression"
    gradient = "Gradient Boosting Regressor"
    candidates = (
        ConsumerCandidate(
            name=P4_CHAMPION,
            consumer="champion",
            version="p4-production-control-v1",
            portfolio=champion_portfolio,
        ),
        ConsumerCandidate(
            name="transfer_gradient",
            consumer="transfer",
            version="p4-transfer-gradient-v1",
            portfolio=ProjectionPortfolio(
                transfer_model=gradient,
                captain_model=ridge,
                chip_model=gradient,
                lineup_model=ridge,
            ),
        ),
        ConsumerCandidate(
            name="captain_gradient",
            consumer="captain",
            version="p4-captain-gradient-v1",
            portfolio=ProjectionPortfolio(
                transfer_model=ridge,
                captain_model=gradient,
                chip_model=gradient,
                lineup_model=ridge,
            ),
        ),
        ConsumerCandidate(
            name="chip_ridge",
            consumer="chip",
            version="p4-chip-ridge-v1",
            portfolio=ProjectionPortfolio(
                transfer_model=ridge,
                captain_model=ridge,
                chip_model=ridge,
                lineup_model=ridge,
            ),
        ),
        ConsumerCandidate(
            name="lineup_gradient",
            consumer="lineup",
            version="p4-lineup-gradient-v1",
            portfolio=ProjectionPortfolio(
                transfer_model=ridge,
                captain_model=ridge,
                chip_model=gradient,
                lineup_model=gradient,
            ),
        ),
        ConsumerCandidate(
            name="minutes_conditional",
            consumer="minutes_availability",
            version="p4-minutes-conditional-v1",
            portfolio=champion_portfolio,
            minutes_mode="conditional_bands",
        ),
        ConsumerCandidate(
            name="minutes_availability_role",
            consumer="minutes_availability",
            version="p4-minutes-availability-role-v1",
            portfolio=champion_portfolio,
            minutes_mode="availability_role",
        ),
        ConsumerCandidate(
            name="initial_identity_safe",
            consumer="initial_squad",
            version="p4-initial-identity-safe-v1",
            portfolio=champion_portfolio,
            initial_squad_policy=CONTROL_INITIAL_SQUAD_POLICY,
        ),
        ConsumerCandidate(
            name="hit_horizon_value",
            consumer="hit",
            version="p4-hit-horizon-v1",
            portfolio=champion_portfolio,
            hit_policy="horizon_value",
        ),
        ConsumerCandidate(
            name="component_projection",
            consumer="projection_engine",
            version="p4-components-v1",
            portfolio=champion_portfolio,
            feature_mode="xg_xa",
            projection_mode="components",
        ),
        ConsumerCandidate(
            name="team_component_projection",
            consumer="projection_engine",
            version="p4-team-components-v1",
            portfolio=champion_portfolio,
            feature_mode="xg_xa",
            projection_mode="m10_team_components",
        ),
    )
    return {candidate.name: candidate for candidate in candidates}


def run_consumer_tournament(
    *,
    stage: str = "screening",
    seasons: tuple[str, ...] = DEFAULT_SEASONS,
    candidate_names: tuple[str, ...] | None = None,
    output_dir: Path | None = None,
    players: pd.DataFrame | None = None,
    generated_at: str | None = None,
    resume: bool = False,
    champion_artifact_dirs: tuple[Path, ...] = (),
) -> P4TournamentResult:
    """Run isolated P4 tracks and persist checkpointed decision evidence."""

    if stage not in P4_STAGES:
        raise ValueError(f"stage must be one of {', '.join(P4_STAGES)}")
    historical = (
        players.copy()
        if players is not None
        else load_historical_player_gameweeks(HISTORICAL_PLAYER_GW_PATH)
    )
    selected_seasons = _validate_seasons(historical, seasons)
    catalog = candidate_catalog()
    requested = tuple(candidate_names or tuple(name for name in catalog if name != P4_CHAMPION))
    unknown = sorted(set(requested).difference(catalog))
    if unknown:
        raise ValueError(f"Unknown P4 candidates: {', '.join(unknown)}")
    selected = [catalog[P4_CHAMPION], *(catalog[name] for name in requested if name != P4_CHAMPION)]
    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    config = {
        "stage": stage,
        "seasons": list(selected_seasons),
        "candidates": [candidate.as_dict() for candidate in selected],
        "schema_version": P4_SCHEMA_VERSION,
    }
    config_hash = _stable_hash(config)
    destination = output_dir or (
        DEFAULT_OUTPUT_ROOT / f"{_filesystem_timestamp(timestamp)}-{stage}-{config_hash[:8]}"
    )
    if destination.exists() and not resume:
        raise FileExistsError(f"P4 output already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    opening_squads = _opening_squads(historical, selected_seasons)
    if champion_artifact_dirs:
        _seed_champion_checkpoints(
            destination,
            artifact_dirs=champion_artifact_dirs,
            candidate=catalog[P4_CHAMPION],
            seasons=selected_seasons,
            config_hash=config_hash,
            historical=historical,
            stage=stage,
        )
    prediction_cache: dict[Any, Any] = {}
    captain_cache: dict[Any, Any] = {}
    future_cache: dict[Any, Any] = {}
    runs: list[CandidateSeasonRun] = []
    for candidate in selected:
        if stage == "screening" and candidate.consumer == "chip":
            continue
        for season in selected_seasons:
            checkpoint = _checkpoint_paths(destination, candidate.name, season)
            loaded = _load_checkpoint(
                checkpoint,
                candidate=candidate,
                season=season,
                config_hash=config_hash,
            ) if resume else None
            if loaded is not None:
                runs.append(loaded)
                continue
            squad_key = (
                CONTROL_INITIAL_SQUAD_POLICY
                if candidate.initial_squad_policy == CONTROL_INITIAL_SQUAD_POLICY
                else PRODUCTION_INITIAL_SQUAD_POLICY
            )
            squad, initial_mode, initial_version = opening_squads[(season, squad_key)]
            result = run_season_benchmark(
                historical,
                season,
                DeterministicTransferStrategy(),
                model_name=candidate.portfolio.transfer_model,
                model_version=candidate.version,
                minutes_mode=candidate.minutes_mode,
                feature_mode=candidate.feature_mode,
                projection_mode=candidate.projection_mode,
                chip_mode=CHIP_MODE_BEAM if stage == "full" else CHIP_MODE_NONE,
                hit_policy=candidate.hit_policy,
                projection_portfolio=candidate.portfolio,
                prediction_cache=prediction_cache,
                captain_prediction_cache=captain_cache,
                future_prediction_cache=future_cache,
                initial_squad_override=squad,
                initial_squad_mode=initial_mode,
                initial_squad_version=initial_version,
            )
            run = CandidateSeasonRun(
                candidate=candidate,
                season=season,
                rows=result.rows.copy(),
                realistic_points=float(result.realistic_total_points),
                hindsight_points=float(result.total_points),
                transfers=int(result.transfers_made),
                hit_cost=int(result.total_hit_cost),
                chips_used=int(result.chips_used),
                initial_squad_hash=str(result.rows["initial_squad_hash"].iloc[0]),
            )
            _write_checkpoint(checkpoint, run=run, config_hash=config_hash)
            runs.append(run)

    summary = _summary_frame(runs)
    decisions = _decision_frame(runs)
    acceptance, per_gameweek, regime_summary = _evaluate_candidates(
        runs,
        historical,
        stage=stage,
        expected_seasons=selected_seasons,
        skipped_chip_candidates=[
            candidate
            for candidate in selected
            if stage == "screening" and candidate.consumer == "chip"
        ],
    )
    _write_outputs(
        destination,
        summary=summary,
        decisions=decisions,
        acceptance=acceptance,
        per_gameweek=per_gameweek,
        regime_summary=regime_summary,
        config=config,
        config_hash=config_hash,
        historical=historical,
        timestamp=timestamp,
    )
    return P4TournamentResult(
        stage=stage,
        summary=summary,
        acceptance=acceptance,
        decisions=decisions,
        per_gameweek=per_gameweek,
        regime_summary=regime_summary,
        output_dir=destination,
    )


def _opening_squads(
    players: pd.DataFrame,
    seasons: tuple[str, ...],
) -> dict[tuple[str, str], tuple[pd.DataFrame, str, str]]:
    output = {}
    for season in seasons:
        output[(season, PRODUCTION_INITIAL_SQUAD_POLICY)] = _initial_squad_for_preset(
            players,
            season,
            policy=PRODUCTION_INITIAL_SQUAD_POLICY,
            model_name="Ridge Regression",
        )
        output[(season, CONTROL_INITIAL_SQUAD_POLICY)] = _initial_squad_for_preset(
            players,
            season,
            policy=CONTROL_INITIAL_SQUAD_POLICY,
            model_name="Ridge Regression",
        )
    return output


def _seed_champion_checkpoints(
    destination: Path,
    *,
    artifact_dirs: tuple[Path, ...],
    candidate: ConsumerCandidate,
    seasons: tuple[str, ...],
    config_hash: str,
    historical: pd.DataFrame,
    stage: str,
) -> None:
    """Import an immutable like-for-like champion instead of recomputing it."""

    if stage != "full":
        raise ValueError("Champion artifact import is only valid for the full stage")
    summaries = []
    decisions = []
    expected_data_hash = _dataframe_hash(historical)
    for artifact_dir in artifact_dirs:
        root = Path(artifact_dir)
        manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
        source_hash = str(manifest.get("source_data", {}).get("sha256", ""))
        if source_hash != expected_data_hash:
            raise ValueError(f"Champion artifact historical-data hash mismatch: {root}")
        configuration = manifest.get("configuration", {})
        if configuration.get("chip_mode") != CHIP_MODE_BEAM:
            raise ValueError(f"Champion artifact is not chip-aware: {root}")
        if configuration.get("projection_portfolio") != candidate.portfolio.as_dict():
            # Older accepted artifacts predate the explicit lineup key. Accept
            # only the exact production assignment with the implicit Ridge lineup.
            legacy = dict(candidate.portfolio.as_dict())
            legacy.pop("lineup_model")
            if configuration.get("projection_portfolio") != legacy:
                raise ValueError(f"Champion artifact portfolio mismatch: {root}")
        summaries.append(pd.read_csv(root / "season_summary.csv"))
        decisions.append(pd.read_csv(root / "gameweek_decisions.csv"))
    summary = pd.concat(summaries, ignore_index=True, sort=False)
    rows = pd.concat(decisions, ignore_index=True, sort=False)
    if summary["season"].duplicated().any() or set(summary["season"].astype(str)) != set(seasons):
        raise ValueError("Champion artifacts must contain exactly one summary per P4 season")
    if rows.duplicated(["season", "gameweek"]).any():
        raise ValueError("Champion artifacts contain duplicate Gameweek decisions")
    counts = rows.groupby("season")["gameweek"].nunique().to_dict()
    if counts != {season: 38 for season in seasons}:
        raise ValueError(f"Champion artifacts are incomplete: {counts}")
    if "lineup_model_name" not in rows:
        rows["lineup_model_name"] = candidate.portfolio.lineup_model
    for season in seasons:
        checkpoint = _checkpoint_paths(destination, candidate.name, season)
        if checkpoint[0].exists() or checkpoint[1].exists():
            continue
        season_summary = summary[summary["season"].astype(str).eq(season)].iloc[0]
        season_rows = rows[rows["season"].astype(str).eq(season)].copy()
        run = CandidateSeasonRun(
            candidate=candidate,
            season=season,
            rows=season_rows,
            realistic_points=float(season_summary["realistic_points"]),
            hindsight_points=float(season_summary["hindsight_points"]),
            transfers=int(season_summary["transfers"]),
            hit_cost=int(season_summary["hit_cost"]),
            chips_used=int(season_summary["chips_used"]),
            initial_squad_hash=str(season_summary["initial_squad_hash"]),
        )
        _write_checkpoint(checkpoint, run=run, config_hash=config_hash)


def _evaluate_candidates(
    runs: list[CandidateSeasonRun],
    players: pd.DataFrame,
    *,
    stage: str,
    expected_seasons: tuple[str, ...],
    skipped_chip_candidates: list[ConsumerCandidate],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    by_candidate: dict[str, list[CandidateSeasonRun]] = {}
    for run in runs:
        by_candidate.setdefault(run.candidate.name, []).append(run)
    champion = by_candidate.get(P4_CHAMPION, [])
    if len(champion) != len(expected_seasons):
        raise ValueError("P4 champion is incomplete")
    acceptance_rows = []
    per_gameweek_frames = []
    regime_frames = []
    for candidate_name, candidate_runs in sorted(by_candidate.items()):
        if candidate_name == P4_CHAMPION:
            continue
        candidate = candidate_runs[0].candidate
        report = build_champion_challenger_report(
            [run.rows for run in champion],
            [run.rows for run in candidate_runs],
            players,
            gate=ChampionChallengerGate(),
        )
        per_gameweek = report.per_gameweek.copy()
        per_gameweek.insert(0, "candidate", candidate.name)
        per_gameweek.insert(1, "consumer", candidate.consumer)
        per_gameweek_frames.append(per_gameweek)
        regime = report.regime_summary.copy()
        regime.insert(0, "candidate", candidate.name)
        regime.insert(1, "consumer", candidate.consumer)
        regime_frames.append(regime)
        relevant_changed, relevant_reason = _relevant_decision_change(
            candidate,
            per_gameweek,
        )
        reasons = list(report.rejection_reasons)
        if not relevant_changed:
            reasons.append(relevant_reason)
        captain_regret_delta = float(report.season_summary["captain_regret_delta"].sum())
        if candidate.consumer == "captain" and captain_regret_delta >= 0:
            reasons.append("Captain regret did not improve across validation seasons.")
        promotion_eligible = stage == "full" and len(candidate_runs) == len(expected_seasons)
        if not promotion_eligible:
            reasons.append("Screening evidence cannot promote a production candidate.")
        acceptance_rows.append(
            {
                "candidate": candidate.name,
                "consumer": candidate.consumer,
                "stage": stage,
                "seasons_evaluated": len(candidate_runs),
                "improved_seasons": int(
                    (report.season_summary["realistic_delta"] > 0).sum()
                ),
                "regressed_seasons": int(
                    (report.season_summary["realistic_delta"] < 0).sum()
                ),
                "aggregate_delta": float(report.season_summary["realistic_delta"].sum()),
                "worst_season_delta": float(report.season_summary["realistic_delta"].min()),
                "captain_regret_delta": captain_regret_delta,
                "relevant_decision_changed": relevant_changed,
                "passed": not reasons,
                "promotion_status": "validated" if not reasons else "rejected",
                "reasons": " | ".join(reasons),
                "per_season_deltas": json.dumps(
                    {
                        str(row.season): float(row.realistic_delta)
                        for row in report.season_summary.itertuples(index=False)
                    },
                    sort_keys=True,
                ),
            }
        )
    for candidate in skipped_chip_candidates:
        acceptance_rows.append(
            {
                "candidate": candidate.name,
                "consumer": candidate.consumer,
                "stage": stage,
                "seasons_evaluated": 0,
                "improved_seasons": 0,
                "regressed_seasons": 0,
                "aggregate_delta": 0.0,
                "worst_season_delta": 0.0,
                "captain_regret_delta": 0.0,
                "relevant_decision_changed": False,
                "passed": False,
                "promotion_status": "not_applicable",
                "reasons": "Chip models require the full chip-aware stage.",
                "per_season_deltas": "{}",
            }
        )
    return (
        pd.DataFrame(acceptance_rows).sort_values("candidate").reset_index(drop=True),
        pd.concat(per_gameweek_frames, ignore_index=True, sort=False)
        if per_gameweek_frames
        else pd.DataFrame(),
        pd.concat(regime_frames, ignore_index=True, sort=False)
        if regime_frames
        else pd.DataFrame(),
    )


def _relevant_decision_change(
    candidate: ConsumerCandidate,
    comparison: pd.DataFrame,
) -> tuple[bool, str]:
    if candidate.consumer == "transfer":
        changed = bool(comparison["transfer_changed"].any())
        return changed, "Transfer challenger did not change a transfer decision."
    if candidate.consumer == "captain":
        changed = bool(comparison["captain_changed"].any())
        return changed, "Captain challenger did not change a captain decision."
    if candidate.consumer == "chip":
        changed = bool(comparison["chip_changed"].any())
        return changed, "Chip challenger did not change a chip decision."
    if candidate.consumer == "lineup":
        changed = bool(
            comparison["realistic_starting_ids_champion"].fillna("").ne(
                comparison["realistic_starting_ids_challenger"].fillna("")
            ).any()
        )
        return changed, "Lineup challenger did not change a starting XI."
    if candidate.consumer == "initial_squad":
        changed = bool(
            comparison["initial_squad_hash_champion"].fillna("").ne(
                comparison["initial_squad_hash_challenger"].fillna("")
            ).any()
        )
        return changed, "Initial-squad challenger did not change the opening squad."
    if candidate.consumer == "hit":
        changed = bool(
            comparison["hit_cost_champion"].fillna(0).ne(
                comparison["hit_cost_challenger"].fillna(0)
            ).any()
        )
        return changed, "Hit challenger did not change a hit decision."
    changed = bool(
        comparison[["transfer_changed", "captain_changed", "chip_changed"]]
        .any(axis=1)
        .any()
        or comparison["realistic_starting_ids_champion"].fillna("").ne(
            comparison["realistic_starting_ids_challenger"].fillna("")
        ).any()
    )
    return changed, "Challenger did not change any downstream decision."


def _summary_frame(runs: list[CandidateSeasonRun]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate": run.candidate.name,
                "consumer": run.candidate.consumer,
                "season": run.season,
                "realistic_points": run.realistic_points,
                "hindsight_points": run.hindsight_points,
                "transfers": run.transfers,
                "hit_cost": run.hit_cost,
                "chips_used": run.chips_used,
                "initial_squad_hash": run.initial_squad_hash,
                **{
                    f"portfolio_{key}": value
                    for key, value in run.candidate.portfolio.as_dict().items()
                },
                "minutes_mode": run.candidate.minutes_mode,
                "feature_mode": run.candidate.feature_mode,
                "projection_mode": run.candidate.projection_mode,
                "hit_policy": run.candidate.hit_policy,
            }
            for run in runs
        ]
    ).sort_values(["candidate", "season"]).reset_index(drop=True)


def _decision_frame(runs: list[CandidateSeasonRun]) -> pd.DataFrame:
    frames = []
    for run in runs:
        rows = run.rows.copy()
        rows.insert(0, "candidate", run.candidate.name)
        rows.insert(1, "consumer", run.candidate.consumer)
        frames.append(rows)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _checkpoint_paths(destination: Path, candidate: str, season: str) -> tuple[Path, Path]:
    root = destination / "checkpoints" / candidate
    return root / f"{season}-decisions.csv", root / f"{season}-metadata.json"


def _write_checkpoint(
    paths: tuple[Path, Path],
    *,
    run: CandidateSeasonRun,
    config_hash: str,
) -> None:
    decisions_path, metadata_path = paths
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    run.rows.to_csv(decisions_path, index=False)
    metadata = {
        "schema_version": P4_SCHEMA_VERSION,
        "config_hash": config_hash,
        "candidate": run.candidate.as_dict(),
        "season": run.season,
        "realistic_points": run.realistic_points,
        "hindsight_points": run.hindsight_points,
        "transfers": run.transfers,
        "hit_cost": run.hit_cost,
        "chips_used": run.chips_used,
        "initial_squad_hash": run.initial_squad_hash,
        "decision_rows": len(run.rows),
        "decision_hash": _file_hash(decisions_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_checkpoint(
    paths: tuple[Path, Path],
    *,
    candidate: ConsumerCandidate,
    season: str,
    config_hash: str,
) -> CandidateSeasonRun | None:
    decisions_path, metadata_path = paths
    if not decisions_path.is_file() or not metadata_path.is_file():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("config_hash") != config_hash:
        raise ValueError(f"P4 checkpoint config mismatch: {metadata_path}")
    if metadata.get("candidate") != candidate.as_dict() or metadata.get("season") != season:
        raise ValueError(f"P4 checkpoint identity mismatch: {metadata_path}")
    if metadata.get("decision_hash") != _file_hash(decisions_path):
        raise ValueError(f"P4 checkpoint hash mismatch: {decisions_path}")
    rows = pd.read_csv(decisions_path)
    if len(rows) != int(metadata["decision_rows"]):
        raise ValueError(f"P4 checkpoint row-count mismatch: {decisions_path}")
    return CandidateSeasonRun(
        candidate=candidate,
        season=season,
        rows=rows,
        realistic_points=float(metadata["realistic_points"]),
        hindsight_points=float(metadata["hindsight_points"]),
        transfers=int(metadata["transfers"]),
        hit_cost=int(metadata["hit_cost"]),
        chips_used=int(metadata["chips_used"]),
        initial_squad_hash=str(metadata["initial_squad_hash"]),
    )


def _write_outputs(
    destination: Path,
    *,
    summary: pd.DataFrame,
    decisions: pd.DataFrame,
    acceptance: pd.DataFrame,
    per_gameweek: pd.DataFrame,
    regime_summary: pd.DataFrame,
    config: dict[str, Any],
    config_hash: str,
    historical: pd.DataFrame,
    timestamp: str,
) -> None:
    artifacts = {
        "tournament_summary": summary,
        "gameweek_decisions": decisions,
        "acceptance": acceptance,
        "per_gameweek_comparisons": per_gameweek,
        "regime_summary": regime_summary,
    }
    artifact_manifest = {}
    for name, frame in artifacts.items():
        path = destination / f"{name}.csv"
        frame.to_csv(path, index=False)
        artifact_manifest[name] = {
            "path": str(path),
            "rows": len(frame),
            "sha256": _file_hash(path),
        }
    manifest = {
        "schema_version": P4_SCHEMA_VERSION,
        "status": "complete",
        "generated_at": timestamp,
        "commit_hash": get_git_commit(),
        "configuration_hash": config_hash,
        "configuration": config,
        "historical_data": {
            "path": str(HISTORICAL_PLAYER_GW_PATH),
            "rows": len(historical),
            "sha256": _dataframe_hash(historical),
        },
        "rules": {
            season: build_historical_season_rules(season).rules_version
            for season in config["seasons"]
        },
        "artifacts": artifact_manifest,
        "promotion_warning": (
            "P4 evaluates candidates independently. No production portfolio is changed "
            "until an integrated promotion gate is reviewed."
        ),
    }
    (destination / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_seasons(
    players: pd.DataFrame,
    requested: tuple[str, ...],
) -> tuple[str, ...]:
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("P4 seasons must be non-empty and unique")
    available = {str(value) for value in players["season"].dropna().unique()}
    missing = sorted(set(requested).difference(available))
    if missing:
        raise ValueError(f"P4 historical seasons unavailable: {', '.join(missing)}")
    for season in requested:
        gameweeks = pd.to_numeric(
            players.loc[players["season"].astype(str).eq(season), "gameweek"],
            errors="coerce",
        ).dropna()
        if set(gameweeks.astype(int)) != set(range(1, 39)):
            raise ValueError(f"P4 requires all 38 Gameweeks for {season}")
        build_historical_season_rules(season)
    return requested


def _dataframe_hash(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    order = [column for column in ("season", "gameweek", "player_id") if column in columns]
    ordered = frame[columns].sort_values(order, kind="stable") if order else frame[columns]
    return hashlib.sha256(
        pd.util.hash_pandas_object(ordered, index=False).values.tobytes()
    ).hexdigest()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _filesystem_timestamp(value: str) -> str:
    return value.replace(":", "").replace("-", "").replace(".", "").replace("Z", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the P4 consumer model tournament.")
    parser.add_argument("--stage", choices=P4_STAGES, default="screening")
    parser.add_argument("--seasons", nargs="+", default=list(DEFAULT_SEASONS))
    parser.add_argument("--candidates", nargs="+")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--champion-artifacts", nargs="+", type=Path, default=[])
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_consumer_tournament(
        stage=args.stage,
        seasons=tuple(args.seasons),
        candidate_names=tuple(args.candidates) if args.candidates else None,
        output_dir=args.output_dir,
        resume=args.resume,
        champion_artifact_dirs=tuple(args.champion_artifacts),
    )
    print(result.summary.to_string(index=False))
    print("\nP4 acceptance")
    print(result.acceptance.to_string(index=False))
    print(f"\nArtifacts: {result.output_dir}")


if __name__ == "__main__":
    main()
