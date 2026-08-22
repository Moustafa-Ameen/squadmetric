import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

PLAYERS_RANKED_REQUIRED_COLUMNS = [
    "player_name",
    "team_name",
    "position",
    "price",
    "points_per_game",
    "form",
    "minutes_security",
    "value_score",
    "captain_score",
    "transfer_score",
    "defensive_contribution_per_90",
]

PLAYERS_RANKED_NUMERIC_COLUMNS = [
    "price",
    "total_points",
    "points_per_game",
    "form",
    "minutes",
    "selected_by_percent",
    "value_score",
    "minutes_security",
    "ownership_risk",
    "captain_score",
    "transfer_score",
    "defensive_contribution",
    "defensive_contribution_per_90",
    "defensive_contribution_per_90_norm",
]

DATA_FILES = {
    "players": "players_ranked.csv",
    "raw_accuracy": "step7_raw_accuracy.csv",
    "adjusted_accuracy": "step7_adjusted_accuracy.csv",
    "captaincy_backtest": "step7_captaincy_backtest.csv",
    "top10_metrics": "step7_top10_metrics.csv",
    "historical_player_gw": "historical_player_gw.csv",
}


@lru_cache(maxsize=len(DATA_FILES) * 4)
def _load_dataset_versioned(key: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    filename = DATA_FILES.get(key)
    if filename is None:
        logging.warning("Unknown data key requested: %s", key)
        return pd.DataFrame()

    path = PROCESSED_DIR / filename
    if not path.exists():
        logging.warning("Processed data file is missing: %s", path)
        return pd.DataFrame()

    return pd.read_csv(path)


def load_dataset(key: str) -> pd.DataFrame:
    filename = DATA_FILES.get(key)
    if filename is None:
        logging.warning("Unknown data key requested: %s", key)
        return pd.DataFrame()
    path = PROCESSED_DIR / filename
    modified_ns = path.stat().st_mtime_ns if path.exists() else 0
    return _load_dataset_versioned(key, modified_ns)


def to_records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    if dataframe.empty:
        return []

    clean = dataframe.astype(object).where(pd.notna(dataframe), None)
    return clean.to_dict(orient="records")


def players() -> pd.DataFrame:
    return load_dataset("players").copy()


def raw_accuracy() -> pd.DataFrame:
    return load_dataset("raw_accuracy").copy()


def adjusted_accuracy() -> pd.DataFrame:
    return load_dataset("adjusted_accuracy").copy()


def captaincy_backtest() -> pd.DataFrame:
    return load_dataset("captaincy_backtest").copy()


def top10_metrics() -> pd.DataFrame:
    return load_dataset("top10_metrics").copy()


def historical_player_gw() -> pd.DataFrame:
    return load_dataset("historical_player_gw").copy()


@lru_cache(maxsize=4)
def _bootstrap_static_versioned(modified_ns: int) -> dict[str, Any]:
    del modified_ns
    path = RAW_DIR / "bootstrap-static.json"
    if not path.exists():
        logging.warning("Bootstrap data file is missing: %s", path)
        return {}

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def bootstrap_static() -> dict[str, Any]:
    path = RAW_DIR / "bootstrap-static.json"
    modified_ns = path.stat().st_mtime_ns if path.exists() else 0
    return _bootstrap_static_versioned(modified_ns)
