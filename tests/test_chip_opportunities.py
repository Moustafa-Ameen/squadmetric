from api.chip_opportunities import build_chip_opportunities


def _bootstrap():
    teams = [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Beta"},
        {"id": 3, "name": "Gamma"},
        {"id": 4, "name": "Delta"},
    ]
    elements = [
        {
            "id": 1,
            "web_name": "Star",
            "team": 1,
            "element_type": 4,
            "minutes": 270,
            "status": "a",
            "expected_goal_involvements_per_90": "0.90",
            "form": "8.0",
        },
        {
            "id": 2,
            "web_name": "Keeper",
            "team": 1,
            "element_type": 1,
            "minutes": 270,
            "expected_goals_conceded_per_90": "1.00",
            "goals_conceded_per_90": "1.00",
        },
        {
            "id": 3,
            "web_name": "Weak Keeper",
            "team": 2,
            "element_type": 1,
            "minutes": 270,
            "expected_goals_conceded_per_90": "2.50",
            "goals_conceded_per_90": "2.00",
        },
        {
            "id": 4,
            "web_name": "Budget One",
            "team": 3,
            "element_type": 2,
            "minutes": 270,
            "status": "a",
        },
        {
            "id": 5,
            "web_name": "Budget Two",
            "team": 3,
            "element_type": 3,
            "minutes": 270,
            "status": "a",
        },
        {
            "id": 6,
            "web_name": "Budget Three",
            "team": 4,
            "element_type": 4,
            "minutes": 270,
            "status": "a",
        },
    ]
    return {"teams": teams, "elements": elements}


def _projected_players():
    players = [
        (1, "Star", "FWD", 1, 9.0, 8.0),
        (2, "Keeper", "GKP", 1, 4.5, 3.0),
        (4, "Budget One", "DEF", 3, 4.5, 3.5),
        (5, "Budget Two", "MID", 3, 5.0, 3.4),
        (6, "Budget Three", "FWD", 4, 5.5, 3.3),
    ]
    output = []
    for player_id, name, position, team_id, price, points in players:
        projections = []
        for gameweek in (5, 6, 7):
            opponent = "Beta" if player_id == 1 else "Alpha"
            projections.append(
                {
                    "gameweek": gameweek,
                    "projected_points": points if gameweek == 6 else points - 1,
                    "blank": False,
                    "double": False,
                    "fixtures": [
                        {
                            "opponent_name": opponent,
                            "home": True,
                            "start_likelihood": 0.9,
                        }
                    ],
                }
            )
        output.append(
            {
                "element_id": player_id,
                "name": name,
                "position": position,
                "team_id": team_id,
                "price": price,
                "projections": projections,
            }
        )
    return output


def _fixtures(*, blank_gameweek: int | None = None):
    rows = []
    for gameweek in (5, 6, 7):
        rows.append(
            {
                "event": gameweek,
                "team_h": 1,
                "team_a": 2,
                "team_h_difficulty": 2,
                "team_a_difficulty": 4,
            }
        )
        if gameweek != blank_gameweek:
            rows.append(
                {
                    "event": gameweek,
                    "team_h": 3,
                    "team_a": 4,
                    "team_h_difficulty": 3,
                    "team_a_difficulty": 3,
                }
            )
    return rows


def test_opportunities_are_league_wide_and_chip_specific():
    opportunities = build_chip_opportunities(
        _bootstrap(),
        _fixtures(),
        _projected_players(),
        target_gameweek=5,
    )
    by_chip = {row["chip_type"]: row for row in opportunities}

    assert set(by_chip) == {"3xc", "bboost", "freehit", "wildcard"}
    assert by_chip["3xc"]["recommended_gameweek"] == 6
    assert "Star against Beta" in by_chip["3xc"]["headline"]
    assert by_chip["bboost"]["primary_candidate"]["projected_bench_points"] > 0
    assert by_chip["freehit"]["recommended_gameweek"] is None


def test_free_hit_requires_a_published_blank_or_double_gameweek():
    opportunities = build_chip_opportunities(
        _bootstrap(),
        _fixtures(blank_gameweek=6),
        _projected_players(),
        target_gameweek=5,
    )
    free_hit = next(row for row in opportunities if row["chip_type"] == "freehit")

    assert free_hit["recommended_gameweek"] == 6
    assert set(free_hit["primary_candidate"]["blank_teams"]) == {"Gamma", "Delta"}
