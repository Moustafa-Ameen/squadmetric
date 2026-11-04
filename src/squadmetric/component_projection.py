"""M7 component-based FPL point projection.

This model predicts observable scoring components separately, then converts
their expectations into FPL points using the active position and rule regime.
It is intentionally separate from the existing total-points Ridge model so
the benchmark can compare it without silently replacing the control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

from squadmetric.component_features import (
    COMPONENT_LAG_FEATURES,
    COMPONENT_MODEL_COLUMNS,
)
from squadmetric.projection_distributions import (
    ProjectionDistribution,
    build_poisson_component_distribution,
)
from squadmetric.season_rules import historical_regime
from squadmetric.step4_models import build_preprocessor, feature_columns_for_mode

COMPONENT_PROJECTION_VERSION = "m7-components-v1"
POSITION_CODES = ("GKP", "GK", "DEF", "MID", "FWD")

GOAL_POINTS = {"GKP": 10.0, "GK": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
CLEAN_SHEET_POINTS = {"GKP": 4.0, "GK": 4.0, "DEF": 4.0, "MID": 1.0, "FWD": 0.0}


def component_feature_columns(feature_mode: str = "xg_xa") -> list[str]:
    """Return point-in-time base features plus lagged component features."""

    return [*feature_columns_for_mode(feature_mode), *COMPONENT_LAG_FEATURES]


def _position_code(value: Any) -> str:
    text = str(value or "").upper()
    if text in POSITION_CODES:
        return text
    if text in {"GOALKEEPER", "GOALKEEPERS"}:
        return "GKP"
    if text in {"DEFENDER", "DEFENDERS"}:
        return "DEF"
    if text in {"MIDFIELDER", "MIDFIELDERS"}:
        return "MID"
    if text in {"FORWARD", "FORWARDS", "STRIKER"}:
        return "FWD"
    return text


def _expected_appearance_points(minutes_probabilities: np.ndarray | None, count: int) -> np.ndarray:
    if minutes_probabilities is None:
        return np.ones(count, dtype=float)
    probabilities = np.asarray(minutes_probabilities, dtype=float)
    if probabilities.shape != (count, 3):
        raise ValueError("minutes_probabilities must have shape (rows, 3)")
    return probabilities[:, 1] + (2.0 * probabilities[:, 2])


def _expected_series(components: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric component series, including for absent optional fields."""

    if column not in components:
        return pd.Series(0.0, index=components.index)
    return pd.to_numeric(components[column], errors="coerce").fillna(0.0)


def score_expected_components(
    components: pd.DataFrame,
    positions: pd.Series,
    *,
    minutes_probabilities: np.ndarray | None = None,
    dc_rule_versions: pd.Series | None = None,
) -> np.ndarray:
    """Convert expected event/component values into expected FPL points."""

    count = len(components)
    position_codes = positions.map(_position_code).to_numpy()
    points = _expected_appearance_points(minutes_probabilities, count)

    goals = _expected_series(components, "expected_goals_scored")
    points += goals.to_numpy() * np.array([GOAL_POINTS.get(value, 0.0) for value in position_codes])
    points += _expected_series(components, "expected_assists").to_numpy() * 3.0
    clean_sheets = _expected_series(components, "expected_clean_sheets")
    points += clean_sheets.to_numpy() * np.array(
        [CLEAN_SHEET_POINTS.get(value, 0.0) for value in position_codes]
    )

    saves = _expected_series(components, "expected_saves")
    points += saves.to_numpy() / 3.0
    points += _expected_series(components, "expected_penalties_saved").to_numpy() * 5.0
    points -= _expected_series(components, "expected_penalties_missed").to_numpy() * 2.0
    points -= _expected_series(components, "expected_own_goals").to_numpy() * 2.0
    points -= _expected_series(components, "expected_yellow_cards").to_numpy()
    points -= _expected_series(components, "expected_red_cards").to_numpy() * 3.0

    conceded = _expected_series(components, "expected_goals_conceded")
    defensive_positions = np.isin(position_codes, ["GKP", "GK", "DEF"])
    points -= np.where(defensive_positions, conceded.to_numpy() / 2.0, 0.0)
    points += _expected_series(components, "expected_bonus").to_numpy()

    dc = _expected_series(components, "expected_defensive_contribution")
    if dc_rule_versions is not None:
        dc = dc.where(dc_rule_versions.astype(str).ne("pre_dc"), 0.0)
    points += dc.to_numpy()
    return np.maximum(points, 0.0)


@dataclass
class ComponentProjectionModel:
    models: dict[str, Pipeline | None]
    fallback_means: dict[str, float]
    feature_columns: list[str]
    target_bps_rule_version: str | None
    training_bps_rule_versions: tuple[str, ...]
    regime_status: str
    multi_model: Pipeline | None = None
    version: str = COMPONENT_PROJECTION_VERSION
    target_dc_rule_version: str | None = None
    training_dc_rule_versions: tuple[str, ...] = ()

    def predict_components(self, features: pd.DataFrame) -> pd.DataFrame:
        output = pd.DataFrame(index=features.index)
        if self.multi_model is not None:
            values = np.asarray(
                self.multi_model.predict(features[self.feature_columns]), dtype=float
            )
            for index, component in enumerate(COMPONENT_MODEL_COLUMNS):
                output[f"expected_{component}"] = np.maximum(values[:, index], 0.0)
            return output
        for component in COMPONENT_MODEL_COLUMNS:
            model = self.models.get(component)
            if model is None:
                values = np.full(len(features), self.fallback_means.get(component, 0.0))
            else:
                values = model.predict(features[self.feature_columns])
            output[f"expected_{component}"] = np.maximum(np.asarray(values, dtype=float), 0.0)
        return output

    def predict_distribution(
        self,
        features: pd.DataFrame,
        *,
        coverage: float = 0.8,
        data_cutoff: str = "unknown",
    ) -> ProjectionDistribution:
        """Return component expectations with explicit Poisson intervals.

        The intervals are an unadjusted event-count baseline until a declared
        held-out calibration sample is supplied. Keeping that distinction in
        ``interval_method`` prevents uncertainty from being presented as
        calibrated merely because intervals exist.
        """

        return build_poisson_component_distribution(
            self.predict_components(features),
            coverage=coverage,
            data_cutoff=data_cutoff,
            model_version=self.version,
        )

    def predict_expected_points(
        self,
        features: pd.DataFrame,
        *,
        minutes_probabilities: np.ndarray | None = None,
        dc_rule_versions: pd.Series | None = None,
    ) -> pd.DataFrame:
        components = self.predict_components(features)
        points = score_expected_components(
            components,
            features["position"],
            minutes_probabilities=minutes_probabilities,
            dc_rule_versions=dc_rule_versions,
        )
        components["component_expected_points"] = points
        components["component_model_version"] = self.version
        components["component_regime_status"] = self.regime_status
        return components


def fit_component_projection_model(
    training: pd.DataFrame,
    *,
    feature_mode: str = "xg_xa",
    target_bps_rule_version: str | None = None,
    target_dc_rule_version: str | None = None,
) -> ComponentProjectionModel:
    """Fit one point-in-time component model per scoring component."""

    feature_columns = component_feature_columns(feature_mode)
    missing = [column for column in feature_columns if column not in training.columns]
    if missing:
        raise ValueError(f"Component projection requires missing features: {', '.join(missing)}")

    matching = training
    regime_status = "unrestricted"
    if target_bps_rule_version is not None and "bps_rule_version" in training.columns:
        matching = training[training["bps_rule_version"] == target_bps_rule_version]
        if matching.empty:
            matching = training
            regime_status = "prior_regime_fallback"
        else:
            regime_status = "matched_regime"

    if target_dc_rule_version is not None and "dc_rule_version" in matching.columns:
        dc_matching = matching[matching["dc_rule_version"] == target_dc_rule_version]
        if dc_matching.empty:
            regime_status = "prior_regime_fallback"
        else:
            matching = dc_matching
            if regime_status == "unrestricted":
                regime_status = "matched_regime"

    training_regimes = tuple(
        sorted(
            str(value)
            for value in matching.get("bps_rule_version", pd.Series(dtype=str)).dropna().unique()
        )
    )
    training_dc_regimes = tuple(
        sorted(
            str(value)
            for value in matching.get("dc_rule_version", pd.Series(dtype=str)).dropna().unique()
        )
    )
    models: dict[str, Pipeline | None] = {}
    fallback_means: dict[str, float] = {}
    for component in COMPONENT_MODEL_COLUMNS:
        if component not in matching.columns:
            models[component] = None
            fallback_means[component] = 0.0
            continue
        target = pd.to_numeric(matching[component], errors="coerce")
        valid = target.notna()
        target = target.fillna(0.0)
        fallback_means[component] = float(target[valid].mean()) if valid.any() else 0.0
        models[component] = None

    multi_model: Pipeline | None = None
    if len(matching) >= 20:
        target_matrix = pd.DataFrame(
            {
                component: pd.to_numeric(
                    matching.get(component, pd.Series(index=matching.index)),
                    errors="coerce",
                ).fillna(0.0)
                for component in COMPONENT_MODEL_COLUMNS
            },
            index=matching.index,
        )
        multi_model = Pipeline(
            steps=[
                ("preprocessor", build_preprocessor(feature_columns)),
                ("model", Ridge(alpha=10.0)),
            ]
        )
        multi_model.fit(matching[feature_columns], target_matrix)

    return ComponentProjectionModel(
        models=models,
        fallback_means=fallback_means,
        feature_columns=feature_columns,
        target_bps_rule_version=target_bps_rule_version,
        training_bps_rule_versions=training_regimes,
        regime_status=regime_status,
        multi_model=multi_model,
        target_dc_rule_version=target_dc_rule_version,
        training_dc_rule_versions=training_dc_regimes,
    )


def default_dc_rule_versions(rows: pd.DataFrame) -> pd.Series:
    if "dc_rule_version" in rows.columns:
        return rows["dc_rule_version"]
    return rows.get("season", pd.Series(index=rows.index, dtype=str)).map(
        lambda season: historical_regime(str(season))["dc_rule_version"]
    )
