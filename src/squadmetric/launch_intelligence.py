"""Timestamped 2026/27 launch priors for unfamiliar players and availability.

Official observations are evidence, not labels.  Any probability stored here is
an explicit model inference and remains source-attributed so it can be replaced
as later preseason lineups or FPL status updates arrive.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAUNCH_EVIDENCE_PATH = (
    PROJECT_ROOT / "data" / "reference" / "launch_player_evidence_2026_27.json"
)
PROMOTED_TEAMS_2026_27 = frozenset({"Coventry City", "Hull City", "Ipswich Town"})


def _timestamp(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("Launch evidence timestamps must include a timezone")
    return parsed.astimezone(UTC)


def normalise_name(value: object) -> str:
    text = str(value or "").strip().casefold()
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


@dataclass(frozen=True)
class LaunchPlayerEvidence:
    season: str
    player_name: str
    team_name: str
    inferred_start_probability: float
    confidence: float
    source_url: str
    published_at: datetime
    observed_at: datetime
    evidence_type: str
    notes: str
    defensive_actions_per_90: float | None = None
    goals: int | None = None
    assists: int | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> LaunchPlayerEvidence:
        evidence = cls(
            season=str(value["season"]),
            player_name=str(value["player_name"]),
            team_name=str(value["team_name"]),
            inferred_start_probability=float(value["inferred_start_probability"]),
            confidence=float(value["confidence"]),
            source_url=str(value["source_url"]),
            published_at=_timestamp(value["published_at"]),
            observed_at=_timestamp(value["observed_at"]),
            evidence_type=str(value["evidence_type"]),
            notes=str(value.get("notes", "")),
            defensive_actions_per_90=(
                float(value["defensive_actions_per_90"])
                if value.get("defensive_actions_per_90") is not None
                else None
            ),
            goals=int(value["goals"]) if value.get("goals") is not None else None,
            assists=int(value["assists"]) if value.get("assists") is not None else None,
        )
        evidence.validate()
        return evidence

    def validate(self) -> None:
        if not self.player_name.strip() or not self.team_name.strip():
            raise ValueError("Launch evidence requires player and team names")
        if not self.source_url.startswith("https://"):
            raise ValueError("Launch evidence requires an HTTPS source URL")
        if self.published_at > self.observed_at:
            raise ValueError("Launch evidence cannot be observed before publication")
        if not 0.0 <= self.inferred_start_probability <= 1.0:
            raise ValueError("inferred_start_probability must be between zero and one")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")

    @property
    def key(self) -> tuple[str, str]:
        return normalise_name(self.player_name), normalise_name(self.team_name)


def load_launch_evidence(
    path: Path = DEFAULT_LAUNCH_EVIDENCE_PATH,
    *,
    season: str | None = None,
    cutoff: datetime | str | None = None,
) -> list[LaunchPlayerEvidence]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    evidence = [
        LaunchPlayerEvidence.from_mapping(value)
        for value in payload.get("observations", [])
    ]
    if season is not None:
        evidence = [item for item in evidence if item.season == season]
    if cutoff is not None:
        cutoff_time = _timestamp(cutoff)
        evidence = [
            item
            for item in evidence
            if item.published_at <= cutoff_time and item.observed_at <= cutoff_time
        ]
    keys = [item.key for item in evidence]
    if len(keys) != len(set(keys)):
        raise ValueError("Launch evidence contains duplicate player/team keys")
    return sorted(evidence, key=lambda item: item.key)


def availability_probability(
    status: object,
    chance_of_playing: object,
) -> float:
    """Return a conservative official-availability cap.

    Missing chance values for an available player remain neutral. Explicit
    injury, suspension, unavailable, or doubtful statuses fail safely.
    """

    status_code = str(status or "").strip().lower()
    chance = pd.to_numeric(pd.Series([chance_of_playing]), errors="coerce").iloc[0]
    if pd.notna(chance):
        return max(0.0, min(1.0, float(chance) / 100.0))
    return {
        "a": 1.0,
        "d": 0.75,
        "i": 0.0,
        "s": 0.0,
        "u": 0.0,
    }.get(status_code, 0.5)

