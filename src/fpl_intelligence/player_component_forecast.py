"""Opt-in bridge from team forecasts to player scoring components for M10."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PLAYER_COMPONENT_FORECAST_VERSION = "m10-player-components-v1"
POSITION_PRIORS = {"GK": 0.01, "GKP": 0.01, "DEF": 0.08, "MID": 0.30, "FWD": 0.45}


def build_player_fixture_components(
    players: pd.DataFrame,
    fixture_forecasts: pd.DataFrame,
    *,
    appearance_probabilities: pd.Series | np.ndarray | None = None,
    data_cutoff: str = "unknown",
    rules_version: str = "unresolved",
) -> pd.DataFrame:
    """Attach team-context expected components to point-in-time player rows.

    The player attacking shares use only lagged xG/xA signals. Current-target
    ``expected_goals`` and ``expected_assists`` columns are intentionally not
    read, so changing them cannot change this bridge's output.
    """

    required_players = {"team", "opponent_team", "home_or_away", "position"}
    missing = required_players.difference(players.columns)
    if missing:
        raise ValueError(f"Player component bridge is missing columns: {sorted(missing)}")
    required_fixtures = {
        "gameweek",
        "home_team",
        "away_team",
        "expected_home_goals",
        "expected_away_goals",
        "home_clean_sheet_probability",
        "away_clean_sheet_probability",
    }
    missing = required_fixtures.difference(fixture_forecasts.columns)
    if missing:
        raise ValueError(f"Fixture forecast is missing columns: {sorted(missing)}")

    frame = players.copy().reset_index(drop=True)
    frame["_row_id"] = np.arange(len(frame))
    frame["_position"] = frame["position"].map(_position_code)
    frame["_home_team"] = (
        frame["team"]
        .where(frame["home_or_away"].astype(str).str.upper().eq("H"), frame["opponent_team"])
        .astype(str)
    )
    frame["_away_team"] = (
        frame["opponent_team"]
        .where(frame["home_or_away"].astype(str).str.upper().eq("H"), frame["team"])
        .astype(str)
    )
    if "gameweek" not in frame:
        raise ValueError("Player component bridge requires gameweek")
    frame["gameweek"] = pd.to_numeric(frame["gameweek"], errors="coerce")
    frame["_xg_signal"] = _positive_signal(frame, "expected_goals_last_3")
    frame["_xa_signal"] = _positive_signal(frame, "expected_assists_last_3")
    frame["_xg_signal"] += frame["_position"].map(POSITION_PRIORS).fillna(0.10)
    frame["_xa_signal"] += frame["_position"].map(POSITION_PRIORS).fillna(0.10) * 0.8

    forecast = fixture_forecasts.copy()
    forecast["_home_team"] = forecast["home_team"].astype(str)
    forecast["_away_team"] = forecast["away_team"].astype(str)
    forecast["gameweek"] = pd.to_numeric(forecast["gameweek"], errors="coerce")
    lookup_columns = [
        "gameweek",
        "_home_team",
        "_away_team",
        "fixture_id",
        "expected_home_goals",
        "expected_away_goals",
        "home_clean_sheet_probability",
        "away_clean_sheet_probability",
    ]
    joined = frame.merge(
        forecast[lookup_columns],
        on=["gameweek", "_home_team", "_away_team"],
        how="left",
        validate="many_to_one",
    )
    if joined["expected_home_goals"].isna().any():
        raise ValueError("Every player row must match one visible fixture forecast")

    group = joined.groupby(["gameweek", "team"], dropna=False)
    joined["_xg_share"] = joined["_xg_signal"] / group["_xg_signal"].transform("sum").clip(
        lower=1e-9
    )
    joined["_xa_share"] = joined["_xa_signal"] / group["_xa_signal"].transform("sum").clip(
        lower=1e-9
    )
    joined["appearance_probability"] = _appearance_probabilities(
        appearance_probabilities, len(joined)
    )
    home = joined["home_or_away"].astype(str).str.upper().eq("H")
    joined["expected_team_goals"] = np.where(
        home, joined["expected_home_goals"], joined["expected_away_goals"]
    )
    joined["expected_opponent_goals"] = np.where(
        home, joined["expected_away_goals"], joined["expected_home_goals"]
    )
    joined["team_clean_sheet_probability"] = np.where(
        home,
        joined["home_clean_sheet_probability"],
        joined["away_clean_sheet_probability"],
    )
    joined["expected_goals_scored"] = (
        joined["expected_team_goals"] * joined["_xg_share"] * joined["appearance_probability"]
    )
    joined["expected_assists"] = (
        joined["expected_team_goals"]
        * 0.35
        * joined["_xa_share"]
        * joined["appearance_probability"]
    )
    joined["expected_clean_sheets"] = (
        joined["team_clean_sheet_probability"] * joined["appearance_probability"]
    )
    joined["expected_goals_conceded"] = (
        joined["expected_opponent_goals"]
        * joined["appearance_probability"]
        * joined["_defensive_position"]
        if "_defensive_position" in joined
        else joined["expected_opponent_goals"] * joined["appearance_probability"]
    )
    joined["expected_saves"] = np.where(
        joined["_position"].isin(["GK", "GKP"]),
        joined["expected_opponent_goals"] * 2.0 * joined["appearance_probability"],
        0.0,
    )
    joined["expected_bonus"] = 0.0
    joined["expected_penalties_saved"] = 0.0
    joined["expected_penalties_missed"] = 0.0
    joined["expected_own_goals"] = 0.0
    joined["expected_yellow_cards"] = 0.0
    joined["expected_red_cards"] = 0.0
    joined["expected_defensive_contribution"] = _dc_signal(joined)
    output_columns = [
        column
        for column in [
            "player_id",
            "player_name",
            "season",
            "gameweek",
            "team",
            "opponent_team",
            "position",
            "home_or_away",
            "fixture_id",
            "expected_team_goals",
            "expected_opponent_goals",
            "team_clean_sheet_probability",
            "appearance_probability",
            "expected_goals_scored",
            "expected_assists",
            "expected_clean_sheets",
            "expected_goals_conceded",
            "expected_saves",
            "expected_bonus",
            "expected_penalties_saved",
            "expected_penalties_missed",
            "expected_own_goals",
            "expected_yellow_cards",
            "expected_red_cards",
            "expected_defensive_contribution",
        ]
        if column in joined.columns
    ]
    output = joined[output_columns].copy()
    output["data_cutoff"] = data_cutoff
    output["rules_version"] = rules_version
    output["model_version"] = PLAYER_COMPONENT_FORECAST_VERSION
    return output


def _positive_signal(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0).clip(lower=0.0)


def _appearance_probabilities(
    values: pd.Series | np.ndarray | None,
    count: int,
) -> np.ndarray:
    if values is None:
        return np.ones(count, dtype=float)
    probabilities = np.asarray(values, dtype=float)
    if probabilities.shape != (count,):
        raise ValueError("appearance_probabilities must have one value per player row")
    return np.clip(probabilities, 0.0, 1.0)


def _position_code(value: Any) -> str:
    value = str(value or "").upper()
    return {
        "GOALKEEPER": "GK",
        "GKP": "GK",
        "DEFENDER": "DEF",
        "MIDFIELDER": "MID",
        "FORWARD": "FWD",
    }.get(value, value)


def _dc_signal(frame: pd.DataFrame) -> pd.Series:
    if "defensive_contribution_last_3" not in frame:
        return pd.Series(0.0, index=frame.index)
    signal = pd.to_numeric(frame["defensive_contribution_last_3"], errors="coerce").fillna(0.0)
    regime = frame.get("dc_rule_version", pd.Series("pre_dc", index=frame.index)).astype(str)
    return (signal / 3.0 * frame["appearance_probability"]).where(regime.ne("pre_dc"), 0.0)
