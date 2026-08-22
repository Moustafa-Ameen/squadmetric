import pandas as pd

from fpl_intelligence.fixture_scenarios import build_fixture_scenario
from fpl_intelligence.multi_gw_projection import (
    _fpl_difficulty,
    _model_opponent_strength,
    project_player,
)


class StrengthSensitivePointsModel:
    def predict(self, features: pd.DataFrame):
        return 20 - features["opponent_strength"].to_numpy() / 100


class AlwaysStartsModel:
    def predict_proba(self, features: pd.DataFrame):
        return [[0.0, 1.0] for _ in range(len(features))]


def test_live_fdr_is_mapped_to_the_historical_model_strength_scale():
    assert _model_opponent_strength(1) == 1000.0
    assert _model_opponent_strength(3) == 1150.0
    assert _model_opponent_strength(5) == 1300.0
    assert _model_opponent_strength(1200) == 1200.0
    assert _model_opponent_strength(None) == 1150.0

    assert _fpl_difficulty(1) == 1
    assert _fpl_difficulty(5) == 5
    assert _fpl_difficulty(1200) is None


def test_projection_handles_single_blank_double_and_fixture_strength():
    projections = project_player(
        10,
        1,
        3,
        players=[
            {
                "element_id": 10,
                "name": "Example Midfielder",
                "team_id": 1,
                "position": "MID",
                "price": 6.0,
                "selected_by_percent": 12.0,
                "minutes_last_3": 270,
                "points_last_3": 18,
            }
        ],
        fixtures=[
            {
                "event": 1,
                "team_h": 1,
                "team_a": 2,
                "team_a_short": "EAS",
                "opponent_strength": 900,
            },
            {
                "event": 3,
                "team_h": 1,
                "team_a": 3,
                "team_a_short": "MED",
                "opponent_strength": 1200,
            },
            {
                "event": 3,
                "team_h": 4,
                "team_a": 1,
                "team_h_short": "HAR",
                "opponent_strength": 1600,
            },
        ],
        teams=[
            {"id": 2, "name": "Easy FC", "short_name": "EAS"},
            {"id": 3, "name": "Medium FC", "short_name": "MED"},
            {"id": 4, "name": "Hard FC", "short_name": "HAR"},
        ],
        models=(StrengthSensitivePointsModel(), AlwaysStartsModel()),
    )

    assert projections[0]["gameweek"] == 1
    assert projections[0]["blank"] is False
    assert projections[0]["double"] is False
    assert projections[0]["fixtures"][0]["opponent"] == "EAS"
    assert projections[0]["fixtures"][0]["opponent_difficulty"] is None
    assert projections[0]["projected_points"] == 11.0

    assert projections[1] == {
        "gameweek": 2,
        "projected_points": 0.0,
        "blank": True,
        "double": False,
        "fixtures": [],
    }

    assert projections[2]["double"] is True
    assert len(projections[2]["fixtures"]) == 2
    assert projections[2]["projected_points"] == 12.0
    assert projections[0]["projected_points"] != projections[2]["projected_points"]


def test_projection_can_carry_fixture_scenario_identity_and_status():
    fixtures = [
        {
            "id": 1,
            "event": 1,
            "team_h": 1,
            "team_a": 2,
            "team_a_short": "EAS",
            "opponent_strength": 900,
            "kickoff_time": "2026-08-15T12:30:00Z",
            "provisional_start_time": False,
        }
    ]
    scenario = build_fixture_scenario(
        fixtures, season="2026-27", start_gameweek=1, horizon_length=3
    )
    projections = project_player(
        10,
        1,
        3,
        players=[
            {
                "element_id": 10,
                "name": "Example Midfielder",
                "team_id": 1,
                "position": "MID",
                "price": 6.0,
            }
        ],
        fixtures=fixtures,
        teams=[{"id": 2, "name": "Easy FC", "short_name": "EAS"}],
        models=(StrengthSensitivePointsModel(), AlwaysStartsModel()),
        fixture_scenario=scenario,
    )

    assert projections[0]["fixture_scenario_id"] == scenario.scenario_id
    assert projections[0]["fixture_data_hash"] == scenario.fixture_data_hash
    assert projections[0]["fixture_confirmed_count"] == 1
    assert projections[0]["fixtures"][0]["status"] == "confirmed"


def test_live_role_evidence_and_availability_adjust_projected_points():
    projections = project_player(
        10,
        1,
        3,
        players=[
            {
                "element_id": 10,
                "name": "Promoted Defender",
                "team_id": 1,
                "position": "DEF",
                "price": 4.0,
                "start_likelihood": 0.6,
                "availability_probability": 0.25,
                "prior_source": "launch_evidence:official_scout_analysis",
            }
        ],
        fixtures=[
            {
                "event": 1,
                "team_h": 1,
                "team_a": 2,
                "team_a_short": "EAS",
                "opponent_strength": 900,
            }
        ],
        teams=[{"id": 2, "name": "Easy FC", "short_name": "EAS"}],
        models=(StrengthSensitivePointsModel(), AlwaysStartsModel()),
    )

    assert projections[0]["fixtures"][0]["start_likelihood"] == 0.25
    assert projections[0]["projected_points"] == 2.75
