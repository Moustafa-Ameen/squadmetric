import asyncio
import hashlib
import json
from copy import deepcopy
from time import monotonic
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api import data_service, fpl_client
from api.chip_recommendations import (
    build_live_chip_state,
    projection_frames,
    squad_frame,
)
from api.chip_tracking import build_chip_status
from api.live_projection_service import current_player_rows, live_projection_rows
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
from api.team_rating import build_team_rating
from fpl_intelligence.artifact_contract import load_current_artifact_manifest
from fpl_intelligence.backtest_transfer_strategy import validate_squad
from fpl_intelligence.beam_search import (
    FREE_TRANSFER_MINIMUM_HORIZON_GAIN,
    DeterministicBeamPlanner,
    _captain_ids,
    _fast_lineup,
    _projection_map,
    apply_transfer_plan,
)
from fpl_intelligence.chip_simulation import ChipState
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
from fpl_intelligence.price_economics import live_pick_price
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.season_rules import build_season_rules

router = APIRouter(
    prefix="/api/predictions",
    tags=["planner"],
    dependencies=[Depends(require_live_artifacts)],
)
ACTIVE_PORTFOLIO = get_production_portfolio()
DECISION_CENTER_CACHE_SECONDS = 60.0
_DECISION_CENTER_CACHE: dict[
    tuple[int, int, float | None, int | None],
    tuple[float, dict[str, Any]],
] = {}


def _live_transfer_planner(
    *, horizon: int, free_transfers: int, allow_chips: bool
) -> DeterministicBeamPlanner:
    """Build the one production planner configuration used by every live path."""

    return DeterministicBeamPlanner(
        beam_width=8,
        horizon=horizon,
        max_transfers=16,
        max_same_gameweek_transfers=min(5, max(2, free_transfers + 1)),
        hit_policy="horizon_value",
        allow_chips=allow_chips,
        minimum_transfer_horizon_gain=FREE_TRANSFER_MINIMUM_HORIZON_GAIN,
    )


class ProvisionalTeamRequest(BaseModel):
    element_ids: list[int] = Field(min_length=15, max_length=15)
    bank: float = Field(default=0.0, ge=0.0, le=20.0)
    free_transfers: int = Field(default=1, ge=0, le=5)


@router.get("/planner")
async def planner(
    team_id: int | None = Query(default=None),
    horizon: int = Query(default=3, ge=1, le=8),
    include_evidence: bool = Query(default=False),
    bank_override: Annotated[float | None, Query(ge=0.0, le=20.0)] = None,
    free_transfers_override: Annotated[int | None, Query(ge=0, le=5)] = None,
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
    team_entry, picks_payload, team_history, team_transfers = await asyncio.gather(
        fpl_client.get_team(team_id),
        fpl_client.get_team_picks(team_id, squad_gameweek),
        fpl_client.get_team_history(team_id),
        fpl_client.get_team_transfers(team_id),
    )
    history = data_service.serving_player_gw()

    player_rows = _current_player_rows(bootstrap)
    if not player_rows:
        raise HTTPException(
            status_code=503,
            detail="FPL player data is unavailable for the planner.",
        )

    projection_horizon = max(horizon, 8)
    allow_personalized_chips = proactive_chip_recommendations_enabled()
    try:
        projected_players, _ = await live_projection_rows(
            model_name=ACTIVE_PORTFOLIO.projections.transfer_model,
            start_gameweek=start_gameweek,
            horizon=projection_horizon,
        )
        chip_projected_players = projected_players
        if (
            allow_personalized_chips
            and ACTIVE_PORTFOLIO.projections.chip_model
            != ACTIVE_PORTFOLIO.projections.transfer_model
        ):
            chip_projected_players, _ = await live_projection_rows(
                model_name=ACTIVE_PORTFOLIO.projections.chip_model,
                start_gameweek=start_gameweek,
                horizon=projection_horizon,
            )
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
    rules = build_season_rules(
        bootstrap,
        season=_season_label_from_bootstrap(bootstrap),
        source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
    )
    manager_state = build_manager_decision_state(
        target_gameweek=start_gameweek,
        picks=picks_payload.get("picks", []),
        team_history=team_history,
        transfers=team_transfers,
        projected_players=projected_players,
        serving_history=history,
        max_free_transfers=int(rules.max_free_transfers or 5),
        started_event=team_entry.get("started_event"),
        last_deadline_bank=team_entry.get("last_deadline_bank"),
    )
    decision_bank = (
        round(float(bank_override), 1)
        if bank_override is not None
        else manager_state.bank_value
    )
    decision_free_transfers = (
        int(free_transfers_override)
        if free_transfers_override is not None
        else manager_state.free_transfers
    )
    bank_state_complete = bank_override is not None or manager_state.bank_basis_complete
    effective_picks = list(manager_state.picks)
    projections_by_id = {player["element_id"]: player for player in projected_players}
    squad = _squad_rows(effective_picks, projections_by_id)
    if not squad:
        raise HTTPException(status_code=404, detail="No squad picks were available for this team.")

    chip_status = build_chip_status(
        bootstrap,
        team_history,
        start_gameweek,
        season_state=season_state,
    )
    chip_state = build_live_chip_state(rules, chip_status)
    decision = None
    decision_evidence = None
    decision_error = None
    decision_squad = squad_frame(effective_picks, projected_players)
    transfer_frames = projection_frames(projected_players)
    chip_frames = projection_frames(chip_projected_players)
    current_predictions = transfer_frames.get(start_gameweek)
    if (
        manager_state.price_basis_complete
        and bank_state_complete
        and len(decision_squad) == 15
        and current_predictions is not None
        and not current_predictions.empty
    ):
        try:
            beam = _live_transfer_planner(
                horizon=horizon,
                free_transfers=decision_free_transfers,
                allow_chips=allow_personalized_chips,
            )
            action = await asyncio.to_thread(
                beam.decide,
                gameweek=start_gameweek,
                squad=decision_squad,
                bank=decision_bank or 0.0,
                free_transfers=decision_free_transfers,
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
            if include_evidence:
                decision_evidence = _decision_evidence_payload(
                    selected_action=action,
                    root_actions=beam.last_evidence_actions or beam.last_root_actions,
                    squad=decision_squad,
                    predictions=current_predictions,
                    bank=decision_bank or 0.0,
                    free_transfers=decision_free_transfers,
                    chip_state=chip_state,
                    planner=beam,
                )
        except (ValueError, KeyError, IndexError) as exc:
            decision_error = str(exc)
    elif not manager_state.price_basis_complete:
        decision_error = (
            "Exact purchase-price history is unavailable for player IDs "
            + ", ".join(str(value) for value in manager_state.missing_purchase_price_ids)
            + "; transfer advice is paused to avoid an invalid budget."
        )
    elif not bank_state_complete:
        decision_error = (
            "The current bank could not be reconstructed from public manager "
            "history; transfer advice is paused to avoid an invalid budget."
        )
    elif len(decision_squad) != 15:
        decision_error = "A complete 15-player squad is required for a legal decision."
    else:
        decision_error = "No live projections were available for the decision gameweek."

    gameweeks = list(range(start_gameweek, start_gameweek + horizon))
    baseline = []
    for gameweek in gameweeks:
        rows = [
            _projection_for_gameweek(player, gameweek) for player in squad if player["is_starter"]
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
    manifest = load_current_artifact_manifest() or {}
    deadline_event = next(
        (
            event
            for event in bootstrap.get("events", [])
            if int(event.get("id") or 0) == start_gameweek
        ),
        {},
    )
    player_pool = [
        _pool_row(player, projections_by_id[player["element_id"]])
        for player in player_rows
        if player["element_id"] in projections_by_id
    ]

    rating = None
    if len(decision_squad) == 15 and transfer_frames:
        selected_branch = next(
            (
                branch
                for branch in _optimized_evidence_branches(decision_evidence or {})
                if branch.get("selected")
            ),
            None,
        )
        no_action_branch = next(
            (
                branch
                for branch in _optimized_evidence_branches(decision_evidence or {})
                if branch.get("chip") is None and int(branch.get("transfer_count") or 0) == 0
            ),
            None,
        )
        try:
            rating = await asyncio.to_thread(
                build_team_rating,
                squad=decision_squad,
                frames=transfer_frames,
                bank=decision_bank or 0.0,
                horizon=min(3, horizon),
                current_horizon_points=(
                    float(no_action_branch.get("expected_horizon_points") or 0.0)
                    if no_action_branch
                    else None
                ),
                recommended_horizon_points=(
                    float(selected_branch.get("expected_horizon_points") or 0.0)
                    if selected_branch
                    else None
                ),
            )
        except (ValueError, KeyError, IndexError):
            rating = None

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
        "decision_engine_version": DeterministicBeamPlanner.version,
        "transfer_model": ACTIVE_PORTFOLIO.projections.transfer_model,
        "captain_model": ACTIVE_PORTFOLIO.projections.captain_model,
        "chip_model": ACTIVE_PORTFOLIO.projections.chip_model,
        "shadow": shadow,
        "rules_version": rules.rules_version,
        "rules_payload_hash": rules.payload_hash,
        "data_cutoff": manifest.get("data_cutoff"),
        "bootstrap_hash": manifest.get("bootstrap_hash"),
        "fixtures_hash": manifest.get("fixtures_hash"),
        "deadline": deadline_event.get("deadline_time"),
        "assumption": (
            "Projections assume current form and role continue; "
            "fixture context changes by gameweek."
        ),
        "bank_value": decision_bank,
        "free_transfers_available": decision_free_transfers,
        "manager_state_provenance": manager_state.provenance,
        "manager_state_confirmation": {
            "bank_source": (
                "user_override" if bank_override is not None else "public_history"
            ),
            "free_transfers_source": (
                "user_override"
                if free_transfers_override is not None
                else "public_history_inference"
            ),
            "can_override": True,
        },
        "purchase_price_state_complete": manager_state.price_basis_complete,
        "bank_state_complete": bank_state_complete,
        "max_extra_free_transfers": int(settings.get("max_extra_free_transfers") or 4),
        "baseline": baseline,
        "squad": squad,
        "player_pool": player_pool,
        "decision": decision,
        "decision_evidence": decision_evidence,
        "decision_error": decision_error,
        "rating": rating,
    }


@router.get("/decision-center")
async def decision_center(
    team_id: int | None = Query(default=None),
    horizon: int = Query(default=3, ge=1, le=8),
    bank_override: Annotated[float | None, Query(ge=0.0, le=20.0)] = None,
    free_transfers_override: Annotated[int | None, Query(ge=0, le=5)] = None,
) -> dict[str, Any]:
    if team_id is None:
        raise HTTPException(
            status_code=400,
            detail="Connect your FPL team ID before requesting a weekly decision.",
        )
    cache_key = (
        int(team_id),
        int(horizon),
        round(float(bank_override), 1) if bank_override is not None else None,
        int(free_transfers_override) if free_transfers_override is not None else None,
    )
    cached = _DECISION_CENTER_CACHE.get(cache_key)
    if cached is not None and monotonic() - cached[0] < DECISION_CENTER_CACHE_SECONDS:
        return deepcopy(cached[1])

    payload = await planner(
        team_id=team_id,
        horizon=horizon,
        include_evidence=True,
        bank_override=bank_override,
        free_transfers_override=free_transfers_override,
    )
    response = _decision_center_payload(payload)
    _DECISION_CENTER_CACHE[cache_key] = (monotonic(), deepcopy(response))
    return response


@router.post("/provisional-team-rating")
async def provisional_team_rating(request: ProvisionalTeamRequest) -> dict[str, Any]:
    """Rate an OCR-imported squad without claiming it is an official team link."""

    if len(set(request.element_ids)) != 15:
        raise HTTPException(
            status_code=400, detail="The screenshot must contain 15 unique players."
        )
    bootstrap = await fpl_client.get_bootstrap()
    fixture_rows = await fpl_client.get_fixtures()
    fixture_state = await fixture_source_state(fixture_rows)
    season_state = _detect_season_state(bootstrap, fixture_state)
    if season_state != "in_season":
        raise HTTPException(
            status_code=409, detail="Provisional ratings are available during the season."
        )

    start_gameweek = _next_gameweek_from_bootstrap(bootstrap) or 1
    try:
        projected_players, _ = await live_projection_rows(
            model_name=ACTIVE_PORTFOLIO.projections.transfer_model,
            start_gameweek=start_gameweek,
            horizon=3,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    by_id = {
        int(player["element_id"]): player
        for player in projected_players
        if player.get("element_id") is not None
    }
    missing = [player_id for player_id in request.element_ids if player_id not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown player IDs: {missing}")
    picks = []
    for index, player_id in enumerate(request.element_ids):
        price = float(by_id[player_id].get("price") or 0.0)
        picks.append(
            {
                "element": player_id,
                "position": index + 1,
                "purchase_price": int(round(price * 10)),
                "selling_price": int(round(price * 10)),
            }
        )
    squad = squad_frame(picks, projected_players)
    violations = validate_squad(squad, budget=float(squad["price"].sum()) + request.bank)
    if violations:
        raise HTTPException(
            status_code=400,
            detail="The detected squad is not legal: " + "; ".join(violations),
        )

    frames = projection_frames(projected_players)
    current_predictions = frames.get(start_gameweek)
    if current_predictions is None or current_predictions.empty:
        raise HTTPException(status_code=503, detail="Live projections are unavailable.")
    rules = build_season_rules(
        bootstrap,
        season=_season_label_from_bootstrap(bootstrap),
        source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
    )
    chip_state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=(),
    )
    beam = _live_transfer_planner(
        horizon=3,
        free_transfers=request.free_transfers,
        allow_chips=False,
    )
    try:
        action = await asyncio.to_thread(
            beam.decide,
            gameweek=start_gameweek,
            squad=squad,
            bank=request.bank,
            free_transfers=request.free_transfers,
            chip_state=chip_state,
            predictions=current_predictions.copy(),
            future_predictions={
                gameweek: frame.copy()
                for gameweek, frame in frames.items()
                if gameweek > start_gameweek
            },
            rules=rules,
        )
        evidence = _decision_evidence_payload(
            selected_action=action,
            root_actions=beam.last_evidence_actions or beam.last_root_actions,
            squad=squad,
            predictions=current_predictions,
            bank=request.bank,
            free_transfers=request.free_transfers,
            chip_state=chip_state,
            planner=beam,
        )
    except (ValueError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    branches = _optimized_evidence_branches(evidence)
    selected = next((branch for branch in branches if branch.get("selected")), None)
    no_action = next(
        (
            branch
            for branch in branches
            if branch.get("chip") is None and int(branch.get("transfer_count") or 0) == 0
        ),
        None,
    )
    rating = await asyncio.to_thread(
        build_team_rating,
        squad=squad,
        frames=frames,
        bank=request.bank,
        horizon=3,
        current_horizon_points=(
            float(no_action.get("expected_horizon_points") or 0.0) if no_action else None
        ),
        recommended_horizon_points=(
            float(selected.get("expected_horizon_points") or 0.0) if selected else None
        ),
        provisional=True,
    )
    player_rows = [_pool_row(player, player) for player in projected_players]
    payload = {
        "team_id": None,
        "season_state": season_state,
        "start_gameweek": start_gameweek,
        "horizon": 3,
        "rules_version": rules.rules_version,
        "portfolio_version": ACTIVE_PORTFOLIO.version,
        "decision_engine_version": DeterministicBeamPlanner.version,
        "transfer_model": ACTIVE_PORTFOLIO.projections.transfer_model,
        "captain_model": ACTIVE_PORTFOLIO.projections.captain_model,
        "chip_model": None,
        "squad": player_rows,
        "player_pool": player_rows,
        "decision": _decision_payload(action, squad, current_predictions),
        "decision_evidence": evidence,
        "rating": rating,
    }
    response = _decision_center_payload(payload)
    response["provisional"] = True
    response["message"] = (
        "Provisional screenshot analysis. Add your official Team ID for exact selling prices, "
        "transfer history, and automatic weekly refreshes."
    )
    return response


def clear_decision_center_cache() -> None:
    _DECISION_CENTER_CACHE.clear()


def _optimized_evidence_branches(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    branches = list(evidence.get("branches") or [])
    optimized = [
        branch
        for branch in branches
        if branch.get("path_optimized", True)
    ]
    return optimized or branches


def _decision_center_payload(payload: dict[str, Any]) -> dict[str, Any]:
    base = {
        "team_id": payload.get("team_id"),
        "season_state": payload.get("season_state"),
        "gameweek": payload.get("start_gameweek"),
        "horizon": payload.get("horizon"),
        "rules_version": payload.get("rules_version"),
        "data_cutoff": payload.get("data_cutoff"),
        "deadline": payload.get("deadline"),
        "bootstrap_hash": payload.get("bootstrap_hash"),
        "fixtures_hash": payload.get("fixtures_hash"),
        "portfolio_version": payload.get("portfolio_version"),
        "decision_engine_version": payload.get("decision_engine_version"),
        "transfer_model": payload.get("transfer_model"),
        "captain_model": payload.get("captain_model"),
        "chip_model": payload.get("chip_model"),
        "rating": payload.get("rating"),
        "manager_state_confirmation": payload.get("manager_state_confirmation"),
    }
    decision = payload.get("decision")
    evidence = payload.get("decision_evidence") or {}
    branches = _optimized_evidence_branches(evidence)
    if payload.get("season_state") != "in_season" or not decision or not branches:
        return {
            **base,
            "status": "unavailable",
            "message": payload.get("decision_error")
            or payload.get("message")
            or "A complete weekly decision is not available.",
        }

    selected = next((branch for branch in branches if branch.get("selected")), None)
    no_action = next(
        (
            branch
            for branch in branches
            if branch.get("chip") is None and int(branch.get("transfer_count") or 0) == 0
        ),
        None,
    )
    if selected is None or no_action is None:
        return {
            **base,
            "status": "unavailable",
            "message": (
                "The planner did not produce both a selected and no-action branch, "
                "so no recommendation is shown."
            ),
        }

    player_by_id = {
        int(player["element_id"]): player
        for player in [*payload.get("squad", []), *payload.get("player_pool", [])]
        if player.get("element_id") is not None
    }
    gameweek = int(payload.get("start_gameweek") or 1)
    starting_xi = [
        _decision_center_player(player_by_id.get(int(player_id)), gameweek)
        for player_id in selected.get("starting_ids", [])
    ]
    bench = [
        _decision_center_player(player_by_id.get(int(player_id)), gameweek)
        for player_id in selected.get("bench_order", [])
    ]
    starting_xi = [player for player in starting_xi if player is not None]
    bench = [player for player in bench if player is not None]
    current_starting_xi = [
        _decision_center_player(player_by_id.get(int(player_id)), gameweek)
        for player_id in no_action.get("starting_ids", [])
    ]
    current_bench = [
        _decision_center_player(player_by_id.get(int(player_id)), gameweek)
        for player_id in no_action.get("bench_order", [])
    ]
    current_starting_xi = [player for player in current_starting_xi if player is not None]
    current_bench = [player for player in current_bench if player is not None]

    ranked_branches = sorted(
        branches,
        key=lambda branch: float(branch.get("search_score") or 0.0),
        reverse=True,
    )
    runner_up = next(
        (
            branch
            for branch in ranked_branches
            if branch.get("branch_id") != selected.get("branch_id")
        ),
        None,
    )
    search_margin = round(
        float(selected.get("search_score") or 0.0)
        - float((runner_up or {}).get("search_score") or 0.0),
        3,
    )
    uncertainty = float(selected.get("uncertainty_penalty") or 0.0)
    confidence = _decision_confidence(search_margin, uncertainty)
    expected_gameweek_points = float(selected.get("expected_gameweek_points") or 0.0)
    uncertainty_band = max(1.0, uncertainty * 2.0)
    no_action_horizon = float(no_action.get("expected_horizon_points") or 0.0)
    selected_horizon = float(selected.get("expected_horizon_points") or 0.0)
    horizon_gain = round(selected_horizon - no_action_horizon, 3)
    transfer_count = int(selected.get("transfer_count") or 0)
    chip = selected.get("chip")

    return {
        **base,
        "status": "ready",
        "message": "Complete personalized weekly decision from one legal planner state.",
        "state_before": {
            "bank": evidence.get("state_before", {}).get("bank"),
            "free_transfers": evidence.get("state_before", {}).get("free_transfers"),
            "remaining_chips": evidence.get("state_before", {}).get("remaining_chips", []),
            "used_chips": evidence.get("state_before", {}).get("used_chips", []),
        },
        "current_lineup": {
            "starting_xi": current_starting_xi,
            "bench_order": current_bench,
            "captain_id": no_action.get("captain_id"),
            "vice_captain_id": no_action.get("vice_captain_id"),
        },
        "recommendation": {
            "transfer_action": (
                "roll"
                if transfer_count == 0
                else f"make_{transfer_count}_transfer" + ("s" if transfer_count != 1 else "")
            ),
            "transfers": selected.get("transfers", []),
            "transfer_count": transfer_count,
            "hit_recommended": int(selected.get("hit_cost") or 0) > 0,
            "hit_cost": int(selected.get("hit_cost") or 0),
            "bank_before": selected.get("bank_before"),
            "bank_after": selected.get("bank_after"),
            "free_transfers_after": selected.get("free_transfers_after_decision"),
            "funds_released": selected.get("funds_released", 0.0),
            "funds_spent": selected.get("funds_spent", 0.0),
            "funding_explanation": selected.get("funding_explanation"),
            "future_plan": selected.get("path", [])[1:],
            "chip_action": chip or "save",
            "chip_key": selected.get("chip_key"),
            "starting_xi": starting_xi,
            "bench_order": bench,
            "captain_id": selected.get("captain_id"),
            "vice_captain_id": selected.get("vice_captain_id"),
            "expected_gameweek_points": round(expected_gameweek_points, 3),
            "expected_horizon_points": round(selected_horizon, 3),
            "gain_vs_no_action": horizon_gain,
            "future_opportunity_cost": selected.get("future_opportunity_cost"),
            "uncertainty_penalty": round(uncertainty, 3),
            "downside_range": {
                "low": round(expected_gameweek_points - uncertainty_band, 2),
                "high": round(expected_gameweek_points + uncertainty_band, 2),
                "method": "expected points plus/minus planner uncertainty adjustment",
            },
            "confidence": confidence,
            "confidence_basis": {
                "search_score_margin": search_margin,
                "uncertainty_penalty": round(uncertainty, 3),
            },
            "reason": selected.get("reason"),
        },
        "no_action": {
            "expected_gameweek_points": no_action.get("expected_gameweek_points"),
            "expected_horizon_points": no_action.get("expected_horizon_points"),
            "starting_ids": no_action.get("starting_ids", []),
            "captain_id": no_action.get("captain_id"),
            "vice_captain_id": no_action.get("vice_captain_id"),
            "reason": no_action.get("reason"),
        },
        "alternatives": [
            {
                "branch_id": branch.get("branch_id"),
                "chip": branch.get("chip") or "save",
                "transfers": branch.get("transfers", []),
                "hit_cost": branch.get("hit_cost"),
                "expected_gameweek_points": branch.get("expected_gameweek_points"),
                "expected_horizon_points": branch.get("expected_horizon_points"),
                "gain_vs_no_action": round(
                    float(branch.get("expected_horizon_points") or 0.0) - no_action_horizon,
                    3,
                ),
                "reason": branch.get("reason"),
            }
            for branch in ranked_branches
            if branch.get("branch_id") != selected.get("branch_id")
        ][:5],
    }


def _decision_center_player(
    player: dict[str, Any] | None,
    gameweek: int,
) -> dict[str, Any] | None:
    if player is None:
        return None
    projection = _projection_for_gameweek(player, gameweek)
    return {
        "element_id": player.get("element_id"),
        "name": player.get("name"),
        "web_name": player.get("web_name"),
        "team": player.get("team"),
        "team_code": player.get("team_code"),
        "position": player.get("position"),
        "price": player.get("price"),
        "expected_points": projection.get("projected_points", 0.0),
        "start_likelihood": player.get("start_likelihood"),
        "blank": projection.get("blank", False),
        "double": projection.get("double", False),
    }


def _decision_confidence(search_margin: float, uncertainty_penalty: float) -> str:
    if search_margin >= 2.0 and uncertainty_penalty <= 0.5:
        return "high"
    if search_margin >= 0.5 and uncertainty_penalty <= 1.5:
        return "medium"
    return "low"


def _decision_payload(action, squad, predictions) -> dict[str, Any]:
    """Convert a beam action into an API-safe complete decision summary."""

    active_squad = squad.copy()
    if action.chip is None or action.chip.name not in {"wildcard", "freehit"}:
        active_squad = apply_transfer_plan(
            active_squad,
            predictions,
            action.transfer_plan,
        )
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
            "hit_cost": action.transfer_plan.hit_cost,
            "hit_selected": action.transfer_plan.hit_cost > 0,
        },
        "transfers": [
            {
                "outgoing_id": move.outgoing_id,
                "outgoing_name": move.outgoing_name,
                "incoming_id": move.incoming_id,
                "incoming_name": move.incoming_name,
                "projected_gain": round(move.projected_gain, 3),
                "hit_cost": move.hit_cost,
                "outgoing_price": move.outgoing_price,
                "incoming_price": move.incoming_price,
                "bank_effect": round(
                    float(move.outgoing_price or 0.0)
                    - float(move.incoming_price or 0.0),
                    1,
                ),
            }
            for move in action.transfers
        ],
        "transfer_count": action.transfer_plan.count,
        "total_hit_cost": action.transfer_plan.hit_cost,
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
        "discounted_horizon_points": round(action.discounted_horizon_points, 3),
        "total_path_hit_cost": int(action.total_hit_cost),
        "path": _path_payload(action.path),
        "reason": action.reason,
    }


def _decision_evidence_payload(
    *,
    selected_action,
    root_actions,
    squad,
    predictions,
    bank: float,
    free_transfers: int,
    chip_state,
    planner: DeterministicBeamPlanner,
) -> dict[str, Any]:
    """Serialize the generated root action space without influencing selection."""

    selected_signature = _action_signature(selected_action)
    actions = [action for action in root_actions if _action_signature(action) != selected_signature]
    actions.append(selected_action)
    actions.sort(
        key=lambda action: (
            -round(float(action.search_score), 8),
            _action_signature(action),
        )
    )
    optimized_signatures = {
        _action_signature(action) for action in planner.last_path_actions
    }
    branches = [
        _branch_evidence_payload(
            action,
            squad,
            predictions,
            bank=bank,
            free_transfers=free_transfers,
            selected=_action_signature(action) == selected_signature,
            path_optimized=_action_signature(action) in optimized_signatures,
            raw_rank=index,
        )
        for index, action in enumerate(actions, start=1)
    ]
    return {
        "schema_version": "live-planner-root-actions-v1",
        "planner": planner.name,
        "planner_version": planner.version,
        "planner_config": {
            "beam_width": planner.beam_width,
            "horizon": planner.horizon,
            "max_transfers": planner.max_transfers,
            "max_same_gameweek_transfers": planner.max_same_gameweek_transfers,
            "hit_policy": planner.hit_policy,
            "allow_chips": planner.allow_chips,
            "minimum_transfer_horizon_gain": planner.minimum_transfer_horizon_gain,
        },
        "candidate_set_complete": True,
        "candidate_scope": (
            "every generated legal root action; surviving paths include optimized future steps"
        ),
        "candidate_count": len(branches),
        "path_optimized_count": sum(
            bool(branch.get("path_optimized")) for branch in branches
        ),
        "selected_branch_id": next(
            branch["branch_id"] for branch in branches if branch["selected"]
        ),
        "state_before": {
            "squad_hash": _squad_hash(squad),
            "bank": round(float(bank), 1),
            "free_transfers": int(free_transfers),
            "remaining_chips": list(chip_state.remaining),
            "used_chips": list(chip_state.used),
            "used_chip_gameweeks": [list(value) for value in chip_state.used_gameweeks],
        },
        "branches": branches,
    }


def _branch_evidence_payload(
    action,
    squad,
    predictions,
    *,
    bank: float,
    free_transfers: int,
    selected: bool,
    path_optimized: bool,
    raw_rank: int,
) -> dict[str, Any]:
    chip_name = action.chip.name if action.chip is not None else None
    if chip_name in {"wildcard", "freehit"} and action.chip_squad is not None:
        active_squad = action.chip_squad.copy()
    else:
        active_squad = apply_transfer_plan(squad.copy(), predictions, action.transfer_plan)
    retained_squad = squad if chip_name == "freehit" else active_squad
    projection = _projection_map(predictions)
    lineup = _fast_lineup(active_squad, projection)
    captain_id, vice_captain_id = _captain_ids(lineup.starting_ids, projection)
    transfer_count = action.transfer_plan.count if chip_name not in {"wildcard", "freehit"} else 0
    bank_after = (
        round(float(action.transfer_plan.bank_after), 1)
        if action.transfer_plan.bank_after is not None
        else round(float(bank), 1)
    )
    if chip_name == "wildcard":
        budget = float(bank) + float(squad["price"].sum())
        bank_after = round(budget - float(active_squad["price"].sum()), 1)
    elif chip_name == "freehit":
        bank_after = round(float(bank), 1)
    free_transfers_after = (
        int(free_transfers)
        if chip_name in {"wildcard", "freehit"}
        else max(0, int(free_transfers) - transfer_count)
    )
    branch_core = {
        "chip_key": action.chip.key if action.chip is not None else "none",
        "transfers": [
            [int(move.outgoing_id), int(move.incoming_id)]
            for move in action.transfers
            if move.outgoing_id is not None and move.incoming_id is not None
        ],
        "active_squad_ids": sorted(int(value) for value in active_squad["player_id"]),
    }
    finance = _transfer_finance(action.transfer_plan)
    branch_id = hashlib.sha256(
        json.dumps(branch_core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:20]
    squad_rows = []
    for row in active_squad.to_dict(orient="records"):
        squad_rows.append(
            {
                "player_id": int(row["player_id"]),
                "position": str(row.get("position") or row.get("position_group") or ""),
                "team": row.get("team"),
                "price": round(float(row.get("price") or 0.0), 1),
                "start_probability": _optional_float(
                    row.get("probability_60_plus_minutes", row.get("start_likelihood"))
                ),
                "status": row.get("status"),
                "chance_of_playing_next_round": _optional_float(
                    row.get("chance_of_playing_next_round")
                ),
                "news": row.get("news"),
                "penalties_order": row.get("penalties_order"),
                "direct_freekicks_order": row.get("direct_freekicks_order"),
                "corners_and_indirect_freekicks_order": row.get(
                    "corners_and_indirect_freekicks_order"
                ),
            }
        )
    return {
        "branch_id": branch_id,
        "raw_rank": raw_rank,
        "selected": selected,
        "path_optimized": path_optimized,
        "chip": chip_name,
        "chip_key": branch_core["chip_key"],
        "ordinary_transfer_allowed": chip_name not in {"wildcard", "freehit"},
        "ordinary_transfer_applied": transfer_count > 0,
        "transfers": [
            {
                "outgoing_id": move.outgoing_id,
                "outgoing_name": move.outgoing_name,
                "incoming_id": move.incoming_id,
                "incoming_name": move.incoming_name,
                "projected_gain": round(float(move.projected_gain), 3),
                "hit_cost": int(move.hit_cost),
                "outgoing_price": move.outgoing_price,
                "incoming_price": move.incoming_price,
                "bank_effect": round(
                    float(move.outgoing_price or 0.0)
                    - float(move.incoming_price or 0.0),
                    1,
                ),
            }
            for move in action.transfers
        ],
        "transfer_count": transfer_count,
        "hit_cost": (
            0 if chip_name in {"wildcard", "freehit"} else int(action.transfer_plan.hit_cost)
        ),
        "squad": sorted(squad_rows, key=lambda row: row["player_id"]),
        "squad_before_hash": _squad_hash(squad),
        "squad_after_hash": _squad_hash(active_squad),
        "post_gameweek_squad_hash": _squad_hash(retained_squad),
        "starting_ids": list(lineup.starting_ids),
        "bench_order": list(lineup.bench_ids),
        "captain_id": captain_id,
        "vice_captain_id": vice_captain_id,
        "bank_before": round(float(bank), 1),
        "bank_after": bank_after,
        "funds_released": finance["funds_released"],
        "funds_spent": finance["funds_spent"],
        "funding_explanation": finance["funding_explanation"],
        "free_transfers_before": int(free_transfers),
        "free_transfers_after_decision": free_transfers_after,
        "expected_gameweek_points": round(float(action.expected_points), 3),
        "expected_horizon_points": round(float(action.expected_horizon_points), 3),
        "no_chip_horizon_points": round(float(action.no_chip_horizon_points), 3),
        "expected_horizon_gain": round(
            float(action.expected_horizon_points - action.no_chip_horizon_points), 3
        ),
        "transfer_expected_horizon_gain": round(float(action.transfer_expected_horizon_gain), 3),
        "transfer_expected_horizon_net_gain": round(
            float(action.transfer_expected_horizon_net_gain), 3
        ),
        "future_opportunity_cost": round(float(action.future_opportunity_cost), 3),
        "uncertainty_penalty": round(float(action.uncertainty_penalty), 3),
        "discounted_horizon_points": round(
            float(action.discounted_horizon_points), 3
        ),
        "total_path_hit_cost": int(action.total_hit_cost),
        "path": _path_payload(action.path),
        "search_score": round(float(action.search_score), 6),
        "reason": action.reason,
    }


def _transfer_finance(transfer_plan) -> dict[str, Any]:
    """Explain the cash flow of a linked transfer package in plain language."""

    releases: list[tuple[str, float]] = []
    upgrades: list[tuple[str, float]] = []
    for move in transfer_plan.moves:
        difference = round(
            float(move.outgoing_price or 0.0) - float(move.incoming_price or 0.0),
            1,
        )
        label = f"{move.outgoing_name} to {move.incoming_name}"
        if difference > 0:
            releases.append((label, difference))
        elif difference < 0:
            upgrades.append((label, abs(difference)))

    funds_released = round(sum(value for _, value in releases), 1)
    funds_spent = round(sum(value for _, value in upgrades), 1)
    explanation = None
    if releases and upgrades:
        release_names = ", ".join(label for label, _ in releases)
        upgrade_names = ", ".join(label for label, _ in upgrades)
        explanation = (
            f"{release_names} releases £{funds_released:.1f}m, helping fund "
            f"{upgrade_names}."
        )
    elif releases:
        explanation = (
            f"This package releases £{funds_released:.1f}m for later upgrades."
        )
    elif upgrades:
        explanation = f"This package uses £{funds_spent:.1f}m from the bank."

    return {
        "funds_released": funds_released,
        "funds_spent": funds_spent,
        "funding_explanation": explanation,
    }


def _path_payload(path) -> list[dict[str, Any]]:
    """Serialize the rolling plan while keeping future actions non-binding."""

    output: list[dict[str, Any]] = []
    for step in path:
        finance = _transfer_finance(step.transfer_plan)
        output.append(
            {
                "gameweek": int(step.gameweek),
                "transfers": [
                    {
                        "outgoing_id": move.outgoing_id,
                        "outgoing_name": move.outgoing_name,
                        "incoming_id": move.incoming_id,
                        "incoming_name": move.incoming_name,
                        "outgoing_price": move.outgoing_price,
                        "incoming_price": move.incoming_price,
                        "bank_effect": round(
                            float(move.outgoing_price or 0.0)
                            - float(move.incoming_price or 0.0),
                            1,
                        ),
                    }
                    for move in step.transfer_plan.moves
                ],
                "transfer_count": int(step.transfer_plan.count),
                "hit_cost": int(step.transfer_plan.hit_cost),
                "expected_points": round(float(step.expected_points), 3),
                "net_expected_points": round(
                    float(step.expected_points) - int(step.transfer_plan.hit_cost),
                    3,
                ),
                "bank_before": round(float(step.bank_before), 1),
                "bank_after": round(float(step.bank_after), 1),
                "free_transfers_before": int(step.free_transfers_before),
                "free_transfers_after": int(step.free_transfers_after),
                **finance,
            }
        )
    return output


def _squad_hash(squad) -> str:
    values = sorted(int(value) for value in squad["player_id"])
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def _action_signature(action) -> str:
    payload = {
        "chip": action.chip.key if action.chip is not None else "none",
        "transfers": [
            [int(move.outgoing_id or 0), int(move.incoming_id or 0)] for move in action.transfers
        ],
        "chip_squad": (
            sorted(int(value) for value in action.chip_squad["player_id"])
            if action.chip_squad is not None
            else []
        ),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _optional_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if numeric != numeric else round(numeric, 4)


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
                "purchase_price": live_pick_price(pick.get("purchase_price")),
                "current_price": player.get("price"),
                "selling_price": live_pick_price(pick.get("selling_price")),
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
        "availability_probability": player.get("availability_probability"),
        "status": player.get("status"),
        "chance_of_playing_next_round": player.get("chance_of_playing_next_round"),
        "news": player.get("news"),
        "penalties_order": player.get("penalties_order"),
        "direct_freekicks_order": player.get("direct_freekicks_order"),
        "corners_and_indirect_freekicks_order": player.get("corners_and_indirect_freekicks_order"),
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
