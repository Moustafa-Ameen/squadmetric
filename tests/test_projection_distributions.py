import numpy as np
import pandas as pd
import pytest

from fpl_intelligence.component_features import COMPONENT_TARGET_COLUMNS
from fpl_intelligence.component_projection import (
    component_feature_columns,
    fit_component_projection_model,
)
from fpl_intelligence.projection_distributions import (
    build_empirical_component_distribution,
    build_poisson_component_distribution,
    fit_empirical_interval_calibrator,
)


def test_poisson_distribution_is_nonnegative_and_auditable():
    expected = pd.DataFrame({"expected_goals_scored": [0.2, 1.5]})
    result = build_poisson_component_distribution(
        expected,
        coverage=0.8,
        data_cutoff="2025-26:GW10",
        model_version="m10-test",
    )
    assert result.interval_method == "poisson_central_interval_unadjusted"
    assert result.data_cutoff == "2025-26:GW10"
    assert (result.lower >= 0).all().all()
    assert (result.upper >= result.lower).all().all()
    assert result.to_frame().shape[1] == 3


def test_empirical_distribution_requires_declared_matching_calibration_sample():
    expected = pd.DataFrame({"expected_assists": [1.0, 1.0, 1.0, 1.0]})
    actual = pd.DataFrame({"expected_assists": [0.0, 1.0, 2.0, 3.0]})
    result = build_empirical_component_distribution(
        expected, actual, coverage=0.8, data_cutoff="held-out-before-cutoff"
    )
    assert result.interval_method == "empirical_residual_interval"
    assert (result.upper["expected_assists"] >= result.lower["expected_assists"]).all()


def test_held_out_calibrator_can_be_applied_to_a_later_cutoff():
    expected = pd.DataFrame({"expected_goals_scored": np.ones(24)})
    actual = pd.DataFrame({"expected_goals_scored": np.arange(24) % 4})
    calibrator = fit_empirical_interval_calibrator(
        expected,
        actual,
        coverage=0.8,
        calibration_cutoff="2025-26:GW20",
        model_version="m10-test",
    )
    result = calibrator.apply(
        pd.DataFrame({"expected_goals_scored": [0.5, 2.0]}),
        data_cutoff="2025-26:GW25",
    )
    assert calibrator.sample_count == 24
    assert result.calibration_cutoff == "2025-26:GW20"
    assert result.data_cutoff == "2025-26:GW25"
    assert result.interval_method == "heldout_empirical_residual_interval"
    assert result.coverage == pytest.approx(0.8)


def test_component_model_distribution_is_opt_in_and_does_not_change_point_predictions():
    rows = []
    features = component_feature_columns("xg_xa")
    for index in range(32):
        row = {column: float((index + 1) % 5) for column in features}
        row["position"] = ("MID", "GK", "DEF", "FWD")[index % 4]
        row["bps_rule_version"] = "bps_v1_2025_26"
        row["dc_rule_version"] = "dc_v1"
        for component_index, component in enumerate(COMPONENT_TARGET_COLUMNS):
            row[component] = float((index + component_index) % 3) / 2.0
        row["defensive_contribution"] = float(index % 4)
        rows.append(row)
    training = pd.DataFrame(rows)
    model = fit_component_projection_model(
        training, feature_mode="xg_xa", target_bps_rule_version="bps_v1_2025_26"
    )
    expected = model.predict_components(training.iloc[:3])
    distribution = model.predict_distribution(training.iloc[:3], data_cutoff="2025-26:GW10")
    assert np.allclose(expected.to_numpy(), distribution.expected.to_numpy())
    assert distribution.model_version == model.version
    assert distribution.data_cutoff == "2025-26:GW10"
