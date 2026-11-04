"""Point-in-time availability events and minutes-risk features.

This module deliberately does not fetch or interpret news. Sources and an
optional extraction layer can create :class:`AvailabilityEvent` values, while
the benchmark consumes only events observed by its deadline cutoff. That
boundary keeps injury, suspension, lineup, and role information auditable and
prevents future news from entering historical decisions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

EVENT_TYPES = frozenset(
    {
        "injury",
        "illness",
        "suspension",
        "international_duty",
        "official_status",
        "press_conference",
        "club_announcement",
        "confirmed_lineup",
        "rotation",
        "role_change",
        "manager_change",
        "new_signing",
    }
)
SEVERITIES = frozenset({"low", "medium", "high", "critical"})
SEVERITY_SCORE = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
ROLE_FEATURE_COLUMNS = (
    "starts_last_3",
    "minutes_mean_last_5",
    "minutes_std_last_5",
    "zero_minutes_rate_last_5",
    "starts_rate_last_5",
)
AVAILABILITY_FEATURE_COLUMNS = (
    "availability_event_count",
    "availability_risk_event_count",
    "availability_role_event_count",
    "availability_severity_score",
    "availability_confidence_max",
    "availability_return_after_target",
    "availability_role_change_flag",
    "availability_known_unavailable",
)
M9_MINUTES_FEATURE_COLUMNS = ROLE_FEATURE_COLUMNS + AVAILABILITY_FEATURE_COLUMNS


def _parse_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Availability timestamps must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class AvailabilityEvent:
    """A source-attributed player availability or role event."""

    player_id: int
    event_type: str
    severity: str
    expected_return_gameweek: int | None
    source: str
    published_at: datetime
    observed_at: datetime
    confidence: float
    expiry: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "published_at", _parse_timestamp(self.published_at))
        object.__setattr__(self, "observed_at", _parse_timestamp(self.observed_at))
        if self.expiry is not None:
            object.__setattr__(self, "expiry", _parse_timestamp(self.expiry))
        self.validate()

    def validate(self) -> None:
        if self.player_id <= 0:
            raise ValueError("player_id must be positive")
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown availability event type: {self.event_type}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"Unknown availability severity: {self.severity}")
        if not str(self.source).strip():
            raise ValueError("source is required for availability events")
        if self.published_at > self.observed_at:
            raise ValueError("published_at cannot be later than observed_at")
        if self.expiry is not None and self.expiry < self.observed_at:
            raise ValueError("expiry cannot be earlier than observed_at")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.expected_return_gameweek is not None and self.expected_return_gameweek < 1:
            raise ValueError("expected_return_gameweek must be positive when supplied")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AvailabilityEvent:
        return cls(
            player_id=int(value["player_id"]),
            event_type=str(value["event_type"]),
            severity=str(value["severity"]),
            expected_return_gameweek=(
                int(value["expected_return_gameweek"])
                if value.get("expected_return_gameweek") is not None
                else None
            ),
            source=str(value["source"]),
            published_at=_parse_timestamp(value["published_at"]),
            observed_at=_parse_timestamp(value["observed_at"]),
            confidence=float(value["confidence"]),
            expiry=(
                _parse_timestamp(value["expiry"])
                if value.get("expiry") is not None
                else None
            ),
        )

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        for key in ("published_at", "observed_at", "expiry"):
            if record[key] is not None:
                record[key] = record[key].isoformat()
        return record


def events_as_of(
    events: Iterable[AvailabilityEvent],
    cutoff: datetime | str,
) -> list[AvailabilityEvent]:
    """Return active events known at ``cutoff`` in deterministic order."""

    cutoff_time = _parse_timestamp(cutoff)
    visible = [
        event
        for event in events
        if event.published_at <= cutoff_time
        and event.observed_at <= cutoff_time
        and (event.expiry is None or event.expiry >= cutoff_time)
    ]
    return sorted(
        visible,
        key=lambda event: (
            event.player_id,
            -event.observed_at.timestamp(),
            event.event_type,
            event.source,
        ),
    )


def build_availability_features(
    player_ids: Iterable[int],
    events: Iterable[AvailabilityEvent],
    *,
    cutoff: datetime | str,
    target_gameweek: int | None = None,
) -> pd.DataFrame:
    """Build one point-in-time availability feature row per player.

    Missing events are represented as neutral features, not as unavailable
    players. ``target_gameweek`` makes expected-return risk explicit when a
    source supplies a return estimate.
    """

    visible = events_as_of(events, cutoff)
    rows: list[dict[str, Any]] = []
    for player_id in sorted({int(value) for value in player_ids}):
        player_events = [event for event in visible if event.player_id == player_id]
        active_risk = [
            event
            for event in player_events
            if event.event_type
            in {"injury", "illness", "suspension", "international_duty", "official_status"}
        ]
        role_events = [
            event
            for event in player_events
            if event.event_type in {"role_change", "manager_change", "new_signing", "rotation"}
        ]
        return_gameweeks = [
            event.expected_return_gameweek
            for event in active_risk
            if event.expected_return_gameweek is not None
        ]
        severe_event = max(
            (SEVERITY_SCORE[event.severity] * event.confidence for event in active_risk),
            default=0.0,
        )
        expected_return = min(return_gameweeks) if return_gameweeks else None
        return_after_target = bool(
            target_gameweek is not None
            and expected_return is not None
            and expected_return > target_gameweek
        )
        rows.append(
            {
                "player_id": player_id,
                "availability_event_count": len(player_events),
                "availability_risk_event_count": len(active_risk),
                "availability_role_event_count": len(role_events),
                "availability_severity_score": severe_event,
                "availability_confidence_max": max(
                    (event.confidence for event in active_risk), default=0.0
                ),
                "availability_return_gameweek": expected_return,
                "availability_return_after_target": return_after_target,
                "availability_role_change_flag": bool(role_events),
                "availability_known_unavailable": bool(
                    any(event.severity == "critical" for event in active_risk)
                ),
                "availability_cutoff": _parse_timestamp(cutoff).isoformat(),
            }
        )
    return pd.DataFrame(rows)


def add_m9_historical_features(players: pd.DataFrame) -> pd.DataFrame:
    """Add strict prior-gameweek role features and neutral event columns.

    This function is safe to run on the complete historical table because all
    rolling values are shifted before aggregation. It never uses the target
    Gameweek's minutes or starts to describe that same target.
    """

    required = {"season", "player_id", "gameweek", "minutes"}
    missing = sorted(required.difference(players.columns))
    if missing:
        raise ValueError("M9 historical features require columns: " + ", ".join(missing))

    output = players.copy().sort_values(["season", "player_id", "gameweek"])
    output["_m9_minutes"] = pd.to_numeric(output["minutes"], errors="coerce").fillna(0.0)
    if "starts" in output:
        output["_m9_starts"] = pd.to_numeric(output["starts"], errors="coerce")
        output["_m9_starts"] = output["_m9_starts"].fillna(
            (output["_m9_minutes"] >= 60).astype(float)
        )
    else:
        # Older processed tables did not retain ``starts``. The 60-minute proxy
        # keeps those tables usable, while rebuilt historical data uses the raw
        # starts field carried through historical_data.py.
        output["_m9_starts"] = (output["_m9_minutes"] >= 60).astype(float)

    grouped = output.groupby(["season", "player_id"], sort=False)
    shifted_minutes = grouped["_m9_minutes"].shift(1)
    shifted_starts = grouped["_m9_starts"].shift(1)
    prior = output[["season", "player_id"]].copy()
    prior["_m9_minutes"] = shifted_minutes.to_numpy()
    prior["_m9_starts"] = shifted_starts.to_numpy()
    prior_grouped = prior.groupby(["season", "player_id"], sort=False)
    output["starts_last_3"] = prior_grouped["_m9_starts"].transform(
        lambda series: series.rolling(3, min_periods=1).sum()
    ).fillna(0.0)
    output["minutes_mean_last_5"] = prior_grouped["_m9_minutes"].transform(
        lambda series: series.rolling(5, min_periods=1).mean()
    ).fillna(0.0)
    output["minutes_std_last_5"] = prior_grouped["_m9_minutes"].transform(
        lambda series: series.rolling(5, min_periods=2).std()
    ).fillna(0.0)
    output["zero_minutes_rate_last_5"] = prior_grouped["_m9_minutes"].transform(
        lambda series: series.eq(0).where(series.notna()).rolling(5, min_periods=1).mean()
    ).fillna(0.0)
    output["starts_rate_last_5"] = prior_grouped["_m9_starts"].transform(
        lambda series: series.rolling(5, min_periods=1).mean()
    ).fillna(0.0)
    output = output.drop(columns=["_m9_minutes", "_m9_starts"])

    neutral_values: dict[str, float | bool] = {
        "availability_event_count": 0.0,
        "availability_risk_event_count": 0.0,
        "availability_role_event_count": 0.0,
        "availability_severity_score": 0.0,
        "availability_confidence_max": 0.0,
        "availability_return_after_target": False,
        "availability_role_change_flag": False,
        "availability_known_unavailable": False,
    }
    for column, default in neutral_values.items():
        if column not in output:
            output[column] = default
        else:
            output[column] = output[column].fillna(default)
    return output.sort_index()


def bootstrap_availability_events(
    players: Iterable[Mapping[str, Any]],
    *,
    observed_at: datetime | str,
    source: str = "fpl_bootstrap",
) -> list[AvailabilityEvent]:
    """Convert official FPL player snapshots into auditable events.

    Available players without news do not create events. A missing chance value
    is never treated as a guaranteed absence; it only lowers confidence in an
    explicit non-available status.
    """

    observed_time = _parse_timestamp(observed_at)
    events: list[AvailabilityEvent] = []
    for player in players:
        raw_player_id = player.get("id", player.get("element_id"))
        if raw_player_id is None:
            continue
        status = str(player.get("status") or "").lower()
        news = str(player.get("news") or "").strip()
        chance_raw = player.get("chance_of_playing_next_round")
        chance = float(chance_raw) if chance_raw is not None else None
        if status in {"a", ""} and not news and (chance is None or chance >= 100):
            continue

        if status == "s":
            event_type = "suspension"
        elif status == "i":
            event_type = "injury"
        elif status == "u":
            event_type = "official_status"
        else:
            event_type = "official_status"

        if chance is not None and chance <= 0:
            severity = "critical"
        elif chance is not None and chance < 50:
            severity = "high"
        elif chance is not None and chance < 100:
            severity = "medium"
        elif status in {"s", "i", "u"}:
            severity = "high"
        else:
            severity = "low"

        published_value = player.get("news_added") or observed_time
        try:
            published_at = _parse_timestamp(published_value)
        except (TypeError, ValueError):
            published_at = observed_time
        if published_at > observed_time:
            published_at = observed_time

        confidence = (chance / 100.0) if chance is not None else 0.75
        if severity in {"critical", "high"}:
            confidence = 1.0 - confidence
        events.append(
            AvailabilityEvent(
                player_id=int(raw_player_id),
                event_type=event_type,
                severity=severity,
                expected_return_gameweek=None,
                source=source,
                published_at=published_at,
                observed_at=observed_time,
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    return events
