import pandas as pd
import pytest

from squadmetric.fixture_scenarios import (
    build_fixture_scenario,
    build_historical_fixture_scenario,
)


def _fixtures():
    return [
        {
            "id": 101,
            "event": 1,
            "team_h": 1,
            "team_a": 2,
            "kickoff_time": "2026-08-15T12:30:00Z",
            "provisional_start_time": False,
        },
        {
            "id": 102,
            "event": 3,
            "original_event": 2,
            "team_h": 1,
            "team_a": 3,
            "kickoff_time": None,
            "provisional_start_time": True,
        },
        {
            "id": 103,
            "event": None,
            "original_event": 3,
            "team_h": 2,
            "team_a": 3,
            "postponed": True,
        },
    ]


def test_fixture_scenario_is_hashed_and_classifies_schedule_states():
    first = build_fixture_scenario(
        _fixtures(), season="2026-27", start_gameweek=1, horizon_length=3
    )
    second = build_fixture_scenario(
        list(reversed(_fixtures())),
        season="2026-27",
        start_gameweek=1,
        horizon_length=3,
    )

    assert first.fixture_data_hash == second.fixture_data_hash
    assert first.scenario_id == second.scenario_id
    assert first.metadata()["fixture_confirmed_count"] == 1
    assert first.metadata()["fixture_rescheduled_count"] == 1
    assert first.metadata()["fixture_postponed_count"] == 1
    assert first.team_summary(1) == {
        "fixture_count": 2,
        "blank_gameweeks": 1,
        "double_gameweeks": 0,
    }


def test_fixture_hash_changes_when_schedule_payload_changes():
    baseline = build_fixture_scenario(
        _fixtures(), season="2026-27", start_gameweek=1, horizon_length=3
    )
    changed = _fixtures()
    changed[0]["team_a"] = 4
    updated = build_fixture_scenario(
        changed, season="2026-27", start_gameweek=1, horizon_length=3
    )

    assert baseline.fixture_data_hash != updated.fixture_data_hash


def test_historical_schedule_scenario_uses_schedule_fields_only():
    players = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "gameweek": 1,
                "team": "Alpha",
                "opponent_team": "Beta",
                "home_or_away": "H",
                "opponent_strength": 1000,
                "total_points": 99,
            },
            {
                "season": "2024-25",
                "gameweek": 2,
                "team": "Alpha",
                "opponent_team": "Gamma",
                "home_or_away": "A",
                "opponent_strength": 1200,
                "total_points": 999,
            },
        ]
    )
    scenario = build_historical_fixture_scenario(
        players, season="2024-25", start_gameweek=1, horizon_length=3
    )

    assert len(scenario.fixtures) == 2
    assert scenario.team_summary("Alpha")["fixture_count"] == 2
    assert all("total_points" not in fixture for fixture in scenario.fixtures)


def test_raw_historical_rows_deduplicate_both_team_perspectives():
    raw = pd.DataFrame(
        [
            {
                "GW": 1,
                "fixture": 10,
                "team": "Alpha",
                "opponent_team": 2,
                "was_home": True,
                "kickoff_time": "2024-08-01T12:00:00Z",
            },
            {
                "GW": 1,
                "fixture": 10,
                "team": "Beta",
                "opponent_team": 1,
                "was_home": False,
                "kickoff_time": "2024-08-01T12:00:00Z",
            },
        ]
    )
    teams = pd.DataFrame({"id": [1, 2], "name": ["Alpha", "Beta"]})
    scenario = build_historical_fixture_scenario(
        pd.DataFrame(),
        season="2024-25",
        start_gameweek=1,
        horizon_length=3,
        raw_fixture_rows=raw,
        historical_teams=teams,
    )

    assert len(scenario.fixtures) == 1
    assert scenario.team_summary("Alpha")["fixture_count"] == 1
    assert scenario.team_summary("Beta")["fixture_count"] == 1


def test_fixture_scenario_rejects_unsupported_horizon():
    with pytest.raises(ValueError, match="horizon_length"):
        build_fixture_scenario(
            _fixtures(), season="2026-27", start_gameweek=1, horizon_length=6
        )
