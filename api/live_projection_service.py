"""Current-season player rows and live fixture projections."""

from __future__ import annotations

import asyncio
from typing import Any

from api import data_service, fpl_client
from fpl_intelligence.artifact_contract import load_current_artifact_manifest
from fpl_intelligence.multi_gw_projection import load_planner_models, project_players
from fpl_intelligence.season_rules import infer_season_from_bootstrap


def current_player_rows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = data_service.players()
    ranked_by_id = {
        int(row["element_id"]): row
        for row in ranked.to_dict(orient="records")
        if row.get("element_id") is not None
    }
    teams = {team.get("id"): team for team in bootstrap.get("teams", [])}
    positions = {
        position.get("id"): position
        for position in bootstrap.get("element_types", [])
    }
    rows: list[dict[str, Any]] = []
    for player in bootstrap.get("elements", []):
        element_id = int(player["id"])
        rank = ranked_by_id.get(element_id, {})
        team = teams.get(player.get("team"), {})
        position = positions.get(player.get("element_type"), {})
        name = (
            f"{player.get('first_name', '')} {player.get('second_name', '')}".strip()
            or player.get("web_name")
            or f"Player {element_id}"
        )
        rows.append(
            {
                "element_id": element_id,
                "name": name,
                "web_name": player.get("web_name") or name,
                "team_id": player.get("team"),
                "team": team.get("short_name") or team.get("name"),
                "team_name": team.get("name"),
                "team_code": team.get("code"),
                "position": (
                    position.get("singular_name_short")
                    or position.get("singular_name")
                ),
                "price": _money(player.get("now_cost")) or 0.0,
                "selected_by_percent": _number(player.get("selected_by_percent")),
                "status": player.get("status"),
                "news": player.get("news"),
                "start_likelihood": _number(rank.get("minutes_security")),
                "prior_source": rank.get("prior_source"),
            }
        )
    return rows


async def live_projection_rows(
    *,
    model_name: str,
    start_gameweek: int | None = None,
    horizon: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bootstrap, fixtures = await asyncio.gather(
        fpl_client.get_bootstrap(),
        fpl_client.get_fixtures(),
    )
    if start_gameweek is None:
        start_gameweek = next(
            (
                int(event["id"])
                for event in bootstrap.get("events", [])
                if event.get("is_next") or event.get("is_current")
            ),
            1,
        )
    players = current_player_rows(bootstrap)
    models = load_planner_models(model_name)
    projected = project_players(
        players,
        fixtures,
        bootstrap.get("teams", []),
        start_gameweek,
        horizon,
        models=models,
        history=data_service.historical_player_gw(),
    )
    manifest = load_current_artifact_manifest() or {}
    return projected, {
        "season": infer_season_from_bootstrap(bootstrap),
        "bootstrap_hash": manifest.get("bootstrap_hash"),
        "rules_version": manifest.get("rules_version"),
        "data_cutoff": manifest.get("data_cutoff"),
        "model": model_name,
        "start_gameweek": start_gameweek,
    }


def _money(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 10, 1)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
