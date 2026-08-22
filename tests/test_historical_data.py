import pandas as pd
import pytest

from fpl_intelligence.component_features import COMPONENT_TARGET_COLUMNS
from fpl_intelligence.historical_data import (
    add_rolling_features,
    build_historical_player_gameweeks,
)


def test_rolling_features_use_only_prior_gameweeks():
    gameweeks = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 1,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 10,
                "minutes": 90,
                "total_points": 5,
            },
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 1,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 3,
                "was_home": False,
                "selected": 10,
                "minutes": 10,
                "total_points": 1,
            },
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 2,
                "value": 51,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": False,
                "selected": 10,
                "minutes": 80,
                "total_points": 3,
            },
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 3,
                "value": 52,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 10,
                "minutes": 70,
                "total_points": 10,
            },
        ]
    )
    teams = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "id": 2,
                "name": "Chelsea",
                "strength_overall_home": 1200,
                "strength_overall_away": 1100,
            },
            {
                "season": "2024-25",
                "id": 3,
                "name": "Spurs",
                "strength_overall_home": 1250,
                "strength_overall_away": 1150,
            }
        ]
    )

    historical = build_historical_player_gameweeks(gameweeks, teams)
    gw1 = historical[historical["gameweek"] == 1].iloc[0]
    gw3 = historical[historical["gameweek"] == 3].iloc[0]

    assert len(historical[historical["gameweek"] == 1]) == 1
    assert gw1["minutes_last_3"] == 0
    assert gw1["points_last_3"] == 0
    assert gw1["price_before_deadline"] == 0
    assert gw1["selected_by_percent_before_deadline"] == 0
    assert gw1["market_snapshot_available"] == 0
    assert gw1["minutes"] == 100
    assert gw1["total_points"] == 6
    assert gw3["minutes_last_3"] == 180
    assert gw3["points_last_3"] == 9
    assert gw3["next_gameweek_points"] == 10
    assert gw3["price_before_deadline"] == 5.1
    gw2 = historical[historical["gameweek"] == 2].iloc[0]
    assert gw3["selected_by_percent_before_deadline"] == gw2["selected_by_percent"]
    assert gw3["market_snapshot_available"] == 1


def test_exact_duplicate_fixture_rows_are_not_double_counted():
    gameweeks = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 1,
                "fixture": 101,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 10,
                "minutes": 90,
                "total_points": 5,
            }
        ]
    )
    teams = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "id": 2,
                "name": "Chelsea",
                "strength_overall_home": 1200,
                "strength_overall_away": 1100,
            }
        ]
    )

    historical = build_historical_player_gameweeks(
        pd.concat([gameweeks, gameweeks], ignore_index=True), teams
    )

    row = historical.iloc[0]
    assert row["minutes"] == 90
    assert row["total_points"] == 5


def test_double_gameweek_ownership_uses_unique_player_gameweeks():
    rows = []
    for player_id in range(1, 16):
        rows.append(
            {
                "season": "2024-25",
                "element": player_id,
                "name": f"Test Player {player_id}",
                "GW": 1,
                "fixture": 100 + player_id,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 10,
                "minutes": 90,
                "total_points": 5,
            }
        )
    rows.append({**rows[0], "fixture": 999})
    teams = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "id": 2,
                "name": "Chelsea",
                "strength_overall_home": 1200,
                "strength_overall_away": 1100,
            }
        ]
    )

    historical = build_historical_player_gameweeks(pd.DataFrame(rows), teams)
    player = historical[historical["player_id"] == 1].iloc[0]

    assert player["minutes"] == 180
    assert player["selected_by_percent"] == 100.0


def test_missing_player_gameweek_is_not_treated_as_a_zero_row():
    gameweeks = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 1,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 10,
                "minutes": 0,
                "total_points": 0,
            },
            {
                "season": "2024-25",
                "element": 1,
                "name": "Test Player",
                "GW": 3,
                "value": 51,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 150,
                "minutes": 90,
                "total_points": 6,
            },
        ]
    )
    teams = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "id": 2,
                "name": "Chelsea",
                "strength_overall_home": 1200,
                "strength_overall_away": 1100,
            }
        ]
    )

    historical = build_historical_player_gameweeks(gameweeks, teams)
    gw3 = historical[historical["gameweek"] == 3].iloc[0]

    assert gw3["minutes_last_3"] == 0
    assert gw3["points_last_3"] == 0
    assert gw3["prior_games_available_last_3"] == 1


def test_raw_to_processed_xg_xa_values_are_aggregated_and_preserved():
    gameweeks = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "element": 1,
                "name": "Test Player",
                "GW": 1,
                "fixture": 101,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 2,
                "was_home": True,
                "selected": 10,
                "minutes": 90,
                "total_points": 5,
                "expected_goals": 0.4,
                "expected_assists": 0.1,
            },
            {
                "season": "2025-26",
                "element": 1,
                "name": "Test Player",
                "GW": 1,
                "fixture": 102,
                "value": 50,
                "position": "MID",
                "team": "Arsenal",
                "opponent_team": 3,
                "was_home": False,
                "selected": 10,
                "minutes": 45,
                "total_points": 2,
                "expected_goals": 0.6,
                "expected_assists": 0.2,
            },
        ]
    )
    teams = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "id": 2,
                "name": "Chelsea",
                "strength_overall_home": 1200,
                "strength_overall_away": 1100,
            },
            {
                "season": "2025-26",
                "id": 3,
                "name": "Spurs",
                "strength_overall_home": 1250,
                "strength_overall_away": 1150,
            },
        ]
    )

    row = build_historical_player_gameweeks(gameweeks, teams).iloc[0]
    assert row["expected_goals"] == 1.0
    assert row["expected_assists"] == pytest.approx(0.3)


def test_lagged_xg_xa_features_never_use_target_gameweek_values():
    players = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "player_id": 1,
                "gameweek": 1,
                "minutes": 90,
                "total_points": 4,
                "expected_goals": 0.4,
                "expected_assists": 0.1,
                "defensive_contribution": float("nan"),
            },
            {
                "season": "2024-25",
                "player_id": 1,
                "gameweek": 2,
                "minutes": 90,
                "total_points": 6,
                "expected_goals": 9.0,
                "expected_assists": 8.0,
                "defensive_contribution": float("nan"),
            },
        ]
    )

    features = add_rolling_features(players)
    target = features[features["gameweek"] == 2].iloc[0]
    assert target["expected_goals_last_1"] == 0.4
    assert target["expected_assists_last_1"] == 0.1
    assert target["expected_goals_last_1"] != 9.0
    assert target["expected_assists_last_1"] != 8.0


def test_lagged_component_features_never_use_target_gameweek_values():
    rows = []
    for gameweek in (1, 2):
        row = {
            "season": "2024-25",
            "player_id": 1,
            "gameweek": gameweek,
            "minutes": 90,
            "total_points": 4,
            "expected_goals": 0.0,
            "expected_assists": 0.0,
            "defensive_contribution": float("nan"),
        }
        row.update({column: float(gameweek) for column in COMPONENT_TARGET_COLUMNS})
        rows.append(row)

    features = add_rolling_features(pd.DataFrame(rows))
    target = features[features["gameweek"] == 2].iloc[0]
    for column in COMPONENT_TARGET_COLUMNS:
        assert target[f"{column}_last_1"] == 1.0
        assert target[f"{column}_last_1"] != 2.0


@pytest.mark.requires_local_artifacts
def test_processed_xg_xa_and_dc_rule_versions_cover_all_local_seasons():
    from fpl_intelligence.step4_models import load_historical_player_gameweeks

    historical = load_historical_player_gameweeks()
    xg_counts = historical.groupby("season")["expected_goals"].count()
    xa_counts = historical.groupby("season")["expected_assists"].count()
    assert (xg_counts.loc[["2023-24", "2024-25", "2025-26"]] > 0).all()
    assert (xa_counts.loc[["2023-24", "2024-25", "2025-26"]] > 0).all()
    assert historical.loc[historical["season"] != "2025-26", "dc_data_available"].eq(0).all()
    assert historical.loc[historical["season"] != "2025-26", "defensive_contribution"].isna().all()
    assert historical.loc[historical["season"] == "2025-26", "dc_data_available"].eq(1).all()
    assert historical.loc[historical["season"] != "2025-26", "bps_rule_version"].isin(
        ["bps_pre_2025_26"]
    ).all()
    assert historical.loc[historical["season"] == "2025-26", "bps_rule_version"].eq(
        "bps_v1_2025_26"
    ).all()
