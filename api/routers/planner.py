import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api import data_service, fpl_client
from api.chip_recommendations import (
    build_live_chip_state,
    projection_frames,
    squad_frame,
)
from api.chip_tracking import build_chip_status
from api.live_projection_service import current_player_rows
from api.readiness import require_live_artifacts
from api.routers.fixtures import fixture_source_state
from api.routers.fpl_live import (
    _current_gameweek_from_bootstrap,
    _detect_season_state,
    _next_gameweek_from_bootstrap,
    _season_label_from_bootstrap,
)
from fpl_intelligence.beam_search import (
    DeterministicBeamPlanner,
    _apply_transfer,
    _captain_ids,
    _fast_lineup,
    _projection_map,
)
from fpl_intelligence.live_shadow import (
    append_shadow_record,
    compare_projection_sets,
    shadow_enabled,
)
from fpl_intelligence.multi_gw_projection import (
    ALLOWED_HORIZONS,
    load_planner_models,
    project_players,
)
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.season_rules import build_season_rules

router = APIRouter(
    prefix="/api/predictions",
    tags=["planner"],
    dependencies=[Depends(require_live_artifacts)],
)
ACTIVE_PORTFOLIO = get_production_portfolio()


@router.get("/planner")
async def planner(
    team_id: int | None = Query(default=None),
    horizon: int = Query(default=3, ge=1, le=8),
) -> dict[str, Any]:
    if team_id is None:
        raise HTTPException(
            status_code=400,
            detail="Connect your FPL team ID before using the multi-gameweek planner.",
        )
    if horizon not in ALLOWED_HORIZONS:
        raise HTTPException(status_code=400, detail="horizon must be one of 3, 5, or 8")

    bootstrap = await fpl_client.get_bootstrap()
    fixture_rows = await fpl_client.get_fixtures()
    fixture_state = await fixture_source_state(fixture_rows)
    season_state = _detect_season_state(bootstrap, fixture_state)
    if season_state != "in_season":
        season = _season_label_from_bootstrap(bootstrap)
        return {
            "team_id": team_id,
            "season_state": season_state,
            "fpl_api_season": season,
            "fixture_season": fixture_state.get("season", "unknown"),
            "next_season_start": fixture_state.get("next_kickoff"),
            "message": _season_transition_message(
                season,
                fixture_state.get("next_kickoff"),
                season_state=season_state,
            ),
            "start_gameweek": _next_gameweek_from_bootstrap(bootstrap) or 1,
            "horizon": horizon,
            "squad_gameweek": 0,
            "model": ACTIVE_PORTFOLIO.projections.transfer_model,
            "portfolio_version": ACTIVE_PORTFOLIO.version,
            "assumption": "Public manager squad picks are unavailable before the GW1 deadline.",
            "bank_value": None,
            "free_transfers_available": 0,
            "max_extra_free_transfers": int(
                bootstrap.get("game_settings", {}).get("max_extra_free_transfers") or 4
            ),
            "baseline": [],
            "squad": [],
            "player_pool": [],
            "decision": None,
            "decision_error": (
                "The complete manager-specific decision will activate after the "
                "GW1 deadline exposes public squad picks."
            ),
        }

    current_gameweek = _current_gameweek_from_bootstrap(bootstrap) or 1
    start_gameweek = _next_gameweek_from_bootstrap(bootstrap) or min(current_gameweek + 1, 38)
    squad_gameweek = max(1, start_gameweek - 1)
    team_entry, picks_payload, team_history = await asyncio.gather(
        fpl_client.get_team(team_id),
        fpl_client.get_team_picks(team_id, squad_gameweek),
        fpl_client.get_team_history(team_id),
    )
    history = data_service.historical_player_gw()

    try:
        models = load_planner_models(ACTIVE_PORTFOLIO.projections.transfer_model)
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    player_rows = _current_player_rows(bootstrap)
    if not player_rows:
        raise HTTPException(
            status_code=503,
            detail="FPL player data is unavailable for the planner.",
        )

    projection_horizon = max(horizon, 8)
    projected_players = project_players(
        player_rows,
        fixture_rows,
        bootstrap.get("teams", []),
        start_gameweek,
        projection_horizon,
        models=models,
        history=history,
    )
    chip_models = (
        models
        if ACTIVE_PORTFOLIO.projections.chip_model
        == ACTIVE_PORTFOLIO.projections.transfer_model
        else load_planner_models(ACTIVE_PORTFOLIO.projections.chip_model)
    )
    chip_projected_players = (
        projected_players
        if chip_models is models
        else project_players(
            player_rows,
            fixture_rows,
            bootstrap.get("teams", []),
            start_gameweek,
            projection_horizon,
            models=chip_models,
            history=history,
        )
    )
    shadow = None
    if shadow_enabled():
        control = get_production_portfolio("m8_control")
        try:
            control_models = load_planner_models(control.projections.transfer_model)
            control_players = project_players(
                player_rows,
                fixture_rows,
                bootstrap.get("teams", []),
                start_gameweek,
                horizon,
                models=control_models,
                history=history,
            )
            shadow = compare_projection_sets(
                active_players=projected_players,
                control_players=control_players,
                start_gameweek=start_gameweek,
                horizon=horizon,
                active_portfolio=ACTIVE_PORTFOLIO,
                control_portfolio=control,
                rules_version=ACTIVE_PORTFOLIO.version,
            )
            append_shadow_record(shadow)
        except (FileNotFoundError, RuntimeError, ValueError, KeyError) as exc:
            shadow = {"status": "unavailable", "error": str(exc)}
    projections_by_id = {player["element_id"]: player for player in projected_players}
    squad = _squad_rows(picks_payload.get("picks", []), projections_by_id)
    if not squad:
        raise HTTPException(status_code=404, detail="No squad picks were available for this team.")

    rules = build_season_rules(
        bootstrap,
        season=_season_label_from_bootstrap(bootstrap),
        source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
    )
    chip_status = build_chip_status(
        bootstrap,
        team_history,
        start_gameweek,
        season_state=season_state,
    )
    chip_state = build_live_chip_state(rules, chip_status)
    decision = None
    decision_error = None
    decision_squad = squad_frame(picks_payload.get("picks", []), projected_players)
    transfer_frames = projection_frames(projected_players)
    chip_frames = projection_frames(chip_projected_players)
    current_predictions = transfer_frames.get(start_gameweek)
    if (
        len(decision_squad) == 15
        and current_predictions is not None
        and not current_predictions.empty
    ):
        try:
            beam = DeterministicBeamPlanner(horizon=min(3, projection_horizon))
            action = beam.decide(
                gameweek=start_gameweek,
                squad=decision_squad,
                bank=_money(team_entry.get("last_deadline_bank")) or 0.0,
                free_transfers=int(team_entry.get("free_transfers") or 1),
                chip_state=chip_state,
                predictions=current_predictions.copy(),
                future_predictions={
                    gameweek: frame.copy()
                    for gameweek, frame in transfer_frames.items()
                    if gameweek > start_gameweek
                },
                chip_predictions=chip_frames.get(start_gameweek, current_predictions).copy(),
                future_chip_predictions={
                    gameweek: frame.copy()
                    for gameweek, frame in chip_frames.items()
                    if gameweek > start_gameweek
                },
                rules=rules,
            )
            decision = _decision_payload(action, decision_squad, current_predictions)
        except (ValueError, KeyError, IndexError) as exc:
            decision_error = str(exc)
    elif len(decision_squad) != 15:
        decision_error = "A complete 15-player squad is required for a legal decision."
    else:
        decision_error = "No live projections were available for the decision gameweek."

    gameweeks = list(range(start_gameweek, start_gameweek + horizon))
    baseline = []
    for gameweek in gameweeks:
        rows = [
            _projection_for_gameweek(player, gameweek)
            for player in squad
            if player["is_starter"]
        ]
        baseline.append(
            {
                "gameweek": gameweek,
                "projected_points": round(sum(row["projected_points"] for row in rows), 2),
                "blank_count": sum(1 for row in rows if row["blank"]),
                "double_count": sum(1 for row in rows if row["double"]),
            }
        )

    settings = bootstrap.get("game_settings", {})
    player_pool = [
        _pool_row(player, projections_by_id[player["element_id"]])
        for player in player_rows
        if player["element_id"] in projections_by_id
    ]

    return {
        "team_id": team_id,
        "season_state": season_state,
        "fpl_api_season": _season_label_from_bootstrap(bootstrap),
        "fixture_season": fixture_state.get("season", "unknown"),
        "start_gameweek": start_gameweek,
        "horizon": horizon,
        "squad_gameweek": squad_gameweek,
        "model": ACTIVE_PORTFOLIO.projections.transfer_model,
        "portfolio_version": ACTIVE_PORTFOLIO.version,
        "transfer_model": ACTIVE_PORTFOLIO.projections.transfer_model,
        "captain_model": ACTIVE_PORTFOLIO.projections.captain_model,
        "chip_model": ACTIVE_PORTFOLIO.projections.chip_model,
        "shadow": shadow,
        "assumption": (
            "Projections assume current form and role continue; "
            "fixture context changes by gameweek."
        ),
        "bank_value": _money(team_entry.get("last_deadline_bank")),
        "free_transfers_available": int(team_entry.get("free_transfers") or 0),
        "max_extra_free_transfers": int(settings.get("max_extra_free_transfers") or 4),
        "baseline": baseline,
        "squad": squad,
        "player_pool": player_pool,
        "decision": decision,
        "decision_error": decision_error,
    }


def _decision_payload(action, squad, predictions) -> dict[str, Any]:
    """Convert a beam action into an API-safe complete decision summary."""

    active_squad = squad.copy()
    if action.chip is None or action.chip.name not in {"wildcard", "freehit"}:
        active_squad = _apply_transfer(active_squad, predictions, action.transfer)
    projection = _projection_map(predictions)
    lineup = _fast_lineup(active_squad, projection)
    captain_id, vice_captain_id = _captain_ids(lineup.starting_ids, projection)
    return {
        "transfer": {
            "outgoing_id": action.transfer.outgoing_id,
            "outgoing_name": action.transfer.outgoing_name,
            "incoming_id": action.transfer.incoming_id,
            "incoming_name": action.transfer.incoming_name,
            "projected_gain": round(action.transfer.projected_gain, 3),
            "hit_cost": action.transfer.hit_cost,
            "hit_selected": action.transfer.hit_cost > 0,
        },
        "chip": action.chip.name if action.chip is not None else None,
        "chip_key": action.chip.key if action.chip is not None else None,
        "starting_ids": list(lineup.starting_ids),
        "bench_order": list(lineup.bench_ids),
        "captain_id": captain_id,
        "vice_captain_id": vice_captain_id,
        "expected_gameweek_points": round(action.expected_points, 3),
        "expected_horizon_points": round(action.expected_horizon_points, 3),
        "no_chip_horizon_points": round(action.no_chip_horizon_points, 3),
        "expected_horizon_gain": round(
            action.expected_horizon_points - action.no_chip_horizon_points, 3
        ),
        "uncertainty_penalty": round(action.uncertainty_penalty, 3),
        "reason": action.reason,
    }


def _season_transition_message(
    season: str,
    next_season_start: str | None,
    *,
    season_state: str | None = None,
) -> str:
    if season_state == "pre_season":
        return (
            f"{season} player prices, fixtures, and projections are loaded. "
            "Manager-specific squad planning becomes available after the GW1 deadline, "
            "when public squad picks can be read."
        )
    if next_season_start:
        start_date = next_season_start[:10]
        return (
            f"The {season} season has ended. Gameweek projections for the next season "
            f"will be available once the new season begins and enough gameweeks have "
            f"been played to establish rolling form data. Season starts {start_date}."
        )
    return (
        f"The {season} season has ended. Gameweek projections for the next season will be "
        "available once official fixtures and enough rolling form data exist."
    )


def _current_player_rows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    return current_player_rows(bootstrap)


def _squad_rows(
    picks: list[dict[str, Any]], projections_by_id: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for index, pick in enumerate(picks):
        player = projections_by_id.get(pick.get("element"))
        if player is None:
            continue
        pick_order = int(pick.get("position") or index + 1)
        rows.append(
            {
                **_pool_row(player, player),
                "pick_order": pick_order,
                "is_starter": pick_order <= 11,
                "is_captain": bool(pick.get("is_captain")),
                "is_vice_captain": bool(pick.get("is_vice_captain")),
            }
        )
    return sorted(rows, key=lambda row: row["pick_order"])


def _pool_row(player: dict[str, Any], projected: dict[str, Any]) -> dict[str, Any]:
    return {
        "element_id": player.get("element_id"),
        "name": player.get("name"),
        "web_name": player.get("web_name"),
        "team": player.get("team"),
        "team_code": player.get("team_code"),
        "position": player.get("position"),
        "price": player.get("price"),
        "start_likelihood": player.get("start_likelihood"),
        "projections": projected.get("projections", []),
    }


def _projection_for_gameweek(player: dict[str, Any], gameweek: int) -> dict[str, Any]:
    return next(
        (projection for projection in player["projections"] if projection["gameweek"] == gameweek),
        {"projected_points": 0.0, "blank": True, "double": False},
    )


def _money(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 10, 1)
