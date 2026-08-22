from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from fpl_intelligence.season_rules import (
    RULES_SCHEMA_VERSION,
    build_season_rules,
    build_snapshot_metadata,
    save_immutable_snapshot,
    save_rules_manifest,
    validate_bootstrap_onboarding,
)

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
BOOTSTRAP_PATH = RAW_DATA_DIR / "bootstrap-static.json"
PLAYERS_CURRENT_PATH = PROCESSED_DATA_DIR / "players_current.csv"

TOP_LEVEL_KEY_DESCRIPTIONS = {
    "chips": "FPL chip definitions such as wildcard, bench boost, free hit, and triple captain.",
    "events": "Gameweek metadata, including deadlines, status, and highest-scoring player ids.",
    "game_settings": "Global game rules and limits such as squad size and league settings.",
    "game_config": "Scoring rules and configurable settings used by the FPL game.",
    "phases": "Season phases used by FPL for overall and monthly periods.",
    "teams": "Premier League teams, ids, names, strengths, and fixture difficulty fields.",
    "total_players": "Total number of registered FPL managers.",
    "element_stats": "Definitions for player statistic fields shown by FPL.",
    "element_types": "Position definitions: goalkeeper, defender, midfielder, and forward.",
    "elements": "Player records, including prices, points, form, minutes, ownership, and team ids.",
}

COLUMN_EXPLANATIONS = {
    "element_id": "Stable FPL player identifier from the bootstrap element id.",
    "team_id": "Stable FPL team identifier.",
    "position_id": "Stable FPL position identifier.",
    "player_name": "Full player name built from first_name and second_name.",
    "web_name": "Short display name used by FPL.",
    "team_name": "Human-readable club name mapped from the player's team id.",
    "team_short_name": "Three-letter club abbreviation mapped from the player's team id.",
    "position": "Human-readable FPL position mapped from the player's element_type id.",
    "price": "Current FPL price converted from now_cost, where 105 becomes 10.5.",
    "total_points": "Total FPL points the player has scored in the current dataset.",
    "points_per_game": "Average FPL points per appearance as reported by FPL.",
    "form": "Recent form value as reported by FPL.",
    "minutes": "Total Premier League minutes played in the current dataset.",
    "selected_by_percent": "Percentage of FPL managers currently owning the player.",
    "status": "Current FPL availability status code.",
    "chance_of_playing_next_round": "FPL-estimated chance of playing in the next round.",
    "chance_of_playing_this_round": "FPL-estimated chance of playing in the current round.",
    "news": "Current FPL news text associated with the player.",
    "news_added": "Timestamp of the latest FPL news update, when supplied.",
    "now_cost": "Current FPL price in tenths of the game currency.",
    "value_score": "Simple value metric: total_points divided by current price.",
    "defensive_contribution": (
        "Season-total FPL points awarded for meeting the defensive contribution threshold."
    ),
    "defensive_contribution_per_90": (
        "Defensive actions per 90 minutes: clearances, blocks, interceptions, tackles, and "
        "recoveries combined under the current FPL Defensive Contributions rule."
    ),
    "starts": "Previous-season starts supplied in the launch bootstrap.",
    "bonus": "Previous-season FPL bonus points under that season's BPS regime.",
    "bps": "Previous-season raw Bonus Points System total.",
    "clearances_blocks_interceptions": "Previous-season CBI action total.",
    "tackles": "Previous-season tackle total.",
    "recoveries": "Previous-season recovery total.",
    "player_code": "Stable Premier League player code used to reconcile set-piece roles.",
    "penalties_order": "Official sortable penalty-taking order for the player's club.",
    "penalties_text": "Official explanatory penalty-taking text, when supplied.",
    "direct_freekicks_order": "Official sortable direct-free-kick order.",
    "direct_freekicks_text": "Official explanatory direct-free-kick text, when supplied.",
    "corners_and_indirect_freekicks_order": (
        "Official sortable corners and indirect-free-kick order."
    ),
    "corners_and_indirect_freekicks_text": (
        "Official explanatory corner/indirect-free-kick text, when supplied."
    ),
}


def fetch_json(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def save_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_bootstrap_data(path: Path = BOOTSTRAP_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def describe_bootstrap_structure(bootstrap_data: dict[str, Any]) -> list[str]:
    descriptions = []
    for key, value in bootstrap_data.items():
        description = TOP_LEVEL_KEY_DESCRIPTIONS.get(key, "No description available yet.")
        if isinstance(value, list):
            shape = f"list with {len(value)} records"
        elif isinstance(value, dict):
            shape = f"dictionary with {len(value)} keys"
        else:
            shape = type(value).__name__

        descriptions.append(f"- {key}: {shape}. {description}")

    return descriptions


def load_players(bootstrap_data: dict[str, Any]) -> pd.DataFrame:
    players = pd.DataFrame(bootstrap_data["elements"])
    teams = pd.DataFrame(bootstrap_data["teams"])[["id", "name", "short_name"]].rename(
        columns={
            "id": "team_id",
            "name": "team_name",
            "short_name": "team_short_name",
        }
    )
    positions = pd.DataFrame(bootstrap_data["element_types"])[["id", "singular_name"]].rename(
        columns={
            "id": "position_id",
            "singular_name": "position",
        }
    )

    players = players.merge(
        teams,
        left_on="team",
        right_on="team_id",
        how="left",
    )
    players = players.merge(
        positions,
        left_on="element_type",
        right_on="position_id",
        how="left",
    )

    players["price"] = players["now_cost"] / 10
    players["element_id"] = players["id"]
    players["player_code"] = players["code"] if "code" in players else pd.NA
    players["player_name"] = players["first_name"] + " " + players["second_name"]
    players["points_per_game"] = pd.to_numeric(players["points_per_game"], errors="coerce")
    players["form"] = pd.to_numeric(players["form"], errors="coerce")
    players["selected_by_percent"] = pd.to_numeric(players["selected_by_percent"], errors="coerce")
    for column in [
        "defensive_contribution",
        "defensive_contribution_per_90",
        "starts",
        "bonus",
        "bps",
        "clearances_blocks_interceptions",
        "tackles",
        "recoveries",
    ]:
        if column in players:
            players[column] = pd.to_numeric(players[column], errors="coerce").fillna(0.0)
        else:
            players[column] = 0.0
    for column in [
        "penalties_order",
        "direct_freekicks_order",
        "corners_and_indirect_freekicks_order",
    ]:
        players[column] = (
            pd.to_numeric(players[column], errors="coerce")
            if column in players
            else pd.NA
        )
    players["value_score"] = players["total_points"].div(
        players["price"].where(players["price"] > 0)
    ).fillna(0.0)

    columns = list(COLUMN_EXPLANATIONS)
    for column in columns:
        if column not in players:
            players[column] = pd.NA
    return players[columns].sort_values("total_points", ascending=False).reset_index(drop=True)


def save_players(players: pd.DataFrame, path: Path = PLAYERS_CURRENT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    players.to_csv(path, index=False)


def save_bootstrap_contract(
    bootstrap_data: dict[str, Any],
    *,
    season: str,
    source_url: str = FPL_BOOTSTRAP_URL,
    retrieved_at: str | None = None,
    cutoff_at: str | None = None,
    snapshot_root: Path | None = None,
    manifest_root: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Persist raw bootstrap data, metadata, and the normalized rules manifest."""

    onboarding_errors = validate_bootstrap_onboarding(bootstrap_data, season=season)
    if onboarding_errors:
        raise ValueError("Bootstrap onboarding validation failed: " + "; ".join(onboarding_errors))

    metadata = build_snapshot_metadata(
        bootstrap_data,
        season=season,
        source_url=source_url,
        retrieved_at=retrieved_at,
        cutoff_at=cutoff_at,
        schema_version=RULES_SCHEMA_VERSION,
    )
    snapshot_path, metadata_path = save_immutable_snapshot(
        bootstrap_data,
        metadata,
        root=snapshot_root if snapshot_root is not None else RAW_DATA_DIR / "snapshots",
    )
    rules = build_season_rules(
        bootstrap_data,
        season=season,
        source_url=source_url,
        retrieved_at=metadata["retrieved_at"],
        cutoff_at=metadata["cutoff_at"],
    )
    manifest_path = save_rules_manifest(
        rules,
        root=manifest_root if manifest_root is not None else PROCESSED_DATA_DIR / "rules",
    )
    return snapshot_path, metadata_path, manifest_path


def fetch_and_save_bootstrap(
    *,
    season: str,
    source_url: str = FPL_BOOTSTRAP_URL,
    legacy_path: Path = BOOTSTRAP_PATH,
    snapshot_root: Path | None = None,
    manifest_root: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Fetch current bootstrap data and persist both legacy and M6 contracts."""

    bootstrap_data = fetch_json(source_url)
    save_json(bootstrap_data, legacy_path)
    return save_bootstrap_contract(
        bootstrap_data,
        season=season,
        source_url=source_url,
        snapshot_root=snapshot_root,
        manifest_root=manifest_root,
    )


def print_column_explanations() -> None:
    print("\nClean player table columns:")
    for column, explanation in COLUMN_EXPLANATIONS.items():
        print(f"- {column}: {explanation}")


def print_top_players(players: pd.DataFrame, sort_column: str, limit: int = 10) -> None:
    display_columns = [
        "player_name",
        "team_name",
        "position",
        "price",
        "total_points",
        "points_per_game",
        "form",
        "minutes",
        "selected_by_percent",
        "value_score",
    ]

    top_players = players.sort_values(sort_column, ascending=False).head(limit)
    print(f"\nTop {limit} players by {sort_column}:")
    print(top_players[display_columns].to_string(index=False))


def main() -> None:
    bootstrap_data = load_bootstrap_data()

    print("bootstrap-static top-level structure:")
    for line in describe_bootstrap_structure(bootstrap_data):
        print(line)

    players = load_players(bootstrap_data)
    print_column_explanations()
    print_top_players(players, "value_score")
    print_top_players(players, "total_points")
    save_players(players)
    print(f"\nSaved cleaned player table to {PLAYERS_CURRENT_PATH}")


if __name__ == "__main__":
    main()
