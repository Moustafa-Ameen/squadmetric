import unicodedata
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from api import data_service, fpl_client
from api.live_projection_service import live_projection_rows
from api.player_signals import add_safety_tiers
from api.readiness import require_current_artifacts
from api.routers.fixtures import fixture_source_state, ticker
from api.routers.fpl_live import _detect_season_state
from fpl_intelligence.production_portfolio import get_production_portfolio

router = APIRouter(
    prefix="/api/players",
    tags=["players"],
    dependencies=[Depends(require_current_artifacts)],
)

PLAYER_COLUMN_MAP = {
    "element_id": "element_id",
    "player_name": "name",
    "web_name": "web_name",
    "team_name": "team",
    "team_code": "team_code",
    "position": "position",
    "price": "price",
    "total_points": "total_points",
    "points_per_game": "ppg",
    "form": "form",
    "minutes_security": "start_likelihood",
    "value_score": "value",
    "captain_score": "captain_rank_score",
    "transfer_score": "transfer_rank_score",
    "selected_by_percent": "selected_by_percent",
    "defensive_contribution": "defensive_contribution",
    "defensive_contribution_per_90": "defensive_contribution_per_90",
    "safety_tier": "safety_tier",
}

NUMERIC_COLUMNS = data_service.PLAYERS_RANKED_NUMERIC_COLUMNS
PLAYER_METADATA_COLUMNS = {
    "season": "season",
    "bootstrap_hash": "bootstrap_hash",
    "data_cutoff": "data_cutoff",
    "prior_source": "prior_source",
}

RECENT_FORM_WINDOW = 3


def _load_players() -> tuple[Any, list[str]]:
    dataframe = data_service.players()
    if dataframe.empty:
        return dataframe, []

    dataframe = _add_element_ids(dataframe)
    dataframe = _add_team_codes(dataframe)

    for column in NUMERIC_COLUMNS:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(
                dataframe[column].astype(str).str.rstrip("%"),
                errors="coerce",
            )
    existing_numeric_columns = [column for column in NUMERIC_COLUMNS if column in dataframe.columns]
    dataframe[existing_numeric_columns] = dataframe[existing_numeric_columns].fillna(0)
    dataframe = _add_historical_form_fallback(dataframe)
    dataframe = add_safety_tiers(dataframe)
    available_columns = list(dataframe.columns)
    missing = [column for column in PLAYER_COLUMN_MAP if column not in dataframe.columns]
    if missing:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "players_ranked.csv is missing required columns.",
                "missing_columns": missing,
                "available_columns": available_columns,
            },
        )
    return dataframe, available_columns


def _plain_player_columns(dataframe):
    output = dataframe.rename(columns=PLAYER_COLUMN_MAP)
    columns = [column for column in PLAYER_COLUMN_MAP.values() if column in output.columns]
    columns.extend(
        destination
        for source, destination in PLAYER_METADATA_COLUMNS.items()
        if source in output.columns and destination not in columns
    )
    return output[columns]


def _add_team_codes(dataframe):
    if "team_code" in dataframe.columns:
        return dataframe

    bootstrap = data_service.bootstrap_static()
    teams = bootstrap.get("teams", [])
    code_by_name = {team.get("name"): team.get("code") for team in teams}
    code_by_short = {team.get("short_name"): team.get("code") for team in teams}
    dataframe["team_code"] = dataframe["team_name"].map(code_by_name)
    if "team_short_name" in dataframe.columns:
        dataframe["team_code"] = dataframe["team_code"].fillna(
            dataframe["team_short_name"].map(code_by_short)
        )
    dataframe["team_code"] = dataframe["team_code"].fillna(1).astype(int)
    return dataframe


def _add_element_ids(dataframe):
    if "element_id" in dataframe.columns:
        return dataframe

    bootstrap = data_service.bootstrap_static()
    teams = bootstrap.get("teams", [])
    team_by_id = {team.get("id"): team for team in teams}
    exact: dict[tuple[str, str], int] = {}
    name_only: dict[str, int | None] = {}

    for player in bootstrap.get("elements", []):
        team = team_by_id.get(player.get("team"), {})
        short = _normalize(team.get("short_name"))
        full_name = f"{player.get('first_name', '')} {player.get('second_name', '')}".strip()
        names = {_normalize(full_name), _normalize(player.get("web_name"))}
        for name in names:
            if not name:
                continue
            exact[(name, short)] = player.get("id")
            name_only[name] = player.get("id") if name not in name_only else None

    def lookup(row: pd.Series) -> int | None:
        row_names = [
            _normalize(row.get("player_name")),
            _normalize(row.get("web_name")),
        ]
        row_teams = [
            _normalize(row.get("team_short_name")),
            _normalize(row.get("team_name")),
        ]
        for row_name in row_names:
            for row_team in row_teams:
                found = exact.get((row_name, row_team))
                if found is not None:
                    return found
        for row_name in row_names:
            found = name_only.get(row_name)
            if found is not None:
                return found
        return None

    dataframe["element_id"] = dataframe.apply(lookup, axis=1)
    return dataframe


def _add_historical_form_fallback(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Fill an empty API form snapshot from the player's latest three GWs.

    The FPL API's form field is sometimes empty early in a season or in a
    stale local snapshot. It must remain a short-term metric, so this fallback
    deliberately uses only the latest three rows for each player in the latest
    season. Season totals are never used to derive form.
    """
    if "form" not in dataframe.columns or dataframe["form"].max() > 0:
        return dataframe

    history = data_service.serving_player_gw()
    if history.empty or "total_points" not in history.columns or "season" not in history.columns:
        return dataframe

    latest_season = history["season"].dropna().max()
    season_history = history[history["season"] == latest_season].copy()
    if season_history.empty:
        return dataframe

    season_history["gameweek"] = pd.to_numeric(season_history["gameweek"], errors="coerce")
    season_history["total_points"] = pd.to_numeric(
        season_history["total_points"], errors="coerce"
    )
    season_history = season_history.dropna(subset=["gameweek", "total_points"])
    if season_history.empty:
        return dataframe

    # Tail per player rather than filtering from one global latest GW. This
    # preserves a player's latest available history when a fixture is missed.
    recent = season_history.sort_values("gameweek")
    recent_by_name: dict[str, float] = {}
    if "player_name" in recent.columns:
        recent["player_key"] = recent["player_name"].map(_normalize)
        recent_by_name = (
            recent[recent["player_key"] != ""]
            .groupby("player_key", sort=False)
            .tail(RECENT_FORM_WINDOW)
            .groupby("player_key")["total_points"]
            .mean()
            .to_dict()
        )

    names = dataframe["player_name"].map(_normalize)
    form = names.map(recent_by_name)
    dataframe["form"] = form.fillna(0.0)
    return dataframe


def _normalize(value: Any) -> str:
    text = str(value or "").strip().casefold()
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _captain_reasoning(row: pd.Series, rank: int) -> str:
    if rank == 1:
        return "Highest historical captain ranking score"
    if row.get("minutes_security", 0) > 0.9 and row.get("form", 0) > 7:
        return "Nailed starter, red-hot form"
    if row.get("minutes_security", 0) > 0.9:
        return "Near-certain starter"
    if row.get("form", 0) > 7:
        return "Excellent recent form"
    return "Strong overall metrics"


@router.get("")
def get_players(
    position: str | None = Query(default=None),
    sort_by: str = Query(default="captain_rank_score"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    dataframe, _ = _load_players()
    if dataframe.empty:
        return []

    if position:
        dataframe = dataframe[dataframe["position"].str.casefold() == position.casefold()]

    output = _plain_player_columns(dataframe)
    if sort_by not in output.columns:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(output.columns)}",
        )

    output = output.sort_values(sort_by, ascending=False).head(limit)
    return data_service.to_records(output)


@router.get("/captains")
def captains() -> list[dict[str, Any]]:
    dataframe, _ = _load_players()
    if dataframe.empty:
        return []

    ranked = dataframe.sort_values("captain_score", ascending=False).head(10).copy()
    ranked["reasoning"] = [
        _captain_reasoning(row, index + 1) for index, (_, row) in enumerate(ranked.iterrows())
    ]
    output = _plain_player_columns(ranked)
    output["reasoning"] = ranked["reasoning"].values
    return data_service.to_records(output)


@router.get("/transfers")
def transfers() -> list[dict[str, Any]]:
    dataframe, _ = _load_players()
    if dataframe.empty:
        return []

    dataframe["rotation_risk"] = dataframe["minutes_security"] < 0.4
    output = dataframe.sort_values("transfer_score", ascending=False).head(20)
    output = _plain_player_columns(output)
    output["rotation_risk"] = dataframe.loc[output.index, "rotation_risk"].astype(bool)
    return data_service.to_records(output)


@router.get("/differentials")
def differentials() -> list[dict[str, Any]]:
    dataframe, _ = _load_players()
    if dataframe.empty:
        return []

    output = dataframe[dataframe["selected_by_percent"] < 15]
    output = _plain_player_columns(output.sort_values("captain_score", ascending=False).head(10))
    return data_service.to_records(output)


@router.get("/compare")
async def compare_players(
    ids: str = Query(..., description="Comma-separated FPL element IDs"),
) -> dict[str, Any]:
    requested_ids = _parse_comparison_ids(ids)
    dataframe, _ = _load_players()
    if dataframe.empty:
        return {"players": [], "season_state": "season_ended_no_next_data"}

    numeric_ids = pd.to_numeric(dataframe["element_id"], errors="coerce")
    selected = dataframe[numeric_ids.isin(requested_ids)].copy()
    found_ids = {int(value) for value in selected["element_id"].dropna()}
    missing_ids = [element_id for element_id in requested_ids if element_id not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "One or more player IDs were not found.",
                "missing_ids": missing_ids,
            },
        )

    bootstrap = await fpl_client.get_bootstrap()
    fixture_state = await fixture_source_state()
    season_state = _detect_season_state(bootstrap, fixture_state)
    live_metrics_available = season_state in {"in_season", "pre_season"}
    live_projection_by_id: dict[int, dict[str, float]] = {}
    if live_metrics_available:
        projected, metadata = await live_projection_rows(
            model_name=get_production_portfolio().projections.captain_model,
            horizon=3,
        )
        gameweek = int(metadata["start_gameweek"])
        for player in projected:
            player_id = int(player["element_id"])
            gameweek_row = next(
                (
                    row
                    for row in player.get("projections", [])
                    if int(row.get("gameweek", -1)) == gameweek
                ),
                {},
            )
            live_projection_by_id[player_id] = {
                "raw_xp": round(
                    sum(
                        float(fixture.get("predicted_points", 0.0))
                        for fixture in gameweek_row.get("fixtures", [])
                    ),
                    3,
                ),
                "expected_points": round(
                    float(gameweek_row.get("projected_points", 0.0)), 3
                ),
            }

    try:
        ticker_rows = await ticker(range=5)
    except HTTPException:
        ticker_rows = []
    fixture_by_team = {
        str(row.get("team_short")): row
        for row in ticker_rows
        if row.get("team_short")
    }
    fixture_by_name = {
        str(row.get("team")): row
        for row in ticker_rows
        if row.get("team")
    }
    team_short_by_code = {
        int(team["code"]): team.get("short_name")
        for team in bootstrap.get("teams", [])
        if team.get("code") is not None and team.get("short_name")
    }
    if not team_short_by_code:
        static_teams = data_service.bootstrap_static().get("teams", [])
        team_short_by_code = {
            int(team["code"]): team.get("short_name")
            for team in static_teams
            if team.get("code") is not None and team.get("short_name")
        }

    output = _plain_player_columns(selected)
    comparison_players = []
    for _, row in output.iterrows():
        team_name = str(row.get("team"))
        team_code = _comparison_int(row.get("team_code"))
        team_short = team_short_by_code.get(team_code) if team_code is not None else None
        fixture_row = (
            fixture_by_team.get(team_short)
            or fixture_by_name.get(team_name)
        )
        next_fixtures = (fixture_row or {}).get("fixtures", [])[:5]
        difficulty_values = [
            float(fixture.get("difficulty"))
            for fixture in next_fixtures
            if fixture.get("difficulty") is not None
        ]
        average_difficulty = (
            round(sum(difficulty_values) / len(difficulty_values), 2)
            if difficulty_values
            else None
        )

        comparison_players.append(
            {
                "element_id": int(row["element_id"]),
                "name": row.get("name"),
                "web_name": row.get("web_name"),
                "team": row.get("team"),
                "position": row.get("position"),
                "price": _comparison_number(row.get("price")),
                "points_per_game": _comparison_number(row.get("ppg")),
                "form": _comparison_number(row.get("form")) if live_metrics_available else None,
                "raw_xp": live_projection_by_id.get(int(row["element_id"]), {}).get(
                    "raw_xp"
                ),
                "expected_points": live_projection_by_id.get(
                    int(row["element_id"]), {}
                ).get("expected_points"),
                "captain_rank_score": (
                    _comparison_number(row.get("captain_rank_score"))
                    if live_metrics_available
                    else None
                ),
                "transfer_rank_score": (
                    _comparison_number(row.get("transfer_rank_score"))
                    if live_metrics_available
                    else None
                ),
                "minutes_security": (
                    _comparison_number(row.get("start_likelihood"))
                    if live_metrics_available
                    else None
                ),
                "defensive_contribution_per_90": _comparison_number(
                    row.get("defensive_contribution_per_90")
                ),
                "selected_by_percent": _comparison_number(row.get("selected_by_percent")),
                "team_code": _comparison_int(row.get("team_code")),
                "fixtures": next_fixtures,
                "average_fixture_difficulty": average_difficulty,
                "live_metrics_available": live_metrics_available,
                "live_metrics_unavailable_reason": (
                    None
                    if live_metrics_available
                    else "Unavailable until the new FPL season starts."
                ),
            }
        )

    players_by_id = {player["element_id"]: player for player in comparison_players}
    return {
        "players": [players_by_id[element_id] for element_id in requested_ids],
        "season_state": season_state,
        "fpl_api_season": _season_label_from_fixture_state(bootstrap),
        "fixture_source": fixture_state.get("source", "Fixture data unavailable"),
        "fixture_season": fixture_state.get("season", "unknown"),
        "difficulty_source": fixture_state.get("difficulty_source", "unknown"),
    }


@router.get("/{name}/history")
def player_history(name: str) -> list[dict[str, Any]]:
    history = data_service.serving_player_gw()
    if history.empty:
        return []

    needle = _normalize(name)
    player_keys = history["player_name"].map(_normalize)
    filtered = history[player_keys == needle].copy()
    if filtered.empty:
        filtered = history[player_keys.str.contains(needle, regex=False, na=False)].copy()
    if filtered.empty:
        return []

    # The serving dataset contains prior seasons for training as well as the live
    # season. A player drawer must never leak last season's closing gameweeks into
    # the current-season chart.
    seasons = filtered["season"].dropna().astype(str)
    if seasons.empty:
        return []
    current_season = max(seasons.unique())
    filtered = filtered[filtered["season"].astype(str) == current_season].copy()

    price = pd.to_numeric(filtered.get("price"), errors="coerce")
    if "price_before_deadline" in filtered.columns:
        price = price.fillna(pd.to_numeric(filtered["price_before_deadline"], errors="coerce"))
    filtered["price"] = price

    filtered = filtered.sort_values("gameweek").tail(10)
    output = filtered.rename(columns={"gameweek": "gw"})
    output = output.rename(columns={"player_id": "element_id"})
    columns = ["element_id", "gw", "price", "total_points", "minutes", "selected_by_percent"]
    for column in columns:
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0)
    return data_service.to_records(output[columns])


def _parse_comparison_ids(value: str) -> list[int]:
    try:
        parsed = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ids must be comma-separated integers") from exc

    if not parsed or len(parsed) > 3 or len(set(parsed)) != len(parsed):
        raise HTTPException(status_code=400, detail="Compare between 1 and 3 unique player IDs")
    return parsed


def _comparison_number(value: Any) -> float | None:
    if value in (None, "") or pd.isna(value):
        return None
    return round(float(value), 2)


def _comparison_int(value: Any) -> int | None:
    if value in (None, "") or pd.isna(value):
        return None
    return int(value)


def _season_label_from_fixture_state(bootstrap: dict[str, Any]) -> str:
    deadlines = [
        event.get("deadline_time")
        for event in bootstrap.get("events", [])
        if event.get("deadline_time")
    ]
    if not deadlines:
        return "unknown"
    year = int(str(min(deadlines))[:4])
    return f"{year}-{str(year + 1)[-2:]}"
