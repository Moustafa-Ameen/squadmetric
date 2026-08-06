"""Read-only, reproducible historical FPL season simulations.

Unlike the permanent benchmark CLI, this command never appends to accepted
benchmark history. Each run writes isolated artifacts under
``data/processed/simulations`` unless an explicit output directory is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fpl_intelligence.chip_simulation import (
    CHIP_MODE_BEAM,
    CHIP_MODE_NONE,
)
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.season_benchmark import (
    HISTORICAL_PLAYER_GW_PATH,
    DeterministicTransferStrategy,
    NoTransfersStrategy,
    SeasonBenchmarkResult,
    get_git_commit,
    run_season_benchmark,
)
from fpl_intelligence.season_rules import build_historical_season_rules
from fpl_intelligence.step4_models import load_historical_player_gameweeks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "simulations"
DEFAULT_SEASONS = ("2023-24", "2024-25", "2025-26")
SIMULATION_SCHEMA_VERSION = "pdc-performance-recovery-simulation-v3"
PRODUCTION_INITIAL_SQUAD_POLICY = "horizon_8_flexible_cold_start_safe"
CONTROL_INITIAL_SQUAD_POLICY = "identity_safe_value"
PRODUCTION_INITIAL_SQUAD_VERSION = "p3-opening-milp-v2-cold-start-safe"


@dataclass(frozen=True)
class SimulationPreset:
    name: str
    portfolio_mode: str
    strategy: str
    chip_mode: str
    minutes_mode: str = "binary"
    feature_mode: str = "baseline"
    projection_mode: str = "total_points"
    hit_policy: str = "current_gw"
    initial_squad_policy: str = CONTROL_INITIAL_SQUAD_POLICY


PRESETS = {
    "production": SimulationPreset(
        name="production",
        portfolio_mode="r2_validated",
        strategy="deterministic-single-transfer",
        chip_mode=CHIP_MODE_BEAM,
        initial_squad_policy=PRODUCTION_INITIAL_SQUAD_POLICY,
    ),
    "control": SimulationPreset(
        name="control",
        portfolio_mode="m8_control",
        strategy="deterministic-single-transfer",
        chip_mode=CHIP_MODE_BEAM,
        initial_squad_policy=CONTROL_INITIAL_SQUAD_POLICY,
    ),
    "no-chip": SimulationPreset(
        name="no-chip",
        portfolio_mode="r2_validated",
        strategy="deterministic-single-transfer",
        chip_mode=CHIP_MODE_NONE,
        initial_squad_policy=PRODUCTION_INITIAL_SQUAD_POLICY,
    ),
    "diagnostic-no-transfers": SimulationPreset(
        name="diagnostic-no-transfers",
        portfolio_mode="m8_control",
        strategy="no-transfers",
        chip_mode=CHIP_MODE_NONE,
        initial_squad_policy=CONTROL_INITIAL_SQUAD_POLICY,
    ),
}


def run_historical_simulation(
    *,
    seasons: tuple[str, ...] = DEFAULT_SEASONS,
    preset_name: str = "production",
    output_dir: Path | None = None,
    verbose: bool = False,
    generated_at: str | None = None,
    players: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Run isolated season simulations and persist their complete artifacts."""

    preset = _preset(preset_name)
    historical = (
        players.copy()
        if players is not None
        else load_historical_player_gameweeks(HISTORICAL_PLAYER_GW_PATH)
    )
    selected_seasons = _validate_seasons(historical, seasons)
    portfolio = get_production_portfolio(preset.portfolio_mode)
    strategy = (
        DeterministicTransferStrategy()
        if preset.strategy == "deterministic-single-transfer"
        else NoTransfersStrategy()
    )
    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    dataset_hash = _dataframe_hash(historical)
    config = {
        **asdict(preset),
        "seasons": list(selected_seasons),
        "portfolio_version": portfolio.version,
        "projection_portfolio": portfolio.projections.as_dict(),
    }
    simulation_key = _stable_hash(
        {
            "schema_version": SIMULATION_SCHEMA_VERSION,
            "dataset_hash": dataset_hash,
            "config": config,
        }
    )[:16]
    destination = output_dir or (
        DEFAULT_OUTPUT_ROOT
        / f"{_filesystem_timestamp(timestamp)}-{preset.name}-{simulation_key[:8]}"
    )
    _validate_output_directory(destination)

    results: list[SeasonBenchmarkResult] = []
    for season in selected_seasons:
        print(f"Simulating {season} with preset '{preset.name}'...")
        initial_squad, initial_mode, initial_version = _initial_squad_for_preset(
            historical,
            season,
            policy=preset.initial_squad_policy,
            model_name=portfolio.projections.transfer_model,
        )
        result = run_season_benchmark(
            historical,
            season,
            strategy,
            model_name=portfolio.projections.transfer_model,
            model_version=portfolio.version,
            minutes_mode=preset.minutes_mode,
            feature_mode=preset.feature_mode,
            projection_mode=preset.projection_mode,
            chip_mode=preset.chip_mode,
            hit_policy=preset.hit_policy,
            projection_portfolio=portfolio.projections,
            initial_squad_override=initial_squad,
            initial_squad_mode=initial_mode,
            initial_squad_version=initial_version,
            verbose=verbose,
        )
        results.append(result)
        print(
            f"  {result.realistic_total_points:.0f} realistic points | "
            f"{result.transfers_made} transfers | -{result.total_hit_cost} hits | "
            f"{result.chips_used} chips"
        )

    destination.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    summary = _season_summary(results)
    decisions = _decision_rows(results, run_id=run_id, simulation_key=simulation_key)
    summary_path = destination / "season_summary.csv"
    decisions_path = destination / "gameweek_decisions.csv"
    manifest_path = destination / "run_manifest.json"
    summary.to_csv(summary_path, index=False)
    decisions.to_csv(decisions_path, index=False)
    manifest = {
        "schema_version": SIMULATION_SCHEMA_VERSION,
        "status": "complete",
        "run_id": run_id,
        "simulation_key": simulation_key,
        "generated_at": timestamp,
        "commit_hash": get_git_commit(),
        "source_data": {
            "path": str(HISTORICAL_PLAYER_GW_PATH),
            "sha256": dataset_hash,
            "rows": int(len(historical)),
            "available_seasons": sorted(
                str(value) for value in historical["season"].dropna().unique()
            ),
        },
        "configuration": config,
        "rules": {
            season: {
                "rules_version": build_historical_season_rules(season).rules_version,
                "chip_count": len(build_historical_season_rules(season).chips),
            }
            for season in selected_seasons
        },
        "artifacts": {
            "season_summary": {
                "path": str(summary_path),
                "sha256": _file_hash(summary_path),
                "rows": int(len(summary)),
            },
            "gameweek_decisions": {
                "path": str(decisions_path),
                "sha256": _file_hash(decisions_path),
                "rows": int(len(decisions)),
            },
        },
        "warning": (
            "Historical realistic points are a decision-quality benchmark, "
            "not a guaranteed live score or rank."
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _print_summary(summary, destination)
    return {
        "manifest": manifest,
        "summary": summary,
        "decisions": decisions,
        "output_dir": destination,
    }


def _season_summary(results: list[SeasonBenchmarkResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        realistic_chip_gain = float(
            pd.to_numeric(
                result.rows.get("realistic_chip_realized_gain", pd.Series(dtype=float)),
                errors="coerce",
            )
            .fillna(0.0)
            .sum()
        )
        chip_rows = result.rows[
            result.rows.get("chip_selected", pd.Series(False, index=result.rows.index))
            .fillna(False)
            .astype(bool)
        ]
        chip_sequence = ";".join(
            f"GW{int(row.gameweek)}:{row.chip_used}" for row in chip_rows.itertuples(index=False)
        )
        rows.append(
            {
                "season": result.season,
                "realistic_points": result.realistic_total_points,
                "realistic_gross_points": result.realistic_gross_points,
                "hindsight_points": result.total_points,
                "captaincy_gap": result.realistic_captaincy_gap,
                "transfers": result.transfers_made,
                "hit_cost": result.total_hit_cost,
                "chips_used": result.chips_used,
                "realistic_chip_gain": round(realistic_chip_gain, 2),
                "chip_sequence": chip_sequence,
                "initial_bank": result.initial_bank,
                "final_bank": result.final_bank,
                "initial_squad_mode": result.initial_squad_mode,
                "initial_squad_version": result.initial_squad_version,
                "initial_squad_hash": (
                    str(result.rows["initial_squad_hash"].iloc[0])
                    if (
                        not result.rows.empty
                        and "initial_squad_hash" in result.rows
                    )
                    else ""
                ),
                "rules_version": build_historical_season_rules(result.season).rules_version,
            }
        )
    return pd.DataFrame(rows)


def _initial_squad_for_preset(
    players: pd.DataFrame,
    season: str,
    *,
    policy: str,
    model_name: str,
) -> tuple[pd.DataFrame | None, str, str]:
    if policy == CONTROL_INITIAL_SQUAD_POLICY:
        from fpl_intelligence.backtest_transfer_strategy import build_initial_squad
        from fpl_intelligence.preseason import (
            IDENTITY_SAFE_INITIAL_SQUAD_MODE,
            IDENTITY_SAFE_INITIAL_SQUAD_VERSION,
        )

        prior_seasons = sorted(
            str(value)
            for value in players["season"].dropna().unique()
            if str(value) < season
        )
        squad = build_initial_squad(
            players,
            season=season,
            prior_season=prior_seasons[-1] if prior_seasons else None,
        )
        return (
            squad,
            IDENTITY_SAFE_INITIAL_SQUAD_MODE,
            IDENTITY_SAFE_INITIAL_SQUAD_VERSION,
        )
    if policy != PRODUCTION_INITIAL_SQUAD_POLICY:
        raise ValueError(f"Unsupported initial-squad policy: {policy}")

    prior_seasons = sorted(
        str(value)
        for value in players["season"].dropna().unique()
        if str(value) < season
    )
    if not prior_seasons:
        fallback_squad, _, fallback_version = _initial_squad_for_preset(
            players,
            season,
            policy=CONTROL_INITIAL_SQUAD_POLICY,
            model_name=model_name,
        )
        return (
            fallback_squad,
            f"{PRODUCTION_INITIAL_SQUAD_POLICY}:identity_safe_fallback",
            fallback_version,
        )

    from fpl_intelligence.initial_squad_championship import (
        P3_CONFIGS,
        build_opening_projection_bundle,
        optimize_opening_squad,
    )

    bundle = build_opening_projection_bundle(
        players,
        season,
        model_name=model_name,
    )
    candidate = optimize_opening_squad(
        bundle,
        P3_CONFIGS["horizon_8_flexible"],
    )
    return (
        candidate.squad,
        PRODUCTION_INITIAL_SQUAD_POLICY,
        PRODUCTION_INITIAL_SQUAD_VERSION,
    )


def _decision_rows(
    results: list[SeasonBenchmarkResult],
    *,
    run_id: str,
    simulation_key: str,
) -> pd.DataFrame:
    frames = []
    for result in results:
        rows = result.rows.copy()
        rows.insert(0, "run_id", run_id)
        rows.insert(1, "simulation_key", simulation_key)
        rows.insert(2, "strategy_version", result.strategy_version)
        rows.insert(3, "model_version", result.model_version)
        frames.append(rows)
    return pd.concat(frames, ignore_index=True, sort=False)


def _validate_seasons(
    players: pd.DataFrame,
    requested: tuple[str, ...],
) -> tuple[str, ...]:
    if not requested:
        raise ValueError("At least one season is required")
    if len(set(requested)) != len(requested):
        raise ValueError("Requested seasons must not contain duplicates")
    available = {
        str(value) for value in players.get("season", pd.Series(dtype=str)).dropna().unique()
    }
    missing = sorted(set(requested).difference(available))
    if missing:
        raise ValueError(
            "Historical data is unavailable for: "
            + ", ".join(missing)
            + ". Available seasons: "
            + ", ".join(sorted(available))
        )
    for season in requested:
        build_historical_season_rules(season)
        gameweeks = pd.to_numeric(
            players.loc[players["season"].astype(str) == season, "gameweek"],
            errors="coerce",
        ).dropna()
        if gameweeks.empty or int(gameweeks.min()) != 1:
            raise ValueError(f"{season} does not contain a complete GW1 starting point")
    return tuple(requested)


def _preset(name: str) -> SimulationPreset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown preset {name!r}; choose from {', '.join(sorted(PRESETS))}"
        ) from exc


def _validate_output_directory(path: Path) -> None:
    if path.exists():
        raise FileExistsError(
            f"Simulation output already exists: {path}. Choose a new --output-dir."
        )
    if path.parent.exists() and not path.parent.is_dir():
        raise NotADirectoryError(f"Simulation output parent is not a directory: {path.parent}")


def _dataframe_hash(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    ordered = frame[columns].sort_values(
        [column for column in ("season", "gameweek", "player_id") if column in columns],
        kind="stable",
    )
    values = pd.util.hash_pandas_object(ordered, index=False).values.tobytes()
    return hashlib.sha256(values).hexdigest()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filesystem_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _print_summary(summary: pd.DataFrame, destination: Path) -> None:
    print("\nRealistic historical score")
    print(
        summary[
            [
                "season",
                "realistic_points",
                "transfers",
                "hit_cost",
                "chips_used",
                "realistic_chip_gain",
            ]
        ].to_string(index=False)
    )
    print(f"\nArtifacts: {destination}")
    print("Permanent benchmark history was not modified.")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate completed FPL seasons without modifying benchmark history."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=list(DEFAULT_SEASONS),
        help="Completed seasons to simulate.",
    )
    parser.add_argument(
        "--preset",
        choices=tuple(PRESETS),
        default="production",
        help="Decision configuration to simulate.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="New directory for isolated simulation artifacts.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    run_historical_simulation(
        seasons=tuple(args.seasons),
        preset_name=args.preset,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
