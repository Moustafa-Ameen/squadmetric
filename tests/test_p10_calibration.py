import pandas as pd

from fpl_intelligence.p10_calibration import (
    calibrate_autosubs,
    calibrate_nonappearance_bands,
    parse_player_ids,
    scenario_players,
)


def test_parse_player_ids_handles_persisted_plus_format():
    assert parse_player_ids("1+22+333") == [1, 22, 333]
    assert parse_player_ids(float("nan")) == []


def test_autosub_calibration_excludes_bench_boost():
    decisions = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "chip_used": "none",
                "selected_bench_ids": "12+13+14+15",
                "realistic_autosub_ids": "12+14",
            },
            {
                "season": "2024-25",
                "chip_used": "none",
                "selected_bench_ids": "22+23+24+25",
                "realistic_autosub_ids": float("nan"),
            },
            {
                "season": "2024-25",
                "chip_used": "bboost",
                "selected_bench_ids": "32+33+34+35",
                "realistic_autosub_ids": "32+33+34+35",
            },
        ]
    )

    result = calibrate_autosubs(decisions)

    assert result["gameweeks"] == 2
    assert result["any_autosub_rate"] == 0.5
    assert result["mean_autosubs"] == 1.0
    assert result["mean_bench_slot_activation"] == 0.25
    assert result["bench_slot_activation"] == [0.5, 0.0, 0.5, 0.0]


def test_scoring_scenario_rescales_only_exposed_adjustment():
    players = [
        {
            "element_id": 1,
            "projections": [
                {
                    "gameweek": 1,
                    "projected_points": 4.0,
                    "fixtures": [
                        {
                            "projected_points": 4.0,
                            "start_likelihood": 0.8,
                            "scoring_regime_adjustment": {
                                "bps_v2_penalty": 0.1,
                                "role_transition_penalty": 0.4,
                            },
                            "set_piece_adjustment": {
                                "total_adjustment": 0.2,
                            },
                        }
                    ],
                }
            ],
        }
    ]

    stressed = scenario_players(
        players,
        bps_multiplier=1.5,
        role_multiplier=1.25,
        set_piece_multiplier=1.5,
    )

    assert stressed[0]["projections"][0]["projected_points"] == 3.96
    assert players[0]["projections"][0]["projected_points"] == 4.0


def test_nonappearance_calibration_uses_point_in_time_reliability_band():
    decisions = pd.DataFrame(
        [{
            "season": "2024-25",
            "gameweek": 1,
            "selected_starting_ids": "1+2",
            "realistic_starting_ids": "1+99",
        }]
    )
    history = pd.DataFrame(
        [
            {
                "season": "2024-25", "gameweek": 1, "player_id": 1,
                "position": "MID", "minutes_last_3": 270,
                "prior_games_available_last_3": 3,
            },
            {
                "season": "2024-25", "gameweek": 1, "player_id": 2,
                "position": "DEF", "minutes_last_3": 90,
                "prior_games_available_last_3": 3,
            },
        ]
    )

    result = calibrate_nonappearance_bands(decisions, history)

    assert result["by_reliability_band"]["high"]["nonappearance_rate"] == 0.0
    assert result["by_reliability_band"]["low"]["nonappearance_rate"] == 1.0
