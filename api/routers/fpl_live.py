import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api import fpl_client
from api.chip_tracking import build_chip_status
from api.live_projection_service import live_projection_rows
from api.manager_state import current_bank_value, infer_free_transfers
from api.readiness import live_decision_context, require_live_artifacts
from api.routers.fixtures import fixture_source_state
from api.routers.predictions import BEST_MODEL
from fpl_intelligence.price_economics import live_pick_price
from fpl_intelligence.season_rules import build_season_rules, infer_season_from_bootstrap

router = APIRouter(prefix="/api/fpl", tags=["fpl-live"])
_LIVE_ARTIFACTS_DEPENDENCY = Depends(require_live_artifacts)


def _current_gameweek_from_bootstrap(bootstrap: dict[str, Any]) -> int | None:
    events = bootstrap.get("events", [])
    current = next((event for event in events if event.get("is_current")), None)
    if current:
        return current.get("id")

    upcoming = next((event for event in events if event.get("is_next")), None)
    if upcoming:
        return upcoming.get("id")

    finished = [event.get("id") for event in events if event.get("finished") and event.get("id")]
    return max(finished, default=0) or None


def _next_gameweek_from_bootstrap(bootstrap: dict[str, Any]) -> int | None:
    events = bootstrap.get("events", [])
    next_event = next((event for event in events if event.get("is_next")), None)
    if next_event:
        return next_event.get("id")

    current = next((event for event in events if event.get("is_current")), None)
    if current and current.get("id"):
        current_id = int(current["id"])
        return current_id + 1 if current_id < 38 else None

    return None


def _season_label_from_bootstrap(bootstrap: dict[str, Any]) -> str:
    return infer_season_from_bootstrap(bootstrap)


def _detect_season_state(
    bootstrap: dict[str, Any],
    fixture_state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str:
    events = bootstrap.get("events", [])
    clock = now or datetime.now(UTC)
    deadlines = [
        datetime.fromisoformat(str(event["deadline_time"]).replace("Z", "+00:00"))
        for event in events
        if event.get("deadline_time")
    ]
    if deadlines and not any(event.get("finished") for event in events):
        first_deadline = min(deadlines)
        if clock < first_deadline:
            return "pre_season"
    has_current = any(event.get("is_current") and not event.get("finished") for event in events)
    if has_current:
        return "in_season"

    last_event = max(
        (event for event in events if event.get("id")),
        key=lambda event: int(event["id"]),
        default=None,
    )
    if not last_event or not last_event.get("finished"):
        return "in_season"

    has_next_season_data = bool(
        fixture_state.get("next_kickoff")
        or fixture_state.get("season") not in {None, "", "unknown"}
    )
    return "season_ended_preseason" if has_next_season_data else "season_ended_no_next_data"


@router.get("/current-gw")
async def current_gameweek() -> dict[str, int | None]:
    bootstrap = await fpl_client.get_bootstrap()
    return {"current_gw": _current_gameweek_from_bootstrap(bootstrap)}


@router.get("/season-state")
async def season_state() -> dict[str, Any]:
    readiness, bootstrap, fixture_rows = await live_decision_context(
        check_models=True
    )
    bootstrap = bootstrap or {}
    fixture_state = (
        await fixture_source_state(fixture_rows)
        if fixture_rows is not None
        else {
            "source": "Fixture data unavailable",
            "season": "unknown",
            "difficulty_source": "unknown",
            "freshness": "unavailable",
            "next_kickoff": None,
        }
    )
    fpl_api_season = (
        _season_label_from_bootstrap(bootstrap) if bootstrap else readiness.season
    )
    season_status = (
        _detect_season_state(bootstrap, fixture_state)
        if bootstrap
        else "unavailable"
    )
    return {
        "fpl_api_season": fpl_api_season,
        "fixture_source": fixture_state["source"],
        "fixture_season": fixture_state["season"],
        "difficulty_source": fixture_state["difficulty_source"],
        "current_gw": _current_gameweek_from_bootstrap(bootstrap),
        "next_gw": _next_gameweek_from_bootstrap(bootstrap),
        "season_state": season_status,
        "recommendations_ready": readiness.ready,
        "decision_status": readiness.status,
        "recommendation_mode": "generic" if readiness.ready else "blocked",
        "decision_blockers": readiness.blockers,
        "artifact_status": readiness.status,
        "artifact_errors": [row["message"] for row in readiness.blockers],
        "artifact_manifest": readiness.manifest,
        "live_data": readiness.live_data,
        "artifact_data": readiness.artifact_data,
        "last_completed_gw": max(
            (int(event["id"]) for event in bootstrap.get("events", []) if event.get("finished")),
            default=None,
        ),
        "next_season_start": fixture_state.get("next_kickoff"),
        "data_freshness": {
            "fpl_api": "live" if bootstrap else "unavailable",
            "fixtures": fixture_state["freshness"],
        },
    }


@router.get("/team/{team_id}")
async def team(team_id: int) -> dict[str, Any]:
    entry, bootstrap, history, transfers = await asyncio.gather(
        fpl_client.get_team(team_id),
        fpl_client.get_bootstrap(),
        fpl_client.get_team_history(team_id),
        fpl_client.get_team_transfers(team_id),
    )
    target_gameweek = (
        _next_gameweek_from_bootstrap(bootstrap)
        or _current_gameweek_from_bootstrap(bootstrap)
        or 1
    )
    rules = build_season_rules(
        bootstrap,
        season=infer_season_from_bootstrap(bootstrap),
        source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
    )
    free_transfers = infer_free_transfers(
        target_gameweek=target_gameweek,
        team_history=history,
        transfers=transfers,
        max_free_transfers=int(rules.max_free_transfers or 5),
        started_event=entry.get("started_event"),
    )
    bank_value = current_bank_value(
        last_deadline_bank=entry.get("last_deadline_bank"),
        transfers=transfers,
        target_gameweek=target_gameweek,
    )
    return {
        "team_name": entry.get("name"),
        "overall_rank": entry.get("summary_overall_rank"),
        "total_points": entry.get("summary_overall_points"),
        "bank_value": bank_value,
        "current_gw_points": entry.get("summary_event_points"),
        "squad_value": _money(entry.get("last_deadline_value")),
        "free_transfers_available": free_transfers,
        "manager_state_provenance": "public-transfer-history-v1",
    }


@router.get("/team/{team_id}/squad")
async def squad(
    team_id: int,
    gw: int = Query(..., ge=1, le=38),
    _readiness=_LIVE_ARTIFACTS_DEPENDENCY,
) -> list[dict[str, Any]]:
    return await _squad_rows(team_id=team_id, gw=gw, include_projections=True)


@router.get("/team/{team_id}/roster")
async def roster(
    team_id: int,
    gw: int = Query(..., ge=1, le=38),
) -> list[dict[str, Any]]:
    """Return public picks without depending on the prediction bundle."""

    return await _squad_rows(team_id=team_id, gw=gw, include_projections=False)


async def _squad_rows(
    *,
    team_id: int,
    gw: int,
    include_projections: bool,
) -> list[dict[str, Any]]:
    bootstrap = await fpl_client.get_bootstrap()
    try:
        picks = await fpl_client.get_team_picks(team_id, gw)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "squad_unavailable",
                    "message": (
                        "This team has no public squad for that gameweek yet. "
                        "Before GW1, use the initial-squad planner instead."
                    ),
                    "team_id": team_id,
                    "gameweek": gw,
                },
            ) from exc
        raise
    projected: list[dict[str, Any]] = []
    if include_projections:
        projected, _ = await live_projection_rows(
            model_name=BEST_MODEL,
            start_gameweek=gw,
            horizon=3,
        )

    players_by_id = {player["id"]: player for player in bootstrap.get("elements", [])}
    teams_by_id = {team["id"]: team for team in bootstrap.get("teams", [])}
    positions_by_id = {
        position["id"]: position for position in bootstrap.get("element_types", [])
    }
    predictions_by_id = {
        int(player["element_id"]): player
        for player in projected
        if player.get("element_id") is not None
    }

    squad_rows = []
    for pick in picks.get("picks", []):
        player = players_by_id.get(pick.get("element"), {})
        first_name = player.get("first_name", "")
        second_name = player.get("second_name", "")
        player_name = f"{first_name} {second_name}".strip() or player.get("web_name")
        projected_player = predictions_by_id.get(int(player.get("id") or 0), {})
        predicted = next(
            (
                row
                for row in projected_player.get("projections", [])
                if int(row.get("gameweek", -1)) == gw
            ),
            {},
        )
        raw_xp = sum(
            float(fixture.get("predicted_points", 0.0))
            for fixture in predicted.get("fixtures", [])
        )
        team_row = teams_by_id.get(player.get("team"), {})
        position_row = positions_by_id.get(player.get("element_type"), {})

        squad_rows.append(
            {
                "element_id": player.get("id"),
                "name": player_name,
                "web_name": player.get("web_name") or player_name,
                "position": position_row.get("singular_name_short")
                or position_row.get("singular_name"),
                "team": team_row.get("short_name") or team_row.get("name"),
                "team_code": team_row.get("code"),
                "price": _money(player.get("now_cost")),
                "purchase_price": live_pick_price(pick.get("purchase_price")),
                "current_price": _money(player.get("now_cost")),
                "selling_price": live_pick_price(pick.get("selling_price")),
                "is_captain": pick.get("is_captain", False),
                "is_vice_captain": pick.get("is_vice_captain", False),
                "raw_xp": round(raw_xp, 3),
                "expected_points": predicted.get("projected_points"),
                "start_adjusted_xp": predicted.get("projected_points"),
                "start_likelihood": max(
                    (
                        fixture.get("start_likelihood", 0.0)
                        for fixture in predicted.get("fixtures", [])
                    ),
                    default=projected_player.get("start_likelihood"),
                ),
                "form": _float_or_none(player.get("form")),
            }
        )

    return squad_rows


@router.get("/team/{team_id}/history")
async def team_history(team_id: int) -> dict[str, Any]:
    return await fpl_client.get_team_history(team_id)


@router.get("/team/{team_id}/chips")
async def team_chips(team_id: int) -> dict[str, Any]:
    bootstrap = await fpl_client.get_bootstrap()
    fixture_rows = await fpl_client.get_fixtures()
    fixture_state = await fixture_source_state(fixture_rows)
    season_state = _detect_season_state(bootstrap, fixture_state)
    history = (
        await fpl_client.get_team_history(team_id)
        if season_state == "in_season"
        else None
    )
    current_gameweek = (
        _next_gameweek_from_bootstrap(bootstrap)
        or _current_gameweek_from_bootstrap(bootstrap)
        or 1
    )
    return {
        **build_chip_status(
            bootstrap,
            history,
            current_gameweek,
            season_state=season_state,
        ),
        "team_id": team_id,
        "fpl_api_season": _season_label_from_bootstrap(bootstrap),
        "fixture_season": fixture_state.get("season", "unknown"),
        "next_season_start": fixture_state.get("next_kickoff"),
    }


@router.get("/chips")
async def chips(team_id: int | None = Query(default=None)) -> dict[str, Any]:
    if team_id is None:
        bootstrap = await fpl_client.get_bootstrap()
        fixture_rows = await fpl_client.get_fixtures()
        fixture_state = await fixture_source_state(fixture_rows)
        season_state = _detect_season_state(bootstrap, fixture_state)
        current_gameweek = (
            _next_gameweek_from_bootstrap(bootstrap)
            or _current_gameweek_from_bootstrap(bootstrap)
            or 1
        )
        return {
            **build_chip_status(
                bootstrap,
                None,
                current_gameweek,
                season_state=season_state,
            ),
            "team_id": None,
            "fpl_api_season": _season_label_from_bootstrap(bootstrap),
            "fixture_season": fixture_state.get("season", "unknown"),
            "message": (
                "Official 2026/27 chip inventory. Connect your FPL team after GW1 "
                "to track personal usage."
            ),
        }
    return await team_chips(team_id)


@router.get("/team/{team_id}/transfers")
async def team_transfers(team_id: int) -> list[dict[str, Any]]:
    return await fpl_client.get_team_transfers(team_id)


def _money(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 10, 1)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
