import json

from fpl_intelligence.live_shadow import (
    append_shadow_record,
    compare_projection_sets,
    shadow_enabled,
)
from fpl_intelligence.production_portfolio import get_production_portfolio


def test_shadow_mode_is_explicit(monkeypatch):
    monkeypatch.delenv("FPL_SHADOW_MODE", raising=False)
    assert shadow_enabled() is False

    monkeypatch.setenv("FPL_SHADOW_MODE", "true")
    assert shadow_enabled() is True


def test_projection_shadow_audit_reports_changed_values():
    active = [{"element_id": 1, "projections": [{"gameweek": 2, "projected_points": 5.0}]}]
    control = [{"element_id": 1, "projections": [{"gameweek": 2, "projected_points": 4.0}]}]
    active_portfolio = get_production_portfolio("r2_validated")
    control_portfolio = get_production_portfolio("m8_control")

    audit = compare_projection_sets(
        active_players=active,
        control_players=control,
        start_gameweek=2,
        horizon=3,
        active_portfolio=active_portfolio,
        control_portfolio=control_portfolio,
        rules_version="test-rules",
    )

    assert audit["changed_projection_keys"] == 1
    assert audit["total_projection_delta"] == 1.0
    assert audit["active_portfolio"] == "r2-consumer-portfolio-v1"


def test_shadow_records_are_append_only_json_lines(tmp_path):
    path = tmp_path / "shadow.jsonl"
    append_shadow_record({"audit_type": "test", "changed": True}, path)
    append_shadow_record({"audit_type": "test-2", "changed": False}, path)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"audit_type": "test", "changed": True},
        {"audit_type": "test-2", "changed": False},
    ]
