"""Deadline freshness, immutable opening-squad snapshots, and drift audits."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHADOW_ROOT = PROJECT_ROOT / "data" / "processed" / "gw1_shadow"


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def deadline_readiness(
    manifest: dict[str, Any],
    bootstrap: dict[str, Any],
    *,
    now: datetime | None = None,
    maximum_age_hours: float = 24.0,
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    cutoff = parse_timestamp(str(manifest["data_cutoff"]))
    upcoming = [
        event for event in bootstrap.get("events", [])
        if event.get("deadline_time") and parse_timestamp(event["deadline_time"]) > current_time
    ]
    event = min(upcoming, key=lambda row: parse_timestamp(row["deadline_time"]), default=None)
    age_hours = max(0.0, (current_time - cutoff).total_seconds() / 3600)
    hours_to_deadline = (
        (parse_timestamp(event["deadline_time"]) - current_time).total_seconds() / 3600
        if event else None
    )
    stale = age_hours > maximum_age_hours
    return {
        "ready": not stale and event is not None,
        "season": manifest.get("season"),
        "data_cutoff": manifest.get("data_cutoff"),
        "data_age_hours": round(age_hours, 2),
        "maximum_age_hours": maximum_age_hours,
        "stale": stale,
        "next_gameweek": event.get("id") if event else None,
        "deadline": event.get("deadline_time") if event else None,
        "hours_to_deadline": round(hours_to_deadline, 2) if hours_to_deadline is not None else None,
        "final_refresh_required": bool(hours_to_deadline is not None and hours_to_deadline <= 24),
        "blockers": (["current artifacts are stale"] if stale else [])
        + (["no future official deadline found"] if event is None else []),
    }


def build_shadow_snapshot(
    recommendation: dict[str, Any],
    *,
    captured_at: str,
) -> dict[str, Any]:
    deadline = str(recommendation.get("deadline") or "").strip()
    if not deadline:
        raise ValueError("Opening-squad shadow capture requires the official GW1 deadline")
    captured = parse_timestamp(captured_at)
    deadline_at = parse_timestamp(deadline)
    cutoff = parse_timestamp(str(recommendation["data_cutoff"]))
    if captured >= deadline_at or cutoff >= deadline_at:
        raise ValueError(
            "Opening-squad shadow capture is locked after the GW1 deadline"
        )
    squad = sorted(int(row["element_id"]) for row in recommendation["squad"])
    payload = {
        "schema_version": "opening-squad-shadow-v4",
        "captured_at": captured_at,
        "deadline": deadline,
        "immutable_after_deadline": True,
        "season": recommendation["season"],
        "data_cutoff": recommendation["data_cutoff"],
        "bootstrap_hash": recommendation["bootstrap_hash"],
        "bootstrap_contract_hash": recommendation.get("bootstrap_contract_hash"),
        "rules_version": recommendation["rules_version"],
        "portfolio_version": recommendation["portfolio_version"],
        "decision_engine_version": recommendation.get("decision_engine_version"),
        "initial_squad_policy": recommendation.get("initial_squad_policy"),
        "initial_squad_policy_version": recommendation.get(
            "initial_squad_policy_version"
        ),
        "risk_profile": recommendation["risk_profile"],
        "squad_ids": squad,
        "captain_id": recommendation["captain_id"],
        "vice_captain_id": recommendation["vice_captain_id"],
        "cost": recommendation["cost"],
        "bank": recommendation["bank"],
        "expected_gw1_points": recommendation["expected_gw1_points"],
        "decision_alternatives": recommendation["decision_alternatives"],
        "decision_audit": recommendation["decision_audit"],
        "robustness": recommendation.get("robustness"),
        "deadline_finalization": recommendation.get("deadline_finalization"),
        "set_piece_summary": recommendation.get("set_piece_summary"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["decision_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def compare_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {"first_snapshot": True, "changed": False, "players_in": [], "players_out": []}
    old_ids = set(previous["squad_ids"])
    new_ids = set(current["squad_ids"])
    return {
        "first_snapshot": False,
        "changed": previous.get("decision_hash") != current.get("decision_hash"),
        "players_in": sorted(new_ids - old_ids),
        "players_out": sorted(old_ids - new_ids),
        "captain_changed": previous.get("captain_id") != current.get("captain_id"),
        "vice_captain_changed": previous.get("vice_captain_id") != current.get("vice_captain_id"),
        "bootstrap_changed": previous.get("bootstrap_hash") != current.get("bootstrap_hash"),
        "points_delta": round(
            float(current.get("expected_gw1_points", 0))
            - float(previous.get("expected_gw1_points", 0)), 3
        ),
    }


def persist_shadow_snapshot(snapshot: dict[str, Any], root: Path = SHADOW_ROOT) -> Path:
    if not snapshot.get("immutable_after_deadline"):
        raise ValueError("Shadow snapshot is missing its immutability contract")
    root.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{snapshot['captured_at'].replace(':', '-')}-"
        f"{snapshot['decision_hash'][:12]}.json"
    )
    path = root / filename
    if not path.exists():
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def latest_shadow_snapshot(root: Path = SHADOW_ROOT) -> dict[str, Any] | None:
    paths = sorted(root.glob("*.json")) if root.exists() else []
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None
