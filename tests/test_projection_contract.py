from api.projection_contract import (
    METRIC_DEFINITIONS,
    PROJECTION_CONTRACT_VERSION,
    ProjectionRecord,
)
from api.routers.predictions import _prediction_record


def test_projection_record_separates_raw_and_decision_grade_points():
    player = {
        "element_id": 101,
        "name": "Example Captain",
        "team": "MCI",
        "position": "FWD",
        "price": 15.0,
        "start_likelihood": 0.8,
        "projections": [
            {
                "gameweek": 1,
                "projected_points": 6.75,
                "blank": False,
                "double": True,
                "fixtures": [
                    {"predicted_points": 4.5, "start_likelihood": 0.9},
                    {"predicted_points": 4.0, "start_likelihood": 0.75},
                ],
            }
        ],
    }
    metadata = {
        "season": "2026-27",
        "bootstrap_hash": "bootstrap-hash",
        "rules_version": "rules-v1",
        "data_cutoff": "2026-08-17T00:00:00Z",
        "model": "Ridge Regression",
    }

    result = _prediction_record(player, 1, metadata)
    validated = ProjectionRecord.model_validate(result)

    assert validated.raw_xp == 8.5
    assert validated.expected_points == 6.75
    assert validated.start_adjusted_xp == validated.expected_points
    assert validated.captain_expected_points == 13.5
    assert validated.captaincy_score == validated.expected_points
    assert validated.start_likelihood == 0.9
    assert validated.projection_contract_version == PROJECTION_CONTRACT_VERSION


def test_projection_contract_has_no_ambiguous_predicted_points_metric():
    assert "predicted_pts" not in METRIC_DEFINITIONS
    assert "adjusted_pts" not in METRIC_DEFINITIONS
    assert "expected_points" in METRIC_DEFINITIONS
    assert "captain_rank_score" in METRIC_DEFINITIONS
