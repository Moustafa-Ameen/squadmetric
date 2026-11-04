import numpy as np
import pandas as pd

from squadmetric.component_features import COMPONENT_TARGET_COLUMNS
from squadmetric.component_projection import (
    component_feature_columns,
    fit_component_projection_model,
    score_expected_components,
)


def _training_rows(count: int = 32) -> pd.DataFrame:
    rows = []
    features = component_feature_columns("xg_xa")
    for index in range(count):
        row = {column: float((index + 1) % 5) for column in features}
        row["position"] = ("MID", "GK", "DEF", "FWD")[index % 4]
        row["bps_rule_version"] = "bps_v1_2025_26" if index % 2 else "bps_pre_2025_26"
        row["dc_rule_version"] = "dc_v1" if index % 2 else "pre_dc"
        row["season"] = "2025-26"
        for component_index, component in enumerate(COMPONENT_TARGET_COLUMNS):
            row[component] = float((index + component_index) % 3) / 2.0
        row["defensive_contribution"] = float(index % 4)
        rows.append(row)
    return pd.DataFrame(rows)


def test_component_projection_is_nonnegative_and_regime_aware():
    training = _training_rows()
    model = fit_component_projection_model(
        training,
        feature_mode="xg_xa",
        target_bps_rule_version="bps_v1_2025_26",
    )
    prediction = model.predict_expected_points(training.iloc[:4])

    assert (prediction.filter(like="expected_") >= 0).all().all()
    assert model.regime_status == "matched_regime"
    assert model.training_bps_rule_versions == ("bps_v1_2025_26",)

    dc_model = fit_component_projection_model(
        training,
        feature_mode="xg_xa",
        target_bps_rule_version="bps_v1_2025_26",
        target_dc_rule_version="dc_v1",
    )
    assert dc_model.target_dc_rule_version == "dc_v1"
    assert dc_model.training_dc_rule_versions == ("dc_v1",)

    fallback = fit_component_projection_model(
        training,
        feature_mode="xg_xa",
        target_bps_rule_version="bps_v2_future",
    )
    assert fallback.regime_status == "prior_regime_fallback"
    assert set(fallback.training_bps_rule_versions) == {
        "bps_pre_2025_26",
        "bps_v1_2025_26",
    }


def test_component_scoring_uses_position_rules_and_hides_pre_dc():
    components = pd.DataFrame(
        [
            {
                "expected_goals_scored": 1.0,
                "expected_assists": 1.0,
                "expected_clean_sheets": 1.0,
                "expected_bonus": 3.0,
                "expected_defensive_contribution": 5.0,
            },
            {
                "expected_saves": 6.0,
                "expected_clean_sheets": 1.0,
                "expected_bonus": 1.0,
                "expected_defensive_contribution": 5.0,
            },
        ]
    )
    positions = pd.Series(["MID", "GK"])
    minutes = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])

    points = score_expected_components(
        components,
        positions,
        minutes_probabilities=minutes,
        dc_rule_versions=pd.Series(["pre_dc", "dc_v1"]),
    )

    assert points[0] == 14.0
    assert points[1] == 2.0 + (6.0 / 3.0) + 4.0 + 1.0 + 5.0
