import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from api import data_service, fpl_client
from api.chip_opportunities import build_chip_opportunities
from api.chip_recommendations import (
    LIVE_RULES_SOURCE,
    build_live_chip_state,
    projection_frames,
    recommend_live_chip,
    squad_frame,
)
from api.chip_signals import BASELINE_WINDOW, generate_chip_alerts
from api.chip_tracking import build_chip_status, filter_actionable_chip_alerts
from api.live_projection_service import live_projection_rows
from api.manager_state import build_manager_decision_state
from api.readiness import require_live_artifacts
from api.recommendation_policy import proactive_chip_recommendations_enabled
from api.routers.fixtures import fixture_source_state
from api.routers.fpl_live import (
    _current_gameweek_from_bootstrap,
    _detect_season_state,
    _next_gameweek_from_bootstrap,
    _season_label_from_bootstrap,
)
from api.routers.planner import _current_player_rows, _season_transition_message
from fpl_intelligence.live_shadow import (
    append_shadow_record,
    compare_chip_recommendations,
    shadow_enabled,
)
from fpl_intelligence.multi_gw_projection import load_planner_models, project_players
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.season_rules import build_season_rules

router = APIRouter(
    prefix="/api",
    tags=["chips"],
    dependencies=[Depends(require_live_artifacts)],
)
ACTIVE_PORTFOLIO = get_production_portfolio()


@router.get("/chip-opportunities")
async def chip_opportunities() -> dict[str, Any]:
    """Return league-wide chip windows without requiring a manager or squad."""

    bootstrap, fixture_rows = await asyncio.gather(
        fpl_client.get_bootstrap(),
        fpl_client.get_fixtures(),
    )
    fixture_state = await fixture_source_state(fixture_rows)
    season = _season_label_from_bootstrap(bootstrap)
    season_state = _detect_season_state(bootstrap, fixture_state)
    response_meta = {
        "season_state": season_state,
        "fpl_api_season": season,
        "fixture_season": fixture_state.get("season", "unknown"),
        "difficulty_source": fixture_state.get("difficulty_source", "unknown"),
        "current_gw": _current_gameweek_from_bootstrap(bootstrap),
        "next_gw": _next_gameweek_from_bootstrap(bootstrap),
    }
    if season_state != "in_season":
        return {
            **response_meta,
            "status": "unavailable",
            "message": _season_transition_message(
                season,
                fixture_state.get("next_kickoff"),
                season_state=season_state,
            ),
            "opportunities": [],
        }

    target_gameweek = (
        _next_gameweek_from_bootstrap(bootstrap)
        or _current_gameweek_from_bootstrap(bootstrap)
        or 1
    )
    try:
        projected_players, _ = await live_projection_rows(
            model_name=ACTIVE_PORTFOLIO.projections.chip_model,
            start_gameweek=target_gameweek,
            horizon=8,
        )
        opportunities = build_chip_opportunities(
            bootstrap,
            fixture_rows,
            projected_players,
            target_gameweek=target_gameweek,
        )
    except (FileNotFoundError, RuntimeError, ValueError, KeyError, IndexError) as exc:
        return {
            **response_meta,
            "status": "unavailable",
            "message": f"Chip opportunities are temporarily unavailable: {exc}",
            "opportunities": [],
        }

    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    horizon_end = max(
        (
            int(row["recommended_gameweek"])
            for row in opportunities
            if row.get("recommended_gameweek") is not None
        ),
        default=target_gameweek + 7,
    )
    return {
        **response_meta,
        "status": "ready",
        "message": (
            "League-wide chip opportunities based on public fixtures, player form, "
            "expected involvement, defensive weakness and predicted minutes."
        ),
        "target_gameweek": target_gameweek,
        "horizon_end_gameweek": max(target_gameweek + 7, horizon_end),
        "opportunities": opportunities,
        "personalized": False,
        "automatic_chip_actions": False,
        "model": ACTIVE_PORTFOLIO.projections.chip_model,
        "portfolio_version": ACTIVE_PORTFOLIO.version,
        "data_cutoff": generated_at,
        "generated_at": generated_at,
        "methodology": [
            "Triple Captain combines projected points, minutes confidence, expected "
            "goal involvement and opponent defensive xGC.",
            "Bench Boost compares affordable four-player bench combinations and minutes.",
            "Free Hit prioritizes published blank and double Gameweeks.",
            "Wildcard highlights clusters of teams beginning strong five-Gameweek runs.",
        ],
    }


@router.get("/chip-tips")
async def chip_tips(team_id: int | None = Query(default=None)) -> dict[str, Any]:
    if team_id is None:
        return {
            "status": "no_team",
            "team_id": None,
            "message": "Connect your FPL team to receive squad-relative chip timing tips.",
            "alerts": [],
        }

    bootstrap = await fpl_client.get_bootstrap()
    fixture_rows = await fpl_client.get_fixtures()
    fixture_state = await fixture_source_state(fixture_rows)
    season = _season_label_from_bootstrap(bootstrap)
    season_state = _detect_season_state(bootstrap, fixture_state)
    response_meta = {
        "team_id": team_id,
        "season_state": season_state,
        "fpl_api_season": season,
        "fixture_season": fixture_state.get("season", "unknown"),
        "difficulty_source": fixture_state.get("difficulty_source", "unknown"),
        "current_gw": _current_gameweek_from_bootstrap(bootstrap),
        "next_gw": _next_gameweek_from_bootstrap(bootstrap),
    }
    if season_state != "in_season":
        return {
            **response_meta,
            "status": "unavailable",
            "message": _season_transition_message(
                season,
                fixture_state.get("next_kickoff"),
                season_state=season_state,
            ),
            "alerts": [],
        }

    target_gameweek = (
        _next_gameweek_from_bootstrap(bootstrap)
        or _current_gameweek_from_bootstrap(bootstrap)
        or 1
    )
    completed_gameweeks = sorted(
        {
            int(event["id"])
            for event in bootstrap.get("events", [])
            if event.get("finished") and event.get("id") and int(event["id"]) < target_gameweek
        }
    )[-BASELINE_WINDOW:]
    squad_gameweek = max(1, target_gameweek - 1)
    (
        team_entry,
        team_picks,
        historical_pick_payloads,
        team_history,
        team_transfers,
    ) = await asyncio.gather(
        fpl_client.get_team(team_id),
        fpl_client.get_team_picks(team_id, squad_gameweek),
        _historical_picks(team_id, completed_gameweeks),
        fpl_client.get_team_history(team_id),
        fpl_client.get_team_transfers(team_id),
    )
    if not proactive_chip_recommendations_enabled():
        return {
            **response_meta,
            "status": "insufficient_data",
            "message": (
                "Proactive chip calls are paused while SquadMetric builds a "
                "season-long owned-squad validation record. Chip availability "
                "remains live, but the optimizer will not tell you to spend one yet."
            ),
            "alerts": [],
            "target_gameweek": target_gameweek,
        }

    try:
        models = load_planner_models(ACTIVE_PORTFOLIO.projections.chip_model)
    except (FileNotFoundError, RuntimeError) as exc:
        return {
            **response_meta,
            "status": "unavailable",
            "message": f"Chip tips are unavailable until projection models are ready: {exc}",
            "alerts": [],
        }

    player_rows = _current_player_rows(bootstrap)
    projected_players = project_players(
        player_rows,
        fixture_rows,
        bootstrap.get("teams", []),
        max(1, target_gameweek - (BASELINE_WINDOW - 1)),
        8,
        models=models,
        history=data_service.serving_player_gw(),
    )
    projections_by_id = {
        player.get("element_id"): player
        for player in projected_players
        if player.get("element_id") is not None
    }
    player_by_id = {
        player.get("element_id"): player
        for player in player_rows
        if player.get("element_id") is not None
    }
    frames = projection_frames(projected_players)
    rules = build_season_rules(
        bootstrap,
        season=season,
        source_url=LIVE_RULES_SOURCE,
    )
    serving_history = data_service.serving_player_gw()
    manager_state = build_manager_decision_state(
        target_gameweek=target_gameweek,
        picks=team_picks.get("picks", []),
        team_history=team_history,
        transfers=team_transfers,
        projected_players=projected_players,
        serving_history=serving_history,
        max_free_transfers=int(rules.max_free_transfers or 5),
        started_event=team_entry.get("started_event"),
        last_deadline_bank=team_entry.get("last_deadline_bank"),
    )
    if not manager_state.price_basis_complete or not manager_state.bank_basis_complete:
        return {
            **response_meta,
            "status": "unavailable",
            "message": (
                "Chip valuation is paused because exact manager price or bank "
                "history is unavailable."
            ),
            "alerts": [],
        }
    chip_status = build_chip_status(
        bootstrap,
        team_history,
        target_gameweek,
        season_state=season_state,
    )
    try:
        recommendation = recommend_live_chip(
            target_gameweek=target_gameweek,
            squad=squad_frame(manager_state.picks, projected_players),
            bank=manager_state.bank_value or 0.0,
            free_transfers=manager_state.free_transfers,
            chip_state=build_live_chip_state(rules, chip_status),
            rules=rules,
            frames=frames,
            data_cutoff=_deadline_for_gameweek(bootstrap, target_gameweek),
            projection_model_name=ACTIVE_PORTFOLIO.projections.chip_model,
            portfolio_version=ACTIVE_PORTFOLIO.version,
        )
    except (ValueError, KeyError, IndexError) as exc:
        return {
            **response_meta,
            "status": "unavailable",
            "message": f"Live chip valuation is temporarily unavailable: {exc}",
            "alerts": [],
        }
    shadow = None
    if shadow_enabled():
        control = get_production_portfolio("m8_control")
        try:
            control_models = load_planner_models(control.projections.chip_model)
            control_projected_players = project_players(
                player_rows,
                fixture_rows,
                bootstrap.get("teams", []),
                max(1, target_gameweek - (BASELINE_WINDOW - 1)),
                8,
                models=control_models,
                history=data_service.serving_player_gw(),
            )
            control_recommendation = recommend_live_chip(
                target_gameweek=target_gameweek,
                squad=squad_frame(manager_state.picks, control_projected_players),
                bank=manager_state.bank_value or 0.0,
                free_transfers=manager_state.free_transfers,
                chip_state=build_live_chip_state(rules, chip_status),
                rules=rules,
                frames=projection_frames(control_projected_players),
                data_cutoff=_deadline_for_gameweek(bootstrap, target_gameweek),
                projection_model_name=control.projections.chip_model,
                portfolio_version=control.version,
            )
            shadow = compare_chip_recommendations(
                active=recommendation,
                control=control_recommendation,
                gameweek=target_gameweek,
                active_portfolio=ACTIVE_PORTFOLIO,
                control_portfolio=control,
                rules_version=rules.rules_version,
                data_cutoff=_deadline_for_gameweek(bootstrap, target_gameweek),
            )
            append_shadow_record(shadow)
        except (ValueError, KeyError, IndexError, FileNotFoundError, RuntimeError) as exc:
            shadow = {"status": "unavailable", "error": str(exc)}
    difficulty_by_team_gw = _difficulty_by_team_gw(fixture_rows)

    history_rows = []
    for gameweek, picks in historical_pick_payloads:
        if picks is None:
            continue
        history_rows.append(
            _build_gameweek_row(
                gameweek,
                picks.get("picks", []),
                player_by_id,
                projections_by_id,
                difficulty_by_team_gw,
            )
        )
    target_row = _build_gameweek_row(
        target_gameweek,
        team_picks.get("picks", []),
        player_by_id,
        projections_by_id,
        difficulty_by_team_gw,
    )
    signals = generate_chip_alerts(history_rows, target_row)
    signals["alerts"] = filter_actionable_chip_alerts(signals["alerts"], chip_status)
    return {
        **response_meta,
        "status": "ready",
        "message": _recommendation_message(recommendation),
        "alerts": signals["alerts"],
        "explanatory_signals": signals,
        "recommendation": recommendation["recommendation"],
        "alternatives": recommendation["alternatives"],
        "remaining_chips": recommendation["remaining_chips"],
        "used_chips": recommendation["used_chips"],
        "target_gameweek": target_gameweek,
        "baseline_gameweeks": completed_gameweeks,
        "model": recommendation["model"],
        "projection_model": recommendation["projection_model"],
        "portfolio_version": recommendation["portfolio_version"],
        "model_version": recommendation["model_version"],
        "chip_mode": recommendation["chip_mode"],
        "rules_version": recommendation["rules_version"],
        "rules_payload_hash": recommendation["rules_payload_hash"],
        "data_cutoff": recommendation["data_cutoff"],
        "generated_at": recommendation["generated_at"],
        "shadow": shadow,
    }


async def _historical_picks(
    team_id: int,
    gameweeks: list[int],
) -> list[tuple[int, dict[str, Any] | None]]:
    payloads = await asyncio.gather(
        *(fpl_client.get_team_picks(team_id, gameweek) for gameweek in gameweeks),
        return_exceptions=True,
    )
    return [
        (gameweek, payload if isinstance(payload, dict) else None)
        for gameweek, payload in zip(gameweeks, payloads, strict=True)
    ]


def _build_gameweek_row(
    gameweek: int,
    picks: list[dict[str, Any]],
    player_by_id: dict[int, dict[str, Any]],
    projections_by_id: dict[int, dict[str, Any]],
    difficulty_by_team_gw: dict[tuple[int, int], list[float]],
) -> dict[str, Any]:
    starting_xi = []
    bench = []
    for index, pick in enumerate(picks):
        element_id = pick.get("element")
        player = player_by_id.get(element_id, {})
        projected = projections_by_id.get(element_id, {})
        projection = next(
            (
                row
                for row in projected.get("projections", [])
                if row.get("gameweek") == gameweek
            ),
            {},
        )
        difficulties = difficulty_by_team_gw.get((player.get("team_id"), gameweek), [])
        fixture_rows = projection.get("fixtures", [])
        start_likelihoods = [
            fixture.get("start_likelihood")
            for fixture in fixture_rows
            if fixture.get("start_likelihood") is not None
        ]
        player_row = {
            "projected_points": projection.get("projected_points", 0.0),
            "start_likelihood": (
                sum(start_likelihoods) / len(start_likelihoods)
                if start_likelihoods
                else player.get("start_likelihood")
            ),
            "fixture_difficulty": difficulties,
        }
        pick_order = int(pick.get("position") or index + 1)
        (starting_xi if pick_order <= 11 else bench).append(player_row)

    return {
        "gameweek": gameweek,
        "starting_xi": starting_xi,
        "bench": bench,
    }


def _difficulty_by_team_gw(
    fixtures: list[dict[str, Any]],
) -> dict[tuple[int, int], list[float]]:
    output: dict[tuple[int, int], list[float]] = {}
    for fixture in fixtures:
        gameweek = fixture.get("event")
        if gameweek is None:
            continue
        for team_key, difficulty_key in (
            ("team_h", "team_h_difficulty"),
            ("team_a", "team_a_difficulty"),
        ):
            team_id = fixture.get(team_key)
            difficulty = fixture.get(difficulty_key)
            if team_id is None or difficulty is None:
                continue
            output.setdefault((team_id, int(gameweek)), []).append(float(difficulty))
    return output


def _deadline_for_gameweek(bootstrap: dict[str, Any], gameweek: int) -> str | None:
    event = next(
        (event for event in bootstrap.get("events", []) if event.get("id") == gameweek),
        None,
    )
    return event.get("deadline_time") if event else None


def _recommendation_message(recommendation: dict[str, Any]) -> str:
    decision = recommendation["recommendation"]
    if decision["action"] == "use":
        return (
            f"Use {decision['chip']} in GW{decision['gameweek']}: projected horizon gain "
            f"+{decision['expected_horizon_gain']:.2f} points "
            f"({decision['confidence']} confidence)."
        )
    alternative = decision.get("best_alternative")
    if alternative:
        return (
            f"Save your chips this week. The strongest projected alternative is "
            f"{alternative['chip']} in GW{alternative['gameweek']} for "
            f"+{alternative['expected_horizon_gain']:.2f} horizon points."
        )
    return (
        "Save your chips this week; no stronger legal chip opportunity was found "
        "in the projected window."
    )
