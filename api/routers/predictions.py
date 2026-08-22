import asyncio
import json
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query

from api import data_service, fpl_client
from api.live_projection_service import live_projection_rows
from api.projection_contract import (
    PROJECTION_CONTRACT_VERSION,
    ProjectionRecord,
    TransferProjectionRecord,
)
from api.readiness import require_current_artifacts
from api.routers import backtest as backtest_router
from api.routers.fixtures import ticker
from fpl_intelligence.backtest_transfer_strategy import select_starting_xi
from fpl_intelligence.initial_squad_championship import (
    GW1_DECISION_PROFILES,
    P3_CONFIGS,
    P3_OPTIMIZER_VERSION,
    build_live_opening_projection_bundle,
    optimize_opening_squad,
)
from fpl_intelligence.p10_calibration import (
    P10_DECISION_ENGINE_VERSION,
    P10_OUTPUT,
)
from fpl_intelligence.p11_deadline_finalization import P11_OUTPUT
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.simulate_seasons import (
    PRODUCTION_INITIAL_SQUAD_POLICY,
    PRODUCTION_INITIAL_SQUAD_VERSION,
)

router = APIRouter(
    prefix="/api/predictions",
    tags=["predictions"],
    dependencies=[Depends(require_current_artifacts)],
)

ACTIVE_PORTFOLIO = get_production_portfolio()
BEST_MODEL = ACTIVE_PORTFOLIO.projections.transfer_model
CAPTAINCY_MODEL = ACTIVE_PORTFOLIO.projections.captain_model


def _gameweek_projection(player: dict[str, Any], gameweek: int) -> dict[str, Any]:
    return next(
        (
            row
            for row in player.get("projections", [])
            if int(row.get("gameweek", -1)) == gameweek
        ),
        {
            "gameweek": gameweek,
            "projected_points": 0.0,
            "fixtures": [],
            "blank": True,
            "double": False,
        },
    )


def _set_piece_record(player: dict[str, Any]) -> dict[str, Any] | None:
    for gameweek in player.get("projections", []):
        for fixture in gameweek.get("fixtures", []):
            adjustment = fixture.get("set_piece_adjustment")
            if adjustment:
                roles = adjustment.get("roles", {})
                return {
                    "model_version": adjustment.get("model_version"),
                    "source_url": adjustment.get("source_url"),
                    "available": adjustment.get("available", False),
                    "reason": adjustment.get("reason"),
                    "transition_adjustment_per_start": adjustment.get(
                        "total_adjustment", 0.0
                    ),
                    "penalties_rank": roles.get("penalties", {}).get(
                        "current_rank"
                    ),
                    "direct_free_kicks_rank": roles.get(
                        "direct_free_kicks", {}
                    ).get("current_rank"),
                    "corners_indirect_rank": roles.get(
                        "corners_indirect_free_kicks", {}
                    ).get("current_rank"),
                }
    return None


def _prediction_record(
    player: dict[str, Any],
    gameweek: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    projection = _gameweek_projection(player, gameweek)
    raw_points = sum(
        float(fixture.get("predicted_points", 0.0))
        for fixture in projection.get("fixtures", [])
    )
    start_likelihood = max(
        (
            float(fixture.get("start_likelihood", 0.0))
            for fixture in projection.get("fixtures", [])
        ),
        default=float(player.get("start_likelihood", 0.0) or 0.0),
    )
    return {
        "element_id": player.get("element_id"),
        "name": player.get("name"),
        "team": player.get("team"),
        "position": player.get("position"),
        "price": player.get("price"),
        "raw_xp": round(raw_points, 3),
        "expected_points": round(float(projection.get("projected_points", 0.0)), 3),
        "start_adjusted_xp": round(float(projection.get("projected_points", 0.0)), 3),
        "captain_expected_points": round(
            2.0 * float(projection.get("projected_points", 0.0)), 3
        ),
        "captaincy_score": round(float(projection.get("projected_points", 0.0)), 3),
        "start_likelihood": round(start_likelihood, 4),
        "blank": bool(projection.get("blank")),
        "double": bool(projection.get("double")),
        "gameweek": gameweek,
        "season": metadata["season"],
        "bootstrap_hash": metadata["bootstrap_hash"],
        "rules_version": metadata["rules_version"],
        "data_cutoff": metadata["data_cutoff"],
        "model": metadata["model"],
        "portfolio_version": ACTIVE_PORTFOLIO.version,
        "projection_contract_version": PROJECTION_CONTRACT_VERSION,
    }


@router.get("/captaincy", response_model=list[ProjectionRecord])
async def captaincy(
    gw: int | None = Query(default=None, ge=1, le=38),
    limit: int = Query(default=50, ge=1, le=250),
) -> list[dict[str, Any]]:
    players, metadata = await live_projection_rows(
        model_name=CAPTAINCY_MODEL,
        start_gameweek=gw,
        horizon=3,
    )
    gameweek = int(gw or metadata["start_gameweek"])
    records = [
        _prediction_record(player, gameweek, metadata)
        for player in players
    ]
    return sorted(
        records,
        key=lambda row: (row["captaincy_score"], row["start_likelihood"]),
        reverse=True,
    )[:limit]


def _transfer_records(
    projected: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    gameweek = int(metadata["start_gameweek"])
    projections = {
        int(player["element_id"]): _prediction_record(player, gameweek, metadata)
        for player in projected
        if player.get("element_id") is not None
    }
    ranked = data_service.players()
    if ranked.empty:
        return []
    ranked["element_id"] = pd.to_numeric(ranked["element_id"], errors="coerce")
    ranked["transfer_score"] = pd.to_numeric(
        ranked["transfer_score"], errors="coerce"
    ).fillna(0.0)
    output: list[dict[str, Any]] = []
    for row in ranked.sort_values("transfer_score", ascending=False).to_dict(
        orient="records"
    ):
        if pd.isna(row.get("element_id")):
            continue
        prediction = projections.get(int(row["element_id"]))
        if prediction is None:
            continue
        output.append(
            {
                **prediction,
                "transfer_rank_score": round(float(row.get("transfer_score", 0.0)), 4),
                "prior_source": row.get("prior_source"),
            }
        )
        if len(output) == limit:
            break
    return output


def _overview_gems(ranked: pd.DataFrame, *, limit: int = 3) -> list[dict[str, Any]]:
    if ranked.empty:
        return []
    differential_rows = ranked[ranked["selected_by_percent"] < 15]
    differential_rows = differential_rows.sort_values(
        "captain_score", ascending=False
    ).head(limit)
    output = []
    for row in differential_rows.to_dict(orient="records"):
        output.append(
            {
                "element_id": row.get("element_id"),
                "name": row.get("player_name"),
                "web_name": row.get("web_name"),
                "team": row.get("team_name"),
                "team_code": row.get("team_code"),
                "position": row.get("position"),
                "price": row.get("price"),
                "total_points": row.get("total_points", 0),
                "ppg": row.get("points_per_game", 0.0),
                "form": row.get("form", 0.0),
                "start_likelihood": row.get("minutes_security", 0.0),
                "value": row.get("value_score", 0.0),
                "captain_rank_score": row.get("captain_score", 0.0),
                "transfer_rank_score": row.get("transfer_score", 0.0),
                "selected_by_percent": row.get("selected_by_percent", 0.0),
                "defensive_contribution": row.get("defensive_contribution", 0.0),
                "defensive_contribution_per_90": row.get(
                    "defensive_contribution_per_90", 0.0
                ),
                "safety_tier": row.get("safety_tier", ""),
            }
        )
    return output


@router.get("/transfers", response_model=list[TransferProjectionRecord])
async def transfers(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    projected, metadata = await live_projection_rows(
        model_name=BEST_MODEL,
        horizon=3,
    )
    return _transfer_records(projected, metadata, limit=limit)


@router.get("/overview")
async def overview() -> dict[str, Any]:
    """Return only the decision data required by the overview page."""
    projection_task = live_projection_rows(
        model_name=CAPTAINCY_MODEL,
        horizon=3,
    )
    fixture_task = ticker(range=5)
    (captain_projected, captain_metadata), fixture_rows = await asyncio.gather(
        projection_task,
        fixture_task,
    )
    if BEST_MODEL == CAPTAINCY_MODEL:
        transfer_projected = captain_projected
        transfer_metadata = captain_metadata
    else:
        transfer_projected, transfer_metadata = await live_projection_rows(
            model_name=BEST_MODEL,
            horizon=3,
        )

    gameweek = int(captain_metadata["start_gameweek"])
    projections = sorted(
        (
            _prediction_record(player, gameweek, captain_metadata)
            for player in captain_projected
        ),
        key=lambda row: (row["captaincy_score"], row["start_likelihood"]),
        reverse=True,
    )[:40]
    ranked = data_service.players()

    return {
        "player_count": len(captain_projected),
        "predictions": projections,
        "captains": projections[:10],
        "transfers": _transfer_records(
            transfer_projected,
            transfer_metadata,
            limit=20,
        ),
        "fixtures": fixture_rows,
        "gems": _overview_gems(ranked),
        "accuracy": backtest_router.accuracy(),
        "projection_contract_version": PROJECTION_CONTRACT_VERSION,
        "data_cutoff": captain_metadata["data_cutoff"],
    }


@router.get("/initial-squad")
async def initial_squad(
    horizon: int = Query(default=8, ge=3, le=8),
    risk_profile: str = Query(
        default="balanced",
        pattern="^(maximum_points|balanced|safe)$",
    ),
) -> dict[str, Any]:
    if horizon not in {3, 5, 8}:
        horizon = 8
    projected, metadata = await live_projection_rows(
        model_name=BEST_MODEL,
        start_gameweek=1,
        horizon=horizon,
    )
    projection_by_id: dict[int, dict[str, Any]] = {}
    for player in projected:
        player_id = int(player["element_id"])
        projection_by_id[player_id] = player

    policy_name = f"horizon_{horizon}_" + {
        3: "attack",
        5: "balanced",
        8: "flexible",
    }[horizon]
    bundle = build_live_opening_projection_bundle(projected, metadata)
    if horizon == 8:
        profile_candidates = {
            profile: optimize_opening_squad(bundle, config)
            for profile, config in GW1_DECISION_PROFILES.items()
        }
        candidate = profile_candidates[risk_profile]
    else:
        profile_candidates = {
            risk_profile: optimize_opening_squad(bundle, P3_CONFIGS[policy_name])
        }
        candidate = profile_candidates[risk_profile]
    squad = candidate.squad
    gw1_projection = (
        bundle.projections[1].set_index("player_id")["projected_points"].to_dict()
    )
    horizon_projection = {
        int(player_id): sum(
            float(
                frame.set_index("player_id")["projected_points"].to_dict().get(
                    player_id,
                    0.0,
                )
            )
            for gameweek, frame in bundle.projections.items()
            if gameweek <= horizon
        )
        for player_id in squad["player_id"]
    }
    lineup = select_starting_xi(squad, gw1_projection)
    starting = set(lineup.starting_ids)
    ordered_ids = [*lineup.starting_ids, *lineup.bench_ids]
    squad_by_id = squad.set_index("player_id").to_dict(orient="index")
    set_piece_by_id = {
        int(player_id): _set_piece_record(projection_by_id[int(player_id)])
        for player_id in squad["player_id"]
    }
    robustness = None
    deadline_finalization = None
    stability_by_id: dict[int, dict[str, Any]] = {}
    if P10_OUTPUT.exists():
        report = json.loads(P10_OUTPUT.read_text(encoding="utf-8"))
        report_metadata = report.get("metadata", {})
        report_contract = report_metadata.get("bootstrap_contract_hash")
        live_contract = metadata.get("bootstrap_contract_hash")
        hashes_match = (
            report_contract == live_contract
            if report_contract is not None and live_contract is not None
            else report_metadata.get("bootstrap_hash") == metadata.get("bootstrap_hash")
        )
        if hashes_match:
            robustness = report.get("robustness")
            stability_by_id = {
                int(row["player_id"]): row
                for row in robustness.get("player_stability", [])
            }
    if P11_OUTPUT.exists():
        p11_report = json.loads(P11_OUTPUT.read_text(encoding="utf-8"))
        p11_contract = p11_report.get("bootstrap_contract_hash")
        live_contract = metadata.get("bootstrap_contract_hash")
        hashes_match = (
            p11_contract == live_contract
            if p11_contract is not None and live_contract is not None
            else p11_report.get("bootstrap_hash") == metadata.get("bootstrap_hash")
        )
        if hashes_match:
            gate = p11_report["gate"]
            challenger = next(
                (
                    row
                    for row in p11_report.get("squad_variants", [])
                    if not row.get("is_central")
                ),
                None,
            )
            deadline_finalization = {
                "status": gate["status"],
                "data_ready": gate["data_ready"],
                "lock_ready": gate["lock_ready"],
                "hours_to_deadline": gate["hours_to_deadline"],
                "final_news_reviewed": gate["final_news_reviewed"],
                "timing_blockers": gate["timing_blockers"],
                "verdict": p11_report["recommendation"]["verdict"],
                "primary_challenger": (
                    {
                        "scenario_rate": challenger["scenario_rate"],
                        "players_out": [
                            row["player_name"] for row in challenger["players_out"]
                        ],
                        "players_in": [
                            row["player_name"] for row in challenger["players_in"]
                        ],
                    }
                    if challenger
                    else None
                ),
            }
    rows = [
        {
            **squad_by_id[player_id],
            "element_id": player_id,
            "gw1_points": round(float(gw1_projection.get(player_id, 0.0)), 3),
            "horizon_points": round(
                float(horizon_projection.get(player_id, 0.0)),
                3,
            ),
            "is_starter": player_id in starting,
            "bench_order": (
                lineup.bench_ids.index(player_id) + 1
                if player_id in lineup.bench_ids
                else None
            ),
            "projections": projection_by_id[player_id].get("projections", []),
            "robustness_class": stability_by_id.get(player_id, {}).get(
                "classification"
            ),
            "scenario_selection_rate": stability_by_id.get(player_id, {}).get(
                "selection_rate"
            ),
            "set_piece": set_piece_by_id.get(player_id),
        }
        for player_id in ordered_ids
    ]
    captain_order = sorted(
        lineup.starting_ids,
        key=lambda player_id: (
            float(gw1_projection.get(player_id, 0.0)),
            float(horizon_projection.get(player_id, 0.0)),
        ),
        reverse=True,
    )
    is_production_policy = horizon == 8 and risk_profile == "balanced"
    policy_label = (
        PRODUCTION_INITIAL_SQUAD_POLICY if is_production_policy else candidate.name
    )
    policy_version = (
        PRODUCTION_INITIAL_SQUAD_VERSION
        if is_production_policy
        else P3_OPTIMIZER_VERSION
    )
    balanced_ids = set(
        profile_candidates.get("balanced", candidate).squad["player_id"].astype(int)
    )
    alternatives = []
    for profile, profile_candidate in profile_candidates.items():
        profile_squad = profile_candidate.squad
        profile_points = bundle.projections[1].set_index("player_id")[
            "projected_points"
        ].to_dict()
        profile_lineup = select_starting_xi(profile_squad, profile_points)
        profile_captains = sorted(
            profile_lineup.starting_ids,
            key=lambda player_id: float(profile_points.get(player_id, 0.0)),
            reverse=True,
        )
        profile_bench = profile_squad[
            ~profile_squad["player_id"].isin(profile_lineup.starting_ids)
            & profile_squad["position_group"].ne("GK")
        ]
        bench_reliability = float(
            profile_bench["start_likelihood"].mean()
            if not profile_bench.empty
            else 0.0
        )
        low_reliability = profile_squad[
            profile_squad["start_likelihood"] < 0.35
        ]
        profile_ids = set(profile_squad["player_id"].astype(int))
        alternatives.append(
            {
                "profile": profile,
                "selected": profile == risk_profile,
                "status": "production_default" if profile == "balanced" else "experimental",
                "cost": round(float(profile_squad["price"].sum()), 1),
                "bank": round(100.0 - float(profile_squad["price"].sum()), 1),
                "expected_gw1_points": round(
                    sum(
                        float(profile_points.get(player_id, 0.0))
                        for player_id in profile_lineup.starting_ids
                    )
                    + float(profile_points.get(profile_captains[0], 0.0)),
                    2,
                ),
                "expected_horizon_points": profile_candidate.projected_metrics.get(
                    f"projected_points_{horizon}"
                ),
                "mean_squad_start_probability": profile_candidate.projected_metrics.get(
                    "mean_start_probability"
                ),
                "outfield_bench_start_probability": round(bench_reliability, 4),
                "low_reliability_players": low_reliability["player_name"].tolist(),
                "squad": [
                    {
                        "player_id": int(row["player_id"]),
                        "position": str(
                            row.get("position") or row.get("position_group") or ""
                        ),
                        "team": row.get("team"),
                        "price": round(float(row.get("price") or 0.0), 1),
                        "start_probability": round(
                            float(row.get("start_likelihood") or 0.0), 4
                        ),
                    }
                    for row in profile_squad.to_dict(orient="records")
                ],
                "starting_ids": list(profile_lineup.starting_ids),
                "bench_order": list(profile_lineup.bench_ids),
                "formation": profile_lineup.formation,
                "captain_id": profile_captains[0],
                "vice_captain_id": profile_captains[1],
                "changes_from_balanced": len(profile_ids.symmetric_difference(balanced_ids)) // 2,
            }
        )
    selected_squad = candidate.squad.set_index("player_id")
    selected_outfield_bench = [
        player_id
        for player_id in lineup.bench_ids
        if str(selected_squad.loc[player_id, "position_group"]) != "GK"
    ]
    first_cover_id = selected_outfield_bench[0] if selected_outfield_bench else None
    low_reliability_starters = [
        str(selected_squad.loc[player_id, "player_name"])
        for player_id in lineup.starting_ids
        if float(selected_squad.loc[player_id, "start_likelihood"]) < 0.65
    ]
    low_reliability_bench = [
        str(selected_squad.loc[player_id, "player_name"])
        for player_id in selected_outfield_bench
        if float(selected_squad.loc[player_id, "start_likelihood"]) < 0.35
    ]
    decision_audit = {
        "availability_clear": not any(
            float(value) <= 0.0
            for value in selected_squad["availability_probability"].fillna(0.5)
        ),
        "low_reliability_starters": low_reliability_starters,
        "low_reliability_bench": low_reliability_bench,
        "captain_start_probability": round(
            float(selected_squad.loc[captain_order[0], "start_likelihood"]), 4
        ),
        "vice_captain_start_probability": round(
            float(selected_squad.loc[captain_order[1], "start_likelihood"]), 4
        ),
        "vice_captain_fallback_points": round(
            float(gw1_projection.get(captain_order[1], 0.0)), 3
        ),
        "first_outfield_cover_id": first_cover_id,
        "first_outfield_cover_points": round(
            float(gw1_projection.get(first_cover_id, 0.0))
            if first_cover_id is not None
            else 0.0,
            3,
        ),
        "first_outfield_cover_start_probability": round(
            float(selected_squad.loc[first_cover_id, "start_likelihood"])
            if first_cover_id is not None
            else 0.0,
            4,
        ),
        "requires_deadline_refresh": True,
        "reason": (
            "Refresh after final pre-season lineups and deadline team news; "
            "late-return and role uncertainty remain point-in-time inputs."
        ),
    }
    return {
        "season": metadata["season"],
        "bootstrap_hash": metadata["bootstrap_hash"],
        "bootstrap_contract_hash": metadata.get("bootstrap_contract_hash"),
        "rules_version": metadata["rules_version"],
        "rules_payload_hash": metadata.get("rules_payload_hash"),
        "data_cutoff": metadata["data_cutoff"],
        "fixtures_hash": metadata.get("fixtures_hash"),
        "deadline": metadata.get("deadline"),
        "model": metadata["model"],
        "portfolio_version": ACTIVE_PORTFOLIO.version,
        "decision_engine_version": P10_DECISION_ENGINE_VERSION,
        "horizon": horizon,
        "risk_profile": risk_profile,
        "decision_alternatives": alternatives,
        "decision_audit": decision_audit,
        "set_piece_summary": {
            "model_version": next(
                (
                    row["model_version"]
                    for row in set_piece_by_id.values()
                    if row and row.get("model_version")
                ),
                None,
            ),
            "source_url": next(
                (
                    row["source_url"]
                    for row in set_piece_by_id.values()
                    if row and row.get("source_url")
                ),
                None,
            ),
            "selected_primary_penalty_takers": [
                squad_by_id[player_id].get("player_name")
                for player_id, row in set_piece_by_id.items()
                if row and row.get("penalties_rank") == 1
            ],
        },
        "deadline_finalization": deadline_finalization,
        "robustness": (
            {
                "scenario_count": robustness["scenario_count"],
                "distinct_squads": robustness["distinct_squads"],
                "robust_squad_rate": robustness["robust_squad_rate"],
                "autosub_activation_probability": P3_CONFIGS[
                    "horizon_8_flexible"
                ].depth_weight,
            }
            if robustness else None
        ),
        "initial_squad_policy": policy_label,
        "initial_squad_policy_version": policy_version,
        "policy_status": "production_default" if is_production_policy else "experimental",
        "budget": 100.0,
        "cost": round(float(squad["price"].sum()), 1),
        "bank": round(100.0 - float(squad["price"].sum()), 1),
        "formation": lineup.formation,
        "captain_id": captain_order[0],
        "vice_captain_id": captain_order[1],
        "expected_gw1_points": round(
            sum(float(gw1_projection[player_id]) for player_id in lineup.starting_ids)
            + float(gw1_projection[captain_order[0]]),
            2,
        ),
        "squad": rows,
        "assumption": (
            "Initial squad uses the reviewed multi-objective opening policy under "
            "official budget, position, and three-per-club constraints."
        ),
    }


@router.get("/draft-workspace")
async def draft_workspace(
    horizon: int = Query(default=8, ge=3, le=8),
    risk_profile: str = Query(
        default="balanced",
        pattern="^(maximum_points|balanced|safe)$",
    ),
) -> dict[str, Any]:
    """Return a compact, Team-ID-independent opening-squad workspace."""
    if horizon not in {3, 5, 8}:
        horizon = 8
    optimized = await initial_squad(horizon=horizon, risk_profile=risk_profile)
    projected, metadata = await live_projection_rows(
        model_name=BEST_MODEL,
        start_gameweek=1,
        horizon=horizon,
    )
    bootstrap = await fpl_client.get_bootstrap()
    settings = bootstrap.get("game_settings", {})
    currency_multiplier = float(settings.get("ui_currency_multiplier") or 10)
    total_spend = settings.get("squad_total_spend")
    budget = (
        float(total_spend) / currency_multiplier
        if total_spend is not None
        else 100.0
    )
    position_counts = {
        str(
            position.get("singular_name_short")
            or position.get("plural_name_short")
            or position.get("singular_name")
        ): int(position.get("squad_select") or 0)
        for position in bootstrap.get("element_types", [])
        if position.get("squad_select") is not None
    }
    player_pool = []
    for player in projected:
        projections = [
            row
            for row in player.get("projections", [])
            if 1 <= int(row.get("gameweek", 0)) <= horizon
        ]
        gw1 = next(
            (row for row in projections if int(row.get("gameweek", 0)) == 1),
            {},
        )
        player_pool.append(
            {
                "element_id": int(player["element_id"]),
                "name": player.get("name"),
                "web_name": player.get("web_name"),
                "team": player.get("team"),
                "team_id": player.get("team_id"),
                "team_code": player.get("team_code"),
                "position": player.get("position"),
                "price": round(float(player.get("price") or 0.0), 1),
                "gw1_points": round(float(gw1.get("projected_points", 0.0)), 3),
                "horizon_points": round(
                    sum(float(row.get("projected_points", 0.0)) for row in projections),
                    3,
                ),
                "start_likelihood": round(
                    float(player.get("start_likelihood") or 0.0), 4
                ),
                "availability_probability": round(
                    float(player.get("availability_probability") or 0.0), 4
                ),
                "status": player.get("status"),
                "prior_source": player.get("prior_source"),
            }
        )

    return {
        "season": metadata["season"],
        "bootstrap_hash": metadata["bootstrap_hash"],
        "fixtures_hash": metadata.get("fixtures_hash"),
        "rules_version": metadata["rules_version"],
        "data_cutoff": metadata["data_cutoff"],
        "model": metadata["model"],
        "horizon": horizon,
        "risk_profile": risk_profile,
        "constraints": {
            "budget": round(budget, 1),
            "squad_size": int(settings.get("squad_squadsize") or 15),
            "starting_xi_size": int(settings.get("squad_squadplay") or 11),
            "max_players_per_team": int(settings.get("squad_team_limit") or 3),
            "position_counts": position_counts
            or {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3},
        },
        "optimized": optimized,
        "player_pool": sorted(
            player_pool,
            key=lambda row: (row["horizon_points"], row["gw1_points"]),
            reverse=True,
        ),
    }
