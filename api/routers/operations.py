import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from fpl_intelligence.artifact_contract import load_current_artifact_manifest
from fpl_intelligence.deadline_intelligence import (
    deadline_readiness,
    latest_shadow_snapshot,
)
from fpl_intelligence.live_decision_evidence import evidence_status
from fpl_intelligence.live_shadow import shadow_audit_path, shadow_enabled
from fpl_intelligence.p11_deadline_finalization import P11_OUTPUT
from fpl_intelligence.p12_set_piece_report import P12_OUTPUT
from fpl_intelligence.production_portfolio import get_production_portfolio
from fpl_intelligence.refresh_current_season import BOOTSTRAP_PATH
from fpl_intelligence.season_rules import decision_bootstrap_hash

router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/portfolio")
def portfolio_status() -> dict[str, Any]:
    active = get_production_portfolio()
    control = get_production_portfolio("m8_control")
    return {
        "active": {
            "mode": active.mode,
            "version": active.version,
            **active.projections.as_dict(),
        },
        "rollback": {
            "mode": control.mode,
            "version": control.version,
            **control.projections.as_dict(),
        },
        "shadow_mode": shadow_enabled(),
        "shadow_audit_path": str(shadow_audit_path()),
        "automatic_execution": False,
    }


@router.get("/shadow-evidence")
def live_shadow_evidence_status() -> dict[str, Any]:
    """Report immutable deadline captures without triggering recommendations."""

    return evidence_status()


@router.get("/deadline-readiness")
def gw1_deadline_readiness() -> dict[str, Any]:
    manifest = load_current_artifact_manifest()
    if manifest is None or not BOOTSTRAP_PATH.exists():
        return {"ready": False, "blockers": ["current artifacts are missing"]}
    bootstrap = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    artifact_contract_hash = decision_bootstrap_hash(bootstrap)
    status = deadline_readiness(manifest, bootstrap, now=datetime.now(UTC))
    latest = latest_shadow_snapshot()
    shadow_current = bool(
        latest
        and (
            latest.get("bootstrap_contract_hash") == artifact_contract_hash
            if latest.get("bootstrap_contract_hash") is not None
            else latest.get("bootstrap_hash") == manifest.get("bootstrap_hash")
        )
    )
    p11 = None
    if P11_OUTPUT.exists():
        candidate = json.loads(P11_OUTPUT.read_text(encoding="utf-8"))
        candidate_contract = candidate.get("bootstrap_contract_hash")
        if (
            candidate_contract == artifact_contract_hash
            if candidate_contract is not None
            else candidate.get("bootstrap_hash") == manifest.get("bootstrap_hash")
        ):
            p11 = candidate
    p12 = None
    if P12_OUTPUT.exists():
        candidate = json.loads(P12_OUTPUT.read_text(encoding="utf-8"))
        candidate_contract = candidate.get("bootstrap_contract_hash")
        if (
            candidate_contract == artifact_contract_hash
            if candidate_contract is not None
            else candidate.get("bootstrap_hash") == manifest.get("bootstrap_hash")
        ):
            p12 = candidate
    status["latest_shadow"] = (
        {
            "captured_at": latest["captured_at"],
            "decision_hash": latest["decision_hash"],
            "expected_gw1_points": latest["expected_gw1_points"],
            "current": shadow_current,
        }
        if latest else None
    )
    status["p11"] = (
        {
            "status": p11["gate"]["status"],
            "data_ready": p11["gate"]["data_ready"],
            "lock_ready": p11["gate"]["lock_ready"],
            "final_news_reviewed": p11["gate"]["final_news_reviewed"],
        }
        if p11
        else None
    )
    status["p12"] = (
        {
            "model_version": p12["model_version"],
            "source_url": p12["source_url"],
            "category_coverage": p12["category_coverage"],
            "primary_penalty_takers": len(p12["primary_penalty_takers"]),
        }
        if p12
        else None
    )
    status["decision_lock_ready"] = bool(p11 and p11["gate"]["lock_ready"])
    status["checklist"] = [
        {"key": "fresh_data", "passed": not status["stale"]},
        {"key": "official_deadline", "passed": status["deadline"] is not None},
        {
            "key": "robustness_current",
            "passed": bool(p11 and p11["gate"]["data_ready"]),
        },
        {"key": "set_piece_roles_current", "passed": p12 is not None},
        {"key": "shadow_captured", "passed": shadow_current},
        {
            "key": "final_team_news",
            "passed": bool(p11 and p11["gate"]["final_news_reviewed"]),
        },
    ]
    return status
