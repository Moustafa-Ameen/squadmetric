from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from squadmetric.availability import (
    AvailabilityEvent,
    add_m9_historical_features,
    bootstrap_availability_events,
    build_availability_features,
    events_as_of,
)


def _event(**overrides: object) -> AvailabilityEvent:
    values = {
        "player_id": 10,
        "event_type": "injury",
        "severity": "high",
        "expected_return_gameweek": 8,
        "source": "official-fpl",
        "published_at": datetime(2026, 7, 1, 10, tzinfo=UTC),
        "observed_at": datetime(2026, 7, 1, 11, tzinfo=UTC),
        "confidence": 0.9,
        "expiry": datetime(2026, 8, 31, tzinfo=UTC),
    }
    values.update(overrides)
    return AvailabilityEvent(**values)


def test_event_contract_requires_timezone_and_valid_ordering():
    with pytest.raises(ValueError, match="timezone"):
        _event(published_at=datetime(2026, 7, 1, 10))
    with pytest.raises(ValueError, match="later than observed"):
        _event(
            published_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
            observed_at=datetime(2026, 7, 1, 11, tzinfo=UTC),
        )


def test_events_as_of_excludes_future_and_expired_events():
    cutoff = datetime(2026, 7, 15, tzinfo=UTC)
    future = _event(
        published_at=cutoff + timedelta(minutes=1),
        observed_at=cutoff + timedelta(minutes=2),
    )
    expired = _event(expiry=cutoff - timedelta(minutes=1))
    visible = events_as_of([_event(), future, expired], cutoff)

    assert len(visible) == 1
    assert visible[0].player_id == 10


def test_availability_features_are_point_in_time_safe_and_neutral_when_missing():
    cutoff = datetime(2026, 7, 15, tzinfo=UTC)
    features = build_availability_features(
        [10, 20],
        [_event(), _event(player_id=10, event_type="role_change", severity="medium")],
        cutoff=cutoff,
        target_gameweek=5,
    ).set_index("player_id")

    assert features.loc[10, "availability_event_count"] == 2
    assert bool(features.loc[10, "availability_role_change_flag"])
    assert bool(features.loc[10, "availability_return_after_target"])
    assert features.loc[20, "availability_event_count"] == 0
    assert features.loc[20, "availability_severity_score"] == 0.0
    assert not bool(features.loc[20, "availability_known_unavailable"])


def test_mapping_round_trip_preserves_source_and_timestamps():
    event = _event()
    restored = AvailabilityEvent.from_mapping(event.to_record())

    assert restored == event


def test_bootstrap_adapter_preserves_official_status_and_ignores_available_players():
    observed_at = datetime(2026, 7, 15, 12, tzinfo=UTC)
    events = bootstrap_availability_events(
        [
            {
                "id": 10,
                "status": "i",
                "chance_of_playing_next_round": 25,
                "news": "Hamstring injury",
                "news_added": "2026-07-15T10:00:00Z",
            },
            {
                "id": 20,
                "status": "s",
                "chance_of_playing_next_round": 0,
                "news": "Suspended",
            },
            {"id": 30, "status": "a", "chance_of_playing_next_round": 100, "news": ""},
        ],
        observed_at=observed_at,
    )

    assert [(event.player_id, event.event_type, event.severity) for event in events] == [
        (10, "injury", "high"),
        (20, "suspension", "critical"),
    ]
    assert all(event.source == "fpl_bootstrap" for event in events)


def test_historical_role_features_are_strictly_prior_only():
    players = pd.DataFrame(
        [
            {"season": "2024-25", "player_id": 1, "gameweek": 1, "minutes": 90, "starts": 1},
            {"season": "2024-25", "player_id": 1, "gameweek": 2, "minutes": 0, "starts": 0},
            {"season": "2024-25", "player_id": 1, "gameweek": 3, "minutes": 60, "starts": 1},
        ]
    )
    mutated = players.copy()
    mutated.loc[mutated["gameweek"] == 3, ["minutes", "starts"]] = [90, 1]

    original_features = add_m9_historical_features(players)
    mutated_features = add_m9_historical_features(mutated)
    target_original = original_features[original_features["gameweek"] == 3].iloc[0]
    target_mutated = mutated_features[mutated_features["gameweek"] == 3].iloc[0]

    assert target_original["starts_last_3"] == target_mutated["starts_last_3"] == 1
    assert target_original["minutes_mean_last_5"] == target_mutated["minutes_mean_last_5"] == 45
    assert target_original["zero_minutes_rate_last_5"] == target_mutated[
        "zero_minutes_rate_last_5"
    ] == 0.5
