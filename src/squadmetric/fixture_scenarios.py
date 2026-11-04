"""Point-in-time fixture scenarios for multi-gameweek planning.

The scenario contract deliberately contains schedule/context fields only. Match
scores and realised player outcomes are excluded so a scenario can be used by
the benchmark without becoming a hindsight source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

ALLOWED_HORIZONS = (3, 5, 8)


@dataclass(frozen=True)
class FixtureScenario:
    """Immutable description of the fixtures visible for one planning horizon."""

    season: str
    start_gameweek: int
    horizon_length: int
    source: str
    data_cutoff: str
    fixture_data_hash: str
    scenario_id: str
    fixtures: tuple[dict[str, Any], ...]
    team_gameweek_counts: dict[str, dict[int, int]]

    @property
    def end_gameweek(self) -> int:
        return self.start_gameweek + self.horizon_length - 1

    def fixtures_for_team(self, team_id: Any) -> tuple[dict[str, Any], ...]:
        return tuple(
            fixture
            for fixture in self.fixtures
            if str(team_id) in {str(fixture.get("team_h")), str(fixture.get("team_a"))}
        )

    def team_summary(self, team_id: Any) -> dict[str, int]:
        counts = self.team_gameweek_counts.get(str(team_id), {})
        return {
            "fixture_count": int(sum(counts.values())),
            "blank_gameweeks": int(
                sum(
                    1
                    for gameweek in range(self.start_gameweek, self.end_gameweek + 1)
                    if counts.get(gameweek, 0) == 0
                )
            ),
            "double_gameweeks": int(sum(1 for count in counts.values() if count > 1)),
        }

    def metadata(self) -> dict[str, Any]:
        statuses = [str(fixture.get("status", "uncertain")) for fixture in self.fixtures]
        return {
            "fixture_scenario_id": self.scenario_id,
            "fixture_data_hash": self.fixture_data_hash,
            "fixture_horizon": self.horizon_length,
            "fixture_start_gameweek": self.start_gameweek,
            "fixture_end_gameweek": self.end_gameweek,
            "fixture_data_cutoff": self.data_cutoff,
            "fixture_confirmed_count": statuses.count("confirmed"),
            "fixture_uncertain_count": statuses.count("uncertain"),
            "fixture_postponed_count": statuses.count("postponed"),
            "fixture_rescheduled_count": statuses.count("rescheduled"),
        }


def build_fixture_scenario(
    fixtures: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    season: str,
    start_gameweek: int,
    horizon_length: int,
    source: str = "fpl-fixtures",
    data_cutoff: str | None = None,
) -> FixtureScenario:
    """Normalize visible fixtures and calculate deterministic scenario hashes."""

    if horizon_length not in ALLOWED_HORIZONS:
        raise ValueError(f"horizon_length must be one of {ALLOWED_HORIZONS}")
    if start_gameweek < 1:
        raise ValueError("start_gameweek must be positive")

    end_gameweek = start_gameweek + horizon_length - 1
    normalized: list[dict[str, Any]] = []
    for raw in fixtures:
        event = _int(raw.get("event", raw.get("gameweek")))
        original_event = _int(raw.get("original_event", raw.get("original_gameweek")))
        effective_event = event if event is not None else original_event
        if effective_event is None or not start_gameweek <= effective_event <= end_gameweek:
            continue

        team_h = raw.get("team_h", raw.get("home_team"))
        team_a = raw.get("team_a", raw.get("away_team"))
        kickoff_time = raw.get("kickoff_time")
        provisional = raw.get("provisional_start_time")
        if bool(raw.get("postponed")) or event is None:
            status = "postponed"
        elif original_event is not None and original_event != event:
            status = "rescheduled"
        elif provisional is False and kickoff_time:
            status = "confirmed"
        else:
            status = "uncertain"

        fixture_id = raw.get("id", raw.get("fixture"))
        if fixture_id is None:
            fixture_id = _stable_id(
                {
                    "event": effective_event,
                    "team_h": team_h,
                    "team_a": team_a,
                    "kickoff_time": kickoff_time,
                }
            )
        normalized.append(
            {
                "fixture_id": fixture_id,
                "event": event,
                "gameweek": effective_event,
                "original_gameweek": original_event,
                "team_h": team_h,
                "team_a": team_a,
                "team_h_short": raw.get("team_h_short"),
                "team_a_short": raw.get("team_a_short"),
                "team_h_name": raw.get("team_h_name"),
                "team_a_name": raw.get("team_a_name"),
                "kickoff_time": kickoff_time,
                "status": status,
                "confirmed": status == "confirmed",
                "postponed": status == "postponed",
                "rescheduled": status == "rescheduled",
                "opponent_strength": raw.get("opponent_strength"),
            }
        )

    normalized.sort(key=lambda row: (int(row["gameweek"]), str(row["fixture_id"])))
    data_hash = _hash_payload(normalized)
    cutoff = data_cutoff or f"{season}:GW{start_gameweek - 1:02d}"
    scenario_id = _hash_payload(
        {
            "season": season,
            "start_gameweek": start_gameweek,
            "horizon_length": horizon_length,
            "source": source,
            "data_cutoff": cutoff,
            "fixture_data_hash": data_hash,
        }
    )[:16]
    counts: dict[str, dict[int, int]] = {}
    for fixture in normalized:
        gameweek = int(fixture["gameweek"])
        if fixture["postponed"]:
            continue
        for team in (fixture["team_h"], fixture["team_a"]):
            counts.setdefault(str(team), {})[gameweek] = (
                counts.setdefault(str(team), {}).get(gameweek, 0) + 1
            )

    return FixtureScenario(
        season=season,
        start_gameweek=start_gameweek,
        horizon_length=horizon_length,
        source=source,
        data_cutoff=cutoff,
        fixture_data_hash=data_hash,
        scenario_id=scenario_id,
        fixtures=tuple(normalized),
        team_gameweek_counts=counts,
    )


def build_historical_fixture_scenario(
    players: pd.DataFrame,
    *,
    season: str,
    start_gameweek: int,
    horizon_length: int,
    raw_fixture_rows: pd.DataFrame | None = None,
    historical_teams: pd.DataFrame | None = None,
) -> FixtureScenario:
    """Build schedule-only scenarios from processed historical player rows."""

    if raw_fixture_rows is not None:
        return _build_raw_historical_fixture_scenario(
            raw_fixture_rows,
            season=season,
            start_gameweek=start_gameweek,
            horizon_length=horizon_length,
            historical_teams=historical_teams,
        )

    required = {"season", "gameweek", "team", "opponent_team", "home_or_away"}
    missing = required.difference(players.columns)
    if missing:
        raise ValueError(f"Historical fixture scenario is missing columns: {sorted(missing)}")

    frame = players[players["season"] == season].copy()
    frame = frame[
        frame["gameweek"].between(
            start_gameweek, start_gameweek + horizon_length - 1, inclusive="both"
        )
    ]
    frame["home_team"] = frame["team"].where(
        frame["home_or_away"].str.upper().eq("H"), frame["opponent_team"]
    )
    frame["away_team"] = frame["opponent_team"].where(
        frame["home_or_away"].str.upper().eq("H"), frame["team"]
    )
    frame = frame.drop_duplicates(["gameweek", "home_team", "away_team"])
    fixture_rows = []
    for _, row in frame.iterrows():
        fixture_rows.append(
            {
                "event": int(row["gameweek"]),
                "team_h": row["home_team"],
                "team_a": row["away_team"],
                "team_h_short": row["home_team"],
                "team_a_short": row["away_team"],
                "opponent_strength": row.get("opponent_strength"),
            }
        )
    return build_fixture_scenario(
        fixture_rows,
        season=season,
        start_gameweek=start_gameweek,
        horizon_length=horizon_length,
        source="historical-processed-schedule",
    )


def _build_raw_historical_fixture_scenario(
    fixture_rows: pd.DataFrame,
    *,
    season: str,
    start_gameweek: int,
    horizon_length: int,
    historical_teams: pd.DataFrame | None,
) -> FixtureScenario:
    required = {"GW", "fixture", "team", "opponent_team", "was_home"}
    missing = required.difference(fixture_rows.columns)
    if missing:
        raise ValueError(f"Historical raw fixtures are missing columns: {sorted(missing)}")

    frame = fixture_rows.copy()
    frame = frame[
        frame["GW"].between(
            start_gameweek, start_gameweek + horizon_length - 1, inclusive="both"
        )
    ].drop_duplicates("fixture")
    team_names: dict[int, str] = {}
    if historical_teams is not None and {"id", "name"}.issubset(historical_teams.columns):
        team_names = {
            int(team_id): str(name)
            for team_id, name in historical_teams[["id", "name"]].dropna().itertuples(
                index=False, name=None
            )
        }

    rows = []
    for _, row in frame.iterrows():
        opponent_id = _int(row["opponent_team"])
        current_team = str(row["team"])
        opponent_name = team_names.get(opponent_id, str(row["opponent_team"]))
        home = bool(row["was_home"])
        rows.append(
            {
                "id": row["fixture"],
                "event": int(row["GW"]),
                "team_h": current_team if home else opponent_name,
                "team_a": opponent_name if home else current_team,
                "kickoff_time": row.get("kickoff_time"),
                # Historical raw files have no point-in-time fixture snapshots;
                # leave final-schedule certainty explicit rather than claiming it.
            }
        )
    return build_fixture_scenario(
        rows,
        season=season,
        start_gameweek=start_gameweek,
        horizon_length=horizon_length,
        source="historical-raw-schedule-no-snapshot",
    )


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_id(value: Any) -> str:
    return _hash_payload(value)[:16]


def _int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
