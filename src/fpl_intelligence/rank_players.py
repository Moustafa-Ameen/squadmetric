from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAYERS_CURRENT_PATH = PROJECT_ROOT / "data" / "processed" / "players_current.csv"
PLAYERS_RANKED_PATH = PROJECT_ROOT / "data" / "processed" / "players_ranked.csv"

FORMULA_EXPLANATIONS = {
    "minutes_security": (
        "minutes / max_minutes_in_dataset, clipped to 0-1. This approximates how nailed-on a "
        "player has been across the season, but it cannot see recent rotation until Step 3 adds "
        "per-gameweek data."
    ),
    "ownership_risk": (
        "1 - selected_by_percent / 100. I treat low ownership as higher risk because differentials "
        "often carry uncertainty around minutes, role, team strength, or proven FPL output."
    ),
    "captain_score": (
        "0.50 * points_per_game_norm + 0.30 * form_norm + 0.20 * minutes_security. Captaincy "
        "prioritizes scoring rate, then current form, then reliable minutes."
    ),
    "transfer_score": (
        "0.70 * value_score_norm + 0.20 * form_norm - 0.10 * ownership_risk. Transfers prioritize "
        "value, reward form, and apply a small penalty for low-ownership risk."
    ),
    "defensive_contribution_per_90": (
        "Live-only defensive actions per 90 rate. It is carried through for rule-based "
        "safety tiers and is intentionally not an ML training feature."
    ),
}


def normalize(series: pd.Series) -> pd.Series:
    max_value = series.max()
    if pd.isna(max_value) or max_value <= 0:
        return pd.Series(0.0, index=series.index)

    return series / max_value


def load_current_players(path: Path = PLAYERS_CURRENT_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def add_rule_based_scores(players: pd.DataFrame) -> pd.DataFrame:
    ranked = players.copy()

    max_minutes = ranked["minutes"].max()
    if pd.isna(max_minutes) or max_minutes <= 0:
        prior = (
            ranked["preseason_minutes_prior"]
            if "preseason_minutes_prior" in ranked
            else pd.Series(0.0, index=ranked.index)
        )
        ranked["minutes_security"] = pd.to_numeric(
            prior, errors="coerce"
        ).fillna(0.0)
    else:
        ranked["minutes_security"] = (ranked["minutes"] / max_minutes).clip(
            lower=0, upper=1
        )
    ranked["ownership_risk"] = (1 - ranked["selected_by_percent"] / 100).clip(lower=0, upper=1)
    if "defensive_contribution_per_90" not in ranked:
        ranked["defensive_contribution_per_90"] = 0.0
    ranked["defensive_contribution_per_90"] = pd.to_numeric(
        ranked["defensive_contribution_per_90"], errors="coerce"
    ).fillna(0.0)
    ranked["defensive_contribution_per_90_norm"] = normalize(
        ranked["defensive_contribution_per_90"]
    )

    points_per_game_norm = normalize(ranked["points_per_game"])
    form_norm = normalize(ranked["form"])
    value_score_norm = normalize(ranked["value_score"])

    ranked["captain_score"] = (
        0.50 * points_per_game_norm + 0.30 * form_norm + 0.20 * ranked["minutes_security"]
    )
    ranked["transfer_score"] = (
        0.70 * value_score_norm + 0.20 * form_norm - 0.10 * ranked["ownership_risk"]
    )

    return ranked


def add_preseason_priors(
    players: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    """Attach explicit, name-matched priors when the live season has no results.

    FPL element IDs are season-local and must never be matched across seasons.
    Returning players are therefore matched by normalized full name. New players
    receive conservative position priors and are clearly labelled.
    """

    output = players.copy()
    output["prior_source"] = "current_season"
    output["preseason_minutes_prior"] = 0.0
    official_previous_stats = output["minutes"].max() > 0
    if official_previous_stats:
        has_official_stats = (
            pd.to_numeric(output["minutes"], errors="coerce").fillna(0.0) > 0
        ) | (
            pd.to_numeric(output["total_points"], errors="coerce").fillna(0.0) > 0
        )
        output.loc[has_official_stats, "prior_source"] = (
            "official_previous_season_stats_unmatched"
        )
    if history.empty:
        return output

    latest_season = str(history["season"].dropna().max())
    latest = history[history["season"].astype(str) == latest_season].copy()
    required = {"player_name", "position", "gameweek", "minutes", "total_points"}
    if latest.empty or not required.issubset(latest.columns):
        return _apply_new_player_priors(output)

    latest["player_key"] = latest["player_name"].map(_normalize_name)
    latest["minutes"] = pd.to_numeric(latest["minutes"], errors="coerce").fillna(0.0)
    latest["total_points"] = pd.to_numeric(
        latest["total_points"], errors="coerce"
    ).fillna(0.0)
    latest["gameweek"] = pd.to_numeric(latest["gameweek"], errors="coerce")
    latest = latest.sort_values("gameweek")

    aggregates = latest.groupby("player_key", as_index=False).agg(
        prior_points=("total_points", "sum"),
        prior_minutes=("minutes", "sum"),
        prior_appearances=("minutes", lambda values: int((values > 0).sum())),
        prior_starts=("minutes", lambda values: int((values >= 60).sum())),
    )
    recent = (
        latest.groupby("player_key", sort=False)
        .tail(3)
        .groupby("player_key", as_index=False)["total_points"]
        .mean()
        .rename(columns={"total_points": "prior_form"})
    )
    aggregates = aggregates.merge(recent, on="player_key", how="left")
    aggregates["prior_ppg"] = aggregates["prior_points"].div(
        aggregates["prior_appearances"].where(aggregates["prior_appearances"] > 0)
    )
    aggregates["preseason_minutes_prior"] = aggregates["prior_starts"].div(38).clip(0, 1)

    output["player_key"] = output["player_name"].map(_normalize_name)
    output = output.merge(
        aggregates[
            [
                "player_key",
                "prior_ppg",
                "prior_form",
                "preseason_minutes_prior",
            ]
        ],
        on="player_key",
        how="left",
    )
    returning = output["prior_ppg"].notna()
    missing_ppg = returning & (
        pd.to_numeric(output["points_per_game"], errors="coerce").fillna(0.0) <= 0
    )
    output.loc[missing_ppg, "points_per_game"] = output.loc[missing_ppg, "prior_ppg"]
    output.loc[returning, "form"] = output.loc[returning, "prior_form"]
    output.loc[returning, "prior_source"] = (
        f"official_{latest_season}_stats"
        if official_previous_stats
        else f"returning_player_{latest_season}"
    )
    output = _apply_new_player_priors(output)
    return output.drop(
        columns=["player_key", "prior_ppg", "prior_form"],
        errors="ignore",
    )


def _apply_new_player_priors(players: pd.DataFrame) -> pd.DataFrame:
    output = players.copy()
    missing = output["prior_source"].isin(
        {"current_season", "official_previous_season_stats_unmatched"}
    ) & (
        pd.to_numeric(output["points_per_game"], errors="coerce").fillna(0.0) <= 0
    )
    ppg_by_position = {
        "Goalkeeper": 3.2,
        "Defender": 3.0,
        "Midfielder": 3.4,
        "Forward": 3.6,
    }
    start_by_status = {"a": 0.55, "d": 0.25, "i": 0.0, "s": 0.0, "u": 0.0}
    output.loc[missing, "points_per_game"] = (
        output.loc[missing, "position"].map(ppg_by_position).fillna(3.0)
    )
    output.loc[missing, "form"] = output.loc[missing, "points_per_game"]
    output.loc[missing, "preseason_minutes_prior"] = (
        output.loc[missing, "status"].map(start_by_status).fillna(0.4)
    )
    output.loc[missing, "prior_source"] = "new_player_position_prior"
    return output


def _normalize_name(value: object) -> str:
    text = str(value or "").strip().casefold()
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def save_ranked_players(players: pd.DataFrame, path: Path = PLAYERS_RANKED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    players.to_csv(path, index=False)


def print_formula_explanations() -> None:
    print("Step 2 rule-based formulas:")
    for column, explanation in FORMULA_EXPLANATIONS.items():
        print(f"- {column}: {explanation}")


def print_top_rankings(players: pd.DataFrame, sort_column: str, limit: int = 10) -> None:
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
        "minutes_security",
        "ownership_risk",
        sort_column,
    ]
    top_players = players.sort_values(sort_column, ascending=False).head(limit)

    print(f"\nTop {limit} players by {sort_column}:")
    print(top_players[display_columns].to_string(index=False))


def find_sanity_warnings(players: pd.DataFrame) -> list[str]:
    warnings = []
    if players["form"].max() == 0:
        warnings.append(
            "All form values are 0 in the current API snapshot, so form does not affect today's "
            "captain_score or transfer_score rankings."
        )

    top_captains = players.sort_values("captain_score", ascending=False).head(10)
    low_minutes_captains = top_captains[top_captains["minutes_security"] < 0.50]
    if not low_minutes_captains.empty:
        names = ", ".join(low_minutes_captains["player_name"].tolist())
        warnings.append(f"Low-minutes players appear in the captain top 10: {names}.")

    top_transfers = players.sort_values("transfer_score", ascending=False).head(10)
    low_minutes_transfers = top_transfers[top_transfers["minutes_security"] < 0.50]
    if not low_minutes_transfers.empty:
        names = ", ".join(low_minutes_transfers["player_name"].tolist())
        warnings.append(
            f"Low-minutes players appear in the transfer top 10: {names}. This can happen because "
            "transfer_score is value-heavy."
        )

    return warnings


def main() -> None:
    players = load_current_players()
    ranked_players = add_rule_based_scores(players)

    print_formula_explanations()
    print_top_rankings(ranked_players, "captain_score")
    print_top_rankings(ranked_players, "transfer_score")

    warnings = find_sanity_warnings(ranked_players)
    print("\nSanity notes:")
    if warnings:
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("- No obvious low-minutes outliers appeared in the top 10 rankings.")

    save_ranked_players(ranked_players)
    print(f"\nSaved ranked player table to {PLAYERS_RANKED_PATH}")


if __name__ == "__main__":
    main()
