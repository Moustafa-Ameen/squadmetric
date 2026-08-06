from typing import Any

from fastapi import APIRouter

from fpl_intelligence.live_shadow import shadow_audit_path, shadow_enabled
from fpl_intelligence.production_portfolio import get_production_portfolio

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
