"""P11 GW1 deadline gate and fragile-slot challenger analysis."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fpl_intelligence.artifact_contract import (
    CURRENT_ARTIFACT_MANIFEST_PATH,
)
from fpl_intelligence.backtest_transfer_strategy import select_starting_xi
from fpl_intelligence.initial_squad_championship import (
    GW1_DECISION_PROFILES,
    build_live_opening_projection_bundle,
    optimize_opening_squad,
)
from fpl_intelligence.p10_calibration import P10_OUTPUT
from fpl_intelligence.refresh_current_season import BOOTSTRAP_PATH
from fpl_intelligence.season_rules import decision_bootstrap_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
P11_OUTPUT = PROJECT_ROOT / "data/processed/p11_deadline_finalization.json"
PLAYERS_PATH = PROJECT_ROOT / "data/processed/players_current.csv"
P11_SCHEMA_VERSION = "p11-gw1-deadline-finalization-v1"


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def player_records(players: pd.DataFrame) -> dict[int, dict[str, Any]]:
    return {
        int(row["element_id"]): row
        for row in players.to_dict(orient="records")
    }


def build_squad_variants(
    robustness: dict[str, Any],
    players_by_id: dict[int, dict[str, Any]],
    horizon_points: dict[int, float],
) -> list[dict[str, Any]]:
    central = set(int(value) for value in robustness["robust_squad_ids"])
    counts = Counter(
        tuple(sorted(int(value) for value in row["squad_ids"]))
        for row in robustness["scenarios"]
    )
    scenario_count = int(robustness["scenario_count"])

    def details(player_id: int) -> dict[str, Any]:
        row = players_by_id[player_id]
        return {
            "player_id": player_id,
            "player_name": row.get("player_name") or row.get("web_name"),
            "position": row.get("position"),
            "price": round(float(row.get("price") or 0.0), 1),
            "horizon_points": round(float(horizon_points.get(player_id, 0.0)), 3),
        }

    variants = []
    for squad, frequency in counts.most_common():
        squad_set = set(squad)
        variants.append(
            {
                "frequency": frequency,
                "scenario_rate": round(frequency / scenario_count, 4),
                "is_central": squad_set == central,
                "players_out": [details(value) for value in sorted(central - squad_set)],
                "players_in": [details(value) for value in sorted(squad_set - central)],
                "squad_ids": list(squad),
            }
        )
    return variants


def build_fragile_challenges(
    robustness: dict[str, Any],
    players_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    central = set(int(value) for value in robustness["robust_squad_ids"])
    stability = {
        int(row["player_id"]): row for row in robustness["player_stability"]
    }
    scenarios = robustness["scenarios"]
    output = []
    for player_id in sorted(central):
        row = stability[player_id]
        if row["classification"] != "fragile":
            continue
        incumbent = players_by_id[player_id]
        absent = [scenario for scenario in scenarios if player_id not in scenario["squad_ids"]]
        alternatives: Counter[int] = Counter()
        for scenario in absent:
            for alternative_id in scenario["squad_ids"]:
                alternative_id = int(alternative_id)
                alternative = players_by_id.get(alternative_id)
                if (
                    alternative_id not in central
                    and alternative is not None
                    and alternative.get("position") == incumbent.get("position")
                ):
                    alternatives[alternative_id] += 1
        output.append(
            {
                "player_id": player_id,
                "player_name": row["player_name"],
                "selection_rate": row["selection_rate"],
                "absent_scenarios": len(absent),
                "verdict": "monitor",
                "conditional_alternatives": [
                    {
                        "player_id": alternative_id,
                        "player_name": players_by_id[alternative_id].get("player_name")
                        or players_by_id[alternative_id].get("web_name"),
                        "price": round(
                            float(players_by_id[alternative_id].get("price") or 0.0),
                            1,
                        ),
                        "selected_when_incumbent_absent": count,
                        "conditional_rate": round(count / len(absent), 4),
                        "overall_selection_rate": stability.get(alternative_id, {}).get(
                            "selection_rate", 0.0
                        ),
                    }
                    for alternative_id, count in alternatives.most_common()
                ],
            }
        )
    return output


def build_deadline_gate(
    *,
    manifest: dict[str, Any],
    bootstrap: dict[str, Any],
    p10_report: dict[str, Any],
    players_by_id: dict[int, dict[str, Any]],
    current_squad_ids: list[int],
    now: datetime,
    final_news_reviewed: bool,
    maximum_age_hours: float = 24.0,
) -> dict[str, Any]:
    cutoff = parse_timestamp(str(manifest["data_cutoff"]))
    age_hours = max(0.0, (now - cutoff).total_seconds() / 3600.0)
    upcoming = [
        event
        for event in bootstrap.get("events", [])
        if event.get("deadline_time")
        and parse_timestamp(str(event["deadline_time"])) > now
    ]
    event = min(
        upcoming,
        key=lambda row: parse_timestamp(str(row["deadline_time"])),
        default=None,
    )
    hours_to_deadline = (
        (parse_timestamp(str(event["deadline_time"])) - now).total_seconds() / 3600.0
        if event
        else None
    )
    p10_metadata = p10_report.get("metadata", {})
    p10_hash = p10_metadata.get("bootstrap_contract_hash")
    manifest_hash = decision_bootstrap_hash(bootstrap)
    if p10_hash is None:
        # Backward-compatible fail-closed check for reports created before the
        # decision-contract hash was persisted.
        p10_hash = p10_metadata.get("bootstrap_hash")
        manifest_hash = manifest.get("bootstrap_hash")
    central_ids = sorted(
        int(value) for value in p10_report["robustness"]["robust_squad_ids"]
    )
    hard_blockers = []
    if p10_hash != manifest_hash:
        hard_blockers.append("p10_bootstrap_hash_mismatch")
    if sorted(current_squad_ids) != central_ids:
        hard_blockers.append("central_squad_differs_from_robust_mode")
    if age_hours > maximum_age_hours:
        hard_blockers.append("current_artifacts_stale")
    if event is None:
        hard_blockers.append("official_deadline_missing")
    unavailable = []
    for player_id in current_squad_ids:
        player = players_by_id.get(player_id)
        if player is None:
            unavailable.append(player_id)
            continue
        chance = player.get("chance_of_playing_next_round")
        if player.get("status") not in {"a", None} or (
            pd.notna(chance) and float(chance) < 100.0
        ):
            unavailable.append(player_id)
    if unavailable:
        hard_blockers.append("selected_player_availability_risk")
    timing_blockers = []
    if hours_to_deadline is None or hours_to_deadline > 24.0:
        timing_blockers.append("outside_final_24h_window")
    if not final_news_reviewed:
        timing_blockers.append("final_team_news_not_reviewed")
    lock_ready = not hard_blockers and not timing_blockers
    return {
        "status": (
            "finalization_ready"
            if lock_ready
            else "blocked"
            if hard_blockers
            else "monitoring"
        ),
        "lock_ready": lock_ready,
        "data_ready": not hard_blockers,
        "data_cutoff": manifest["data_cutoff"],
        "data_age_hours": round(age_hours, 2),
        "maximum_age_hours": maximum_age_hours,
        "next_gameweek": event.get("id") if event else None,
        "deadline": event.get("deadline_time") if event else None,
        "hours_to_deadline": (
            round(hours_to_deadline, 2) if hours_to_deadline is not None else None
        ),
        "final_news_reviewed": final_news_reviewed,
        "hard_blockers": hard_blockers,
        "timing_blockers": timing_blockers,
        "unavailable_player_ids": unavailable,
    }


async def build_live_report(
    *,
    final_news_reviewed: bool = False,
    final_news_sources: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    from api.live_projection_service import live_projection_rows

    from fpl_intelligence.production_portfolio import get_production_portfolio

    manifest = json.loads(CURRENT_ARTIFACT_MANIFEST_PATH.read_text(encoding="utf-8"))
    bootstrap = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    p10_report = json.loads(P10_OUTPUT.read_text(encoding="utf-8"))
    players = pd.read_csv(PLAYERS_PATH)
    players_by_id = player_records(players)
    portfolio = get_production_portfolio()
    projected, metadata = await live_projection_rows(
        model_name=portfolio.projections.transfer_model,
        start_gameweek=1,
        horizon=8,
    )
    horizon_points = {
        int(row["element_id"]): sum(
            float(gameweek.get("projected_points") or 0.0)
            for gameweek in row.get("projections", [])
        )
        for row in projected
        if row.get("element_id") is not None
    }
    bundle = build_live_opening_projection_bundle(projected, metadata)
    candidate = optimize_opening_squad(bundle, GW1_DECISION_PROFILES["balanced"])
    squad_ids = sorted(candidate.squad["player_id"].astype(int).tolist())
    gw1 = bundle.projections[1].set_index("player_id")["projected_points"].to_dict()
    lineup = select_starting_xi(candidate.squad, gw1)
    captain_order = sorted(
        lineup.starting_ids,
        key=lambda player_id: (
            float(gw1.get(player_id, 0.0)),
            float(horizon_points.get(player_id, 0.0)),
        ),
        reverse=True,
    )
    robustness = p10_report["robustness"]
    gate = build_deadline_gate(
        manifest=manifest,
        bootstrap=bootstrap,
        p10_report=p10_report,
        players_by_id=players_by_id,
        current_squad_ids=squad_ids,
        now=now or datetime.now(UTC),
        final_news_reviewed=final_news_reviewed,
    )
    return {
        "schema_version": P11_SCHEMA_VERSION,
        "season": manifest["season"],
        "bootstrap_hash": manifest["bootstrap_hash"],
        "bootstrap_contract_hash": decision_bootstrap_hash(bootstrap),
        "rules_version": manifest["rules_version"],
        "projection_hash": bundle.projection_hash,
        "gate": gate,
        "final_news_review": {
            "reviewed": final_news_reviewed,
            "sources": final_news_sources or [],
            "reviewed_at": (
                (now or datetime.now(UTC)).isoformat().replace("+00:00", "Z")
                if final_news_reviewed
                else None
            ),
        },
        "recommendation": {
            "squad_ids": squad_ids,
            "starting_ids": lineup.starting_ids,
            "bench_ids": lineup.bench_ids,
            "formation": lineup.formation,
            "captain_id": captain_order[0],
            "vice_captain_id": captain_order[1],
            "cost": round(float(candidate.squad["price"].sum()), 1),
            "expected_gw1_points": round(
                sum(float(gw1[player_id]) for player_id in lineup.starting_ids)
                + float(gw1[captain_order[0]]),
                2,
            ),
            "verdict": "retain_central_squad_pending_final_news",
        },
        "robustness_summary": {
            "scenario_count": robustness["scenario_count"],
            "distinct_squads": robustness["distinct_squads"],
            "central_squad_frequency": robustness["robust_squad_frequency"],
            "central_squad_rate": robustness["robust_squad_rate"],
        },
        "fragile_challenges": build_fragile_challenges(
            robustness, players_by_id
        ),
        "squad_variants": build_squad_variants(
            robustness, players_by_id, horizon_points
        ),
        "official_sources": [
            "https://fantasy.premierleague.com/api/bootstrap-static/",
            "https://www.premierleague.com/en/news/4679613/what-to-look-out-for-in-pre-season-ahead-of-202627-fantasy",
            "https://www.premierleague.com/en/news/4677216/fpl-signings-will-andersons-defensive-contributions-be-reduced-at-man-city",
        ],
    }


def persist_report(report: dict[str, Any]) -> None:
    P11_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    P11_OUTPUT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final-news-reviewed",
        action="store_true",
        help="Acknowledge a manual review of final official team news.",
    )
    parser.add_argument(
        "--final-news-source",
        action="append",
        default=[],
        help="Official source URL reviewed before acknowledging final team news.",
    )
    args = parser.parse_args()
    if args.final_news_reviewed and not args.final_news_source:
        parser.error("--final-news-reviewed requires --final-news-source")
    report = asyncio.run(
        build_live_report(
            final_news_reviewed=args.final_news_reviewed,
            final_news_sources=args.final_news_source,
        )
    )
    persist_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
