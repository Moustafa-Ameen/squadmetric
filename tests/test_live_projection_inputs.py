import pandas as pd
from api import live_projection_service


def test_current_player_rows_apply_live_official_availability(monkeypatch):
    monkeypatch.setattr(
        live_projection_service.data_service,
        "players",
        lambda: pd.DataFrame(
            [
                {
                    "element_id": 1,
                    "minutes_security": 0.95,
                    "availability_probability": 1.0,
                    "prior_source": "historical_match",
                }
            ]
        ),
    )
    bootstrap = {
        "teams": [{"id": 1, "name": "Test FC", "short_name": "TST"}],
        "element_types": [{"id": 3, "singular_name_short": "MID"}],
        "elements": [
            {
                "id": 1,
                "first_name": "Test",
                "second_name": "Player",
                "team": 1,
                "element_type": 3,
                "now_cost": 55,
                "status": "d",
                "chance_of_playing_next_round": 25,
            }
        ],
    }

    row = live_projection_service.current_player_rows(bootstrap)[0]

    assert row["availability_probability"] == 0.25
    assert row["start_likelihood"] == 0.95
