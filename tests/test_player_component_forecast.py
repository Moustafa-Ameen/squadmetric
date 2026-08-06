import numpy as np
import pandas as pd
import pytest

from fpl_intelligence.player_component_forecast import build_player_fixture_components


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fixture_id": "fx-1",
                "gameweek": 5,
                "home_team": "Alpha",
                "away_team": "Beta",
                "expected_home_goals": 2.0,
                "expected_away_goals": 1.0,
                "home_clean_sheet_probability": 0.35,
                "away_clean_sheet_probability": 0.20,
            }
        ]
    )


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "player_name": "Alpha Forward",
                "season": "2025-26",
                "gameweek": 5,
                "team": "Alpha",
                "opponent_team": "Beta",
                "position": "FWD",
                "home_or_away": "H",
                "expected_goals_last_3": 2.0,
                "expected_assists_last_3": 1.0,
                "expected_goals": 99.0,
                "expected_assists": 99.0,
                "dc_rule_version": "dc_v1",
                "defensive_contribution_last_3": 3.0,
            },
            {
                "player_id": 2,
                "player_name": "Alpha Defender",
                "season": "2025-26",
                "gameweek": 5,
                "team": "Alpha",
                "opponent_team": "Beta",
                "position": "DEF",
                "home_or_away": "H",
                "expected_goals_last_3": 0.5,
                "expected_assists_last_3": 0.5,
                "expected_goals": 88.0,
                "expected_assists": 88.0,
                "dc_rule_version": "dc_v1",
                "defensive_contribution_last_3": 6.0,
            },
        ]
    )


def test_player_bridge_uses_lagged_rates_and_fixture_context_only():
    players = _players()
    baseline = build_player_fixture_components(
        players,
        _fixtures(),
        appearance_probabilities=np.array([0.8, 0.9]),
        data_cutoff="2025-26:GW04",
        rules_version="rules-v1",
    )
    changed_target = players.copy()
    changed_target["expected_goals"] = 0.0
    changed_target["expected_assists"] = 0.0
    changed = build_player_fixture_components(
        changed_target,
        _fixtures(),
        appearance_probabilities=np.array([0.8, 0.9]),
        data_cutoff="2025-26:GW04",
        rules_version="rules-v1",
    )
    component_columns = ["expected_goals_scored", "expected_assists", "expected_clean_sheets"]
    assert np.allclose(baseline[component_columns], changed[component_columns])
    assert baseline.loc[1, "expected_clean_sheets"] == pytest.approx(0.35 * 0.9)
    assert baseline.loc[1, "expected_defensive_contribution"] > 0
    assert baseline["model_version"].eq("m10-player-components-v1").all()


def test_player_bridge_requires_visible_fixture_match_and_respects_pre_dc():
    players = _players()
    players.loc[1, "dc_rule_version"] = "pre_dc"
    result = build_player_fixture_components(players, _fixtures())
    assert result.loc[1, "expected_defensive_contribution"] == 0.0
    with pytest.raises(ValueError, match="Every player row"):
        build_player_fixture_components(players.assign(gameweek=6), _fixtures())
