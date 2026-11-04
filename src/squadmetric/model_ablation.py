"""Multi-season ablation and validation infrastructure.

This module provides the stable evaluation contract that M2/M3 variants must
use: the same seasons,
strategies, captaincy tracks, regime definitions, DC applicability states, and
acceptance bar.

To add a future variant, register an :class:`AblationVariant` with a unique name
and a runner that accepts the same arguments as ``run_season_benchmark``. The
runner may select a different feature/model configuration, but it must return a
``SeasonBenchmarkResult`` so the comparison remains apples-to-apples.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from squadmetric.season_benchmark import (
    CHIP_MODE_NONE,
    DEFAULT_BENCHMARK_SEASONS,
    DEFAULT_MODEL,
    HISTORY_PATH,
    OPTIMIZER_VERSION,
    BenchmarkStrategy,
    DeterministicTransferStrategy,
    NoTransfersStrategy,
    SeasonBenchmarkResult,
    append_decision_rows_to_history,
    append_result_to_history,
    get_git_commit,
    run_season_benchmark,
)

SUPPORTED_VALIDATION_SEASONS = tuple(DEFAULT_BENCHMARK_SEASONS)
DC_RULE_START_SEASON = "2025-26"
DC_COLUMNS = (
    "clearances_blocks_interceptions",
    "defensive_contribution",
    "recoveries",
    "tackles",
)
DC_STATES = ("not_applicable", "insufficient_data", "evaluated")
REGIMES = ("blank", "double", "post_transfer", "no_recent_transfer")

BenchmarkRunner = Callable[..., SeasonBenchmarkResult]
DCState = Literal["not_applicable", "insufficient_data", "evaluated", "not_required"]


@dataclass(frozen=True)
class AblationVariant:
    """A named, reproducible benchmark configuration."""

    name: str
    description: str
    runner: BenchmarkRunner = run_season_benchmark
    dc_dependent: bool = False


class AblationRegistry:
    """Extensible registry for named model/feature variants."""

    def __init__(self, variants: Iterable[AblationVariant] = ()) -> None:
        self._variants: dict[str, AblationVariant] = {}
        for variant in variants:
            self.register(variant)

    def register(self, variant: AblationVariant, *, replace: bool = False) -> None:
        if variant.name in self._variants and not replace:
            raise ValueError(f"Ablation variant already registered: {variant.name}")
        self._variants[variant.name] = variant

    def get(self, name: str) -> AblationVariant:
        try:
            return self._variants[name]
        except KeyError as exc:
            raise KeyError(f"Unknown ablation variant: {name}") from exc

    def values(self) -> tuple[AblationVariant, ...]:
        return tuple(self._variants.values())


BASELINE_VARIANT = AblationVariant(
    name="baseline",
    description=(
        "Current M1.5 system with existing features, transfer logic, and both captaincy tracks."
    ),
)


def run_minutes_v2_benchmark(*args: Any, **kwargs: Any) -> SeasonBenchmarkResult:
    """Run the benchmark with the M2 three-band conditional expectation model."""
    kwargs["minutes_mode"] = "conditional_bands"
    return run_season_benchmark(*args, **kwargs)


MINUTES_V2_VARIANT = AblationVariant(
    name="baseline+minutes_v2",
    description=(
        "M1.5 system with three-class minutes probabilities and band-specific "
        "conditional point expectations; transfer and captaincy logic unchanged."
    ),
    runner=run_minutes_v2_benchmark,
)


def run_xg_xa_benchmark(*args: Any, **kwargs: Any) -> SeasonBenchmarkResult:
    """Run the xG/xA candidate directly from the accepted baseline."""
    kwargs["feature_mode"] = "xg_xa"
    return run_season_benchmark(*args, **kwargs)


XG_XA_VARIANT = AblationVariant(
    name="baseline+xg_xa",
    description=(
        "Accepted M1.5 baseline with strictly lagged xG/xA and xGI-per-90 features; "
        "original binary minutes, transfer, and captaincy logic retained."
    ),
    runner=run_xg_xa_benchmark,
)


def run_component_benchmark(*args: Any, **kwargs: Any) -> SeasonBenchmarkResult:
    """Run the M7 component projection candidate on the xG/xA feature set."""

    kwargs["projection_mode"] = "components"
    kwargs["feature_mode"] = "xg_xa"
    return run_season_benchmark(*args, **kwargs)


COMPONENT_VARIANT = AblationVariant(
    name="baseline+xg_xa+components",
    description=(
        "M7 component projection layered on the lagged xG/xA variant; "
        "rule-aware scoring and existing transfer/captaincy logic retained."
    ),
    runner=run_component_benchmark,
)


def run_dc_benchmark(*args: Any, **kwargs: Any) -> SeasonBenchmarkResult:
    """Run the DC feature mode when a DC-applicable season is supplied."""
    kwargs["feature_mode"] = "dc"
    return run_season_benchmark(*args, **kwargs)


DC_VARIANT = AblationVariant(
    name="baseline+dc",
    description=(
        "Accepted baseline with rule-versioned Defensive Contributions features; "
        "wired for 2025-26+ but not applicable to current validation seasons."
    ),
    runner=run_dc_benchmark,
    dc_dependent=True,
)


def default_registry() -> AblationRegistry:
    """Return a fresh registry so callers can add variants without global state."""

    return AblationRegistry(
        (
            BASELINE_VARIANT,
            MINUTES_V2_VARIANT,
            XG_XA_VARIANT,
            COMPONENT_VARIANT,
            DC_VARIANT,
        )
    )


@dataclass(frozen=True)
class AcceptanceDecision:
    variant_name: str
    strategy_name: str
    passed: bool
    validation_status: Literal["provisional", "validated"]
    acceptance_result: Literal["pass", "fail"]
    reason: str
    metrics: dict[str, Any]
    run_id: str | None = None


@dataclass
class MultiSeasonAblationResult:
    """All comparison outputs for one multi-season ablation run."""

    comparison: pd.DataFrame
    regime_breakdown: pd.DataFrame
    dc_states: pd.DataFrame
    season_results: dict[tuple[str, str, str], SeasonBenchmarkResult] = field(default_factory=dict)
    run_id: str | None = None
    history_path: Path | None = None
    decision_history_path: Path | None = None


def dc_data_state(
    players: pd.DataFrame,
    season: str,
    variant: AblationVariant,
) -> tuple[DCState, str]:
    """Return explicit DC applicability state and an auditable explanation."""

    if not variant.dc_dependent:
        return "not_required", "Variant does not depend on Defensive Contributions data."
    if season < DC_RULE_START_SEASON:
        return "not_applicable", f"{season} predates the DC scoring rule ({DC_RULE_START_SEASON})."

    season_rows = players[players["season"] == season]
    missing = [column for column in DC_COLUMNS if column not in season_rows.columns]
    if missing:
        return "insufficient_data", f"Missing DC columns: {', '.join(missing)}."
    if season_rows[list(DC_COLUMNS)].notna().any(axis=1).sum() == 0:
        return "insufficient_data", "DC columns exist but contain no usable observations."
    return "evaluated", "All required DC columns have usable observations."


def gameweek_regimes(players: pd.DataFrame, season: str) -> pd.DataFrame:
    """Classify blank/double gameweeks from the existing aggregated player rows."""

    season_rows = players[players["season"] == season]
    rows: list[dict[str, Any]] = []
    for gameweek, frame in season_rows.groupby("gameweek", sort=True):
        opponent_text = frame["opponent_team"].astype(str)
        is_double = bool(
            frame["home_or_away"].eq("M").any()
            or opponent_text.str.contains(r"\+", regex=True).any()
        )
        rows.append(
            {
                "season": season,
                "gameweek": int(gameweek),
                "is_blank_gameweek": frame["team"].nunique() < 20,
                "is_double_gameweek": is_double,
            }
        )
    return pd.DataFrame(rows)


def build_regime_breakdown(
    result: SeasonBenchmarkResult,
    players: pd.DataFrame,
    *,
    variant_name: str,
) -> pd.DataFrame:
    """Summarize benchmark points in the required edge-case regimes."""

    rows = result.rows.merge(gameweek_regimes(players, result.season), on="gameweek", how="left")
    rows["post_transfer"] = rows["transfers_made"].astype(int).gt(0)
    masks = {
        "blank": rows["is_blank_gameweek"],
        "double": rows["is_double_gameweek"],
        "post_transfer": rows["post_transfer"],
        "no_recent_transfer": ~rows["post_transfer"],
    }
    output: list[dict[str, Any]] = []
    for regime, mask in masks.items():
        selected = rows[mask].copy()
        output.append(
            {
                "variant_name": variant_name,
                "season": result.season,
                "strategy_name": result.strategy_name,
                "regime": regime,
                "gameweek_count": len(selected),
                "gameweeks": "+".join(str(value) for value in selected["gameweek"]),
                "hindsight_points": float(selected["net_points"].sum()),
                "realistic_points": float(selected["realistic_net_points"].sum()),
                "average_realistic_points": (
                    float(selected["realistic_net_points"].mean()) if not selected.empty else np.nan
                ),
            }
        )
    return pd.DataFrame(output)


def run_multi_season_ablation(
    players: pd.DataFrame,
    *,
    seasons: Sequence[str] = SUPPORTED_VALIDATION_SEASONS,
    strategies: Sequence[BenchmarkStrategy] | None = None,
    registry: AblationRegistry | None = None,
    variant_names: Sequence[str] | None = None,
    model_name: str = DEFAULT_MODEL,
    max_free_transfers: int | None = None,
    persist: bool = False,
    history_path: Path | None = None,
    run_id: str | None = None,
    commit_hash: str | None = None,
    optimizer_version: str = OPTIMIZER_VERSION,
    chip_mode: str = CHIP_MODE_NONE,
) -> MultiSeasonAblationResult:
    """Run registered variants and optionally persist one canonical suite."""

    if history_path is not None and not persist:
        raise ValueError("history_path requires persist=True")
    if persist:
        history_path = history_path or HISTORY_PATH
        run_id = run_id or uuid.uuid4().hex
        commit_hash = commit_hash or get_git_commit()

    registry = registry or default_registry()
    variants = (
        [registry.get(name) for name in variant_names]
        if variant_names
        else list(registry.values())
    )
    selected_strategies = list(
        strategies or (NoTransfersStrategy(), DeterministicTransferStrategy())
    )
    comparison_rows: list[dict[str, Any]] = []
    regime_frames: list[pd.DataFrame] = []
    dc_rows: list[dict[str, Any]] = []
    season_results: dict[tuple[str, str, str], SeasonBenchmarkResult] = {}

    for variant in variants:
        prediction_cache: dict[
            tuple[str, int, str, str, str, str], tuple[pd.DataFrame, pd.DataFrame]
        ] = {}
        captain_prediction_cache: dict[
            tuple[str, int, str, str, str], pd.DataFrame
        ] = {}
        future_prediction_cache: dict[
            tuple[str, int, str, str, str, str], dict[int, pd.DataFrame]
        ] = {}
        for season in seasons:
            dc_status, dc_reason = dc_data_state(players, season, variant)
            dc_rows.append(
                {
                    "variant_name": variant.name,
                    "season": season,
                    "dc_status": dc_status,
                    "dc_reason": dc_reason,
                }
            )
            for strategy in selected_strategies:
                base_row = {
                    "variant_name": variant.name,
                    "variant_description": variant.description,
                    "season": season,
                    "strategy_name": strategy.name,
                    "strategy_version": strategy.version,
                    "dc_status": dc_status,
                    "dc_reason": dc_reason,
                    "validation_status": "provisional",
                    "acceptance_result": "not_evaluated",
                }
                if variant.dc_dependent and dc_status != "evaluated":
                    comparison_rows.append(
                        {
                            **base_row,
                            "hindsight_points": np.nan,
                            "realistic_points": np.nan,
                            "captaincy_gap": np.nan,
                            "transfers_made": np.nan,
                            "total_hit_cost": np.nan,
                        }
                    )
                    continue

                benchmark_result = variant.runner(
                    players,
                    season,
                    strategy,
                    model_name=model_name,
                    max_free_transfers=max_free_transfers,
                    chip_mode=chip_mode,
                    prediction_cache=prediction_cache,
                    captain_prediction_cache=captain_prediction_cache,
                    future_prediction_cache=future_prediction_cache,
                )
                key = (variant.name, season, strategy.name)
                season_results[key] = benchmark_result
                comparison_rows.append(
                    {
                        **base_row,
                        "hindsight_points": benchmark_result.total_points,
                        "realistic_points": benchmark_result.realistic_total_points,
                        "captaincy_gap": benchmark_result.realistic_captaincy_gap,
                        "transfers_made": benchmark_result.transfers_made,
                        "total_hit_cost": benchmark_result.total_hit_cost,
                    }
                )
                regime_frames.append(
                    build_regime_breakdown(
                        benchmark_result,
                        players,
                        variant_name=variant.name,
                    )
                )

    if persist:
        assert history_path is not None
        assert run_id is not None
        decision_history_path: Path | None = None
        for variant_name, season, strategy_name in season_results:
            result = season_results[(variant_name, season, strategy_name)]
            append_result_to_history(
                result,
                history_path=history_path,
                variant_name=variant_name,
                run_id=run_id,
                commit_hash=commit_hash or "unavailable",
                optimizer_version=optimizer_version,
            )
            decision_history_path = append_decision_rows_to_history(
                result,
                history_path=history_path,
                variant_name=variant_name,
                run_id=run_id,
                commit_hash=commit_hash or "unavailable",
            )
    else:
        decision_history_path = None

    return MultiSeasonAblationResult(
        comparison=pd.DataFrame(comparison_rows),
        regime_breakdown=(
            pd.concat(regime_frames, ignore_index=True)
            if regime_frames
            else pd.DataFrame()
        ),
        dc_states=pd.DataFrame(dc_rows),
        season_results=season_results,
        run_id=run_id,
        history_path=history_path if persist else None,
        decision_history_path=decision_history_path,
    )


def evaluate_acceptance_bar(
    result: MultiSeasonAblationResult,
    variant_name: str,
    *,
    strategy_name: str = "deterministic-single-transfer",
    baseline_name: str = "baseline",
    severe_regression_fraction: float = 0.10,
    history_path: Path | None = None,
    run_id: str | None = None,
) -> AcceptanceDecision:
    """Apply the M1.75 acceptance bar and optionally update history status."""

    effective_history_path = history_path or result.history_path
    effective_run_id = run_id or result.run_id
    comparison = result.comparison
    variant_rows = comparison[
        (comparison["variant_name"] == variant_name)
        & (comparison["strategy_name"] == strategy_name)
    ]
    baseline_rows = comparison[
        (comparison["variant_name"] == baseline_name)
        & (comparison["strategy_name"] == strategy_name)
    ]
    if variant_rows.empty or baseline_rows.empty:
        decision = _failed_decision(
            variant_name,
            strategy_name,
            "Acceptance bar cannot run: variant or baseline rows are missing.",
        )
        if effective_history_path:
            update_history_validation_status(
                effective_history_path, decision, run_id=effective_run_id
            )
        return decision

    dc_dependent = variant_rows["dc_status"].ne("not_required").any()
    evaluated_seasons: list[str] = []
    reasons: list[str] = []
    season_deltas: dict[str, float] = {}
    for season in sorted(variant_rows["season"].unique()):
        variant_row = variant_rows[variant_rows["season"] == season].iloc[0]
        baseline_row = baseline_rows[baseline_rows["season"] == season]
        if baseline_row.empty:
            reasons.append(f"{season}: baseline row missing")
            continue
        dc_status = str(variant_row["dc_status"])
        if dc_dependent and dc_status == "not_applicable":
            reasons.append(f"{season}: DC variant legitimately not applicable")
            continue
        if dc_dependent and dc_status != "evaluated":
            reasons.append(f"{season}: DC state is {dc_status}, not evaluated")
            continue
        evaluated_seasons.append(season)
        delta = float(variant_row["realistic_points"]) - float(
            baseline_row.iloc[0]["realistic_points"]
        )
        season_deltas[season] = delta
        if delta < 0:
            reasons.append(f"{season}: realistic track regressed by {delta:.2f} points")

    aggregate_delta = float(sum(season_deltas.values()))
    if evaluated_seasons and aggregate_delta <= 0:
        reasons.append(
            f"aggregate realistic improvement is {aggregate_delta:.2f}, not positive"
        )
    if not evaluated_seasons:
        reasons.append("no applicable evaluated seasons remain")

    regime_deltas: dict[str, float] = {}
    variant_regimes = result.regime_breakdown[
        (result.regime_breakdown["variant_name"] == variant_name)
        & (result.regime_breakdown["strategy_name"] == strategy_name)
    ]
    baseline_regimes = result.regime_breakdown[
        (result.regime_breakdown["variant_name"] == baseline_name)
        & (result.regime_breakdown["strategy_name"] == strategy_name)
    ]
    for _, row in variant_regimes.iterrows():
        if row["regime"] not in ("blank", "double") or row["season"] not in evaluated_seasons:
            continue
        baseline_row = baseline_regimes[
            (baseline_regimes["season"] == row["season"])
            & (baseline_regimes["regime"] == row["regime"])
        ]
        if baseline_row.empty or int(baseline_row.iloc[0]["gameweek_count"]) == 0:
            continue
        baseline_points = float(baseline_row.iloc[0]["realistic_points"])
        variant_points = float(row["realistic_points"])
        delta = variant_points - baseline_points
        regime_deltas[f"{row['season']}:{row['regime']}"] = delta
        if baseline_points > 0 and variant_points < baseline_points * (
            1 - severe_regression_fraction
        ):
            reasons.append(
                f"{row['season']} {row['regime']} regime declined by more than "
                f"{severe_regression_fraction:.0%}"
            )

    passed = not reasons or all(
        "legitimately not applicable" in reason for reason in reasons
    )
    # Positive aggregate improvement and a complete evaluated comparison are
    # mandatory unless every skipped season is explicitly not_applicable.
    if not evaluated_seasons or aggregate_delta <= 0:
        passed = False
    if any(
        "regressed" in reason
        or "not evaluated" in reason
        or "more than" in reason
        or "missing" in reason
        for reason in reasons
    ):
        passed = False
    if not reasons:
        reasons.append("All realistic-track, aggregate, and blank/double-regime checks passed.")

    decision = AcceptanceDecision(
        variant_name=variant_name,
        strategy_name=strategy_name,
        passed=passed,
        validation_status="validated" if passed else "provisional",
        acceptance_result="pass" if passed else "fail",
        reason=" ".join(reasons),
        metrics={
            "evaluated_seasons": evaluated_seasons,
            "season_realistic_deltas": season_deltas,
            "aggregate_realistic_delta": aggregate_delta,
            "regime_realistic_deltas": regime_deltas,
            "severe_regression_fraction": severe_regression_fraction,
        },
        run_id=effective_run_id,
    )
    if effective_history_path:
        update_history_validation_status(
            effective_history_path, decision, run_id=effective_run_id
        )
    return decision


def evaluate_strategy_acceptance_bar(
    result: MultiSeasonAblationResult,
    variant_name: str,
    *,
    candidate_strategy_name: str = "two-gameweek-lookahead",
    control_strategy_name: str = "deterministic-single-transfer",
    severe_regression_fraction: float = 0.10,
    history_path: Path | None = None,
    run_id: str | None = None,
) -> AcceptanceDecision:
    """Evaluate a transfer strategy against a control under one fixed variant."""

    effective_history_path = history_path or result.history_path
    effective_run_id = run_id or result.run_id
    comparison = result.comparison
    candidate_rows = comparison[
        (comparison["variant_name"] == variant_name)
        & (comparison["strategy_name"] == candidate_strategy_name)
    ]
    control_rows = comparison[
        (comparison["variant_name"] == variant_name)
        & (comparison["strategy_name"] == control_strategy_name)
    ]
    reasons: list[str] = []
    season_deltas: dict[str, float] = {}
    evaluated_seasons: list[str] = []

    for season in sorted(candidate_rows["season"].unique()):
        candidate_row = candidate_rows[candidate_rows["season"] == season]
        control_row = control_rows[control_rows["season"] == season]
        if candidate_row.empty or control_row.empty:
            reasons.append(f"{season}: candidate or control row missing")
            continue
        evaluated_seasons.append(season)
        delta = float(candidate_row.iloc[0]["realistic_points"]) - float(
            control_row.iloc[0]["realistic_points"]
        )
        season_deltas[season] = delta
        if delta < 0:
            reasons.append(f"{season}: realistic track regressed by {delta:.2f} points")

    aggregate_delta = float(sum(season_deltas.values()))
    if not evaluated_seasons:
        reasons.append("no evaluated seasons remain")
    elif aggregate_delta <= 0:
        reasons.append(
            f"aggregate realistic improvement is {aggregate_delta:.2f}, not positive"
        )

    regime_deltas: dict[str, float] = {}
    candidate_regimes = result.regime_breakdown[
        (result.regime_breakdown["variant_name"] == variant_name)
        & (result.regime_breakdown["strategy_name"] == candidate_strategy_name)
    ]
    control_regimes = result.regime_breakdown[
        (result.regime_breakdown["variant_name"] == variant_name)
        & (result.regime_breakdown["strategy_name"] == control_strategy_name)
    ]
    for _, candidate_regime in candidate_regimes.iterrows():
        if (
            candidate_regime["regime"] not in ("blank", "double")
            or candidate_regime["season"] not in evaluated_seasons
        ):
            continue
        control_regime = control_regimes[
            (control_regimes["season"] == candidate_regime["season"])
            & (control_regimes["regime"] == candidate_regime["regime"])
        ]
        if control_regime.empty or int(control_regime.iloc[0]["gameweek_count"]) == 0:
            continue
        delta = float(candidate_regime["realistic_points"]) - float(
            control_regime.iloc[0]["realistic_points"]
        )
        key = f"{candidate_regime['season']}:{candidate_regime['regime']}"
        regime_deltas[key] = delta
        control_points = float(control_regime.iloc[0]["realistic_points"])
        candidate_points = float(candidate_regime["realistic_points"])
        if control_points > 0 and candidate_points < control_points * (
            1 - severe_regression_fraction
        ):
            reasons.append(
                f"{key} regime declined by more than {severe_regression_fraction:.0%}"
            )

    passed = bool(evaluated_seasons and aggregate_delta > 0 and not reasons)
    if not reasons:
        reasons.append("All strategy realistic-track and regime checks passed.")
    decision = AcceptanceDecision(
        variant_name=variant_name,
        strategy_name=candidate_strategy_name,
        passed=passed,
        validation_status="validated" if passed else "provisional",
        acceptance_result="pass" if passed else "fail",
        reason=" ".join(reasons),
        metrics={
            "candidate_strategy": candidate_strategy_name,
            "control_strategy": control_strategy_name,
            "evaluated_seasons": evaluated_seasons,
            "season_realistic_deltas": season_deltas,
            "aggregate_realistic_delta": aggregate_delta,
            "regime_realistic_deltas": regime_deltas,
            "severe_regression_fraction": severe_regression_fraction,
        },
        run_id=effective_run_id,
    )
    if effective_history_path:
        update_history_validation_status(
            effective_history_path, decision, run_id=effective_run_id
        )
    return decision


def _failed_decision(
    variant_name: str,
    strategy_name: str,
    reason: str,
) -> AcceptanceDecision:
    return AcceptanceDecision(
        variant_name=variant_name,
        strategy_name=strategy_name,
        passed=False,
        validation_status="provisional",
        acceptance_result="fail",
        reason=reason,
        metrics={},
    )


def update_history_validation_status(
    history_path: Path,
    decision: AcceptanceDecision,
    *,
    run_id: str | None = None,
) -> int:
    """Update matching history rows without inventing results for missing runs."""

    if not history_path.exists():
        return 0
    from squadmetric.season_benchmark import HISTORY_COLUMNS

    history = pd.read_csv(history_path)
    effective_run_id = run_id or decision.run_id
    if not effective_run_id:
        raise ValueError("run_id is required for a scoped history status update")
    defaults = {
        "variant_name": "baseline",
        "acceptance_result": "",
        "acceptance_reason": "",
        "validation_status": "provisional",
    }
    for column in HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = defaults.get(column, pd.NA)
    for column in (
        "run_id",
        "commit_hash",
        "optimizer_version",
        "variant_name",
        "acceptance_result",
        "acceptance_reason",
        "validation_status",
    ):
        history[column] = history[column].astype("object")
    mask = (
        (history["run_id"] == effective_run_id)
        & (history["variant_name"] == decision.variant_name)
        & (history["strategy_name"] == decision.strategy_name)
    )
    updated = int(mask.sum())
    history.loc[mask, "validation_status"] = decision.validation_status
    history.loc[mask, "acceptance_result"] = decision.acceptance_result
    history.loc[mask, "acceptance_reason"] = decision.reason
    history.to_csv(history_path, index=False)
    return updated
