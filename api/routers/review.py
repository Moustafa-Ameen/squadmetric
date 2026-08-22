from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api import fpl_client
from fpl_intelligence.post_gameweek_review import build_post_gameweek_review
from fpl_intelligence.season_rules import infer_season_from_bootstrap

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/post-gameweek")
async def post_gameweek_review(team_id: int = Query(..., ge=1)) -> dict[str, Any]:
    bootstrap = await fpl_client.get_bootstrap()
    try:
        history = await fpl_client.get_team_history(team_id)
    except HTTPException as exc:
        # Before GW1, FPL does not publish entry history even for a valid team.
        # Treat that specific pre-season 404 as an empty review, but keep
        # failing closed once any Gameweek has begun.
        season_started = any(
            event.get("finished") or event.get("is_current")
            for event in bootstrap.get("events", [])
        )
        if exc.status_code != 404 or season_started:
            raise
        history = {"current": []}
    return {
        "team_id": team_id,
        **build_post_gameweek_review(
            season=infer_season_from_bootstrap(bootstrap),
            bootstrap=bootstrap,
            team_history=history,
        ),
    }
