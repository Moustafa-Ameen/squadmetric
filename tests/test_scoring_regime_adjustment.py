from fpl_intelligence.scoring_regime_adjustment import bps_v2_adjustment


def test_bps_v2_adjustment_penalises_dc_bonus_overlap_without_changing_threshold():
    player = {
        "position": "MID",
        "team_name": "Man City",
        "previous_minutes": 3332,
        "previous_starts": 37,
        "previous_bonus": 16,
        "previous_cbi": 106,
        "previous_tackles": 103,
        "previous_recoveries": 306,
    }

    result = bps_v2_adjustment(player, {"prior_team": "Nott'm Forest"})

    assert result.team_changed
    assert result.dc_actions_per_90 > 12
    assert result.bps_v2_penalty > 0
    assert result.role_transition_penalty > 0
    assert result.total_penalty <= 0.85


def test_unchanged_team_has_no_role_transition_penalty():
    player = {
        "position": "DEF",
        "team_name": "Everton",
        "previous_minutes": 3330,
        "previous_starts": 37,
        "previous_bonus": 12,
        "previous_cbi": 325,
        "previous_tackles": 51,
        "previous_recoveries": 90,
    }

    result = bps_v2_adjustment(player, {"prior_team": "Everton"})

    assert not result.team_changed
    assert result.role_transition_penalty == 0
    assert result.bps_v2_penalty > 0
