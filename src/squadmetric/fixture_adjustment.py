"""Scale projections by venue and opponent, learned from earlier Gameweeks only.

The points model is additive, so home advantage adds the same small amount to every
player and fixtures barely move a forecast. Actual scoring moves more than that, and
differently by position. Each multiplier compares actual with predicted points for
regular starters in one fixture type, relative to that position's overall ratio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from squadmetric.step4_models import BASE_FEATURE_COLUMNS, build_ridge_model

REGULAR_STARTER_MINUTES_LAST_3 = 180
MINIMUM_FIT_ROWS = 2000
SHRINKAGE_ROWS = 300
MULTIPLIER_RANGE = (0.8, 1.25)
# Historical strength ratings are one end-of-season value per team, so they know how
# the season turned out. Replays rebuild them from the prior season plus results so far.
STRENGTH_POINTS_PER_GOAL_DIFFERENCE = 60.0
RESULTS_SHRINKAGE_MATCHES = 6.0


@dataclass(frozen=True)
class FixtureMultipliers:
    """Multipliers by position group, venue, and opponent-strength band."""

    low_strength: float = 0.0
    high_strength: float = 0.0
    table: dict[str, float] = field(default_factory=dict)

    def multiplier(self, position: Any, venue: Any, opponent_strength: Any) -> float:
        if not self.table or str(venue) not in {"H", "A"}:
            return 1.0
        strength = pd.to_numeric(opponent_strength, errors="coerce")
        if pd.isna(strength):
            return 1.0
        band = (
            "easy"
            if strength <= self.low_strength
            else "hard"
            if strength >= self.high_strength
            else "mid"
        )
        return self.table.get(f"{_position_group(position)}|{venue}|{band}", 1.0)


def _position_group(position: Any) -> str:
    code = str(position).upper()[:1]
    return "DEF" if code in {"G", "D"} else "MID" if code == "M" else "FWD"


def fit_fixture_multipliers(training: pd.DataFrame) -> FixtureMultipliers:
    """Learn multipliers from finished Gameweeks; too little history means no change."""

    usable = training.dropna(subset=["next_gameweek_points"])
    regular = usable[
        usable["minutes_last_3"].fillna(0).ge(REGULAR_STARTER_MINUTES_LAST_3)
        & usable["home_or_away"].isin(["H", "A"])
        & usable["opponent_strength"].notna()
    ]
    if len(regular) < MINIMUM_FIT_ROWS:
        return FixtureMultipliers()
    model = build_ridge_model(BASE_FEATURE_COLUMNS)
    model.fit(usable[BASE_FEATURE_COLUMNS], usable["next_gameweek_points"])
    low, high = np.quantile(regular["opponent_strength"], [1 / 3, 2 / 3])
    frame = pd.DataFrame(
        {
            "group": regular["position"].map(_position_group),
            "venue": regular["home_or_away"],
            "band": np.select(
                [regular["opponent_strength"] <= low, regular["opponent_strength"] >= high],
                ["easy", "hard"],
                default="mid",
            ),
            "actual": regular["next_gameweek_points"],
            "predicted": np.clip(model.predict(regular[BASE_FEATURE_COLUMNS]), 0.0, None),
        }
    )
    group_ratio = frame.groupby("group")["actual"].sum() / frame.groupby("group")["predicted"].sum()
    table: dict[str, float] = {}
    for (group, venue, band), cell in frame.groupby(["group", "venue", "band"]):
        raw = (cell["actual"].sum() / cell["predicted"].sum()) / group_ratio[group]
        weight = len(cell) / (len(cell) + SHRINKAGE_ROWS)
        table[f"{group}|{venue}|{band}"] = round(
            float(np.clip(weight * raw + (1 - weight), *MULTIPLIER_RANGE)),
            4,
        )
    return FixtureMultipliers(float(low), float(high), table)


def add_point_in_time_opponent_strength(players: pd.DataFrame) -> pd.DataFrame:
    """Replace opponent strength with a rating built only from earlier results."""

    output = players.copy()
    single = output[~output["opponent_team"].astype(str).str.contains("+", regex=False)]
    season_order = sorted(output["season"].astype(str).unique())
    snapshot = (
        single.dropna(subset=["opponent_strength"])
        .groupby(["season", "opponent_team", "home_or_away"])["opponent_strength"]
        .first()
        .to_dict()
    )
    league = single.groupby(["season", "home_or_away"])["opponent_strength"].agg(["mean", "min"])
    matches = (
        output.drop_duplicates(["season", "gameweek", "team"])
        .assign(
            fixtures=lambda frame: frame["opponent_team"].astype(str).str.count(r"\+") + 1,
            goal_difference=lambda frame: pd.to_numeric(frame["team_goals"], errors="coerce")
            - pd.to_numeric(frame["opponent_goals"], errors="coerce"),
        )
        .dropna(subset=["goal_difference"])
    )
    results: dict[tuple[str, str], list[tuple[int, float, int]]] = {}
    for row in matches.itertuples(index=False):
        results.setdefault((str(row.season), str(row.team)), []).append(
            (int(row.gameweek), float(row.goal_difference), int(row.fixtures))
        )

    def rating(season: str, gameweek: int, opponent: str, venue: str) -> float:
        # A player at home meets the opponent's away rating; the snapshot key is the
        # player's venue, matching how the original column was built.
        index = season_order.index(season)
        prior_season = season_order[index - 1] if index else None
        if prior_season is None:
            base = float(league.loc[(season, venue), "mean"])
        else:
            base = snapshot.get(
                (prior_season, opponent, venue),
                float(league.loc[(prior_season, venue), "min"]),
            )
        earlier = [row for row in results.get((season, opponent), []) if row[0] < gameweek]
        played = sum(row[2] for row in earlier)
        if not played:
            return float(base)
        per_match = sum(row[1] for row in earlier) / played
        weight = played / (played + RESULTS_SHRINKAGE_MATCHES)
        return float(base + STRENGTH_POINTS_PER_GOAL_DIFFERENCE * weight * per_match)

    cache: dict[tuple[str, int, str, str], float] = {}

    def row_rating(season: str, gameweek: int, opponents: str, venue: str) -> float:
        key = (season, gameweek, opponents, venue)
        if key not in cache:
            parts = opponents.split("+")
            if len(parts) == 1:
                cache[key] = rating(season, gameweek, parts[0], venue)
            else:
                # A mixed double hides each match's venue, so use both venue ratings.
                cache[key] = float(
                    np.mean(
                        [
                            rating(season, gameweek, part, side)
                            for part in parts
                            for side in ("H", "A")
                        ]
                    )
                    if venue == "M"
                    else np.mean([rating(season, gameweek, part, venue) for part in parts])
                )
        return cache[key]

    output["opponent_strength"] = [
        row_rating(str(season), int(gameweek), str(opponents), str(venue))
        for season, gameweek, opponents, venue in zip(
            output["season"],
            output["gameweek"],
            output["opponent_team"],
            output["home_or_away"],
            strict=True,
        )
    ]
    return output
