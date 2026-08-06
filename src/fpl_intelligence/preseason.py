"""Identity-safe preseason evidence and opening-squad baseline.

FPL ``element`` IDs are allocated independently for each season.  This module
therefore treats them as season-local row identifiers and never as player
identities across seasons.
"""

from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

from fpl_intelligence.squad_optimizer import position_group

IDENTITY_SAFE_INITIAL_SQUAD_MODE = "identity_safe_value"
IDENTITY_SAFE_INITIAL_SQUAD_VERSION = "identity-safe-preseason-v1"


def build_identity_safe_preseason_pool(
    players: pd.DataFrame,
    *,
    season: str,
    prior_season: str | None,
) -> pd.DataFrame:
    """Attach unambiguous prior-season evidence using normalized player names."""

    gw1 = (
        players[
            (players["season"].astype(str) == season)
            & (pd.to_numeric(players["gameweek"], errors="coerce") == 1)
        ]
        .sort_values(["player_id", "gameweek"])
        .drop_duplicates("player_id")
        .copy()
    )
    if gw1.empty:
        raise ValueError(f"No {season} GW1 candidates are available")
    if "player_name" not in gw1:
        raise ValueError("Identity-safe preseason matching requires player_name")

    gw1["player_key"] = gw1["player_name"].map(normalise_player_name)
    gw1["position_group"] = gw1["position"].map(position_group)
    gw1["price"] = decision_price(gw1)
    gw1["prior_matched"] = False
    gw1["prior_player_id"] = pd.Series(pd.NA, index=gw1.index, dtype="Int64")
    gw1["prior_points"] = 0.0
    gw1["prior_minutes"] = 0.0
    gw1["prior_appearances"] = 0
    gw1["prior_points_per_appearance"] = 0.0
    gw1["prior_value"] = 0.0
    gw1["promoted_team"] = False
    gw1["identity_match_method"] = "unmatched"

    current_key_counts = gw1.groupby("player_key")["player_id"].transform("nunique")
    ambiguous_current = current_key_counts > 1

    if prior_season is not None:
        prior = players[players["season"].astype(str) == prior_season].copy()
        if "player_name" not in prior:
            raise ValueError("Identity-safe preseason matching requires player_name")
        prior["player_key"] = prior["player_name"].map(normalise_player_name)
        summary = prior.groupby("player_key", as_index=False).agg(
            prior_player_id=("player_id", "first"),
            prior_player_count=("player_id", "nunique"),
            prior_points=("total_points", "sum"),
            prior_minutes=("minutes", "sum"),
            prior_appearances=("minutes", lambda values: int((values > 0).sum())),
            prior_last_price=("price", "last"),
        )
        # A name shared by multiple distinct players is not a safe identity.
        summary = summary[summary["prior_player_count"] == 1].copy()
        summary["prior_points_per_appearance"] = summary["prior_points"].div(
            summary["prior_appearances"].clip(lower=1)
        )
        summary["prior_value"] = summary["prior_points"].div(
            pd.to_numeric(summary["prior_last_price"], errors="coerce").replace(0, np.nan)
        ).fillna(0.0)
        columns = [
            "player_key",
            "prior_player_id",
            "prior_points",
            "prior_minutes",
            "prior_appearances",
            "prior_points_per_appearance",
            "prior_value",
        ]
        gw1 = gw1.drop(columns=columns[1:]).merge(
            summary[columns],
            on="player_key",
            how="left",
            validate="many_to_one",
        )
        gw1["prior_matched"] = gw1["prior_points"].notna() & ~ambiguous_current.to_numpy()
        gw1.loc[~gw1["prior_matched"], "prior_player_id"] = pd.NA
        for column in columns[2:]:
            gw1[column] = pd.to_numeric(gw1[column], errors="coerce").fillna(0.0)
        gw1["prior_player_id"] = pd.to_numeric(
            gw1["prior_player_id"], errors="coerce"
        ).astype("Int64")
        gw1.loc[gw1["prior_matched"], "identity_match_method"] = "normalized_name"
        prior_teams = set(prior["team"].dropna().astype(str))
        gw1["promoted_team"] = ~gw1["team"].astype(str).isin(prior_teams)

    position_prior = gw1[gw1["prior_matched"]].groupby("position_group")[
        "prior_points_per_appearance"
    ].median()
    global_prior = float(
        gw1.loc[gw1["prior_matched"], "prior_points_per_appearance"].median()
    )
    if not np.isfinite(global_prior):
        global_prior = 2.5
    unmatched = ~gw1["prior_matched"]
    gw1.loc[unmatched, "prior_points_per_appearance"] = (
        gw1.loc[unmatched, "position_group"].map(position_prior).fillna(global_prior)
    )
    gw1.loc[unmatched, "prior_value"] = gw1.loc[
        unmatched, "prior_points_per_appearance"
    ].div(gw1.loc[unmatched, "price"].replace(0, np.nan)).fillna(0.0)
    gw1["unmatched_player"] = unmatched
    ownership = (
        gw1["selected_by_percent"]
        if "selected_by_percent" in gw1
        else pd.Series(0.0, index=gw1.index)
    )
    gw1["identity_value_score"] = (
        0.55 * normalise_numeric(gw1["prior_points_per_appearance"])
        + 0.25 * normalise_numeric(gw1["prior_value"])
        + 0.10 * normalise_numeric(gw1["prior_minutes"])
        + 0.10 * normalise_numeric(ownership)
        - 0.08 * gw1["unmatched_player"].astype(float)
        - 0.04 * gw1["promoted_team"].astype(float)
    ).clip(lower=0.0)
    return gw1


def decision_price(frame: pd.DataFrame) -> pd.Series:
    current = pd.to_numeric(frame["price"], errors="coerce")
    if "price_before_deadline" not in frame:
        return current
    snapshot = pd.to_numeric(frame["price_before_deadline"], errors="coerce")
    return snapshot.where(snapshot > 0, current)


def normalise_numeric(series: pd.Series | float) -> pd.Series:
    values = (
        pd.Series(series)
        if not isinstance(series, pd.Series)
        else pd.to_numeric(series, errors="coerce")
    )
    maximum = values.max()
    return (
        pd.Series(0.0, index=values.index)
        if pd.isna(maximum) or maximum <= 0
        else values.fillna(0.0) / maximum
    )


def normalise_player_name(value: object) -> str:
    text = str(value or "").strip().casefold()
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
