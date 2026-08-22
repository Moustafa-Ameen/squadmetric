"""Official post-Gameweek review reconciled with frozen deadline evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fpl_intelligence.live_decision_evidence import EVIDENCE_ROOT

REVIEW_SCHEMA_VERSION = "post-gameweek-review-v1"


def build_post_gameweek_review(
    *,
    season: str,
    bootstrap: Mapping[str, Any],
    team_history: Mapping[str, Any],
    evidence_root: Path = EVIDENCE_ROOT,
) -> dict[str, Any]:
    """Return finalized manager results without rewriting pre-deadline evidence."""

    finalized = {
        int(event["id"])
        for event in bootstrap.get("events", [])
        if event.get("id") is not None
        and bool(event.get("finished"))
        and bool(event.get("data_checked"))
    }
    history_rows = sorted(
        (
            dict(row)
            for row in team_history.get("current", [])
            if int(row.get("event") or 0) in finalized
        ),
        key=lambda row: int(row["event"]),
    )
    total_managers = _integer(bootstrap.get("total_players"))
    reviews = []
    previous_rank: int | None = None
    for history in history_rows:
        gameweek = int(history["event"])
        gross_points = _number(history.get("points"))
        hit_cost = _number(history.get("event_transfers_cost"))
        overall_rank = _integer(history.get("overall_rank"))
        outcome = _latest_outcome(season, gameweek, evidence_root)
        selected_branch = _selected_branch(outcome)
        rank_change = (
            previous_rank - overall_rank
            if previous_rank is not None and overall_rank is not None
            else None
        )
        reviews.append(
            {
                "gameweek": gameweek,
                "gross_points": gross_points,
                "hit_cost": hit_cost,
                "net_points": round(gross_points - hit_cost, 3),
                "total_points": _number(history.get("total_points")),
                "overall_rank": overall_rank,
                "rank_change": rank_change,
                "rank_percentile": (
                    round(100 * overall_rank / total_managers, 3)
                    if overall_rank is not None and total_managers
                    else None
                ),
                "points_on_bench": _number(history.get("points_on_bench")),
                "transfers": _integer(history.get("event_transfers")) or 0,
                "squad_value": _money(history.get("value")),
                "bank": _money(history.get("bank")),
                "decision_evidence": (
                    {
                        "status": "finalized",
                        "snapshot_hash": outcome.get("snapshot_hash"),
                        "outcome_hash": outcome.get("outcome_hash"),
                        "expected_points": _optional_number(
                            selected_branch.get("expected_gameweek_points")
                            if selected_branch else None
                        ),
                        "selected_net_points": _optional_number(
                            outcome.get("selected_net_points")
                        ),
                        "best_frozen_branch_points": _optional_number(
                            outcome.get("best_frozen_branch_points")
                        ),
                        "selected_regret": _optional_number(
                            outcome.get("selected_regret")
                        ),
                    }
                    if outcome
                    else {"status": "not_captured"}
                ),
            }
        )
        if overall_rank is not None:
            previous_rank = overall_rank

    evidence_rows = [
        row for row in reviews if row["decision_evidence"]["status"] == "finalized"
    ]
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "season": season,
        "official_finalized_gameweeks": sorted(finalized),
        "reviewed_gameweeks": len(reviews),
        "total_managers": total_managers,
        "summary": {
            "net_points": round(sum(row["net_points"] for row in reviews), 3),
            "hit_cost": round(sum(row["hit_cost"] for row in reviews), 3),
            "points_on_bench": round(
                sum(row["points_on_bench"] for row in reviews), 3
            ),
            "decision_evidence_gameweeks": len(evidence_rows),
            "decision_regret": round(
                sum(
                    float(row["decision_evidence"].get("selected_regret") or 0.0)
                    for row in evidence_rows
                ),
                3,
            ),
            "latest_overall_rank": (
                reviews[-1]["overall_rank"] if reviews else None
            ),
        },
        "rank_mode": {
            "available": bool(reviews and total_managers),
            "validated_for_recommendations": False,
            "default_mode": "points",
            "reason": (
                "Rank mode is an optional review lens. It does not change the "
                "production points-maximizing optimizer until field-relative "
                "decision validation passes."
            ),
        },
        "gameweeks": reviews,
        "automatic_fpl_actions": False,
    }


def _latest_outcome(season: str, gameweek: int, root: Path) -> dict[str, Any] | None:
    directory = root / season / f"GW{gameweek:02d}" / "outcomes"
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def _selected_branch(outcome: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not outcome:
        return None
    return next(
        (dict(row) for row in outcome.get("branches", []) if row.get("selected")),
        None,
    )


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    return None if value is None else _number(value)


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _money(value: Any) -> float | None:
    integer = _integer(value)
    return round(integer / 10, 1) if integer is not None else None
