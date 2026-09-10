"""FastAPI dependencies for current-season decision readiness.

Stored artifacts are necessary but not sufficient for a live recommendation.
Every decision-serving request also reconciles those artifacts with the latest
official bootstrap and fixture payloads and fails closed on drift or staleness.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Response

from api import fpl_client
from fpl_intelligence.artifact_contract import (
    CURRENT_ARTIFACT_MANIFEST_PATH,
    ArtifactReadiness,
    validate_current_artifacts,
)
from fpl_intelligence.season_rules import (
    build_season_rules,
    decision_bootstrap_hash,
    infer_season_from_bootstrap,
    payload_hash,
    rules_contract_hash,
)

DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24.0

@dataclass(frozen=True)
class LiveDecisionReadiness:
    """Authoritative state for serving current FPL decisions."""

    status: str
    season: str
    blockers: list[dict[str, str]]
    warnings: list[str]
    manifest: dict[str, Any] | None
    live_data: dict[str, Any]
    artifact_data: dict[str, Any]
    models_checked: bool

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "season": self.season,
            "blockers": self.blockers,
            "errors": [blocker["message"] for blocker in self.blockers],
            "warnings": self.warnings,
            "manifest": self.manifest,
            "live_data": self.live_data,
            "artifact_data": self.artifact_data,
            "models_checked": self.models_checked,
        }


@lru_cache(maxsize=8)
def _cached_readiness(
    expected_season: str,
    check_models: bool,
    artifact_fingerprint: tuple[tuple[str, int, int], ...],
) -> ArtifactReadiness:
    del artifact_fingerprint
    return validate_current_artifacts(
        expected_season=expected_season,
        check_models=check_models,
    )


def artifact_readiness(
    expected_season: str,
    *,
    check_models: bool,
) -> ArtifactReadiness:
    return _cached_readiness(
        expected_season,
        check_models,
        _artifact_fingerprint(CURRENT_ARTIFACT_MANIFEST_PATH),
    )


def _artifact_fingerprint(
    manifest_path: Path,
) -> tuple[tuple[str, int, int], ...]:
    """Track every serving file so readiness cannot outlive an artifact change."""

    paths: set[Path] = {manifest_path}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        manifest = {}
    for field, value in manifest.items():
        if field.endswith("_path") and value:
            paths.add(Path(str(value)))
    model_metadata_path = Path(str(manifest.get("model_metadata_path") or ""))
    if model_metadata_path.is_file():
        try:
            model_metadata: dict[str, Any] = json.loads(
                model_metadata_path.read_text(encoding="utf-8")
            )
            for artifact in model_metadata.get("artifacts", {}).values():
                artifact_name = str(artifact.get("path") or "").strip()
                if artifact_name:
                    paths.add(model_metadata_path.parent / artifact_name)
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    fingerprint = []
    for path in sorted(paths, key=lambda value: str(value).casefold()):
        try:
            stat = path.stat()
            fingerprint.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            fingerprint.append((str(path), -1, -1))
    return tuple(fingerprint)


def expected_live_season(now: datetime | None = None) -> str:
    override = os.getenv("FPL_ACTIVE_SEASON")
    if override:
        return override
    clock = now or datetime.now(UTC)
    start_year = clock.year if clock.month >= 6 else clock.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def max_artifact_age_hours() -> float:
    raw = os.getenv("FPL_MAX_ARTIFACT_AGE_HOURS", str(DEFAULT_MAX_ARTIFACT_AGE_HOURS))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_MAX_ARTIFACT_AGE_HOURS


def evaluate_live_decision_readiness(
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    *,
    check_models: bool,
    now: datetime | None = None,
) -> LiveDecisionReadiness:
    """Reconcile stored artifacts with the official payloads used right now."""

    clock = now or datetime.now(UTC)
    checked_at = clock.isoformat().replace("+00:00", "Z")
    season = infer_season_from_bootstrap(bootstrap)
    stored = artifact_readiness(season, check_models=check_models)
    manifest = stored.manifest or {}
    warnings = list(stored.warnings)
    blockers = [
        {"code": "artifact_contract_error", "message": message}
        for message in stored.errors
    ]

    live_bootstrap_hash = payload_hash(bootstrap)
    live_bootstrap_contract_hash = decision_bootstrap_hash(bootstrap)
    live_fixtures_hash = payload_hash(fixtures)
    live_rules_contract_hash = rules_contract_hash(
        build_season_rules(
            bootstrap,
            season=season,
            source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
            retrieved_at=checked_at,
            cutoff_at=checked_at,
        )
    )
    live_player_ids = _player_ids(bootstrap)
    artifact_player_ids = _artifact_player_ids(manifest)
    artifact_fixtures_hash = _artifact_json_payload_hash(
        manifest.get("fixtures_path")
    )
    artifact_age_hours = _artifact_age_hours(manifest, clock)
    official_finalized_gameweeks = _official_finalized_gameweeks(bootstrap)
    artifact_finalized_gameweeks = _artifact_finalized_gameweeks(manifest)
    missing_finalized_gameweeks = sorted(
        set(official_finalized_gameweeks).difference(artifact_finalized_gameweeks)
    )

    if season == "unknown":
        blockers.append(
            {
                "code": "live_season_unknown",
                "message": "The official FPL payload does not identify an active season.",
            }
        )
    if missing_finalized_gameweeks:
        latest_official = max(official_finalized_gameweeks)
        latest_artifact = (
            max(artifact_finalized_gameweeks)
            if artifact_finalized_gameweeks
            else "none"
        )
        blockers.append(
            {
                "code": "finalized_gameweek_missing",
                "message": (
                    f"Official GW{latest_official} is finalized, but the current model "
                    f"bundle covers finalized gameweeks only through {latest_artifact}. "
                    "Run the manual season refresh before serving recommendations."
                ),
            }
        )
    if (
        manifest.get("rules_contract_hash")
        and live_rules_contract_hash != manifest.get("rules_contract_hash")
    ):
        blockers.append(
            {
                "code": "rules_contract_drift",
                "message": (
                    "Official scoring, squad, transfer, chip, DC, or BPS rules changed. "
                    "The rules contract must be reviewed before recommendations resume."
                ),
            }
        )
    artifact_bootstrap = _artifact_json_payload(manifest.get("bootstrap_path"))
    artifact_bootstrap_contract_hash = (
        decision_bootstrap_hash(artifact_bootstrap) if artifact_bootstrap else None
    )
    if (
        manifest
        and artifact_bootstrap_contract_hash
        and live_bootstrap_contract_hash != artifact_bootstrap_contract_hash
    ):
        warnings.append(
            "Latest official player prices, availability and role data are being "
            "applied directly to this request."
        )
    elif manifest and live_bootstrap_hash != manifest.get("bootstrap_hash"):
        warnings.append(
            "Official ownership or manager-count values moved after the last refresh; "
            "the decision-relevant bootstrap contract is unchanged."
        )
    if manifest and artifact_fixtures_hash != live_fixtures_hash:
        warnings.append(
            "Latest official fixtures are being applied directly to this request."
        )
    if manifest and len(live_player_ids) != int(manifest.get("player_count", -1)):
        warnings.append(
            f"Official FPL now has {len(live_player_ids)} players; new player records "
            "are being onboarded directly from the live player pool."
        )
    if artifact_player_ids is not None and live_player_ids != artifact_player_ids:
        added = len(live_player_ids.difference(artifact_player_ids))
        removed = len(artifact_player_ids.difference(live_player_ids))
        warnings.append(
            "The official player pool changed "
            f"({added} new, {removed} removed); stable live IDs and conservative "
            "new-player priors are being used for this request."
        )
    live_team_count = len(
        {team.get("id") for team in bootstrap.get("teams", []) if team.get("id") is not None}
    )
    if manifest and live_team_count != int(manifest.get("team_count", -1)):
        blockers.append(
            {
                "code": "team_count_drift",
                "message": (
                    f"Official FPL has {live_team_count} teams but the processed artifacts "
                    f"contain {manifest.get('team_count', 'an unknown number')}."
                ),
            }
        )
    if artifact_age_hours is None:
        blockers.append(
            {
                "code": "invalid_data_cutoff",
                "message": "The artifact data cutoff is missing or invalid.",
            }
        )
    elif artifact_age_hours > max_artifact_age_hours():
        warnings.append(
            f"The validated model snapshot is {artifact_age_hours:.1f} hours old. "
            "Official prices, availability, roles and fixtures are still applied live."
        )

    blockers = _deduplicate_blockers(blockers)
    return LiveDecisionReadiness(
        status="ready" if not blockers else "blocked",
        season=season,
        blockers=blockers,
        warnings=warnings,
        manifest=stored.manifest,
        live_data={
            "checked_at": checked_at,
            "bootstrap_hash": live_bootstrap_hash,
            "bootstrap_contract_hash": live_bootstrap_contract_hash,
            "fixtures_hash": live_fixtures_hash,
            "rules_contract_hash": live_rules_contract_hash,
            "live_inputs_applied": True,
            "player_count": len(live_player_ids),
            "team_count": live_team_count,
            "finalized_gameweeks": official_finalized_gameweeks,
            "latest_finalized_gameweek": (
                max(official_finalized_gameweeks)
                if official_finalized_gameweeks
                else None
            ),
        },
        artifact_data={
            "data_cutoff": manifest.get("data_cutoff"),
            "age_hours": artifact_age_hours,
            "bootstrap_hash": manifest.get("bootstrap_hash"),
            "bootstrap_contract_hash": artifact_bootstrap_contract_hash,
            "fixtures_hash": artifact_fixtures_hash,
            "player_count": manifest.get("player_count"),
            "team_count": manifest.get("team_count"),
            "rules_version": manifest.get("rules_version"),
            "finalized_gameweeks": artifact_finalized_gameweeks,
            "latest_finalized_gameweek": (
                max(artifact_finalized_gameweeks)
                if artifact_finalized_gameweeks
                else None
            ),
        },
        models_checked=check_models,
    )


async def live_decision_context(
    *,
    check_models: bool,
) -> tuple[LiveDecisionReadiness, dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Fetch both official sources and always return a displayable state."""

    bootstrap_result, fixtures_result = await asyncio.gather(
        fpl_client.get_bootstrap(),
        fpl_client.get_fixtures(),
        return_exceptions=True,
    )
    source_blockers: list[dict[str, str]] = []
    if isinstance(bootstrap_result, Exception):
        source_blockers.append(
            {
                "code": "bootstrap_unavailable",
                "message": "Official FPL player and rules data is temporarily unavailable.",
            }
        )
    if isinstance(fixtures_result, Exception):
        source_blockers.append(
            {
                "code": "fixtures_unavailable",
                "message": "Official FPL fixture data is temporarily unavailable.",
            }
        )
    if source_blockers:
        season = expected_live_season()
        stored = artifact_readiness(season, check_models=check_models)
        manifest = stored.manifest or {}
        return (
            LiveDecisionReadiness(
                status="unavailable",
                season=season,
                blockers=source_blockers,
                warnings=stored.warnings,
                manifest=stored.manifest,
                live_data={
                    "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "bootstrap_hash": None,
                    "fixtures_hash": None,
                    "player_count": None,
                    "team_count": None,
                },
                artifact_data={
                    "data_cutoff": manifest.get("data_cutoff"),
                    "age_hours": _artifact_age_hours(manifest, datetime.now(UTC)),
                    "bootstrap_hash": manifest.get("bootstrap_hash"),
                    "fixtures_hash": _artifact_json_payload_hash(
                        manifest.get("fixtures_path")
                    ),
                    "player_count": manifest.get("player_count"),
                    "team_count": manifest.get("team_count"),
                    "rules_version": manifest.get("rules_version"),
                },
                models_checked=check_models,
            ),
            None if isinstance(bootstrap_result, Exception) else bootstrap_result,
            None if isinstance(fixtures_result, Exception) else fixtures_result,
        )
    bootstrap = bootstrap_result
    fixtures = fixtures_result
    assert isinstance(bootstrap, dict)
    assert isinstance(fixtures, list)
    return (
        evaluate_live_decision_readiness(
            bootstrap,
            fixtures,
            check_models=check_models,
        ),
        bootstrap,
        fixtures,
    )


def _player_ids(bootstrap: dict[str, Any]) -> set[int]:
    return {
        int(player["id"])
        for player in bootstrap.get("elements", [])
        if player.get("id") is not None
    }


def _artifact_player_ids(manifest: dict[str, Any]) -> set[int] | None:
    raw_path = str(manifest.get("players_current_path") or "").strip()
    if not raw_path:
        return None
    try:
        import pandas as pd

        rows = pd.read_csv(Path(raw_path), usecols=["element_id"])
        return set(pd.to_numeric(rows["element_id"], errors="coerce").dropna().astype(int))
    except (OSError, ValueError, KeyError):
        return None


def _artifact_json_payload_hash(raw_path: Any) -> str | None:
    payload = _artifact_json_payload(raw_path)
    return payload_hash(payload) if payload is not None else None


def _official_finalized_gameweeks(bootstrap: dict[str, Any]) -> list[int]:
    return sorted(
        int(event["id"])
        for event in bootstrap.get("events", [])
        if event.get("id") is not None
        and bool(event.get("finished"))
        and bool(event.get("data_checked"))
    )


def _artifact_finalized_gameweeks(manifest: dict[str, Any]) -> list[int]:
    metadata = _artifact_json_payload(manifest.get("model_metadata_path"))
    if not isinstance(metadata, dict):
        return []
    values = metadata.get("finalized_current_season_gameweeks", [])
    if not isinstance(values, list):
        return []
    result: set[int] = set()
    for value in values:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(result)


def _artifact_json_payload(raw_path: Any) -> Any | None:
    path = Path(str(raw_path or ""))
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _artifact_age_hours(
    manifest: dict[str, Any],
    now: datetime,
) -> float | None:
    raw_cutoff = str(manifest.get("data_cutoff") or "").strip()
    if not raw_cutoff:
        return None
    try:
        cutoff = datetime.fromisoformat(raw_cutoff.replace("Z", "+00:00"))
    except ValueError:
        return None
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return max(0.0, (now - cutoff.astimezone(UTC)).total_seconds() / 3600)


def _deduplicate_blockers(
    blockers: list[dict[str, str]],
) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for blocker in blockers:
        key = (blocker["code"], blocker["message"])
        if key not in seen:
            seen.add(key)
            result.append(blocker)
    return result


async def require_current_artifacts(response: Response) -> LiveDecisionReadiness:
    readiness, _, _ = await live_decision_context(check_models=True)
    if not readiness.ready:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "recommendations_blocked",
                "message": f"{readiness.season} recommendations are not decision-ready.",
                "decision_status": readiness.status,
                "season": readiness.season,
                "blockers": readiness.blockers,
            },
        )
    manifest = readiness.manifest or {}
    response.headers["X-FPL-Season"] = readiness.season
    response.headers["X-FPL-Bootstrap-Hash"] = str(
        readiness.live_data.get("bootstrap_hash", "")
    )
    response.headers["X-FPL-Fixtures-Hash"] = str(
        readiness.live_data.get("fixtures_hash", "")
    )
    response.headers["X-FPL-Live-Checked-At"] = str(
        readiness.live_data.get("checked_at", "")
    )
    response.headers["X-FPL-Artifact-Bootstrap-Hash"] = str(
        manifest.get("bootstrap_hash", "")
    )
    response.headers["X-FPL-Rules-Version"] = str(manifest.get("rules_version", ""))
    response.headers["X-FPL-Data-Cutoff"] = str(manifest.get("data_cutoff", ""))
    return readiness


async def require_live_artifacts(response: Response) -> LiveDecisionReadiness:
    """Backward-compatible dependency name for live squad/chip routes."""

    return await require_current_artifacts(response)
