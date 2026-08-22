import pandas as pd

from fpl_intelligence.rank_players import add_rule_based_scores


def test_add_rule_based_scores_adds_expected_columns():
    players = pd.DataFrame(
        [
            {
                "player_name": "Reliable Player",
                "team_name": "Arsenal",
                "position": "Midfielder",
                "price": 10.0,
                "total_points": 200,
                "points_per_game": 6.0,
                "form": 5.0,
                "minutes": 3000,
                "selected_by_percent": 50.0,
                "value_score": 20.0,
            },
            {
                "player_name": "Rotation Player",
                "team_name": "Chelsea",
                "position": "Forward",
                "price": 5.0,
                "total_points": 50,
                "points_per_game": 3.0,
                "form": 2.0,
                "minutes": 600,
                "selected_by_percent": 5.0,
                "value_score": 10.0,
            },
        ]
    )

    ranked = add_rule_based_scores(players)

    expected_columns = {
        "minutes_security",
        "ownership_risk",
        "captain_score",
        "transfer_score",
        "defensive_contribution_per_90",
        "defensive_contribution_per_90_norm",
    }
    assert expected_columns.issubset(ranked.columns)
    assert ranked.loc[0, "minutes_security"] == 1.0
    assert ranked.loc[0, "availability_probability"] == 1.0
    assert ranked.loc[1, "ownership_risk"] == 0.95
    assert ranked.loc[0, "captain_score"] > ranked.loc[1, "captain_score"]
