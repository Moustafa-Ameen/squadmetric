"""Capture one immutable live GW1 recommendation and report drift."""

from datetime import UTC, datetime

from api.main import app
from fastapi.testclient import TestClient

from fpl_intelligence.deadline_intelligence import (
    build_shadow_snapshot,
    compare_snapshots,
    latest_shadow_snapshot,
    persist_shadow_snapshot,
)

with TestClient(app) as client:
    response = client.get(
        "/api/predictions/initial-squad?horizon=8&risk_profile=balanced"
    )
    response.raise_for_status()
    captured_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    snapshot = build_shadow_snapshot(response.json(), captured_at=captured_at)
    previous = latest_shadow_snapshot()
    path = persist_shadow_snapshot(snapshot)
    print({"path": str(path), "drift": compare_snapshots(previous, snapshot)})
