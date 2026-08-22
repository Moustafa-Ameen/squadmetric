import asyncio

from api.routers import review
from fastapi import HTTPException


def test_post_gameweek_review_endpoint_keeps_team_scope(monkeypatch, tmp_path):
    async def bootstrap():
        return {
            "events": [{"id": 1, "finished": True, "data_checked": True}],
            "total_players": 100,
        }

    async def history(team_id):
        assert team_id == 42
        return {"current": [{"event": 1, "points": 50, "overall_rank": 10}]}

    monkeypatch.setattr(review.fpl_client, "get_bootstrap", bootstrap)
    monkeypatch.setattr(review.fpl_client, "get_team_history", history)
    monkeypatch.setattr(review, "infer_season_from_bootstrap", lambda payload: "2026-27")

    payload = asyncio.run(review.post_gameweek_review(team_id=42))

    assert payload["team_id"] == 42
    assert payload["reviewed_gameweeks"] == 1
    assert payload["gameweeks"][0]["rank_percentile"] == 10


def test_post_gameweek_review_treats_preseason_history_404_as_empty(monkeypatch):
    async def bootstrap():
        return {
            "events": [{"id": 1, "finished": False, "is_current": False}],
            "total_players": 100,
        }

    async def history(team_id):
        assert team_id == 42
        raise HTTPException(status_code=404, detail="not published")

    monkeypatch.setattr(review.fpl_client, "get_bootstrap", bootstrap)
    monkeypatch.setattr(review.fpl_client, "get_team_history", history)
    monkeypatch.setattr(review, "infer_season_from_bootstrap", lambda payload: "2026-27")

    payload = asyncio.run(review.post_gameweek_review(team_id=42))

    assert payload["reviewed_gameweeks"] == 0
    assert payload["gameweeks"] == []
