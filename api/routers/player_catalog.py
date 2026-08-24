"""Always-available official FPL player directory.

Decision endpoints fail closed when processed artifacts drift. The player
directory still needs to remain useful, so this endpoint exposes only current
official bootstrap facts and explicitly marks model metrics unavailable.
"""

from typing import Any

from fastapi import APIRouter, Query

from api import fpl_client

router = APIRouter(prefix="/api/player-catalog", tags=["players"])


@router.get("")
async def player_catalog(
    limit: int = Query(default=1000, ge=1, le=1000),
) -> list[dict[str, Any]]:
    bootstrap = await fpl_client.get_bootstrap()
    teams = {int(team["id"]): team for team in bootstrap.get("teams", []) if team.get("id")}
    positions = {
        int(position["id"]): position
        for position in bootstrap.get("element_types", [])
        if position.get("id")
    }
    rows = []
    for player in bootstrap.get("elements", [])[:limit]:
        team = teams.get(int(player.get("team") or 0), {})
        position = positions.get(int(player.get("element_type") or 0), {})
        price = _number(player.get("now_cost")) / 10
        ppg = _number(player.get("points_per_game"))
        rows.append(
            {
                "element_id": int(player.get("id") or 0),
                "name": " ".join(
                    part
                    for part in [player.get("first_name"), player.get("second_name")]
                    if part
                ).strip()
                or str(player.get("web_name") or "Unknown player"),
                "web_name": player.get("web_name"),
                "team": team.get("name") or team.get("short_name") or "Unknown",
                "team_code": team.get("code"),
                "position": (
                    position.get("singular_name_short")
                    or position.get("singular_name")
                    or ""
                ),
                "price": price,
                "total_points": int(_number(player.get("total_points"))),
                "ppg": ppg,
                "form": _number(player.get("form")),
                "start_likelihood": _official_availability(player),
                "value": round(ppg / price, 3) if price > 0 else 0.0,
                "captain_rank_score": 0.0,
                "transfer_rank_score": 0.0,
                "selected_by_percent": _number(player.get("selected_by_percent")),
                "metrics_available": False,
                "catalog_source": "official_fpl_bootstrap",
            }
        )
    return rows


def _official_availability(player: dict[str, Any]) -> float:
    chance = player.get("chance_of_playing_next_round")
    if chance is not None:
        return max(0.0, min(1.0, _number(chance) / 100))
    return 1.0 if player.get("status") == "a" else 0.5


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
