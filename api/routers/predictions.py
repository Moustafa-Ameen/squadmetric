from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query

from api import data_service
from api.live_projection_service import live_projection_rows
from api.readiness import require_current_artifacts
from fpl_intelligence.backtest_transfer_strategy import select_starting_xi
from fpl_intelligence.initial_squad_championship import (
    P3_CONFIGS,
    P3_OPTIMIZER_VERSION,
    build_live_opening_projection_bundle,
    optimize_opening_squad,
)
from fpl_intelligence.production_portfolio import get_production_portfolio

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
        "predicted_pts": round(raw_points, 3),
        "adjusted_pts": round(float(projection.get("projected_points", 0.0)), 3),
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
    }


@router.get("/captaincy")
async def captaincy(
    gw: int | None = Query(default=None, ge=1, le=38),
    limit: int = Query(default=1000, ge=1, le=1000),
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
        key=lambda row: (row["adjusted_pts"], row["start_likelihood"]),
        reverse=True,
    )[:limit]


@router.get("/transfers")
async def transfers() -> list[dict[str, Any]]:
    projected, metadata = await live_projection_rows(
        model_name=BEST_MODEL,
        horizon=3,
    )
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
                "transfer_score": round(float(row.get("transfer_score", 0.0)), 4),
                "prior_source": row.get("prior_source"),
            }
        )
        if len(output) == 20:
            break
    return output


@router.get("/initial-squad")
async def initial_squad(
    horizon: int = Query(default=8, ge=3, le=8),
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
    candidate = optimize_opening_squad(bundle, P3_CONFIGS[policy_name])
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
    return {
        "season": metadata["season"],
        "bootstrap_hash": metadata["bootstrap_hash"],
        "rules_version": metadata["rules_version"],
        "data_cutoff": metadata["data_cutoff"],
        "model": metadata["model"],
        "portfolio_version": ACTIVE_PORTFOLIO.version,
        "horizon": horizon,
        "initial_squad_policy": policy_name,
        "initial_squad_policy_version": P3_OPTIMIZER_VERSION,
        "policy_status": (
            "validated" if policy_name == "horizon_8_flexible" else "experimental"
        ),
        "budget": 100.0,
        "cost": round(float(squad["price"].sum()), 1),
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
