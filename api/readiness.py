"""FastAPI dependencies for current-season artifact readiness."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import HTTPException, Response

from api import fpl_client
from fpl_intelligence.artifact_contract import (
    CURRENT_ARTIFACT_MANIFEST_PATH,
    ArtifactReadiness,
    validate_current_artifacts,
)
from fpl_intelligence.season_rules import infer_season_from_bootstrap


@lru_cache(maxsize=8)
def _cached_readiness(
    expected_season: str,
    check_models: bool,
    manifest_mtime_ns: int,
) -> ArtifactReadiness:
    del manifest_mtime_ns
    return validate_current_artifacts(
        expected_season=expected_season,
        check_models=check_models,
    )


def artifact_readiness(
    expected_season: str,
    *,
    check_models: bool,
) -> ArtifactReadiness:
    mtime = (
        CURRENT_ARTIFACT_MANIFEST_PATH.stat().st_mtime_ns
        if CURRENT_ARTIFACT_MANIFEST_PATH.exists()
        else 0
    )
    return _cached_readiness(expected_season, check_models, mtime)


def expected_live_season(now: datetime | None = None) -> str:
    override = os.getenv("FPL_ACTIVE_SEASON")
    if override:
        return override
    clock = now or datetime.now(UTC)
    start_year = clock.year if clock.month >= 6 else clock.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def require_current_artifacts(response: Response) -> ArtifactReadiness:
    season = expected_live_season()
    readiness = artifact_readiness(season, check_models=True)
    if not readiness.ready:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    f"{season} recommendations are blocked until current-season "
                    "artifacts pass readiness."
                ),
                "season": season,
                "errors": readiness.errors,
            },
        )
    manifest = readiness.manifest or {}
    response.headers["X-FPL-Season"] = season
    response.headers["X-FPL-Bootstrap-Hash"] = str(manifest.get("bootstrap_hash", ""))
    response.headers["X-FPL-Rules-Version"] = str(manifest.get("rules_version", ""))
    response.headers["X-FPL-Data-Cutoff"] = str(manifest.get("data_cutoff", ""))
    return readiness


async def require_live_artifacts(response: Response) -> ArtifactReadiness:
    bootstrap = await fpl_client.get_bootstrap()
    season = infer_season_from_bootstrap(bootstrap)
    readiness = artifact_readiness(season, check_models=True)
    if not readiness.ready:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    f"{season} recommendations are blocked until current-season "
                    "artifacts pass readiness."
                ),
                "season": season,
                "errors": readiness.errors,
            },
        )
    manifest = readiness.manifest or {}
    response.headers["X-FPL-Season"] = season
    response.headers["X-FPL-Bootstrap-Hash"] = str(manifest.get("bootstrap_hash", ""))
    response.headers["X-FPL-Rules-Version"] = str(manifest.get("rules_version", ""))
    response.headers["X-FPL-Data-Cutoff"] = str(manifest.get("data_cutoff", ""))
    return readiness
