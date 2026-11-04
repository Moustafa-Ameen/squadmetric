from __future__ import annotations

from pathlib import Path

import pandas as pd

from squadmetric.component_features import (
    COMPONENT_LAG_FEATURES,
    COMPONENT_TARGET_COLUMNS,
)
from squadmetric.season_rules import historical_regime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_HISTORICAL_DIR = PROJECT_ROOT / "data" / "raw" / "historical"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
HISTORICAL_PLAYER_GW_PATH = PROCESSED_DATA_DIR / "historical_player_gw.csv"

SEASONS = ["2023-24", "2024-25", "2025-26"]
XG_XA_COLUMNS = ["expected_goals", "expected_assists"]
DC_COLUMNS = [
    "clearances_blocks_interceptions",
    "defensive_contribution",
    "recoveries",
    "tackles",
]
ADVANCED_STAT_COLUMNS = XG_XA_COLUMNS + DC_COLUMNS + list(COMPONENT_TARGET_COLUMNS)

SOURCE_FILES = {
    season: {
        "merged_gw": RAW_HISTORICAL_DIR / season / "merged_gw.csv",
        "teams": RAW_HISTORICAL_DIR / season / "teams.csv",
    }
    for season in SEASONS
}

RELEVANT_COLUMN_EXPLANATIONS = {
    "season": "FPL season the row came from.",
    "player_id": "Vaastav/FPL player identifier from the element column.",
    "player_name": "Player name from Vaastav's per-gameweek row.",
    "gameweek": "The target gameweek being predicted.",
    "feature_cutoff_gameweek": "Last completed gameweek allowed in rolling features.",
    "price": (
        "Raw FPL price snapshot associated with the target gameweek, converted from value / 10; "
        "retained for roster accounting, not model features."
    ),
    "price_before_deadline": (
        "Latest observed price from a prior player-gameweek row; the explicit timing-safe "
        "approximation used by historical models."
    ),
    "position": "FPL position abbreviation such as GK, DEF, MID, or FWD.",
    "team": "Player's team in that gameweek.",
    "opponent_team": "Opponent team name mapped from the opponent_team id.",
    "opponent_strength": "Opponent overall strength for the venue they are playing in.",
    "home_or_away": "H if the player is at home, A if away.",
    "selected_by_percent": (
        "Estimated ownership percentage for the raw gameweek snapshot; retained for analysis, "
        "not model features."
    ),
    "selected_by_percent_before_deadline": (
        "Latest observed ownership from a prior player-gameweek row; the explicit timing-safe "
        "approximation used by historical models."
    ),
    "market_snapshot_available": (
        "1 when a prior player-gameweek market snapshot exists; 0 for first-observed rows "
        "such as historical GW1."
    ),
    "minutes": "Actual minutes played in the target gameweek.",
    "starts": "Number of fixtures started in the target gameweek.",
    "total_points": "Actual FPL points scored in the target gameweek.",
    "minutes_last_3": "Sum of minutes from the player's previous three gameweeks only.",
    "points_last_3": "Sum of points from the player's previous three gameweeks only.",
    "prior_games_available_last_3": "Count of prior player-gameweek rows available in the window.",
    "next_gameweek_points": "Prediction target: actual total_points in the target gameweek.",
    "expected_goals": (
        "Raw expected goals in the target gameweek; only prior rolling values are model features."
    ),
    "expected_assists": (
        "Raw expected assists in the target gameweek; only prior rolling values are model features."
    ),
    "dc_rule_version": "Rule era for Defensive Contributions: pre_dc or dc_v1.",
    "bps_rule_version": "Bonus Points System rule era for the season.",
}


def combine_unique_text(values: pd.Series) -> str:
    unique_values = sorted(str(value) for value in values.dropna().unique())
    return "+".join(unique_values)


def combine_home_away(values: pd.Series) -> str:
    unique_values = sorted(str(value) for value in values.dropna().unique())
    if len(unique_values) == 1:
        return unique_values[0]

    return "M"


def load_historical_raw(seasons: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected_seasons = seasons or SEASONS
    gameweek_frames = []
    team_frames = []

    for season in selected_seasons:
        files = SOURCE_FILES[season]
        gameweeks = pd.read_csv(files["merged_gw"])
        teams = pd.read_csv(files["teams"])

        gameweeks["season"] = season
        teams["season"] = season

        gameweek_frames.append(gameweeks)
        team_frames.append(teams)

    return pd.concat(gameweek_frames, ignore_index=True), pd.concat(team_frames, ignore_index=True)


def print_raw_structure(gameweeks: pd.DataFrame) -> None:
    print("Raw Vaastav merged_gw.csv columns:")
    print(", ".join(gameweeks.columns))

    print("\nRelevant columns:")
    for column, explanation in RELEVANT_COLUMN_EXPLANATIONS.items():
        if column in {"feature_cutoff_gameweek", "price", "opponent_strength", "home_or_away"}:
            source_note = "derived"
        elif column == "player_id":
            source_note = "from element"
        elif column == "player_name":
            source_note = "from name"
        elif column == "gameweek":
            source_note = "from GW"
        elif column == "selected_by_percent":
            source_note = "derived from selected / estimated managers"
        elif column == "next_gameweek_points":
            source_note = "from total_points"
        else:
            source_note = "raw or rolling"
        print(f"- {column}: {explanation} ({source_note})")


def build_opponent_lookup(teams: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "season",
        "id",
        "name",
        "strength_overall_home",
        "strength_overall_away",
    ]
    return teams[columns].rename(
        columns={
            "id": "opponent_team_id",
            "name": "opponent_team",
        }
    )


def add_selected_by_percent(gameweeks: pd.DataFrame) -> pd.DataFrame:
    ranked = gameweeks.copy()
    player_key = "element" if "element" in ranked.columns else "name"
    unique_player_gameweeks = ranked.drop_duplicates(["season", "GW", player_key])
    estimated_managers = (
        unique_player_gameweeks.groupby(["season", "GW"], as_index=False)["selected"]
        .sum()
        .assign(estimated_managers=lambda frame: frame["selected"] / 15)
        [["season", "GW", "estimated_managers"]]
    )
    ranked = ranked.merge(estimated_managers, on=["season", "GW"], how="left")
    ranked["selected_by_percent"] = (
        ranked["selected"] / ranked["estimated_managers"] * 100
    ).fillna(0)
    ranked = ranked.drop(columns=["estimated_managers"])
    return ranked


def deduplicate_exact_fixture_rows(gameweeks: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate fixture records without hiding conflicting duplicates."""

    key = [column for column in ("season", "GW", "element", "fixture") if column in gameweeks]
    if len(key) == 4:
        return gameweeks.drop_duplicates(key, keep="first").copy()
    return gameweeks.copy()


def add_rolling_features(players: pd.DataFrame) -> pd.DataFrame:
    """Add strict prior-row rolling features without inventing missing rows.

    A present player-gameweek row with zero minutes is genuine zero production and
    remains in the window.  An absent row is not filled in, so it does not count
    toward ``prior_games_available_last_3``.
    """

    sorted_players = players.sort_values(["season", "player_id", "gameweek"]).copy()
    grouped = sorted_players.groupby(["season", "player_id"], group_keys=False)

    sorted_players["minutes_last_3"] = grouped["minutes"].transform(
        lambda series: series.shift(1).rolling(window=3, min_periods=1).sum()
    )
    sorted_players["points_last_3"] = grouped["total_points"].transform(
        lambda series: series.shift(1).rolling(window=3, min_periods=1).sum()
    )
    sorted_players["prior_games_available_last_3"] = grouped["total_points"].transform(
        lambda series: series.shift(1).rolling(window=3, min_periods=1).count()
    )

    columns_to_fill = ["minutes_last_3", "points_last_3", "prior_games_available_last_3"]
    for source_column in XG_XA_COLUMNS:
        for window in (1, 3, 5, 8):
            feature_name = f"{source_column}_last_{window}"
            sorted_players[feature_name] = grouped[source_column].transform(
                lambda series, window=window: series.shift(1)
                .rolling(window=window, min_periods=1)
                .sum()
            )
            columns_to_fill.append(feature_name)

    component_columns_present = list(COMPONENT_TARGET_COLUMNS)
    for source_column in component_columns_present:
        if source_column not in sorted_players:
            sorted_players[source_column] = float("nan")
        else:
            sorted_players[source_column] = pd.to_numeric(
                sorted_players[source_column], errors="coerce"
            )
    component_prior = sorted_players.groupby(
        ["season", "player_id"], sort=False
    )[component_columns_present].shift(1)
    component_grouped = component_prior.groupby(
        [sorted_players["season"], sorted_players["player_id"]], sort=False
    )
    for window in (1, 3, 5, 8):
        rolling_components = component_grouped[component_columns_present].rolling(
            window=window, min_periods=1
        ).sum()
        rolling_components = rolling_components.reset_index(level=[0, 1], drop=True)
        for source_column in component_columns_present:
            feature_name = f"{source_column}_last_{window}"
            sorted_players[feature_name] = rolling_components[source_column]
            columns_to_fill.append(feature_name)


    for window in (1, 3, 5, 8):
        rolling_xgi = (
            grouped["expected_goals"].transform(
                lambda series, window=window: series.shift(1)
                .rolling(window=window, min_periods=1)
                .sum()
            )
            + grouped["expected_assists"].transform(
                lambda series, window=window: series.shift(1)
                .rolling(window=window, min_periods=1)
                .sum()
            )
        )
        rolling_minutes = grouped["minutes"].transform(
            lambda series, window=window: series.shift(1)
            .rolling(window=window, min_periods=1)
            .sum()
        )
        per90_name = f"xgi_per_90_last_{window}"
        sorted_players[per90_name] = (
            rolling_xgi.div(rolling_minutes.where(rolling_minutes > 0)).mul(90).fillna(0.0)
        )
        columns_to_fill.append(per90_name)

    if "defensive_contribution" in sorted_players:
        rolling_dc = grouped["defensive_contribution"].transform(
            lambda series: series.shift(1).rolling(window=3, min_periods=1).sum()
        )
        rolling_dc_minutes = grouped["minutes"].transform(
            lambda series: series.shift(1).rolling(window=3, min_periods=1).sum()
        )
        sorted_players["defensive_contribution_last_3"] = rolling_dc
        sorted_players["defensive_contribution_per_90_last_3"] = (
            rolling_dc.div(rolling_dc_minutes.where(rolling_dc_minutes > 0))
            .mul(90)
            .fillna(0.0)
        )
        columns_to_fill.extend(
            ["defensive_contribution_last_3", "defensive_contribution_per_90_last_3"]
        )

    sorted_players[columns_to_fill] = sorted_players[columns_to_fill].fillna(0)

    return sorted_players


def aggregate_fixture_rows_to_gameweeks(fixture_rows: pd.DataFrame) -> pd.DataFrame:
    def sum_with_min_count(values: pd.Series) -> float:
        return float(values.sum(min_count=1))

    aggregated = (
        fixture_rows.groupby(["season", "player_id", "gameweek"], as_index=False)
        .agg(
            player_name=("player_name", "first"),
            feature_cutoff_gameweek=("feature_cutoff_gameweek", "first"),
            price=("price", "last"),
            position=("position", "first"),
            team=("team", "first"),
            opponent_team=("opponent_team", combine_unique_text),
            opponent_strength=("opponent_strength", "mean"),
            home_or_away=("home_or_away", combine_home_away),
            team_goals=("team_goals", sum_with_min_count),
            opponent_goals=("opponent_goals", sum_with_min_count),
            team_clean_sheet=("team_clean_sheet", "min"),
            selected_by_percent=("selected_by_percent", "max"),
            minutes=("minutes", "sum"),
            starts=("starts", "sum"),
            total_points=("total_points", "sum"),
            next_gameweek_points=("next_gameweek_points", "sum"),
            expected_goals=("expected_goals", sum_with_min_count),
            expected_assists=("expected_assists", sum_with_min_count),
            clearances_blocks_interceptions=(
                "clearances_blocks_interceptions",
                sum_with_min_count,
            ),
            defensive_contribution=("defensive_contribution", sum_with_min_count),
            recoveries=("recoveries", sum_with_min_count),
            tackles=("tackles", sum_with_min_count),
            dc_rule_version=("dc_rule_version", "first"),
            bps_rule_version=("bps_rule_version", "first"),
            dc_data_available=("dc_data_available", "max"),
            **{
                column: (column, sum_with_min_count)
                for column in COMPONENT_TARGET_COLUMNS
            },
        )
        .sort_values(["season", "gameweek", "player_id"])
        .reset_index(drop=True)
    )
    return aggregated


def build_historical_player_gameweeks(gameweeks: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    source = deduplicate_exact_fixture_rows(gameweeks)
    if "starts" not in source:
        source["starts"] = pd.NA
    source["starts"] = pd.to_numeric(source["starts"], errors="coerce")
    for column in ADVANCED_STAT_COLUMNS:
        if column not in source:
            source[column] = pd.NA
        source[column] = pd.to_numeric(source[column], errors="coerce")
    source["dc_data_available"] = source[DC_COLUMNS].notna().any(axis=1).astype(int)
    regimes = source["season"].map(historical_regime)
    source["dc_rule_version"] = regimes.map(lambda regime: regime["dc_rule_version"])
    source["bps_rule_version"] = regimes.map(lambda regime: regime["bps_rule_version"])
    source = add_selected_by_percent(source)
    source["opponent_team_id"] = source["opponent_team"]
    source = source.drop(columns=["opponent_team"])
    opponents = build_opponent_lookup(teams)

    merged = source.merge(
        opponents,
        left_on=["season", "opponent_team_id"],
        right_on=["season", "opponent_team_id"],
        how="left",
    )

    merged["player_id"] = merged["element"]
    merged["player_name"] = merged["name"]
    merged["gameweek"] = merged["GW"]
    merged["feature_cutoff_gameweek"] = merged["gameweek"] - 1
    merged["price"] = merged["value"] / 10
    merged["home_or_away"] = merged["was_home"].map({True: "H", False: "A"})
    merged["opponent_strength"] = merged.apply(
        lambda row: row["strength_overall_away"]
        if row["was_home"]
        else row["strength_overall_home"],
        axis=1,
    )
    # These are required for chip-era scoring context.  Historical exports
    # predating score retention stay explicitly missing rather than becoming
    # false clean sheets or zero-goal fixtures.
    for column in ("team_h_score", "team_a_score"):
        if column not in merged:
            merged[column] = pd.NA
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged["team_goals"] = merged["team_h_score"].where(
        merged["was_home"], merged["team_a_score"]
    )
    merged["opponent_goals"] = merged["team_a_score"].where(
        merged["was_home"], merged["team_h_score"]
    )
    merged["team_clean_sheet"] = (merged["opponent_goals"] == 0).where(
        merged["opponent_goals"].notna(), pd.NA
    )
    merged["next_gameweek_points"] = merged["total_points"]

    columns = [
        "season",
        "player_id",
        "player_name",
        "gameweek",
        "feature_cutoff_gameweek",
        "price",
        "position",
        "team",
        "opponent_team",
        "opponent_strength",
        "home_or_away",
        "team_goals",
        "opponent_goals",
        "team_clean_sheet",
        "selected_by_percent",
        "minutes",
        "starts",
        "total_points",
        "next_gameweek_points",
        "expected_goals",
        "expected_assists",
        *DC_COLUMNS,
        *COMPONENT_TARGET_COLUMNS,
        "dc_rule_version",
        "bps_rule_version",
        "dc_data_available",
    ]

    fixture_rows = merged[columns].copy()
    clean = aggregate_fixture_rows_to_gameweeks(fixture_rows)
    clean = add_rolling_features(clean)
    market_group = clean.sort_values(["season", "player_id", "gameweek"]).groupby(
        ["season", "player_id"], group_keys=False
    )
    clean["price_before_deadline"] = market_group["price"].transform(lambda series: series.shift(1))
    clean["selected_by_percent_before_deadline"] = market_group[
        "selected_by_percent"
    ].transform(lambda series: series.shift(1))
    clean["market_snapshot_available"] = (
        clean["price_before_deadline"].notna()
        & clean["selected_by_percent_before_deadline"].notna()
    ).astype(int)
    # Keep the feature schema populated for early expanding-window fits. Zero is
    # only a sentinel here; market_snapshot_available tells the model that no
    # pre-deadline snapshot existed and prevents confusing it with a real value.
    clean[["price_before_deadline", "selected_by_percent_before_deadline"]] = clean[
        ["price_before_deadline", "selected_by_percent_before_deadline"]
    ].fillna(0.0)

    final_columns = [
        "season",
        "player_id",
        "player_name",
        "gameweek",
        "feature_cutoff_gameweek",
        "price",
        "price_before_deadline",
        "position",
        "team",
        "opponent_team",
        "opponent_strength",
        "home_or_away",
        "team_goals",
        "opponent_goals",
        "team_clean_sheet",
        "selected_by_percent",
        "selected_by_percent_before_deadline",
        "market_snapshot_available",
        "minutes_last_3",
        "points_last_3",
        "prior_games_available_last_3",
        *XG_XA_COLUMNS,
        *[f"{column}_last_{window}" for column in XG_XA_COLUMNS for window in (1, 3, 5, 8)],
        *[f"xgi_per_90_last_{window}" for window in (1, 3, 5, 8)],
        *COMPONENT_LAG_FEATURES,
        *COMPONENT_TARGET_COLUMNS,
        "clearances_blocks_interceptions",
        "defensive_contribution",
        "recoveries",
        "tackles",
        "defensive_contribution_last_3",
        "defensive_contribution_per_90_last_3",
        "dc_rule_version",
        "bps_rule_version",
        "dc_data_available",
        "minutes",
        "starts",
        "total_points",
        "next_gameweek_points",
    ]
    return (
        clean[final_columns]
        .sort_values(["season", "gameweek", "player_id"])
        .reset_index(drop=True)
    )


def save_historical_player_gameweeks(
    players: pd.DataFrame,
    path: Path = HISTORICAL_PLAYER_GW_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    players.to_csv(path, index=False)


def print_sanity_checks(players: pd.DataFrame) -> None:
    print("\nSanity checks:")
    print(f"- Row count: {len(players):,}")
    print(
        "- Season/gameweek range: "
        f"{players['season'].min()} GW{players['gameweek'].min()} to "
        f"{players['season'].max()} GW{players['gameweek'].max()}"
    )
    print(
        "- Rolling window convention: raw fixture rows are first aggregated to one row per "
        "player-gameweek. For target gameweek N, minutes_last_3 and points_last_3 sum "
        "player-gameweeks N-3 through N-1 only; gameweek N is never included."
    )
    print(
        "- Early gameweeks: missing prior history is filled with 0, while an absent "
        "player-gameweek row is not invented; prior_games_available_last_3 shows how "
        "many observed prior rows existed."
    )
    print(
        "- Target mapping: each row's features are for the target gameweek shown; "
        "next_gameweek_points is the actual total_points in that target gameweek."
    )

    sample_columns = [
        "season",
        "player_id",
        "player_name",
        "gameweek",
        "feature_cutoff_gameweek",
        "minutes_last_3",
        "points_last_3",
        "minutes",
        "total_points",
        "next_gameweek_points",
    ]
    sample = players[
        (players["season"] == "2024-25") & (players["prior_games_available_last_3"] >= 3)
    ].head(5)
    print("\nSample rows with full 3-gameweek history:")
    print(sample[sample_columns].to_string(index=False))


def main() -> None:
    print("Historical source: vaastav/Fantasy-Premier-League")
    print("Pulled seasons: 2023-24, 2024-25, and 2025-26.")
    print(
        "Reason: 2025-26 is the most recent complete Vaastav season available locally for a clean "
        "future backtest; 2023-24 and 2024-25 add prior history for later "
        "chronological experiments."
    )

    gameweeks, teams = load_historical_raw()
    print_raw_structure(gameweeks)

    players = build_historical_player_gameweeks(gameweeks, teams)
    save_historical_player_gameweeks(players)
    print_sanity_checks(players)
    print(f"\nSaved historical player-gameweek table to {HISTORICAL_PLAYER_GW_PATH}")


if __name__ == "__main__":
    main()
