from squadmetric.fetch_fpl import load_players


def test_load_players_adds_display_columns():
    bootstrap_data = {
        "elements": [
            {
                "id": 1,
                "first_name": "Mohamed",
                "second_name": "Salah",
                "team": 1,
                "element_type": 3,
                "now_cost": 140,
                "web_name": "Salah",
                "total_points": 280,
                "points_per_game": "7.4",
                "form": "8.1",
                "minutes": 3100,
                "selected_by_percent": "55.0",
                "defensive_contribution": 42,
                "defensive_contribution_per_90": 5.2,
            }
        ],
        "teams": [{"id": 1, "name": "Liverpool", "short_name": "LIV"}],
        "element_types": [{"id": 3, "singular_name": "Midfielder", "singular_name_short": "MID"}],
    }

    players = load_players(bootstrap_data)

    assert players.loc[0, "player_name"] == "Mohamed Salah"
    assert players.loc[0, "team_name"] == "Liverpool"
    assert players.loc[0, "position"] == "Midfielder"
    assert players.loc[0, "element_id"] == 1
    assert players.loc[0, "team_id"] == 1
    assert players.loc[0, "position_id"] == 3
    assert players.loc[0, "price"] == 14.0
    assert players.loc[0, "value_score"] == 20.0
    assert players.loc[0, "defensive_contribution_per_90"] == 5.2
