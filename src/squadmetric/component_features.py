"""Shared component outcome and lagged-feature definitions for M7."""

from __future__ import annotations

COMPONENT_TARGET_COLUMNS = (
    "goals_scored",
    "assists",
    "clean_sheets",
    "saves",
    "penalties_saved",
    "penalties_missed",
    "own_goals",
    "yellow_cards",
    "red_cards",
    "goals_conceded",
    "bonus",
)
COMPONENT_LAG_WINDOWS = (1, 3, 5, 8)
COMPONENT_LAG_FEATURES = tuple(
    f"{column}_last_{window}"
    for column in COMPONENT_TARGET_COLUMNS
    for window in COMPONENT_LAG_WINDOWS
)
COMPONENT_MODEL_COLUMNS = COMPONENT_TARGET_COLUMNS + ("defensive_contribution",)


def component_lag_features() -> list[str]:
    return list(COMPONENT_LAG_FEATURES)
