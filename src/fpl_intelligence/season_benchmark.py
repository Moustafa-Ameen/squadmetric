"""Permanent, realistic season benchmark for comparing FPL strategies.

This harness answers a directional research question: does a transfer strategy
score better than its previous version when evaluated under the same historical
season and FPL constraints? It is not a claim that the result is exactly what a
real manager would have scored.

The simulation uses starting-XI-only scoring, legal formations, basic autosubs,
free-transfer banking, hit costs, budget and club limits, and reports two captaincy
tracks: hindsight-optimal attribution and point-in-time realistic captain/vice
selection. Chips are opt-in through ``chip_mode``; the default no-chip path is
the permanent control and the baseline planner is deliberately provisional.

The strategy interface is deliberately small: a strategy receives the current
squad and only the data available before the target gameweek, then returns a
single legal transfer decision. New strategies can therefore use this harness
without changing scoring, transfer accounting, or result persistence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from fpl_intelligence.availability import (
    AVAILABILITY_FEATURE_COLUMNS,
    M9_MINUTES_FEATURE_COLUMNS,
    AvailabilityEvent,
    add_m9_historical_features,
    build_availability_features,
)
from fpl_intelligence.backtest_transfer_strategy import (
    DEFAULT_GAIN_THRESHOLD,
    FREE_TRANSFER_CAP,
    INITIAL_BUDGET,
    MODEL_BUILDERS,
    TransferDecision,
    build_initial_squad,
    build_preseason_scores,
    choose_transfer,
    resolve_active_lineup,
    score_gameweek,
    select_starting_xi,
    validate_squad,
)
from fpl_intelligence.beam_search import HIT_POLICIES, DeterministicBeamPlanner
from fpl_intelligence.chip_simulation import (
    CHIP_MODE_BASELINE,
    CHIP_MODE_BEAM,
    CHIP_MODE_NONE,
    CHIP_MODES,
    ChipCounterfactual,
    ChipDecision,
    ChipDefinition,
    DeterministicChipPlanner,
    apply_chip,
    apply_chip_to_score,
    apply_squad_transition,
    bench_points_not_autosubbed,
    chip_replaces_ordinary_transfer,
    initial_chip_state,
)
from fpl_intelligence.component_projection import (
    COMPONENT_MODEL_COLUMNS,
    component_feature_columns,
    default_dc_rule_versions,
    fit_component_projection_model,
    score_expected_components,
)
from fpl_intelligence.fixture_scenarios import (
    build_historical_fixture_scenario,
)
from fpl_intelligence.historical_data import load_historical_raw
from fpl_intelligence.player_component_forecast import build_player_fixture_components
from fpl_intelligence.preseason import (
    IDENTITY_SAFE_INITIAL_SQUAD_MODE,
    IDENTITY_SAFE_INITIAL_SQUAD_VERSION,
)
from fpl_intelligence.projection_portfolio import ProjectionPortfolio
from fpl_intelligence.season_rules import build_historical_season_rules
from fpl_intelligence.step4_models import (
    build_minutes_classifier,
    feature_columns_for_mode,
    fit_minutes_band_conditional_model,
    load_historical_player_gameweeks,
)
from fpl_intelligence.team_forecast import fit_team_goal_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_PLAYER_GW_PATH = PROJECT_ROOT / "data" / "processed" / "historical_player_gw.csv"
BOOTSTRAP_PATH = PROJECT_ROOT / "data" / "raw" / "bootstrap-static.json"
HISTORY_PATH = PROJECT_ROOT / "data" / "processed" / "season_benchmark_history.csv"
HISTORICAL_MAX_FREE_TRANSFERS = {
    "2023-24": 2,
    "2024-25": 5,
    "2025-26": 5,
}
DEFAULT_BENCHMARK_SEASONS = ("2023-24", "2024-25")
DEFAULT_MODEL = "Ridge Regression"
DEFAULT_MODEL_VERSION = "local benchmark"
DEFAULT_PROJECTION_MODE = "total_points"
CHIP_MODE_DEFAULT = CHIP_MODE_NONE
PROJECTION_MODES = ("total_points", "components", "m10_team_components")
OPTIMIZER_VERSION = "m3.5-milp-v1"
HISTORY_COLUMNS = [
    "run_timestamp",
    "run_id",
    "commit_hash",
    "optimizer_version",
    "season",
    "strategy_name",
    "strategy_version",
    "model_name",
    "model_version",
    "variant_name",
    "total_points",
    "gross_points",
    "hindsight_total_points",
    "realistic_total_points",
    "realistic_gross_points",
    "captaincy_gap",
    "acceptance_result",
    "acceptance_reason",
    "transfers_made",
    "total_hit_cost",
    "max_free_transfers",
    "initial_bank",
    "final_bank",
    "validation_status",
    "chip_mode",
    "chips_used",
    "chip_points",
    "rules_version",
    "minutes_mode",
    "hit_policy",
]


@dataclass(frozen=True)
class StrategyContext:
    season: str
    gameweek: int
    squad: pd.DataFrame
    predictions: pd.DataFrame
    bank: float
    free_transfers: int
    available_data: pd.DataFrame
    free_transfer_cap: int = FREE_TRANSFER_CAP
    future_predictions: dict[int, pd.DataFrame] = field(default_factory=dict)


class BenchmarkStrategy(Protocol):
    name: str
    version: str

    def decide(self, context: StrategyContext) -> TransferDecision:
        """Return a transfer decision using only ``context.available_data``."""


@dataclass(frozen=True)
class NoTransfersStrategy:
    name: str = "no-transfers"
    version: str = "v1"

    def decide(self, context: StrategyContext) -> TransferDecision:
        del context
        return _empty_decision()


@dataclass(frozen=True)
class DeterministicTransferStrategy:
    gain_threshold: float = DEFAULT_GAIN_THRESHOLD
    name: str = "deterministic-single-transfer"
    version: str = "v1"

    def decide(self, context: StrategyContext) -> TransferDecision:
        return choose_transfer(
            context.squad,
            context.predictions,
            bank=context.bank,
            free_transfers=context.free_transfers,
            gain_threshold=self.gain_threshold,
        )


@dataclass(frozen=True)
class SeasonBenchmarkResult:
    season: str
    strategy_name: str
    strategy_version: str
    model_name: str
    model_version: str
    rows: pd.DataFrame
    initial_squad: pd.DataFrame
    final_squad: pd.DataFrame
    total_points: float
    gross_points: float
    realistic_total_points: float
    realistic_gross_points: float
    realistic_captaincy_gap: float
    transfers_made: int
    total_hit_cost: int
    max_free_transfers: int
    initial_bank: float
    final_bank: float
    chip_mode: str = CHIP_MODE_NONE
    chip_points: float = 0.0
    chips_used: int = 0
    minutes_mode: str = "binary"
    hit_policy: str = "current_gw"
    initial_squad_mode: str = IDENTITY_SAFE_INITIAL_SQUAD_MODE
    initial_squad_version: str = IDENTITY_SAFE_INITIAL_SQUAD_VERSION


@dataclass(frozen=True)
class RealisticCaptainScore:
    points: float
    raw_starter_points: float
    captain_id: int
    vice_captain_id: int
    captain_predicted_points: float
    vice_captain_predicted_points: float
    captain_actual_points: float
    vice_captain_actual_points: float
    vice_captain_fallback: bool
    starting_ids: tuple[int, ...]
    bench_ids: tuple[int, ...]
    autosub_ids: tuple[int, ...]
    formation: str


def get_training_data_for_season(
    players: pd.DataFrame,
    season: str,
    gameweek: int,
    training_seasons: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Return rows available before a target gameweek and assert no leakage."""

    available_seasons = sorted(str(value) for value in players["season"].unique())
    allowed_seasons = list(
        training_seasons or [value for value in available_seasons if value < season]
    )
    training = players[
        players["season"].isin(allowed_seasons)
        | ((players["season"] == season) & (players["gameweek"] < gameweek))
    ].copy()

    current_training = training[training["season"] == season]
    if not current_training.empty:
        max_current_gameweek = int(current_training["gameweek"].max())
        assert max_current_gameweek < gameweek, (
            f"Lookahead detected: target {season} GW{gameweek} has current-season "
            f"training data through GW{max_current_gameweek}."
        )
    assert not ((training["season"] == season) & (training["gameweek"] >= gameweek)).any(), (
        "Training data contains target or future rows."
    )
    return training


def _minutes_feature_columns(minutes_mode: str, feature_mode: str) -> list[str]:
    """Return the feature set for the selected minutes candidate."""

    columns = list(feature_columns_for_mode(feature_mode))
    if minutes_mode == "availability_role":
        columns.extend(M9_MINUTES_FEATURE_COLUMNS)
    return columns


def _fit_total_points_prediction_context(
    training: pd.DataFrame,
    *,
    model_name: str,
    minutes_mode: str,
    feature_mode: str,
) -> dict[str, Any]:
    """Fit reusable total-points models for one point-in-time cutoff."""

    feature_columns = feature_columns_for_mode(feature_mode)
    minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
    points_model: Pipeline = MODEL_BUILDERS[model_name](feature_columns)
    points_model.fit(training[feature_columns], training["next_gameweek_points"])
    minutes_model: Pipeline | None = None
    minutes_band_model: Any | None = None
    if minutes_mode == "binary":
        minutes_model = build_minutes_classifier(minutes_feature_columns)
        minutes_model.fit(
            training[minutes_feature_columns], (training["minutes"] >= 60).astype(int)
        )
    else:
        minutes_band_model = fit_minutes_band_conditional_model(
            training, minutes_feature_columns
        )
    start_model: Pipeline | None = None
    start_fallback = 0.5
    if minutes_mode == "availability_role":
        start_model, start_fallback = _fit_start_probability_model(
            training, minutes_feature_columns
        )
    return {
        "points_model": points_model,
        "minutes_model": minutes_model,
        "minutes_band_model": minutes_band_model,
        "start_model": start_model,
        "start_fallback": start_fallback,
    }


def _get_total_points_prediction_context(
    training: pd.DataFrame,
    *,
    season: str,
    gameweek: int,
    model_name: str,
    minutes_mode: str,
    feature_mode: str,
    cache: dict[tuple[Any, ...], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Reuse one fitted model context across current and future frames."""

    key = (season, gameweek, model_name, minutes_mode, feature_mode)
    if cache is not None and key in cache:
        return cache[key]
    context = _fit_total_points_prediction_context(
        training,
        model_name=model_name,
        minutes_mode=minutes_mode,
        feature_mode=feature_mode,
    )
    if cache is not None:
        cache[key] = context
    return context


def _fit_start_probability_model(
    training: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[Pipeline | None, float]:
    """Fit a start-probability model, with a safe prior for one-class windows."""

    if "starts" in training:
        start_target = (pd.to_numeric(training["starts"], errors="coerce").fillna(0) > 0).astype(
            int
        )
    else:
        start_target = (pd.to_numeric(training["minutes"], errors="coerce").fillna(0) >= 60).astype(
            int
        )
    fallback = float(start_target.mean()) if len(start_target) else 0.5
    if start_target.nunique() < 2:
        return None, fallback
    model = build_minutes_classifier(feature_columns)
    model.fit(training[feature_columns], start_target)
    return model, fallback


def _start_probability(
    target: pd.DataFrame,
    model: Pipeline | None,
    fallback: float,
    feature_columns: list[str],
) -> np.ndarray:
    if model is None:
        return np.full(len(target), fallback, dtype=float)
    return model.predict_proba(target[feature_columns])[:, 1]


def _add_role_probability_outputs(
    target: pd.DataFrame,
    band_probabilities: np.ndarray,
    start_probabilities: np.ndarray,
) -> pd.DataFrame:
    """Expose the M9 start/substitute/60+ probability contract."""

    target["probability_start"] = np.clip(start_probabilities, 0.0, 1.0)
    target["probability_substitute"] = np.clip(band_probabilities[:, 1], 0.0, 1.0)
    target["probability_60_plus_minutes"] = np.clip(band_probabilities[:, 2], 0.0, 1.0)
    target["expected_minutes_if_start"] = (
        target["minutes_mean_last_5"] if "minutes_mean_last_5" in target else 0.0
    ).clip(lower=0.0, upper=90.0)
    return target


def _apply_live_availability_features(
    target: pd.DataFrame,
    events: Iterable[AvailabilityEvent] | None,
    cutoff: datetime | str | None,
    target_gameweek: int,
) -> pd.DataFrame:
    """Overlay source-attributed live events on target rows only."""

    if events is None:
        return target
    if cutoff is None:
        raise ValueError("availability_cutoff is required when availability_events are supplied")
    features = build_availability_features(
        target["player_id"].tolist(),
        events,
        cutoff=cutoff,
        target_gameweek=target_gameweek,
    )
    availability_columns = [column for column in AVAILABILITY_FEATURE_COLUMNS if column in features]
    return target.drop(columns=availability_columns, errors="ignore").merge(
        features[["player_id", *availability_columns]],
        on="player_id",
        how="left",
    )


def _component_target_predictions(
    training: pd.DataFrame,
    target: pd.DataFrame,
    *,
    feature_mode: str,
    minutes_mode: str,
    context: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Apply M7 component scoring to one target gameweek."""

    component_columns = component_feature_columns(feature_mode)
    minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
    target_bps_rule_version = (
        str(target["bps_rule_version"].iloc[0])
        if "bps_rule_version" in target.columns and not target.empty
        else None
    )
    context = context or _fit_m10_component_context(
        training,
        feature_mode=feature_mode,
        minutes_mode=minutes_mode,
        target_bps_rule_version=target_bps_rule_version,
    )
    component_model = context["component_model"]
    start_model = context["start_model"]
    start_fallback = context["start_fallback"]

    if minutes_mode == "binary":
        minutes_model = context["minutes_model"]
        probability_60_plus = minutes_model.predict_proba(target[minutes_feature_columns])[:, 1]
        band_probabilities = np.column_stack(
            [1.0 - probability_60_plus, np.zeros(len(target)), probability_60_plus]
        )
        predicted_bands = band_probabilities.argmax(axis=1)
    else:
        minutes_band_model = context["minutes_band_model"]
        band_probabilities = minutes_band_model.predict_proba(target[minutes_feature_columns])
        probability_60_plus = band_probabilities[:, 2]
        predicted_bands = band_probabilities.argmax(axis=1)

    component_predictions = component_model.predict_expected_points(
        target[component_columns],
        minutes_probabilities=band_probabilities,
        dc_rule_versions=default_dc_rule_versions(target),
    )
    component_predictions = component_predictions.rename(
        columns={
            column: f"component_{column}"
            for column in component_predictions.columns
            if column.startswith("expected_")
        }
    )
    output = target.copy()
    output = output.join(component_predictions)
    output["predicted_points"] = output["component_expected_points"]
    output["expected_points_adjusted"] = output["component_expected_points"]
    output["probability_0_minutes"] = band_probabilities[:, 0]
    output["probability_1_59_minutes"] = band_probabilities[:, 1]
    output["probability_60_plus_minutes_v2"] = band_probabilities[:, 2]
    output["probability_60_plus_minutes"] = probability_60_plus
    output["predicted_minutes_band"] = predicted_bands
    output["component_regime_status"] = component_model.regime_status
    output["component_training_bps_rule_versions"] = ",".join(
        component_model.training_bps_rule_versions
    )
    if minutes_mode == "availability_role":
        _add_role_probability_outputs(
            output,
            band_probabilities,
            _start_probability(
                target,
                start_model,
                start_fallback,
                minutes_feature_columns,
            ),
        )
    output["model"] = "Component Projection"
    return output


def _fit_m10_component_context(
    training: pd.DataFrame,
    *,
    feature_mode: str,
    minutes_mode: str,
    target_bps_rule_version: str | None = None,
) -> dict[str, Any]:
    """Fit one point-in-time component/minutes context for horizon reuse."""

    minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
    component_model = fit_component_projection_model(
        training,
        feature_mode=feature_mode,
        target_bps_rule_version=target_bps_rule_version,
    )
    minutes_model = None
    minutes_band_model = None
    if minutes_mode == "binary":
        minutes_model = build_minutes_classifier(minutes_feature_columns)
        minutes_model.fit(
            training[minutes_feature_columns], (training["minutes"] >= 60).astype(int)
        )
    else:
        minutes_band_model = fit_minutes_band_conditional_model(training, minutes_feature_columns)
    start_model: Pipeline | None = None
    start_fallback = 0.5
    if minutes_mode == "availability_role":
        start_model, start_fallback = _fit_start_probability_model(
            training, minutes_feature_columns
        )
    return {
        "component_model": component_model,
        "minutes_model": minutes_model,
        "minutes_band_model": minutes_band_model,
        "start_model": start_model,
        "start_fallback": start_fallback,
    }


def _m10_fixture_forecasts(
    training: pd.DataFrame,
    target: pd.DataFrame,
    *,
    season: str,
    gameweek: int,
    team_model: Any | None = None,
) -> pd.DataFrame:
    """Build target fixtures from schedule fields and pre-target outcomes only."""

    rules = build_historical_season_rules(season)
    if team_model is None:
        team_model = fit_team_goal_model(
            training,
            cutoff_gameweek=gameweek,
            season=season,
            data_cutoff=f"{season}:GW{gameweek - 1:02d}",
            rules_version=rules.rules_version,
        )
    rows = target[["gameweek", "team", "opponent_team", "home_or_away"]].copy()
    home_mask = rows["home_or_away"].astype(str).str.upper().eq("H")
    rows["_home_team"] = rows["team"].where(home_mask, rows["opponent_team"]).astype(str)
    rows["_away_team"] = rows["opponent_team"].where(home_mask, rows["team"]).astype(str)
    rows = rows.drop_duplicates(["gameweek", "_home_team", "_away_team"])
    forecasts = []
    for _, row in rows.iterrows():
        home = str(row["_home_team"])
        away = str(row["_away_team"])
        forecasts.append(
            team_model.predict_fixture(
                {
                    "fixture_id": f"{int(row['gameweek'])}:{home}:{away}",
                    "gameweek": int(row["gameweek"]),
                    "team_h": home,
                    "team_a": away,
                    "status": "historical-visible-schedule",
                }
            ).to_dict()
        )
    return pd.DataFrame(forecasts)


def _m10_target_predictions(
    training: pd.DataFrame,
    target: pd.DataFrame,
    *,
    season: str,
    gameweek: int,
    feature_mode: str,
    minutes_mode: str,
    team_model: Any | None = None,
    component_context: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build an opt-in team-context component projection for one GW."""

    target = target.copy().reset_index(drop=True)
    if training.empty:
        output = target.copy()
        output["probability_0_minutes"] = 0.5
        output["probability_1_59_minutes"] = 0.0
        output["probability_60_plus_minutes_v2"] = 0.5
        output["probability_60_plus_minutes"] = 0.5
        output["predicted_minutes_band"] = 2
        for component in COMPONENT_MODEL_COLUMNS:
            output[f"component_expected_{component}"] = 0.0
        output["component_expected_points"] = 0.0
        output["component_model_version"] = "m10-team-components-v1"
        output["component_regime_status"] = "preseason_prior"
    else:
        minutes_context = component_context or _fit_m10_minutes_context(
            training,
            feature_mode=feature_mode,
            minutes_mode=minutes_mode,
        )
        output = target.copy()
        minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
        if minutes_mode == "binary":
            probability_60_plus = minutes_context["minutes_model"].predict_proba(
                output[minutes_feature_columns]
            )[:, 1]
            band_probabilities = np.column_stack(
                [1.0 - probability_60_plus, np.zeros(len(output)), probability_60_plus]
            )
        else:
            band_probabilities = minutes_context["minutes_band_model"].predict_proba(
                output[minutes_feature_columns]
            )
            probability_60_plus = band_probabilities[:, 2]
        output["probability_0_minutes"] = band_probabilities[:, 0]
        output["probability_1_59_minutes"] = band_probabilities[:, 1]
        output["probability_60_plus_minutes_v2"] = band_probabilities[:, 2]
        output["probability_60_plus_minutes"] = probability_60_plus
        output["predicted_minutes_band"] = band_probabilities.argmax(axis=1)
        for component in COMPONENT_MODEL_COLUMNS:
            lagged = f"{component}_last_3"
            output[f"component_expected_{component}"] = (
                pd.to_numeric(output[lagged], errors="coerce").fillna(0.0) / 3.0
                if lagged in output
                else 0.0
            )
        if minutes_mode == "availability_role":
            _add_role_probability_outputs(
                output,
                band_probabilities,
                _start_probability(
                    output,
                    minutes_context["start_model"],
                    minutes_context["start_fallback"],
                    minutes_feature_columns,
                ),
            )
        output["component_regime_status"] = "m10_team_bridge"

    fixture_forecasts = _m10_fixture_forecasts(
        training,
        output,
        season=season,
        gameweek=gameweek,
        team_model=team_model,
    )
    appearance = 1.0 - output["probability_0_minutes"].to_numpy(dtype=float)
    bridge = build_player_fixture_components(
        output,
        fixture_forecasts,
        appearance_probabilities=appearance,
        data_cutoff=f"{season}:GW{gameweek - 1:02d}",
        rules_version=build_historical_season_rules(season).rules_version,
    )
    for component in (
        "goals_scored",
        "assists",
        "clean_sheets",
        "saves",
        "goals_conceded",
        "defensive_contribution",
    ):
        output[f"component_expected_{component}"] = bridge[f"expected_{component}"].to_numpy()

    component_frame = pd.DataFrame(
        {
            f"expected_{component}": output[f"component_expected_{component}"]
            for component in COMPONENT_MODEL_COLUMNS
        }
    )
    minute_probabilities = output[
        [
            "probability_0_minutes",
            "probability_1_59_minutes",
            "probability_60_plus_minutes_v2",
        ]
    ].to_numpy(dtype=float)
    output["component_expected_points"] = score_expected_components(
        component_frame,
        output["position"],
        minutes_probabilities=minute_probabilities,
        dc_rule_versions=default_dc_rule_versions(output),
    )
    output["predicted_points"] = output["component_expected_points"]
    output["expected_points_adjusted"] = output["component_expected_points"]
    output["component_model_version"] = "m10-team-components-v1"
    output["component_bridge_model_version"] = bridge["model_version"].iloc[0]
    output["team_forecast_model_version"] = "m10-team-poisson-v1"
    output["team_forecast_data_cutoff"] = bridge["data_cutoff"].iloc[0]
    output["team_rules_version"] = bridge["rules_version"].iloc[0]
    output["component_calibration_status"] = "unadjusted_event_intervals"
    output["model"] = "M10 Team Components"
    return output


def _fit_m10_minutes_context(
    training: pd.DataFrame,
    *,
    feature_mode: str,
    minutes_mode: str,
) -> dict[str, Any]:
    """Fit only the reusable minutes context required by the M10 bridge."""

    minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
    minutes_model = None
    minutes_band_model = None
    if minutes_mode == "binary":
        minutes_model = build_minutes_classifier(minutes_feature_columns)
        minutes_model.fit(
            training[minutes_feature_columns], (training["minutes"] >= 60).astype(int)
        )
    else:
        minutes_band_model = fit_minutes_band_conditional_model(training, minutes_feature_columns)
    start_model: Pipeline | None = None
    start_fallback = 0.5
    if minutes_mode == "availability_role":
        start_model, start_fallback = _fit_start_probability_model(
            training, minutes_feature_columns
        )
    return {
        "minutes_model": minutes_model,
        "minutes_band_model": minutes_band_model,
        "start_model": start_model,
        "start_fallback": start_fallback,
    }


def train_gameweek_predictions(
    players: pd.DataFrame,
    season: str,
    gameweek: int,
    model_name: str = DEFAULT_MODEL,
    minutes_mode: str = "binary",
    feature_mode: str = "baseline",
    projection_mode: str = DEFAULT_PROJECTION_MODE,
    availability_events: Iterable[AvailabilityEvent] | None = None,
    availability_cutoff: datetime | str | None = None,
    _model_context_cache: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train and predict one target gameweek using an expanding time window."""

    if model_name not in MODEL_BUILDERS:
        raise ValueError(f"Unknown model {model_name!r}; choose from {', '.join(MODEL_BUILDERS)}")
    if minutes_mode not in {"binary", "conditional_bands", "availability_role"}:
        raise ValueError(
            "minutes_mode must be 'binary', 'conditional_bands', or 'availability_role'"
        )
    if projection_mode not in PROJECTION_MODES:
        raise ValueError(f"projection_mode must be one of {', '.join(PROJECTION_MODES)}")
    if minutes_mode == "availability_role" and not set(M9_MINUTES_FEATURE_COLUMNS).issubset(
        players.columns
    ):
        players = add_m9_historical_features(players)
    feature_columns = feature_columns_for_mode(feature_mode)
    minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
    training = get_training_data_for_season(players, season, gameweek)
    target = players[(players["season"] == season) & (players["gameweek"] == gameweek)].copy()
    if target.empty:
        raise ValueError(f"No target rows for {season} GW{gameweek}")
    if minutes_mode == "availability_role":
        target = _apply_live_availability_features(
            target,
            availability_events,
            availability_cutoff,
            gameweek,
        )

    if training.empty:
        # The earliest available season has no prior season file. GW1 therefore
        # uses the same preseason heuristic as the initial squad, without future
        # match results or current-season minutes.
        if projection_mode == "m10_team_components":
            target = _m10_target_predictions(
                training,
                target,
                season=season,
                gameweek=gameweek,
                feature_mode=feature_mode,
                minutes_mode=minutes_mode,
            )
        else:
            preseason = build_preseason_scores(players, season=season, prior_season=None)
            projection = preseason.set_index("player_id")["preseason_value_score"]
            target["predicted_points"] = target["player_id"].map(projection).fillna(0.0)
            target["probability_60_plus_minutes"] = 0.5
            target["probability_0_minutes"] = 0.0
            target["probability_1_59_minutes"] = 0.0
            target["probability_60_plus_minutes_v2"] = 1.0
            target["probability_start"] = 0.5
            target["probability_substitute"] = 0.0
            target["expected_minutes_if_start"] = 90.0
            target["predicted_minutes_band"] = 2
            target["expected_points_adjusted"] = target["predicted_points"]
            target["model"] = "Preseason heuristic"
        target["minutes_model_mode"] = minutes_mode
        target["feature_mode"] = feature_mode
        target["projection_mode"] = projection_mode
        target["training_row_count"] = 0
        target["max_training_current_season_gameweek"] = None
        target["decision_price"] = target["price_before_deadline"].fillna(target["price"])
        return target, training

    if projection_mode == "components":
        target = _component_target_predictions(
            training,
            target,
            feature_mode=feature_mode,
            minutes_mode=minutes_mode,
        )
    elif projection_mode == "m10_team_components":
        target = _m10_target_predictions(
            training,
            target,
            season=season,
            gameweek=gameweek,
            feature_mode=feature_mode,
            minutes_mode=minutes_mode,
        )
    else:
        context = _get_total_points_prediction_context(
            training,
            season=season,
            gameweek=gameweek,
            model_name=model_name,
            minutes_mode=minutes_mode,
            feature_mode=feature_mode,
            cache=_model_context_cache,
        )
        points_model: Pipeline = context["points_model"]

        target["predicted_points"] = points_model.predict(target[feature_columns])
        if minutes_mode == "binary":
            minutes_model = context["minutes_model"]
            assert minutes_model is not None
            target["probability_60_plus_minutes"] = minutes_model.predict_proba(
                target[minutes_feature_columns]
            )[:, 1]
            target["expected_points_adjusted"] = (
                target["predicted_points"] * target["probability_60_plus_minutes"]
            ).clip(lower=0.0)
        else:
            # This is intentionally independent benchmark logic: it fits its own
            # three-class model and band-specific point estimators for each target GW.
            minutes_band_model = context["minutes_band_model"]
            assert minutes_band_model is not None
            band_probabilities = minutes_band_model.predict_proba(target[minutes_feature_columns])
            target["probability_0_minutes"] = band_probabilities[:, 0]
            target["probability_1_59_minutes"] = band_probabilities[:, 1]
            target["probability_60_plus_minutes_v2"] = band_probabilities[:, 2]
            target["probability_60_plus_minutes"] = band_probabilities[:, 2]
            target["predicted_minutes_band"] = minutes_band_model.predict(
                target[minutes_feature_columns]
            )
            target["expected_points_adjusted"] = minutes_band_model.predict_expected_points(
                target[minutes_feature_columns]
            ).clip(0.0)
            if minutes_mode == "availability_role":
                _add_role_probability_outputs(
                    target,
                    band_probabilities,
                    _start_probability(
                        target,
                        context["start_model"],
                        context["start_fallback"],
                        minutes_feature_columns,
                    ),
                )
    target["minutes_model_mode"] = minutes_mode
    target["feature_mode"] = feature_mode
    target["projection_mode"] = projection_mode
    target["decision_price"] = target["price_before_deadline"].fillna(target["price"])
    target["training_row_count"] = len(training)
    current_training = training[training["season"] == season]
    target["max_training_current_season_gameweek"] = (
        None if current_training.empty else int(current_training["gameweek"].max())
    )
    target["model"] = (
        "Component Projection"
        if projection_mode == "components"
        else "M10 Team Components"
        if projection_mode == "m10_team_components"
        else model_name
    )
    return target, training


def _point_in_time_future_frame(
    players: pd.DataFrame,
    season: str,
    decision_gameweek: int,
    target_gameweek: int,
    feature_mode: str = "xg_xa",
) -> pd.DataFrame:
    """Build future target features using only the decision-time snapshot."""

    target = players[
        (players["season"] == season) & (players["gameweek"] == target_gameweek)
    ].copy()
    if target.empty:
        return target

    snapshot = players[
        (players["season"] == season) & (players["gameweek"] == decision_gameweek)
    ].copy()
    if snapshot.empty:
        snapshot = players[
            (players["season"] == season) & (players["gameweek"] < decision_gameweek)
        ].copy()
    snapshot = snapshot.sort_values(["player_id", "gameweek"]).drop_duplicates(
        "player_id", keep="last"
    )
    known_ids = set(snapshot["player_id"].tolist())
    target = target[target["player_id"].isin(known_ids)].copy()
    if target.empty:
        return target

    safe = (
        target.sort_values(["player_id", "gameweek"])
        .drop_duplicates("player_id", keep="last")
        .copy()
    )
    snapshot_by_id = snapshot.set_index("player_id")
    safe_by_id = safe.set_index("player_id")

    # Fixture context is known from the published schedule. All player-state
    # features, prices, positions, and ownership remain frozen at decision time.
    for column in (
        "price",
        "price_before_deadline",
        "selected_by_percent",
        "selected_by_percent_before_deadline",
        "market_snapshot_available",
        "position",
        *[
            feature
            for feature in component_feature_columns(feature_mode)
            if feature not in {"home_or_away", "opponent_strength", "position"}
        ],
        *M9_MINUTES_FEATURE_COLUMNS,
    ):
        if column in snapshot_by_id.columns:
            safe_by_id[column] = snapshot_by_id[column].reindex(safe_by_id.index)

    safe = safe_by_id.reset_index()
    safe["decision_price"] = safe["price_before_deadline"].fillna(safe["price"])
    safe["as_of_gameweek"] = decision_gameweek
    safe["future_target_gameweek"] = target_gameweek
    return safe


def train_future_gameweek_predictions(
    players: pd.DataFrame,
    season: str,
    decision_gameweek: int,
    *,
    model_name: str = DEFAULT_MODEL,
    minutes_mode: str = "binary",
    feature_mode: str = "baseline",
    projection_mode: str = DEFAULT_PROJECTION_MODE,
    horizons: Sequence[int] = (1, 2),
    availability_events: Iterable[AvailabilityEvent] | None = None,
    availability_cutoff: datetime | str | None = None,
    _model_context_cache: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> dict[int, pd.DataFrame]:
    """Forecast t+1/t+2 using only information available before gameweek t."""

    if any(horizon < 1 or horizon > 8 for horizon in horizons):
        raise ValueError("future horizons must be between 1 and 8 gameweeks")
    if model_name not in MODEL_BUILDERS:
        raise ValueError(f"Unknown model {model_name!r}; choose from {', '.join(MODEL_BUILDERS)}")
    if minutes_mode not in {"binary", "conditional_bands", "availability_role"}:
        raise ValueError(
            "minutes_mode must be 'binary', 'conditional_bands', or 'availability_role'"
        )
    if projection_mode not in PROJECTION_MODES:
        raise ValueError(f"projection_mode must be one of {', '.join(PROJECTION_MODES)}")
    if minutes_mode == "availability_role" and not set(M9_MINUTES_FEATURE_COLUMNS).issubset(
        players.columns
    ):
        players = add_m9_historical_features(players)
    feature_columns = feature_columns_for_mode(feature_mode)
    minutes_feature_columns = _minutes_feature_columns(minutes_mode, feature_mode)
    training = get_training_data_for_season(players, season, decision_gameweek)
    output: dict[int, pd.DataFrame] = {}

    points_model: Pipeline | None = None
    minutes_model: Pipeline | None = None
    minutes_band_model: Any | None = None
    start_model: Pipeline | None = None
    start_fallback = 0.5
    component_model: Any | None = None
    m10_team_model: Any | None = None
    m10_component_context: dict[str, Any] | None = None
    if not training.empty:
        if projection_mode == "components":
            component_model = fit_component_projection_model(
                training,
                feature_mode=feature_mode,
            )
        elif projection_mode == "m10_team_components":
            m10_component_context = _fit_m10_minutes_context(
                training,
                feature_mode=feature_mode,
                minutes_mode=minutes_mode,
            )
            m10_team_model = fit_team_goal_model(
                training,
                cutoff_gameweek=decision_gameweek + 1,
                season=season,
                data_cutoff=f"{season}:GW{decision_gameweek:02d}",
                rules_version=build_historical_season_rules(season).rules_version,
            )
        else:
            context = _get_total_points_prediction_context(
                training,
                season=season,
                gameweek=decision_gameweek,
                model_name=model_name,
                minutes_mode=minutes_mode,
                feature_mode=feature_mode,
                cache=_model_context_cache,
            )
            points_model = context["points_model"]
            minutes_model = context["minutes_model"]
            minutes_band_model = context["minutes_band_model"]
            start_model = context["start_model"]
            start_fallback = context["start_fallback"]

    for horizon in horizons:
        target_gameweek = decision_gameweek + horizon
        target = _point_in_time_future_frame(
            players,
            season,
            decision_gameweek,
            target_gameweek,
            feature_mode=feature_mode,
        )
        if target.empty:
            output[target_gameweek] = pd.DataFrame()
            continue
        if minutes_mode == "availability_role":
            target = _apply_live_availability_features(
                target,
                availability_events,
                availability_cutoff,
                target_gameweek,
            )

        if projection_mode == "m10_team_components":
            target = _m10_target_predictions(
                training,
                target,
                season=season,
                gameweek=target_gameweek,
                feature_mode=feature_mode,
                minutes_mode=minutes_mode,
                team_model=m10_team_model,
                component_context=m10_component_context,
            )
        elif training.empty:
            preseason = build_preseason_scores(players, season=season, prior_season=None).set_index(
                "player_id"
            )
            target["predicted_points"] = (
                target["player_id"].map(preseason["preseason_value_score"]).fillna(0.0)
            )
            target["expected_points_adjusted"] = target["predicted_points"]
            target["probability_60_plus_minutes"] = 0.5
            target["probability_start"] = 0.5
            target["probability_substitute"] = 0.0
            target["expected_minutes_if_start"] = 90.0
        elif projection_mode == "components":
            assert component_model is not None
            if minutes_mode == "binary":
                minutes_model = build_minutes_classifier(minutes_feature_columns)
                minutes_model.fit(
                    training[minutes_feature_columns], (training["minutes"] >= 60).astype(int)
                )
                probability_60_plus = minutes_model.predict_proba(target[minutes_feature_columns])[
                    :, 1
                ]
                band_probabilities = np.column_stack(
                    [
                        1.0 - probability_60_plus,
                        np.zeros(len(target)),
                        probability_60_plus,
                    ]
                )
            else:
                assert minutes_band_model is not None
                band_probabilities = minutes_band_model.predict_proba(
                    target[minutes_feature_columns]
                )
                probability_60_plus = band_probabilities[:, 2]
            component_predictions = component_model.predict_expected_points(
                target[component_feature_columns(feature_mode)],
                minutes_probabilities=band_probabilities,
                dc_rule_versions=default_dc_rule_versions(target),
            )
            component_predictions = component_predictions.rename(
                columns={
                    column: f"component_{column}"
                    for column in component_predictions.columns
                    if column.startswith("expected_")
                }
            )
            target = target.join(component_predictions)
            target["predicted_points"] = target["component_expected_points"]
            target["expected_points_adjusted"] = target["component_expected_points"]
            target["probability_60_plus_minutes"] = probability_60_plus
            if minutes_mode == "availability_role":
                _add_role_probability_outputs(
                    target,
                    band_probabilities,
                    _start_probability(
                        target,
                        start_model,
                        start_fallback,
                        minutes_feature_columns,
                    ),
                )
        else:
            assert points_model is not None
            target["predicted_points"] = points_model.predict(target[feature_columns])
            if minutes_mode == "binary":
                assert minutes_model is not None
                target["probability_60_plus_minutes"] = minutes_model.predict_proba(
                    target[feature_columns]
                )[:, 1]
                target["expected_points_adjusted"] = (
                    target["predicted_points"] * target["probability_60_plus_minutes"]
                ).clip(lower=0.0)
            else:
                assert minutes_band_model is not None
                target["probability_60_plus_minutes"] = minutes_band_model.predict_proba(
                    target[minutes_feature_columns]
                )[:, 2]
                target["expected_points_adjusted"] = minutes_band_model.predict_expected_points(
                    target[minutes_feature_columns]
                ).clip(0.0)
                if minutes_mode == "availability_role":
                    band_probabilities = minutes_band_model.predict_proba(
                        target[minutes_feature_columns]
                    )
                    _add_role_probability_outputs(
                        target,
                        band_probabilities,
                        _start_probability(
                            target,
                            start_model,
                            start_fallback,
                            minutes_feature_columns,
                        ),
                    )

        target["minutes_model_mode"] = minutes_mode
        target["feature_mode"] = feature_mode
        target["projection_mode"] = projection_mode
        target["training_row_count"] = len(training)
        target["max_training_current_season_gameweek"] = (
            decision_gameweek - 1 if decision_gameweek > 1 else None
        )
        target["model"] = (
            "M10 Team Components"
            if projection_mode == "m10_team_components"
            else model_name
            if not training.empty
            else "Preseason heuristic"
        )
        # Actual outcomes are deliberately excluded from the strategy-facing frame.
        output_columns = [
            "player_id",
            "player_name",
            "position",
            "team",
            "price",
            "decision_price",
            "gameweek",
            "expected_points_adjusted",
            "predicted_points",
            "probability_60_plus_minutes",
            "minutes_model_mode",
            "feature_mode",
            "projection_mode",
            "training_row_count",
            "max_training_current_season_gameweek",
            "as_of_gameweek",
            "future_target_gameweek",
        ]
        if minutes_mode == "availability_role":
            output_columns.extend(
                [
                    "probability_start",
                    "probability_substitute",
                    "expected_minutes_if_start",
                ]
            )
        if projection_mode == "m10_team_components":
            output_columns.extend(
                [
                    "component_bridge_model_version",
                    "team_forecast_model_version",
                    "team_forecast_data_cutoff",
                    "team_rules_version",
                    "component_calibration_status",
                ]
            )
        output[target_gameweek] = target[output_columns].copy()
    return output


def train_realistic_captain_predictions(
    players: pd.DataFrame,
    season: str,
    gameweek: int,
    *,
    model_name: str = DEFAULT_MODEL,
    minutes_mode: str = "binary",
    feature_mode: str = "baseline",
    projection_mode: str = DEFAULT_PROJECTION_MODE,
    availability_events: Iterable[AvailabilityEvent] | None = None,
    availability_cutoff: datetime | str | None = None,
) -> pd.DataFrame:
    """Train a fresh point-in-time model for captain selection."""

    training = get_training_data_for_season(players, season, gameweek)
    target = players[(players["season"] == season) & (players["gameweek"] == gameweek)].copy()
    if target.empty:
        raise ValueError(f"No target rows for {season} GW{gameweek}")
    if minutes_mode == "availability_role":
        target = _apply_live_availability_features(
            target,
            availability_events,
            availability_cutoff,
            gameweek,
        )
    if projection_mode not in PROJECTION_MODES:
        raise ValueError(f"projection_mode must be one of {', '.join(PROJECTION_MODES)}")

    current_training = training[training["season"] == season]
    max_current_gameweek = (
        None if current_training.empty else int(current_training["gameweek"].max())
    )
    if training.empty:
        # Only the earliest available season's GW1 can reach this fallback. It is
        # deterministic and pre-deadline by construction, but remains subject to
        # the benchmark's documented weak-GW1 heuristic limitation.
        preseason = build_preseason_scores(players, season=season, prior_season=None)
        projection = preseason.set_index("player_id")["preseason_value_score"]
        target["captain_predicted_points"] = target["player_id"].map(projection).fillna(0.0)
        target["captain_model"] = "Preseason captain fallback"
    elif projection_mode == "components":
        component_target = _component_target_predictions(
            training,
            target,
            feature_mode=feature_mode,
            minutes_mode=minutes_mode,
        )
        target["captain_predicted_points"] = component_target["component_expected_points"]
        target["captain_model"] = "Component Projection"
    elif projection_mode == "m10_team_components":
        component_target = _m10_target_predictions(
            training,
            target,
            season=season,
            gameweek=gameweek,
            feature_mode=feature_mode,
            minutes_mode=minutes_mode,
        )
        target["captain_predicted_points"] = component_target["component_expected_points"]
        target["captain_model"] = "M10 Team Components"
    else:
        if model_name not in MODEL_BUILDERS:
            raise ValueError(
                f"Unknown model {model_name!r}; choose from {', '.join(MODEL_BUILDERS)}"
            )
        model = MODEL_BUILDERS[model_name]()
        model.fit(
            training[feature_columns_for_mode(feature_mode)],
            training["next_gameweek_points"],
        )
        target["captain_predicted_points"] = model.predict(
            target[feature_columns_for_mode(feature_mode)]
        )
        target["captain_model"] = model_name
    target["captain_model_name"] = target["captain_model"]

    target["captain_training_row_count"] = len(training)
    target["captain_max_training_current_season_gameweek"] = max_current_gameweek
    target["projection_mode"] = projection_mode
    return target


def score_realistic_gameweek(
    squad: pd.DataFrame,
    target: pd.DataFrame,
    projected_points: dict[int, float],
    captain_predictions: pd.DataFrame,
) -> RealisticCaptainScore:
    """Score with predicted captain/vice selection and real FPL fallback rules."""

    lineup = select_starting_xi(squad, projected_points)
    prediction_by_id = captain_predictions.set_index("player_id")[
        "captain_predicted_points"
    ].to_dict()
    predicted_order = sorted(
        lineup.starting_ids,
        key=lambda player_id: (float(prediction_by_id.get(player_id, 0.0)), -player_id),
        reverse=True,
    )
    captain_id, vice_captain_id = predicted_order[:2]
    active_ids, autosub_ids = resolve_active_lineup(squad, target, lineup)

    target_rows = target.drop_duplicates("player_id").set_index("player_id")
    minutes = target_rows["minutes"].to_dict()
    points = target_rows["next_gameweek_points"].to_dict()
    raw_starter_points = float(sum(float(points.get(player_id, 0)) for player_id in active_ids))
    captain_actual_points = float(points.get(captain_id, 0))
    vice_actual_points = float(points.get(vice_captain_id, 0))
    captain_played = float(minutes.get(captain_id, 0)) > 0
    vice_played = float(minutes.get(vice_captain_id, 0)) > 0

    if captain_played:
        bonus_points = captain_actual_points
        vice_captain_fallback = False
    elif vice_played:
        bonus_points = vice_actual_points
        vice_captain_fallback = True
    else:
        bonus_points = 0.0
        vice_captain_fallback = False

    return RealisticCaptainScore(
        points=raw_starter_points + bonus_points,
        raw_starter_points=raw_starter_points,
        captain_id=captain_id,
        vice_captain_id=vice_captain_id,
        captain_predicted_points=float(prediction_by_id.get(captain_id, 0.0)),
        vice_captain_predicted_points=float(prediction_by_id.get(vice_captain_id, 0.0)),
        captain_actual_points=captain_actual_points,
        vice_captain_actual_points=vice_actual_points,
        vice_captain_fallback=vice_captain_fallback,
        starting_ids=tuple(active_ids),
        bench_ids=lineup.bench_ids,
        autosub_ids=autosub_ids,
        formation=lineup.formation,
    )


def run_season_benchmark(
    players: pd.DataFrame,
    season: str,
    strategy: BenchmarkStrategy,
    *,
    model_name: str = DEFAULT_MODEL,
    model_version: str = DEFAULT_MODEL_VERSION,
    max_free_transfers: int | None = None,
    verbose: bool = False,
    minutes_mode: str = "binary",
    feature_mode: str = "baseline",
    projection_mode: str = DEFAULT_PROJECTION_MODE,
    chip_mode: str = CHIP_MODE_DEFAULT,
    hit_policy: str = "current_gw",
    projection_portfolio: ProjectionPortfolio | None = None,
    availability_events: Iterable[AvailabilityEvent] | None = None,
    availability_cutoff: datetime | str | None = None,
    prediction_cache: dict[
        tuple[str, int, str, str, str, str],
        tuple[pd.DataFrame, pd.DataFrame | None],
    ]
    | None = None,
    captain_prediction_cache: dict[tuple[str, int, str, str, str, str], pd.DataFrame]
    | None = None,
    future_prediction_cache: dict[tuple[str, int, str, str, str, str], dict[int, pd.DataFrame]]
    | None = None,
    initial_squad_override: pd.DataFrame | None = None,
    initial_squad_mode: str = IDENTITY_SAFE_INITIAL_SQUAD_MODE,
    initial_squad_version: str = IDENTITY_SAFE_INITIAL_SQUAD_VERSION,
) -> SeasonBenchmarkResult:
    """Run one strategy through every available gameweek in one season."""

    if chip_mode not in CHIP_MODES:
        raise ValueError(f"chip_mode must be one of {', '.join(CHIP_MODES)}")
    if hit_policy not in HIT_POLICIES:
        raise ValueError(f"hit_policy must be one of {', '.join(HIT_POLICIES)}")
    portfolio = projection_portfolio or ProjectionPortfolio(
        transfer_model=model_name,
        captain_model=model_name,
        chip_model=model_name,
    )
    if portfolio.transfer_model != model_name:
        raise ValueError(
            "projection_portfolio.transfer_model must match model_name; "
            "the benchmark's model_name remains the ordinary transfer model."
        )
    captain_model_name = portfolio.captain_model
    chip_model_name = portfolio.chip_model
    lineup_model_name = portfolio.lineup_model
    if minutes_mode == "availability_role" and not set(M9_MINUTES_FEATURE_COLUMNS).issubset(
        players.columns
    ):
        players = add_m9_historical_features(players)

    season_players = players[players["season"] == season].copy()
    gameweeks = sorted(int(value) for value in season_players["gameweek"].unique())
    if not gameweeks or gameweeks[0] != 1:
        raise ValueError(f"Expected {season} data starting at GW1")

    prior_season = _previous_season(players, season)
    if initial_squad_override is None:
        initial_squad = build_initial_squad(
            players,
            season=season,
            prior_season=prior_season,
            minutes_floor=None,
        )
    else:
        requested_ids = {
            int(value)
            for value in initial_squad_override["player_id"].dropna().tolist()
        }
        gw1 = (
            season_players[season_players["gameweek"] == 1]
            .sort_values(["player_id", "gameweek"])
            .drop_duplicates("player_id")
        )
        initial_squad = gw1[gw1["player_id"].astype(int).isin(requested_ids)].copy()
        if len(requested_ids) != 15 or len(initial_squad) != 15:
            raise ValueError(
                "Initial-squad override must contain 15 unique players present in "
                f"{season} GW1"
            )
        initial_squad["price"] = pd.to_numeric(
            initial_squad["price_before_deadline"], errors="coerce"
        ).where(
            pd.to_numeric(initial_squad["price_before_deadline"], errors="coerce") > 0,
            pd.to_numeric(initial_squad["price"], errors="coerce"),
        )
        violations = validate_squad(initial_squad)
        if violations:
            raise ValueError(
                "Initial-squad override is invalid: " + "; ".join(violations)
            )
    squad = initial_squad.copy()
    initial_squad_hash = _squad_hash(initial_squad)
    initial_bank = round(INITIAL_BUDGET - float(squad["price"].sum()), 1)
    bank = initial_bank
    free_transfers = 1
    transfer_cap = (
        max_free_transfers
        if max_free_transfers is not None
        else load_max_free_transfers(season=season)
    )
    rows: list[dict[str, Any]] = []
    gross_points = 0.0
    total_points = 0.0
    realistic_gross_points = 0.0
    realistic_total_points = 0.0
    transfers_made = 0
    total_hit_cost = 0
    chip_points = 0.0
    chips_used = 0
    rules = build_historical_season_rules(season)
    chip_state = initial_chip_state(rules)
    chip_planner = DeterministicChipPlanner()
    beam_planner = DeterministicBeamPlanner(
        hit_policy=hit_policy,
        max_transfers=2 if hit_policy == "horizon_value" else 6,
    )
    model_context_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
    fixture_scenario_cache: dict[tuple[int, int], Any] = {}
    historical_raw, historical_teams = load_historical_raw([season])

    if verbose:
        print(f"Season benchmark: {season} | {strategy.name} {strategy.version}")
        print(f"- Model: {model_name} ({model_version})")
        print(f"- Free-transfer cap: {transfer_cap}; initial bank: GBP {initial_bank:.1f}m")

    for gameweek in gameweeks:
        cache_key = (
            season,
            gameweek,
            model_name,
            minutes_mode,
            feature_mode,
            projection_mode,
        )
        if prediction_cache is not None and cache_key in prediction_cache:
            target, cached_available_data = prediction_cache[cache_key]
            available_data = (
                cached_available_data
                if cached_available_data is not None
                else get_training_data_for_season(players, season, gameweek)
            )
        else:
            target, available_data = train_gameweek_predictions(
                players,
                season,
                gameweek,
                model_name=model_name,
                minutes_mode=minutes_mode,
                feature_mode=feature_mode,
                projection_mode=projection_mode,
                availability_events=availability_events,
                availability_cutoff=availability_cutoff,
                _model_context_cache=model_context_cache,
            )
            if prediction_cache is not None:
                # Training data expands every Gameweek and can contain tens of
                # thousands of rows. Retaining one full copy per cache key made
                # multi-candidate tournaments consume gigabytes before the
                # first season checkpoint. Predictions are the reusable asset;
                # point-in-time training history is cheap to reconstruct.
                prediction_cache[cache_key] = (target, None)
        needs_future = getattr(strategy, "requires_future_predictions", False)
        needs_future = needs_future or chip_mode in {CHIP_MODE_BASELINE, CHIP_MODE_BEAM}
        if needs_future:
            if future_prediction_cache is not None and cache_key in future_prediction_cache:
                future_predictions = future_prediction_cache[cache_key]
            else:
                future_predictions = train_future_gameweek_predictions(
                    players,
                    season,
                    gameweek,
                    model_name=model_name,
                    minutes_mode=minutes_mode,
                    feature_mode=feature_mode,
                    projection_mode=projection_mode,
                    availability_events=availability_events,
                    availability_cutoff=availability_cutoff,
                    horizons=(
                        tuple(range(1, 9))
                        if chip_mode == CHIP_MODE_BASELINE
                        else ((1, 2, 3, 4, 5, 6) if chip_mode == CHIP_MODE_BEAM else (1, 2, 3))
                    ),
                    _model_context_cache=model_context_cache,
                )
                if future_prediction_cache is not None:
                    future_prediction_cache[cache_key] = future_predictions
        else:
            future_predictions = {}
        predictions = target.copy()
        lineup_predictions = predictions
        if lineup_model_name != model_name:
            lineup_cache_key = (
                season,
                gameweek,
                lineup_model_name,
                minutes_mode,
                feature_mode,
                projection_mode,
            )
            if prediction_cache is not None and lineup_cache_key in prediction_cache:
                lineup_predictions, _ = prediction_cache[lineup_cache_key]
            else:
                lineup_predictions, _ = train_gameweek_predictions(
                    players,
                    season,
                    gameweek,
                    model_name=lineup_model_name,
                    minutes_mode=minutes_mode,
                    feature_mode=feature_mode,
                    projection_mode=projection_mode,
                    availability_events=availability_events,
                    availability_cutoff=availability_cutoff,
                    _model_context_cache=model_context_cache,
                )
                if prediction_cache is not None:
                    prediction_cache[lineup_cache_key] = (
                        lineup_predictions,
                        None,
                    )
        chip_predictions = predictions
        chip_future_predictions = future_predictions
        if chip_mode in {CHIP_MODE_BASELINE, CHIP_MODE_BEAM} and chip_model_name != model_name:
            chip_cache_key = (
                season,
                gameweek,
                chip_model_name,
                minutes_mode,
                feature_mode,
                projection_mode,
            )
            if prediction_cache is not None and chip_cache_key in prediction_cache:
                chip_predictions, _ = prediction_cache[chip_cache_key]
            else:
                chip_predictions, _ = train_gameweek_predictions(
                    players,
                    season,
                    gameweek,
                    model_name=chip_model_name,
                    minutes_mode=minutes_mode,
                    feature_mode=feature_mode,
                    projection_mode=projection_mode,
                    availability_events=availability_events,
                    availability_cutoff=availability_cutoff,
                    _model_context_cache=model_context_cache,
                )
            if prediction_cache is not None:
                prediction_cache[chip_cache_key] = (chip_predictions, None)
            if needs_future:
                if (
                    future_prediction_cache is not None
                    and chip_cache_key in future_prediction_cache
                ):
                    chip_future_predictions = future_prediction_cache[chip_cache_key]
                else:
                    chip_future_predictions = train_future_gameweek_predictions(
                        players,
                        season,
                        gameweek,
                        model_name=chip_model_name,
                        minutes_mode=minutes_mode,
                        feature_mode=feature_mode,
                        projection_mode=projection_mode,
                        availability_events=availability_events,
                        availability_cutoff=availability_cutoff,
                        horizons=(
                            tuple(range(1, 9))
                            if chip_mode == CHIP_MODE_BASELINE
                            else (1, 2, 3, 4, 5, 6)
                        ),
                        _model_context_cache=model_context_cache,
                    )
                    if future_prediction_cache is not None:
                        future_prediction_cache[chip_cache_key] = chip_future_predictions
        prices = _latest_prices(players, season, gameweek)
        scenario_key = (gameweek, 8)
        if scenario_key not in fixture_scenario_cache:
            fixture_scenario_cache[scenario_key] = build_historical_fixture_scenario(
                players,
                season=season,
                start_gameweek=gameweek,
                horizon_length=8,
                raw_fixture_rows=historical_raw,
                historical_teams=historical_teams,
            )
        fixture_scenario = fixture_scenario_cache[scenario_key]
        squad["price"] = squad["player_id"].map(prices).fillna(squad["price"])
        bank_before = bank
        free_transfers_before = free_transfers
        pre_chip_squad = squad.copy()
        squad_before_hash = _squad_hash(pre_chip_squad)
        transfer_candidate = _empty_decision()
        transfer_expected_horizon_gain = 0.0
        transfer_expected_horizon_net_gain = 0.0
        post_transfer_squad = pre_chip_squad.copy()
        post_transfer_bank = bank
        post_transfer_free_transfers = free_transfers
        if gameweek >= 2 and chip_mode != CHIP_MODE_BEAM:
            context = StrategyContext(
                season=season,
                gameweek=gameweek,
                squad=pre_chip_squad.copy(),
                predictions=predictions.copy(),
                bank=bank,
                free_transfers=free_transfers,
                available_data=available_data.copy(),
                free_transfer_cap=transfer_cap,
                future_predictions={
                    target_gameweek: frame.copy()
                    for target_gameweek, frame in future_predictions.items()
                },
            )
            transfer_candidate = strategy.decide(context)
            if transfer_candidate.made:
                _assert_transfer_budget(pre_chip_squad, transfer_candidate, bank)
                post_transfer_squad = _apply_benchmark_transfer(
                    pre_chip_squad, predictions, transfer_candidate
                )
                post_transfer_bank = round(
                    bank
                    + float(transfer_candidate.outgoing_price)
                    - float(transfer_candidate.incoming_price),
                    1,
                )
                post_transfer_free_transfers = max(0, free_transfers - 1)

        chip_decision = ChipDecision(gameweek=gameweek)
        chip_definition = None
        chip_squad = None
        if chip_mode == CHIP_MODE_BASELINE:
            chip_decision, chip_definition, chip_squad = chip_planner.decide(
                chip_state,
                gameweek,
                pre_chip_squad.copy(),
                chip_predictions.copy(),
                {gw: frame.copy() for gw, frame in chip_future_predictions.items()},
                bank=bank,
                rules=rules,
                no_chip_squad=post_transfer_squad.copy(),
                no_chip_bank=post_transfer_bank,
            )
            if chip_definition is not None:
                chip_state = apply_chip(chip_state, chip_definition, gameweek, rules)
                chips_used += 1
        elif chip_mode == CHIP_MODE_BEAM:
            beam_action = beam_planner.decide(
                gameweek=gameweek,
                squad=pre_chip_squad.copy(),
                bank=bank,
                free_transfers=free_transfers,
                chip_state=chip_state,
                predictions=predictions.copy(),
                future_predictions={
                    target_gameweek: frame.copy()
                    for target_gameweek, frame in future_predictions.items()
                },
                chip_predictions=chip_predictions.copy(),
                future_chip_predictions={
                    target_gameweek: frame.copy()
                    for target_gameweek, frame in chip_future_predictions.items()
                },
                rules=rules,
                fixture_scenario=fixture_scenario,
            )
            transfer_candidate = beam_action.transfer
            chip_definition = beam_action.chip
            chip_squad = beam_action.chip_squad
            transfer_expected_horizon_gain = beam_action.transfer_expected_horizon_gain
            transfer_expected_horizon_net_gain = beam_action.transfer_expected_horizon_net_gain
            if transfer_candidate.made:
                _assert_transfer_budget(pre_chip_squad, transfer_candidate, bank)
                post_transfer_squad = _apply_benchmark_transfer(
                    pre_chip_squad, predictions, transfer_candidate
                )
                post_transfer_bank = round(
                    bank
                    + float(transfer_candidate.outgoing_price)
                    - float(transfer_candidate.incoming_price),
                    1,
                )
                post_transfer_free_transfers = max(0, free_transfers - 1)
            if chip_definition is not None:
                chip_decision = ChipDecision(
                    gameweek=gameweek,
                    chip_name=chip_definition.name,
                    chip_number=chip_definition.number,
                    expected_points=beam_action.expected_points,
                    no_chip_expected_points=beam_action.no_chip_expected_points,
                    expected_gain=(
                        beam_action.expected_horizon_points - beam_action.no_chip_horizon_points
                    ),
                    decision_status="planned",
                    reason=beam_action.reason,
                    expected_gameweek_points=beam_action.expected_points,
                    expected_horizon_points=beam_action.expected_horizon_points,
                    no_chip_horizon_points=beam_action.no_chip_horizon_points,
                    future_opportunity_cost=beam_action.future_opportunity_cost,
                    uncertainty_penalty=beam_action.uncertainty_penalty,
                    counterfactuals=tuple(
                        _beam_counterfactual(action, beam_action)
                        for action in beam_planner.last_counterfactuals
                    )
                    or (
                        ChipCounterfactual(
                            chip_key=chip_definition.key,
                            chip_number=chip_definition.number,
                            legal=True,
                            expected_gameweek_points=beam_action.expected_points,
                            no_chip_gameweek_points=beam_action.no_chip_expected_points,
                            expected_gain=(
                                beam_action.expected_horizon_points
                                - beam_action.no_chip_horizon_points
                            ),
                            status="selected",
                            reason=beam_action.reason,
                        ),
                    ),
                )
            elif beam_planner.last_counterfactuals:
                chip_decision = ChipDecision(
                    gameweek=gameweek,
                    expected_points=beam_action.expected_points,
                    no_chip_expected_points=beam_action.no_chip_expected_points,
                    expected_gameweek_points=beam_action.expected_points,
                    expected_horizon_points=beam_action.expected_horizon_points,
                    no_chip_horizon_points=beam_action.no_chip_horizon_points,
                    decision_status="not_used",
                    reason="selected no-chip control",
                    counterfactuals=tuple(
                        _beam_counterfactual(action, beam_action)
                        for action in beam_planner.last_counterfactuals
                    ),
                )
            if chip_definition is not None:
                chip_state = apply_chip(chip_state, chip_definition, gameweek, rules)
                chips_used += 1

        ordinary_transfer_allowed = not chip_replaces_ordinary_transfer(chip_definition)
        if chip_replaces_ordinary_transfer(chip_definition):
            if chip_squad is None:
                raise AssertionError("Squad-changing chip has no legal squad")
            squad, post_chip_squad = apply_squad_transition(
                pre_chip_squad, chip_squad, chip_definition
            )
            decision = _empty_decision()
        else:
            squad = post_transfer_squad
            bank = post_transfer_bank
            free_transfers = post_transfer_free_transfers
            decision = transfer_candidate
            if decision.made:
                transfers_made += 1
                total_hit_cost += decision.hit_cost

        active_squad = squad.copy()
        projections = lineup_predictions.set_index("player_id")[
            "expected_points_adjusted"
        ].to_dict()
        original_lineup = select_starting_xi(active_squad, projections)
        score = score_gameweek(active_squad, target, projections)
        captain_cache_key = (
            season,
            gameweek,
            minutes_mode,
            feature_mode,
            projection_mode,
            captain_model_name,
        )
        if captain_prediction_cache is not None and captain_cache_key in captain_prediction_cache:
            captain_predictions = captain_prediction_cache[captain_cache_key]
        else:
            captain_predictions = train_realistic_captain_predictions(
                players,
                season,
                gameweek,
                minutes_mode=minutes_mode,
                feature_mode=feature_mode,
                projection_mode=projection_mode,
                model_name=captain_model_name,
                availability_events=availability_events,
                availability_cutoff=availability_cutoff,
            )
            if captain_prediction_cache is not None:
                captain_prediction_cache[captain_cache_key] = captain_predictions
        realistic_score = score_realistic_gameweek(
            active_squad,
            target,
            projections,
            captain_predictions,
        )
        score_bench_points = bench_points_not_autosubbed(target, score.bench_ids, score.autosub_ids)
        realistic_bench_points = bench_points_not_autosubbed(
            target, original_lineup.bench_ids, realistic_score.autosub_ids
        )
        target_points = target.drop_duplicates("player_id").set_index("player_id")[
            "next_gameweek_points"
        ]
        captain_actual = float(target_points.get(score.captain_id, 0.0))
        realistic_captain_actual = realistic_score.captain_actual_points
        if realistic_score.vice_captain_fallback:
            realistic_captain_actual = realistic_score.vice_captain_actual_points
        chip_score_points = apply_chip_to_score(
            score.points,
            captain_actual,
            chip=chip_definition,
            bench_points=score_bench_points,
        )
        realistic_chip_points = apply_chip_to_score(
            realistic_score.points,
            realistic_captain_actual,
            chip=chip_definition,
            bench_points=realistic_bench_points,
        )
        no_chip_score_points = score.points
        realistic_no_chip_score_points = realistic_score.points
        if chip_replaces_ordinary_transfer(chip_definition):
            no_chip_score_points = score_gameweek(
                post_transfer_squad,
                target,
                projections,
            ).points
            realistic_no_chip_score_points = score_realistic_gameweek(
                post_transfer_squad,
                target,
                projections,
                captain_predictions,
            ).points
        chip_realized_gain = _realized_chip_gain(
            chip_definition,
            scored_points=chip_score_points,
            active_squad_base_points=score.points,
            no_chip_counterfactual_points=no_chip_score_points,
        )
        realistic_chip_realized_gain = _realized_chip_gain(
            chip_definition,
            scored_points=realistic_chip_points,
            active_squad_base_points=realistic_score.points,
            no_chip_counterfactual_points=realistic_no_chip_score_points,
        )
        chip_points += chip_realized_gain
        gross_points += chip_score_points
        total_points += chip_score_points - decision.hit_cost
        realistic_gross_points += realistic_chip_points
        realistic_total_points += realistic_chip_points - decision.hit_cost
        if chip_definition is not None and chip_definition.free_hit_reversion:
            squad = post_chip_squad
            bank = bank_before
            free_transfers = free_transfers_before
        bank_after = bank
        free_transfers_after = min(transfer_cap, free_transfers + 1)
        post_gameweek_squad_hash = _squad_hash(squad)
        active_squad_hash = _squad_hash(active_squad)
        counterfactuals = json.dumps(
            [asdict(value) for value in chip_decision.counterfactuals],
            sort_keys=True,
        )
        rows.append(
            {
                "season": season,
                "gameweek": gameweek,
                "strategy_name": strategy.name,
                "initial_squad_mode": initial_squad_mode,
                "initial_squad_version": initial_squad_version,
                "initial_squad_hash": initial_squad_hash,
                "model": target["model"].iloc[0],
                "gross_points": chip_score_points,
                "raw_starter_points": score.raw_starter_points,
                "hit_cost": decision.hit_cost,
                "hit_selected": decision.hit_cost > 0,
                "hit_break_even_cost": 4,
                "net_points": chip_score_points - decision.hit_cost,
                "cumulative_points": total_points,
                "realistic_gross_points": realistic_chip_points,
                "realistic_net_points": realistic_chip_points - decision.hit_cost,
                "realistic_cumulative_points": realistic_total_points,
                "captain_id": score.captain_id,
                "realistic_captain_id": realistic_score.captain_id,
                "realistic_vice_captain_id": realistic_score.vice_captain_id,
                "realistic_captain_predicted_points": round(
                    realistic_score.captain_predicted_points, 4
                ),
                "realistic_vice_captain_predicted_points": round(
                    realistic_score.vice_captain_predicted_points, 4
                ),
                "realistic_captain_actual_points": realistic_score.captain_actual_points,
                "realistic_vice_captain_actual_points": realistic_score.vice_captain_actual_points,
                "realistic_vice_captain_fallback": realistic_score.vice_captain_fallback,
                "squad_ids": "+".join(
                    str(value)
                    for value in squad["player_id"].astype(int).sort_values().tolist()
                ),
                "active_squad_ids": "+".join(
                    str(value)
                    for value in active_squad["player_id"].astype(int).sort_values().tolist()
                ),
                "selected_starting_ids": "+".join(
                    str(value) for value in original_lineup.starting_ids
                ),
                "selected_bench_ids": "+".join(
                    str(value) for value in original_lineup.bench_ids
                ),
                "realistic_starting_ids": "+".join(
                    str(value) for value in realistic_score.starting_ids
                ),
                "realistic_autosub_ids": "+".join(
                    str(value) for value in realistic_score.autosub_ids
                ),
                "realistic_formation": realistic_score.formation,
                "starting_ids": "+".join(str(value) for value in score.starting_ids),
                "autosub_ids": "+".join(str(value) for value in score.autosub_ids),
                "formation": score.formation,
                "transfers_made": int(decision.made),
                "outgoing_id": decision.outgoing_id,
                "incoming_id": decision.incoming_id,
                "outgoing": decision.outgoing_name,
                "incoming": decision.incoming_name,
                "projected_gain": round(decision.projected_gain, 3),
                "net_projected_gain": round(decision.net_projected_gain, 3),
                "transfer_expected_horizon_gain": round(transfer_expected_horizon_gain, 4),
                "transfer_expected_horizon_net_gain": round(transfer_expected_horizon_net_gain, 4),
                "bank_before": round(bank_before, 1),
                "free_transfers_before": free_transfers_before,
                "bank_after": round(bank_after, 1),
                "free_transfers_after": free_transfers_after,
                "training_row_count": int(target["training_row_count"].iloc[0]),
                "minutes_model_mode": target["minutes_model_mode"].iloc[0],
                "feature_mode": target["feature_mode"].iloc[0],
                "projection_mode": target["projection_mode"].iloc[0],
                "max_training_current_season_gameweek": target[
                    "max_training_current_season_gameweek"
                ].iloc[0],
                "captain_training_row_count": int(
                    captain_predictions["captain_training_row_count"].iloc[0]
                ),
                "captain_max_training_current_season_gameweek": captain_predictions[
                    "captain_max_training_current_season_gameweek"
                ].iloc[0],
                "captain_model_name": captain_predictions["captain_model_name"].iloc[0],
                "chip_model_name": chip_model_name,
                "lineup_model_name": lineup_model_name,
                "chip_mode": chip_mode,
                "hit_policy": hit_policy,
                "chip_key": chip_decision.chip_key,
                "chip_selected": chip_definition is not None,
                "chip_used": chip_decision.chip_name if chip_definition is not None else "none",
                "chip_slot": chip_decision.chip_number,
                "ordinary_transfer_allowed": ordinary_transfer_allowed,
                "ordinary_transfer_applied": decision.made,
                "squad_before_hash": squad_before_hash,
                "squad_after_hash": active_squad_hash,
                "post_gameweek_squad_hash": post_gameweek_squad_hash,
                "remaining_chips": "+".join(chip_state.remaining),
                "expected_gameweek_points": round(chip_decision.expected_gameweek_points, 4),
                "expected_horizon_points": round(chip_decision.expected_horizon_points, 4),
                "no_chip_horizon_points": round(chip_decision.no_chip_horizon_points, 4),
                "chip_expected_gain": round(chip_decision.expected_gain, 4),
                "future_opportunity_cost": round(chip_decision.future_opportunity_cost, 4),
                "uncertainty_penalty": round(chip_decision.uncertainty_penalty, 4),
                "chip_realized_gain": round(chip_realized_gain, 4),
                "realistic_chip_realized_gain": round(realistic_chip_realized_gain, 4),
                "chip_counterfactuals": counterfactuals,
                "rules_version": rules.rules_version,
                "data_cutoff": f"{season}:GW{max(0, gameweek - 1):02d}",
                **fixture_scenario.metadata(),
            }
        )
        model_context_cache.clear()
        free_transfers = free_transfers_after
        if verbose:
            print(
                f"- GW{gameweek:02d}: {score.points:.1f} gross, captain {score.captain_id}, "
                f"realistic {realistic_score.points:.1f} captain {realistic_score.captain_id}, "
                f"hit -{decision.hit_cost}, bank GBP {bank:.1f}m"
            )

    result = SeasonBenchmarkResult(
        season=season,
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        model_name=model_name,
        model_version=model_version,
        rows=pd.DataFrame(rows),
        initial_squad=initial_squad,
        final_squad=squad,
        total_points=round(total_points, 2),
        gross_points=round(gross_points, 2),
        realistic_total_points=round(realistic_total_points, 2),
        realistic_gross_points=round(realistic_gross_points, 2),
        realistic_captaincy_gap=round(total_points - realistic_total_points, 2),
        transfers_made=transfers_made,
        total_hit_cost=total_hit_cost,
        max_free_transfers=transfer_cap,
        initial_bank=initial_bank,
        final_bank=round(bank, 1),
        chip_mode=chip_mode,
        chip_points=round(chip_points, 2),
        chips_used=chips_used,
        minutes_mode=minutes_mode,
        hit_policy=hit_policy,
        initial_squad_mode=initial_squad_mode,
        initial_squad_version=initial_squad_version,
    )
    _assert_no_lookahead(result.rows, season)
    return result


def run_benchmark_suite(
    players: pd.DataFrame,
    seasons: Iterable[str] = DEFAULT_BENCHMARK_SEASONS,
    *,
    strategies: Sequence[BenchmarkStrategy] | None = None,
    model_name: str = DEFAULT_MODEL,
    model_version: str = DEFAULT_MODEL_VERSION,
    max_free_transfers: int | None = None,
    minutes_mode: str = "binary",
    feature_mode: str = "baseline",
    projection_mode: str = DEFAULT_PROJECTION_MODE,
    chip_mode: str = CHIP_MODE_DEFAULT,
    hit_policy: str = "current_gw",
    availability_events: Iterable[AvailabilityEvent] | None = None,
    availability_cutoff: datetime | str | None = None,
    verbose: bool = False,
) -> list[SeasonBenchmarkResult]:
    if minutes_mode == "availability_role" and not set(M9_MINUTES_FEATURE_COLUMNS).issubset(
        players.columns
    ):
        players = add_m9_historical_features(players)
    selected_strategies = list(
        strategies or (NoTransfersStrategy(), DeterministicTransferStrategy())
    )
    prediction_cache: dict[
        tuple[str, int, str, str, str, str],
        tuple[pd.DataFrame, pd.DataFrame | None],
    ] = {}
    captain_prediction_cache: dict[tuple[str, int, str, str, str, str], pd.DataFrame] = {}
    future_prediction_cache: dict[tuple[str, int, str, str, str, str], dict[int, pd.DataFrame]] = {}
    return [
        run_season_benchmark(
            players,
            season,
            strategy,
            model_name=model_name,
            model_version=model_version,
            max_free_transfers=max_free_transfers,
            minutes_mode=minutes_mode,
            feature_mode=feature_mode,
            projection_mode=projection_mode,
            chip_mode=chip_mode,
            hit_policy=hit_policy,
            availability_events=availability_events,
            availability_cutoff=availability_cutoff,
            verbose=verbose,
            prediction_cache=prediction_cache,
            captain_prediction_cache=captain_prediction_cache,
            future_prediction_cache=future_prediction_cache,
        )
        for season in seasons
        for strategy in selected_strategies
    ]


def append_result_to_history(
    result: SeasonBenchmarkResult,
    history_path: Path = HISTORY_PATH,
    validation_status: str = "provisional",
    variant_name: str = "baseline",
    acceptance_result: str = "not_evaluated",
    acceptance_reason: str = "",
    *,
    run_id: str | None = None,
    commit_hash: str = "unavailable",
    optimizer_version: str = OPTIMIZER_VERSION,
) -> pd.Series | None:
    """Append one result and return the latest prior same-season strategy row."""

    run_id = run_id or uuid.uuid4().hex
    if not str(run_id).strip():
        raise ValueError("run_id must be a non-empty identifier")
    key_columns = ("run_id", "variant_name", "season", "strategy_name")
    previous = None
    if history_path.exists():
        history = pd.read_csv(history_path)
        for column in HISTORY_COLUMNS:
            if column not in history.columns:
                if column == "variant_name":
                    history[column] = "baseline"
                elif column in {"commit_hash", "optimizer_version", "acceptance_reason"}:
                    history[column] = ""
                elif column == "validation_status":
                    history[column] = "provisional"
                elif column == "acceptance_result":
                    history[column] = "not_evaluated"
                else:
                    history[column] = pd.NA
        history = history[HISTORY_COLUMNS]
        populated_run_ids = history["run_id"].notna() & history["run_id"].astype(str).ne("")
        if history.loc[populated_run_ids].duplicated(list(key_columns), keep=False).any():
            raise ValueError("History contains duplicate run/variant/season/strategy rows")
        matching = history[
            (history["season"] == result.season)
            & (history["strategy_name"] == result.strategy_name)
            & (history["variant_name"] == variant_name)
        ]
        if not matching.empty:
            previous = matching.iloc[-1]
    else:
        history = pd.DataFrame(columns=HISTORY_COLUMNS)

    record = pd.DataFrame(
        [
            {
                "run_timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "run_id": run_id,
                "commit_hash": commit_hash,
                "optimizer_version": optimizer_version,
                "season": result.season,
                "strategy_name": result.strategy_name,
                "strategy_version": result.strategy_version,
                "model_name": result.model_name,
                "model_version": result.model_version,
                "variant_name": variant_name,
                "total_points": result.total_points,
                "gross_points": result.gross_points,
                "hindsight_total_points": result.total_points,
                "realistic_total_points": result.realistic_total_points,
                "realistic_gross_points": result.realistic_gross_points,
                "captaincy_gap": result.realistic_captaincy_gap,
                "acceptance_result": acceptance_result,
                "acceptance_reason": acceptance_reason,
                "transfers_made": result.transfers_made,
                "total_hit_cost": result.total_hit_cost,
                "max_free_transfers": result.max_free_transfers,
                "initial_bank": result.initial_bank,
                "final_bank": result.final_bank,
                "validation_status": validation_status,
                "chip_mode": result.chip_mode,
                "chips_used": result.chips_used,
                "chip_points": result.chip_points,
                "rules_version": build_historical_season_rules(result.season).rules_version,
                "minutes_mode": result.minutes_mode,
                "hit_policy": result.hit_policy,
            }
        ],
        columns=HISTORY_COLUMNS,
    )
    key = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "variant_name": variant_name,
                "season": result.season,
                "strategy_name": result.strategy_name,
            }
        ]
    )
    if (
        pd.concat([history[list(key_columns)], key], ignore_index=True)
        .duplicated(list(key_columns), keep=False)
        .any()
    ):
        raise ValueError("History row would duplicate run/variant/season/strategy")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([history, record], ignore_index=True)[HISTORY_COLUMNS].to_csv(
        history_path, index=False
    )
    return previous


def append_decision_rows_to_history(
    result: SeasonBenchmarkResult,
    *,
    history_path: Path = HISTORY_PATH,
    run_id: str,
    variant_name: str = "baseline",
    commit_hash: str = "unavailable",
) -> Path:
    """Persist per-Gameweek decisions and counterfactuals beside season history."""

    if not str(run_id).strip():
        raise ValueError("run_id must be a non-empty identifier")
    decision_path = history_path.with_name(f"{history_path.stem}_decisions.csv")
    rows = result.rows.copy()
    for column, value in (
        ("season", result.season),
        ("strategy_name", result.strategy_name),
    ):
        if column not in rows.columns:
            rows.insert(0, column, value)
    required_columns = {"season", "strategy_name", "gameweek"}
    missing_columns = sorted(required_columns.difference(rows.columns))
    if missing_columns:
        raise ValueError(
            "Decision rows are missing required columns: " + ", ".join(missing_columns)
        )
    rows.insert(0, "run_id", run_id)
    rows.insert(1, "variant_name", variant_name)
    rows.insert(2, "commit_hash", commit_hash)
    rows.insert(3, "decision_timestamp", datetime.now(UTC).isoformat(timespec="seconds"))
    key_columns = ["run_id", "variant_name", "season", "strategy_name", "gameweek"]
    if decision_path.exists():
        history = pd.read_csv(decision_path)
    else:
        history = pd.DataFrame()
    combined = pd.concat([history, rows], ignore_index=True, sort=False)
    if combined.duplicated(key_columns, keep=False).any():
        raise ValueError("Decision history contains duplicate run/season/strategy/gameweek rows")
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(decision_path, index=False)
    return decision_path


def get_git_commit() -> str:
    """Return the current commit when available without making metadata fatal."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return "unavailable"
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and commit else "unavailable"


def print_result_summary(result: SeasonBenchmarkResult, previous: pd.Series | None = None) -> None:
    print(
        f"{result.season} | {result.strategy_name} {result.strategy_version}: "
        f"{result.total_points:.1f} pts; {result.transfers_made} transfers; "
        f"{result.chips_used} chips; hits -{result.total_hit_cost}"
    )
    print(
        f"  Hindsight captaincy: {result.total_points:.1f} pts | "
        f"Realistic captaincy: {result.realistic_total_points:.1f} pts | "
        f"Gap: {result.realistic_captaincy_gap:+.1f} pts"
    )
    if previous is not None:
        previous_points = float(previous["total_points"])
        change = result.total_points - previous_points
        print(
            f"Previous run ({previous['run_timestamp']}): {previous_points:.1f} pts. "
            f"Change: {change:+.1f} pts"
        )


def load_max_free_transfers(
    season: str | None = None,
    path: Path = BOOTSTRAP_PATH,
) -> int:
    """Return the rule-versioned historical cap or the current cached fallback."""

    if season in HISTORICAL_MAX_FREE_TRANSFERS:
        return HISTORICAL_MAX_FREE_TRANSFERS[season]

    try:
        with path.open(encoding="utf-8") as handle:
            bootstrap = json.load(handle)
        value = int(bootstrap.get("game_settings", {}).get("max_extra_free_transfers", 0))
        return value if value > 0 else FREE_TRANSFER_CAP
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return FREE_TRANSFER_CAP


def _previous_season(players: pd.DataFrame, season: str) -> str | None:
    seasons = sorted(str(value) for value in players["season"].unique())
    previous = [value for value in seasons if value < season]
    return previous[-1] if previous else None


def _latest_prices(players: pd.DataFrame, season: str, gameweek: int) -> dict[int, float]:
    cutoff = gameweek if gameweek == 1 else gameweek - 1
    rows = players[(players["season"] == season) & (players["gameweek"] <= cutoff)]
    latest = rows.sort_values(["player_id", "gameweek"]).drop_duplicates("player_id", keep="last")
    return {int(row.player_id): float(row.price) for row in latest.itertuples()}


def _decision_price(row: pd.Series) -> float:
    value = row.get("decision_price")
    if value is not None and pd.notna(value):
        return float(value)
    return float(row["price"])


def _assert_transfer_budget(
    squad: pd.DataFrame,
    decision: TransferDecision,
    bank: float,
) -> None:
    if not decision.made:
        return
    if decision.incoming_price is None or decision.outgoing_price is None:
        raise AssertionError("A transfer decision must include incoming and outgoing prices")
    if float(decision.incoming_price) > float(decision.outgoing_price) + bank + 1e-9:
        raise AssertionError("Transfer exceeds the player's sale price plus bank")
    outgoing = squad[squad["player_id"] == decision.outgoing_id]
    if outgoing.empty:
        raise AssertionError("Transfer decision names an outgoing player outside the squad")


def _apply_benchmark_transfer(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    decision: TransferDecision,
) -> pd.DataFrame:
    """Apply a transfer after sale-price-plus-bank validation.

    Current player prices can push a squad's market value above the original
    budget after price rises. FPL's relevant transfer constraint is the incoming
    price against the outgoing sale price plus bank, so roster validation here
    checks shape and club limits without incorrectly reapplying the initial
    budget to current market values.
    """

    incoming = predictions[predictions["player_id"] == decision.incoming_id].iloc[0]
    incoming = incoming.copy()
    incoming["price"] = _decision_price(incoming)
    updated = squad[squad["player_id"] != decision.outgoing_id].copy()
    updated = pd.concat([updated, pd.DataFrame([incoming])], ignore_index=True)
    violations = validate_squad(updated, budget=float("inf"))
    if violations:
        raise ValueError(f"Transfer produced an invalid squad: {'; '.join(violations)}")
    return updated


def _assert_no_lookahead(rows: pd.DataFrame, season: str) -> None:
    for training_column in (
        "max_training_current_season_gameweek",
        "captain_max_training_current_season_gameweek",
    ):
        leakage = rows[
            rows[training_column].notna()
            & (pd.to_numeric(rows[training_column]) >= pd.to_numeric(rows["gameweek"]))
        ]
        assert leakage.empty, (
            f"No-lookahead assertion failed for {season} ({training_column}): "
            f"{leakage.to_dict('records')}"
        )


def _empty_decision() -> TransferDecision:
    return TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)


def _beam_counterfactual(beam_action: Any, selected_action: Any) -> ChipCounterfactual:
    candidate_key = beam_action.chip.key if beam_action.chip is not None else "none"
    selected_key = selected_action.chip.key if selected_action.chip is not None else "none"
    expected_gain = beam_action.expected_horizon_points - beam_action.no_chip_horizon_points
    return ChipCounterfactual(
        chip_key=candidate_key,
        chip_number=beam_action.chip.number if beam_action.chip is not None else None,
        legal=True,
        expected_gameweek_points=beam_action.expected_points,
        no_chip_gameweek_points=beam_action.no_chip_expected_points,
        expected_gain=expected_gain,
        status="selected" if candidate_key == selected_key else "rejected",
        reason=(
            selected_action.reason
            if candidate_key == selected_key
            else "rejected: another legal beam branch had higher guarded value"
        ),
        expected_horizon_points=beam_action.expected_horizon_points,
        no_chip_horizon_points=beam_action.no_chip_horizon_points,
        future_opportunity_cost=beam_action.future_opportunity_cost,
        uncertainty_penalty=beam_action.uncertainty_penalty,
    )


def _squad_hash(squad: pd.DataFrame) -> str:
    columns = [column for column in ("player_id", "team", "position", "price") if column in squad]
    records = squad[columns].copy().sort_values("player_id").to_dict("records")
    payload = json.dumps(records, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _realized_chip_gain(
    chip: ChipDefinition | None,
    *,
    scored_points: float,
    active_squad_base_points: float,
    no_chip_counterfactual_points: float,
) -> float:
    """Return direct GW gain against the correct no-chip counterfactual squad."""

    baseline = (
        no_chip_counterfactual_points
        if chip_replaces_ordinary_transfer(chip)
        else active_squad_base_points
    )
    return float(scored_points - baseline)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the permanent FPL season benchmark.")
    parser.add_argument("--seasons", nargs="+", default=list(DEFAULT_BENCHMARK_SEASONS))
    parser.add_argument(
        "--strategy",
        choices=("all", "no-transfers", "deterministic-single-transfer"),
        default="all",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=tuple(MODEL_BUILDERS))
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument(
        "--minutes-mode",
        choices=("binary", "conditional_bands", "availability_role"),
        default="binary",
    )
    parser.add_argument("--hit-policy", choices=HIT_POLICIES, default="current_gw")
    parser.add_argument("--chip-mode", choices=CHIP_MODES, default=CHIP_MODE_DEFAULT)
    parser.add_argument("--history-path", type=Path, default=HISTORY_PATH)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    players = load_historical_player_gameweeks(HISTORICAL_PLAYER_GW_PATH)
    if args.strategy == "all":
        strategies = (NoTransfersStrategy(), DeterministicTransferStrategy())
    elif args.strategy == "no-transfers":
        strategies = (NoTransfersStrategy(),)
    else:
        strategies = (DeterministicTransferStrategy(),)

    results = run_benchmark_suite(
        players,
        seasons=args.seasons,
        strategies=strategies,
        model_name=args.model,
        model_version=args.model_version,
        minutes_mode=args.minutes_mode,
        hit_policy=args.hit_policy,
        chip_mode=args.chip_mode,
        verbose=args.verbose,
    )
    run_id = uuid.uuid4().hex
    commit_hash = get_git_commit()
    for result in results:
        previous = append_result_to_history(
            result,
            args.history_path,
            run_id=run_id,
            commit_hash=commit_hash,
        )
        append_decision_rows_to_history(
            result,
            history_path=args.history_path,
            run_id=run_id,
            commit_hash=commit_hash,
        )
        print_result_summary(result, previous)
    print(f"Appended benchmark history to {args.history_path}")


if __name__ == "__main__":
    main()
