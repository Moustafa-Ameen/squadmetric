"""Current-season player rows and live fixture projections."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from api import data_service, fpl_client
from fpl_intelligence.artifact_contract import load_current_artifact_manifest
from fpl_intelligence.multi_gw_projection import load_planner_models, project_players
from fpl_intelligence.season_rules import (
    decision_bootstrap_hash,
    infer_season_from_bootstrap,
    payload_hash,
)

PROJECTION_CACHE_SECONDS = 300.0
PROJECTION_CACHE_MAX_ENTRIES = 12
_PROJECTION_CACHE: dict[
    tuple[str, int, int, str, str],
    tuple[float, list[dict[str, Any]], dict[str, Any]],
] = {}


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
                "player_code": player.get("code"),
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
                "chance_of_playing_next_round": player.get(
                    "chance_of_playing_next_round"
                ),
                "news": player.get("news"),
                "start_likelihood": _number(rank.get("minutes_security")),
                "availability_probability": _number(
                    rank.get("availability_probability")
                ),
                "prior_source": rank.get("prior_source"),
                "launch_evidence_confidence": _number(
                    rank.get("launch_evidence_confidence")
                ),
                "launch_evidence_type": rank.get("launch_evidence_type"),
                "launch_evidence_source": rank.get("launch_evidence_source"),
                "season": rank.get("season"),
                "previous_minutes": player.get("minutes"),
                "previous_starts": player.get("starts"),
                "previous_bonus": player.get("bonus"),
                "previous_bps": player.get("bps"),
                "previous_cbi": player.get("clearances_blocks_interceptions"),
                "previous_tackles": player.get("tackles"),
                "previous_recoveries": player.get("recoveries"),
                "penalties_order": player.get("penalties_order"),
                "penalties_text": player.get("penalties_text"),
                "direct_freekicks_order": player.get("direct_freekicks_order"),
                "direct_freekicks_text": player.get("direct_freekicks_text"),
                "corners_and_indirect_freekicks_order": player.get(
                    "corners_and_indirect_freekicks_order"
                ),
                "corners_and_indirect_freekicks_text": player.get(
                    "corners_and_indirect_freekicks_text"
                ),
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
    bootstrap_hash = payload_hash(bootstrap)
    fixtures_hash = payload_hash(fixtures)
    cache_key = (
        model_name,
        int(start_gameweek),
        int(horizon),
        bootstrap_hash,
        fixtures_hash,
    )
    cached = _PROJECTION_CACHE.get(cache_key)
    if cached is not None and monotonic() - cached[0] < PROJECTION_CACHE_SECONDS:
        return deepcopy(cached[1]), deepcopy(cached[2])

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
    checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    deadline_event = next(
        (
            event
            for event in bootstrap.get("events", [])
            if int(event.get("id") or 0) == int(start_gameweek)
        ),
        {},
    )
    metadata = {
        "season": infer_season_from_bootstrap(bootstrap),
        "bootstrap_hash": bootstrap_hash,
        "bootstrap_contract_hash": decision_bootstrap_hash(bootstrap),
        "rules_version": manifest.get("rules_version"),
        "rules_payload_hash": manifest.get("rules_payload_hash"),
        "data_cutoff": checked_at,
        "fixtures_hash": fixtures_hash,
        "live_data_checked_at": checked_at,
        "artifact_bootstrap_hash": manifest.get("bootstrap_hash"),
        "artifact_fixtures_hash": manifest.get("fixtures_hash"),
        "artifact_data_cutoff": manifest.get("data_cutoff"),
        "deadline": deadline_event.get("deadline_time"),
        "model": model_name,
        "start_gameweek": start_gameweek,
    }
    now = monotonic()
    expired = [
        key
        for key, (created_at, _, _) in _PROJECTION_CACHE.items()
        if now - created_at >= PROJECTION_CACHE_SECONDS
    ]
    for key in expired:
        _PROJECTION_CACHE.pop(key, None)
    if len(_PROJECTION_CACHE) >= PROJECTION_CACHE_MAX_ENTRIES:
        oldest_key = min(
            _PROJECTION_CACHE,
            key=lambda key: _PROJECTION_CACHE[key][0],
        )
        _PROJECTION_CACHE.pop(oldest_key, None)
    _PROJECTION_CACHE[cache_key] = (
        now,
        deepcopy(projected),
        deepcopy(metadata),
    )
    return projected, metadata


def clear_projection_cache() -> None:
    _PROJECTION_CACHE.clear()


def _money(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 10, 1)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
