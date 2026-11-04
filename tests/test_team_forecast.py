import numpy as np
import pandas as pd

from squadmetric.calibration import (
    binary_calibration_report,
    fit_probability_calibrator,
    poisson_calibration_report,
)
from squadmetric.fixture_scenarios import build_fixture_scenario
from squadmetric.team_forecast import (
    fit_team_goal_model,
    summarise_team_forecasts,
    walk_forward_team_forecasts,
)


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": "2025-26",
                "gameweek": 1,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
                "team_goals": 3,
                "opponent_goals": 0,
            },
            {
                "season": "2025-26",
                "gameweek": 1,
                "team": "B",
                "opponent_team": "A",
                "home_or_away": "A",
                "team_goals": 0,
                "opponent_goals": 3,
            },
            {
                "season": "2025-26",
                "gameweek": 2,
                "team": "A",
                "opponent_team": "C",
                "home_or_away": "A",
                "team_goals": 1,
                "opponent_goals": 1,
            },
            {
                "season": "2025-26",
                "gameweek": 2,
                "team": "C",
                "opponent_team": "A",
                "home_or_away": "H",
                "team_goals": 1,
                "opponent_goals": 1,
            },
            {
                "season": "2025-26",
                "gameweek": 3,
                "team": "B",
                "opponent_team": "C",
                "home_or_away": "H",
                "team_goals": 2,
                "opponent_goals": 2,
            },
            {
                "season": "2025-26",
                "gameweek": 3,
                "team": "C",
                "opponent_team": "B",
                "home_or_away": "A",
                "team_goals": 2,
                "opponent_goals": 2,
            },
        ]
    )


def test_team_model_deduplicates_player_perspectives_and_excludes_target_gw():
    history = _history()
    future = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "gameweek": 4,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
                "team_goals": 10,
                "opponent_goals": 0,
            }
        ]
    )
    baseline = fit_team_goal_model(
        history, cutoff_gameweek=4, season="2025-26", rules_version="bps_v1"
    )
    with_future = fit_team_goal_model(
        pd.concat([history, future]), cutoff_gameweek=4, season="2025-26", rules_version="bps_v1"
    )
    assert baseline.training_match_count == 3
    assert with_future.training_match_count == baseline.training_match_count
    fixture = {"id": 44, "event": 4, "team_h": "A", "team_a": "B", "status": "confirmed"}
    assert (
        baseline.predict_fixture(fixture).to_dict()
        == with_future.predict_fixture(fixture).to_dict()
    )


def test_fixture_forecast_has_valid_result_and_clean_sheet_probabilities():
    model = fit_team_goal_model(
        _history(),
        cutoff_gameweek=4,
        season="2025-26",
        data_cutoff="2025-08-31T00:00:00Z",
        rules_version="rules-v1",
    )
    scenario = build_fixture_scenario(
        [
            {
                "id": 44,
                "event": 4,
                "team_h": "A",
                "team_a": "B",
                "provisional_start_time": False,
                "kickoff_time": "2025-09-01T12:00:00Z",
            }
        ],
        season="2025-26",
        start_gameweek=4,
        horizon_length=3,
        data_cutoff="2025-08-31T00:00:00Z",
    )
    result = model.predict_scenario(scenario).iloc[0]
    assert np.isclose(
        result[["home_win_probability", "draw_probability", "away_win_probability"]].sum(), 1.0
    )
    assert 0.0 <= result["home_clean_sheet_probability"] <= 1.0
    assert result["data_cutoff"] == "2025-08-31T00:00:00Z"
    assert result["rules_version"] == "rules-v1"


def test_probability_calibration_reports_and_sparse_identity_are_deterministic():
    actual = np.array([0, 1, 0, 1, 1, 0] * 8)
    predicted = np.linspace(0.05, 0.95, len(actual))
    report = binary_calibration_report(actual, predicted, bins=5)
    assert report["sample_count"] == len(actual)
    assert report["reliability"]["support"].sum() == len(actual)
    calibrator = fit_probability_calibrator(
        actual, predicted, training_cutoff="2025-26:GW10", min_samples=10
    )
    assert calibrator.training_cutoff == "2025-26:GW10"
    assert np.all((calibrator.predict(predicted) >= 0) & (calibrator.predict(predicted) <= 1))
    sparse = fit_probability_calibrator(
        actual[:3], predicted[:3], training_cutoff="cutoff", min_samples=10
    )
    assert np.allclose(sparse.predict(predicted[:3]), predicted[:3])


def test_poisson_report_exposes_interval_coverage_and_error_metrics():
    report = poisson_calibration_report([0, 1, 2, 3], [0.5, 1.0, 2.0, 2.5])
    assert report["sample_count"] == 4
    assert 0.0 <= report["interval_coverage"] <= 1.0
    assert report["poisson_log_loss"] >= 0.0


def test_walk_forward_evaluation_uses_target_gameweek_only_for_scoring():
    forecasts = walk_forward_team_forecasts(_history(), season="2025-26", rules_version="bps_v1")
    assert len(forecasts) == 3
    assert forecasts["data_cutoff"].tolist() == [
        "2025-26:GW00",
        "2025-26:GW01",
        "2025-26:GW02",
    ]
    summary = summarise_team_forecasts(forecasts)
    assert summary["overall"]["fixture_count"] == 3
    assert summary["by_season"]["2025-26"]["fixture_count"] == 3
