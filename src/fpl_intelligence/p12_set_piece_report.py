"""P12 live set-piece role and transition audit report."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fpl_intelligence.p11_deadline_finalization import P11_OUTPUT
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.set_piece_intelligence import (
    CATEGORY_FIELDS,
    CORNER_INDIRECT_POINTS_POOL,
    DIRECT_FREE_KICK_POINTS_POOL,
    PENALTY_CONVERSION_RATE,
    PENALTY_EVENT_RATE_PER_TEAM_FIXTURE,
    SET_PIECE_MODEL_VERSION,
    SET_PIECE_SOURCE,
    previous_bootstrap_audit,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
P12_OUTPUT = PROJECT_ROOT / "data/processed/p12_set_piece_report.json"
P12_SCHEMA_VERSION = "p12-set-piece-audit-v1"


def _first_adjustment(player: dict[str, Any]) -> dict[str, Any] | None:
    for gameweek in player.get("projections", []):
        for fixture in gameweek.get("fixtures", []):
            adjustment = fixture.get("set_piece_adjustment")
            if adjustment:
                return adjustment
    return None


def build_set_piece_report(
    players: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    selected_ids: set[int] | None = None,
) -> dict[str, Any]:
    selected = selected_ids or set()
    rows = []
    primary_penalty_takers = []
    category_coverage = {category: 0 for category in CATEGORY_FIELDS}
    unavailable_prior = 0
    for player in players:
        adjustment = _first_adjustment(player)
        if adjustment is None:
            continue
        roles = adjustment.get("roles", {})
        for category in CATEGORY_FIELDS:
            if roles.get(category, {}).get("current_rank") is not None:
                category_coverage[category] += 1
        if adjustment.get("reason") == "promoted_team_prior_unavailable":
            unavailable_prior += 1
        player_id = int(player["element_id"])
        row = {
            "player_id": player_id,
            "player_name": player.get("name") or player.get("web_name"),
            "web_name": player.get("web_name"),
            "team": player.get("team"),
            "position": player.get("position"),
            "selected": player_id in selected,
            "available": adjustment.get("available", False),
            "reason": adjustment.get("reason"),
            "penalty_adjustment": adjustment.get("penalty_adjustment", 0.0),
            "direct_free_kick_adjustment": adjustment.get(
                "direct_free_kick_adjustment", 0.0
            ),
            "corner_adjustment": adjustment.get("corner_adjustment", 0.0),
            "total_adjustment_per_start": adjustment.get("total_adjustment", 0.0),
            "roles": roles,
        }
        rows.append(row)
        penalty = roles.get("penalties", {})
        if penalty.get("current_rank") == 1:
            primary_penalty_takers.append(
                {
                    "player_id": player_id,
                    "player_name": row["player_name"],
                    "team": row["team"],
                    "role_share": penalty.get("current_share"),
                    "selected": row["selected"],
                }
            )
    rows.sort(
        key=lambda row: (
            -abs(float(row["total_adjustment_per_start"])),
            str(row["player_name"]),
        )
    )
    return {
        "schema_version": P12_SCHEMA_VERSION,
        "model_version": SET_PIECE_MODEL_VERSION,
        "season": metadata.get("season"),
        "bootstrap_hash": metadata.get("bootstrap_hash"),
        "bootstrap_contract_hash": metadata.get("bootstrap_contract_hash"),
        "rules_version": metadata.get("rules_version"),
        "data_cutoff": metadata.get("data_cutoff"),
        "source_url": SET_PIECE_SOURCE,
        "method": (
            "Official current role share minus official 2025/26 role share; "
            "the minutes probability is applied once by the fixture projection."
        ),
        "previous_role_source": previous_bootstrap_audit(),
        "assumptions": {
            "penalty_events_per_team_fixture": PENALTY_EVENT_RATE_PER_TEAM_FIXTURE,
            "penalty_conversion_rate": PENALTY_CONVERSION_RATE,
            "direct_free_kick_points_pool": DIRECT_FREE_KICK_POINTS_POOL,
            "corner_indirect_points_pool": CORNER_INDIRECT_POINTS_POOL,
        },
        "category_coverage": category_coverage,
        "players_without_promoted_team_prior": unavailable_prior,
        "primary_penalty_takers": sorted(
            primary_penalty_takers, key=lambda row: str(row["team"])
        ),
        "selected_player_roles": [row for row in rows if row["selected"]],
        "largest_role_transitions": rows[:30],
    }


async def _run_live() -> dict[str, Any]:
    from api.live_projection_service import live_projection_rows

    portfolio = get_production_portfolio()
    players, metadata = await live_projection_rows(
        model_name=portfolio.projections.transfer_model,
        start_gameweek=1,
        horizon=3,
    )
    selected_ids: set[int] = set()
    if P11_OUTPUT.exists():
        p11 = json.loads(P11_OUTPUT.read_text(encoding="utf-8"))
        p11_contract = p11.get("bootstrap_contract_hash")
        live_contract = metadata.get("bootstrap_contract_hash")
        hashes_match = (
            p11_contract == live_contract
            if p11_contract is not None and live_contract is not None
            else p11.get("bootstrap_hash") == metadata.get("bootstrap_hash")
        )
        if hashes_match:
            selected_ids = {
                int(value) for value in p11["recommendation"]["squad_ids"]
            }
    return build_set_piece_report(players, metadata, selected_ids=selected_ids)


def main() -> None:
    report = asyncio.run(_run_live())
    P12_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    P12_OUTPUT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
