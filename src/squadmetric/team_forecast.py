"""Point-in-time team and fixture forecasts for M10.

This module deliberately uses only completed match outcomes supplied by the
caller.  It is an intentionally small, deterministic Poisson-style baseline:
team attack and defence rates are shrunk towards league priors, then converted
to fixture goal, result, and clean-sheet probabilities.  It is an opt-in M10
candidate and does not replace the accepted benchmark projection.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import poisson

from squadmetric.calibration import binary_calibration_report, poisson_calibration_report
from squadmetric.fixture_scenarios import FixtureScenario

TEAM_FORECAST_VERSION = "m10-team-poisson-v1"


@dataclass(frozen=True)
class TeamFixtureForecast:
    """Forecast for one visible fixture, with no realised-match fields."""

    fixture_id: str
    gameweek: int
    home_team: str
    away_team: str
    status: str
    expected_home_goals: float
    expected_away_goals: float
    home_win_probability: float
    draw_probability: float
    away_win_probability: float
    home_clean_sheet_probability: float
    away_clean_sheet_probability: float
    data_cutoff: str
    rules_version: str
    training_match_count: int
    model_version: str = TEAM_FORECAST_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "gameweek": self.gameweek,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "status": self.status,
            "expected_home_goals": self.expected_home_goals,
            "expected_away_goals": self.expected_away_goals,
            "home_win_probability": self.home_win_probability,
            "draw_probability": self.draw_probability,
            "away_win_probability": self.away_win_probability,
            "home_clean_sheet_probability": self.home_clean_sheet_probability,
            "away_clean_sheet_probability": self.away_clean_sheet_probability,
            "data_cutoff": self.data_cutoff,
            "rules_version": self.rules_version,
            "training_match_count": self.training_match_count,
            "model_version": self.model_version,
        }


@dataclass(frozen=True)
class TeamGoalModel:
    """Shrunk home/away attack-defence model fitted to completed fixtures."""

    season: str | None
    cutoff_gameweek: int
    data_cutoff: str
    rules_version: str
    prior_strength: float
    league_home_goals: float
    league_away_goals: float
    home_attack: dict[str, float]
    away_attack: dict[str, float]
    home_defence: dict[str, float]
    away_defence: dict[str, float]
    training_match_count: int
    version: str = TEAM_FORECAST_VERSION

    def predict_fixture(self, fixture: Mapping[str, Any]) -> TeamFixtureForecast:
        """Forecast a fixture using only the state captured in this model."""

        home = str(fixture.get("team_h", fixture.get("home_team")))
        away = str(fixture.get("team_a", fixture.get("away_team")))
        home_rate = self.league_home_goals
        away_rate = self.league_away_goals
        home_rate *= self.home_attack.get(home, 1.0)
        home_rate *= self.away_defence.get(away, 1.0)
        away_rate *= self.away_attack.get(away, 1.0)
        away_rate *= self.home_defence.get(home, 1.0)
        home_rate = max(float(home_rate), 1e-6)
        away_rate = max(float(away_rate), 1e-6)

        max_goals = max(
            12, int(math.ceil(max(home_rate, away_rate) + 8 * math.sqrt(max(home_rate, away_rate))))
        )
        goals = np.arange(max_goals + 1)
        home_pmf = poisson.pmf(goals, home_rate)
        away_pmf = poisson.pmf(goals, away_rate)
        matrix = np.outer(home_pmf, away_pmf)
        matrix = matrix / matrix.sum()
        home_win = float(np.tril(matrix, k=-1).sum())
        draw = float(np.trace(matrix))
        away_win = float(np.triu(matrix, k=1).sum())

        return TeamFixtureForecast(
            fixture_id=str(fixture.get("fixture_id", fixture.get("id", "unknown"))),
            gameweek=int(fixture.get("gameweek", fixture.get("event", 0))),
            home_team=home,
            away_team=away,
            status=str(fixture.get("status", "uncertain")),
            expected_home_goals=home_rate,
            expected_away_goals=away_rate,
            home_win_probability=home_win,
            draw_probability=draw,
            away_win_probability=away_win,
            home_clean_sheet_probability=float(math.exp(-away_rate)),
            away_clean_sheet_probability=float(math.exp(-home_rate)),
            data_cutoff=self.data_cutoff,
            rules_version=self.rules_version,
            training_match_count=self.training_match_count,
        )

    def predict_scenario(self, scenario: FixtureScenario) -> pd.DataFrame:
        """Return deterministic forecasts for every fixture in a scenario."""

        rows = [self.predict_fixture(fixture).to_dict() for fixture in scenario.fixtures]
        return pd.DataFrame(rows)


def fit_team_goal_model(
    matches: pd.DataFrame | Iterable[Mapping[str, Any]],
    *,
    cutoff_gameweek: int,
    season: str | None = None,
    data_cutoff: str | None = None,
    rules_version: str = "unresolved",
    prior_strength: float = 5.0,
    prior_home_goals: float = 1.45,
    prior_away_goals: float = 1.15,
) -> TeamGoalModel:
    """Fit a strictly pre-cutoff team-goal model.

    ``matches`` may be fixture-level rows using ``home_team``/``away_team``
    and goal columns, or processed player rows containing ``team``,
    ``opponent_team``, ``home_or_away``, ``team_goals`` and
    ``opponent_goals``.  Duplicate player perspectives are collapsed before
    fitting.  Rows at the target gameweek and later are never used.
    """

    frame = _normalise_match_rows(matches)
    frame["gameweek"] = pd.to_numeric(frame["gameweek"], errors="coerce")
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce")
    frame = frame.dropna(subset=["gameweek", "home_goals", "away_goals"])
    if season is not None and "season" in frame:
        frame = frame[frame["season"].astype(str) == str(season)]
    frame = frame[frame["gameweek"] < cutoff_gameweek].copy()
    frame["gameweek"] = frame["gameweek"].astype(int)

    home_goals = float(frame["home_goals"].mean()) if not frame.empty else prior_home_goals
    away_goals = float(frame["away_goals"].mean()) if not frame.empty else prior_away_goals
    home_goals = max(home_goals, 1e-6)
    away_goals = max(away_goals, 1e-6)

    stats = _team_rates(frame, prior_strength, home_goals, away_goals)
    return TeamGoalModel(
        season=season,
        cutoff_gameweek=cutoff_gameweek,
        data_cutoff=data_cutoff
        or (f"{season}:GW{cutoff_gameweek - 1:02d}" if season else "unknown"),
        rules_version=rules_version,
        prior_strength=float(prior_strength),
        league_home_goals=home_goals,
        league_away_goals=away_goals,
        home_attack=stats["home_attack"],
        away_attack=stats["away_attack"],
        home_defence=stats["home_defence"],
        away_defence=stats["away_defence"],
        training_match_count=len(frame),
    )


def walk_forward_team_forecasts(
    matches: pd.DataFrame | Iterable[Mapping[str, Any]],
    *,
    season: str,
    data_cutoff_template: str | None = None,
    rules_version: str = "unresolved",
    prior_strength: float = 5.0,
) -> pd.DataFrame:
    """Forecast every historical gameweek using only earlier gameweeks.

    The returned frame is an evaluation artifact and therefore includes actual
    goals.  It must not be passed to a live planner; live planning should use
    :meth:`TeamGoalModel.predict_scenario`, whose fixture inputs contain no
    realised outcomes.
    """

    normalised = _normalise_match_rows(matches)
    normalised["gameweek"] = pd.to_numeric(normalised["gameweek"], errors="coerce")
    normalised["home_goals"] = pd.to_numeric(normalised["home_goals"], errors="coerce")
    normalised["away_goals"] = pd.to_numeric(normalised["away_goals"], errors="coerce")
    normalised = normalised.dropna(subset=["gameweek", "home_goals", "away_goals"])
    normalised = normalised[normalised["season"].astype(str) == str(season)]
    rows: list[dict[str, Any]] = []
    for gameweek in sorted(normalised["gameweek"].astype(int).unique()):
        model = fit_team_goal_model(
            normalised,
            cutoff_gameweek=gameweek,
            season=season,
            data_cutoff=(
                data_cutoff_template.format(gameweek=gameweek - 1)
                if data_cutoff_template
                else f"{season}:GW{gameweek - 1:02d}"
            ),
            rules_version=rules_version,
            prior_strength=prior_strength,
        )
        target = normalised[normalised["gameweek"] == gameweek]
        for _, match in target.iterrows():
            fixture = {
                "fixture_id": match.get("fixture_id"),
                "gameweek": gameweek,
                "team_h": match["home_team"],
                "team_a": match["away_team"],
                "status": "historical_evaluation",
            }
            forecast = model.predict_fixture(fixture)
            rows.append(
                {
                    **forecast.to_dict(),
                    "season": season,
                    "actual_home_goals": float(match["home_goals"]),
                    "actual_away_goals": float(match["away_goals"]),
                    "actual_home_clean_sheet": int(match["away_goals"] == 0),
                    "actual_away_clean_sheet": int(match["home_goals"] == 0),
                }
            )
    return pd.DataFrame(rows)


def summarise_team_forecasts(forecasts: pd.DataFrame) -> dict[str, Any]:
    """Summarise a walk-forward forecast frame by season and overall."""

    required = {
        "expected_home_goals",
        "expected_away_goals",
        "actual_home_goals",
        "actual_away_goals",
        "home_clean_sheet_probability",
        "away_clean_sheet_probability",
        "actual_home_clean_sheet",
        "actual_away_clean_sheet",
    }
    missing = required.difference(forecasts.columns)
    if missing:
        raise ValueError(f"Forecast evaluation is missing columns: {sorted(missing)}")

    def metrics(frame: pd.DataFrame) -> dict[str, Any]:
        home = poisson_calibration_report(frame["actual_home_goals"], frame["expected_home_goals"])
        away = poisson_calibration_report(frame["actual_away_goals"], frame["expected_away_goals"])
        clean_sheet = binary_calibration_report(
            pd.concat([frame["actual_home_clean_sheet"], frame["actual_away_clean_sheet"]]),
            pd.concat(
                [frame["home_clean_sheet_probability"], frame["away_clean_sheet_probability"]]
            ),
        )
        return {
            "fixture_count": int(len(frame)),
            "home_goal_mae": home["mae"],
            "away_goal_mae": away["mae"],
            "home_goal_rmse": home["rmse"],
            "away_goal_rmse": away["rmse"],
            "home_goal_interval_coverage": home["interval_coverage"],
            "away_goal_interval_coverage": away["interval_coverage"],
            "clean_sheet_brier_score": clean_sheet["brier_score"],
            "clean_sheet_log_loss": clean_sheet["log_loss"],
        }

    by_season = {
        str(season): metrics(group)
        for season, group in forecasts.groupby(
            forecasts.get("season", pd.Series("all", index=forecasts.index))
        )
    }
    return {"overall": metrics(forecasts), "by_season": by_season}


def _normalise_match_rows(
    matches: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> pd.DataFrame:
    frame = matches.copy() if isinstance(matches, pd.DataFrame) else pd.DataFrame(list(matches))
    if frame.empty:
        return pd.DataFrame(
            columns=["season", "gameweek", "home_team", "away_team", "home_goals", "away_goals"]
        )

    if {"home_team", "away_team", "home_goals", "away_goals"}.issubset(frame.columns):
        selected = frame.copy()
        selected["home_team"] = selected["home_team"].astype(str)
        selected["away_team"] = selected["away_team"].astype(str)
    else:
        required = {"team", "opponent_team", "home_or_away", "team_goals", "opponent_goals"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Team match history is missing columns: {sorted(missing)}")
        home = frame["home_or_away"].astype(str).str.upper().eq("H")
        selected = pd.DataFrame(
            {
                "season": frame.get("season"),
                "gameweek": frame.get("gameweek"),
                "home_team": frame["team"].where(home, frame["opponent_team"]),
                "away_team": frame["opponent_team"].where(home, frame["team"]),
                "home_goals": frame["team_goals"].where(home, frame["opponent_goals"]),
                "away_goals": frame["opponent_goals"].where(home, frame["team_goals"]),
                "fixture_id": frame.get("fixture_id", frame.get("fixture")),
            }
        )
    selected["home_team"] = selected["home_team"].astype(str)
    selected["away_team"] = selected["away_team"].astype(str)
    if "season" not in selected:
        selected["season"] = None
    key_columns = ["season", "gameweek", "home_team", "away_team"]
    if "fixture_id" in selected and selected["fixture_id"].notna().any():
        selected["_fixture_key"] = selected["fixture_id"].astype(str)
    else:
        selected["_fixture_key"] = selected[key_columns].astype(str).agg("|".join, axis=1)
    return selected.drop_duplicates("_fixture_key").drop(columns="_fixture_key")


def _team_rates(
    frame: pd.DataFrame,
    prior_strength: float,
    league_home_goals: float,
    league_away_goals: float,
) -> dict[str, dict[str, float]]:
    teams = set(frame.get("home_team", pd.Series(dtype=str)).astype(str)) | set(
        frame.get("away_team", pd.Series(dtype=str)).astype(str)
    )
    result = {
        "home_attack": {},
        "away_attack": {},
        "home_defence": {},
        "away_defence": {},
    }
    for team in teams:
        home = frame[frame["home_team"] == team]
        away = frame[frame["away_team"] == team]
        result["home_attack"][team] = (
            _shrunk_rate(home["home_goals"].sum(), len(home), league_home_goals, prior_strength)
            / league_home_goals
        )
        result["home_defence"][team] = (
            _shrunk_rate(home["away_goals"].sum(), len(home), league_away_goals, prior_strength)
            / league_away_goals
        )
        result["away_attack"][team] = (
            _shrunk_rate(away["away_goals"].sum(), len(away), league_away_goals, prior_strength)
            / league_away_goals
        )
        result["away_defence"][team] = (
            _shrunk_rate(away["home_goals"].sum(), len(away), league_home_goals, prior_strength)
            / league_home_goals
        )
    return result


def _shrunk_rate(total: float, count: int, prior: float, strength: float) -> float:
    return (float(total) + strength * prior) / (float(count) + strength)
