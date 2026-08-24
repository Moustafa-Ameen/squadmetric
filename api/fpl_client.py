from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from fastapi import HTTPException

BASE_URL = "https://fantasy.premierleague.com/api/"
TIMEOUT_SECONDS = 10.0
UNAVAILABLE_MESSAGE = "FPL data is temporarily unavailable. Try again shortly."
BOOTSTRAP_CACHE_SECONDS = 300.0
FIXTURES_CACHE_SECONDS = 60.0
ARTIFACT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "processed"
    / "current_artifact_manifest.json"
)
_BOOTSTRAP_CACHE: tuple[float, int | None, dict[str, Any]] | None = None
_FIXTURES_CACHE: tuple[float, int | None, list[dict[str, Any]]] | None = None


def _artifact_manifest_mtime_ns() -> int | None:
    """Return the serving-manifest version used to invalidate live API caches."""

    try:
        return ARTIFACT_MANIFEST_PATH.stat().st_mtime_ns
    except OSError:
        return None


async def _get(path: str) -> Any:
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(path)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "fpl_resource_not_found",
                    "message": "The requested FPL team or gameweek data was not found.",
                },
            ) from exc
        raise HTTPException(
            status_code=503,
            detail={"code": "fpl_api_unavailable", "message": UNAVAILABLE_MESSAGE},
        ) from exc
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "fpl_api_unavailable", "message": UNAVAILABLE_MESSAGE},
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "fpl_api_unavailable", "message": UNAVAILABLE_MESSAGE},
        ) from exc


async def get_bootstrap() -> dict[str, Any]:
    global _BOOTSTRAP_CACHE
    manifest_mtime = _artifact_manifest_mtime_ns()
    if (
        _BOOTSTRAP_CACHE is not None
        and monotonic() - _BOOTSTRAP_CACHE[0] < BOOTSTRAP_CACHE_SECONDS
        and _BOOTSTRAP_CACHE[1] == manifest_mtime
    ):
        return _BOOTSTRAP_CACHE[2]
    payload = await _get("bootstrap-static/")
    _BOOTSTRAP_CACHE = (monotonic(), manifest_mtime, payload)
    return payload


def clear_bootstrap_cache() -> None:
    global _BOOTSTRAP_CACHE
    _BOOTSTRAP_CACHE = None


async def get_fixtures() -> list[dict[str, Any]]:
    global _FIXTURES_CACHE
    manifest_mtime = _artifact_manifest_mtime_ns()
    if (
        _FIXTURES_CACHE is not None
        and monotonic() - _FIXTURES_CACHE[0] < FIXTURES_CACHE_SECONDS
        and _FIXTURES_CACHE[1] == manifest_mtime
    ):
        return _FIXTURES_CACHE[2]
    payload = await _get("fixtures/")
    _FIXTURES_CACHE = (monotonic(), manifest_mtime, payload)
    return payload


def clear_fixtures_cache() -> None:
    global _FIXTURES_CACHE
    _FIXTURES_CACHE = None


async def get_team(team_id: int) -> dict[str, Any]:
    return await _get(f"entry/{team_id}/")


async def get_team_picks(team_id: int, gw: int) -> dict[str, Any]:
    return await _get(f"entry/{team_id}/event/{gw}/picks/")


async def get_team_history(team_id: int) -> dict[str, Any]:
    return await _get(f"entry/{team_id}/history/")


async def get_team_transfers(team_id: int) -> list[dict[str, Any]]:
    return await _get(f"entry/{team_id}/transfers/")


async def get_live_gw(gw: int) -> dict[str, Any]:
    return await _get(f"event/{gw}/live/")
