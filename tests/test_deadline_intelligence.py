from datetime import UTC, datetime

from fpl_intelligence.deadline_intelligence import (
    build_shadow_snapshot,
    compare_snapshots,
    deadline_readiness,
    latest_shadow_snapshot,
    persist_shadow_snapshot,
)


def _recommendation() -> dict:
    return {
        "season": "2026-27",
        "data_cutoff": "2026-08-07T08:00:00Z",
        "deadline": "2026-08-21T17:30:00Z",
        "bootstrap_hash": "bootstrap",
        "rules_version": "rules",
        "portfolio_version": "portfolio",
        "decision_engine_version": "p10-test-v1",
        "initial_squad_policy": "balanced",
        "initial_squad_policy_version": "policy-v1",
        "risk_profile": "balanced",
        "squad": [{"element_id": value} for value in range(1, 16)],
        "captain_id": 1,
        "vice_captain_id": 2,
        "cost": 100.0,
        "bank": 0.0,
        "expected_gw1_points": 62.2,
        "decision_alternatives": [],
        "decision_audit": {"availability_clear": True},
        "robustness": {"scenario_count": 27, "robust_squad_rate": 0.3},
        "deadline_finalization": {"status": "monitoring", "lock_ready": False},
        "set_piece_summary": {
            "model_version": "p12-set-piece-transition-v1",
            "selected_primary_penalty_takers": ["Player 1"],
        },
    }


def test_deadline_readiness_blocks_stale_artifacts():
    result = deadline_readiness(
        {"season": "2026-27", "data_cutoff": "2026-08-05T00:00:00Z"},
        {"events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}]},
        now=datetime(2026, 8, 7, 12, tzinfo=UTC),
    )

    assert not result["ready"]
    assert result["stale"]
    assert result["next_gameweek"] == 1


def test_shadow_snapshot_is_deterministic_and_reports_drift(tmp_path):
    first = build_shadow_snapshot(
        _recommendation(), captured_at="2026-08-07T09:00:00Z"
    )
    repeated = build_shadow_snapshot(
        _recommendation(), captured_at="2026-08-07T09:00:00Z"
    )
    assert first["decision_hash"] == repeated["decision_hash"]
    assert first["decision_engine_version"] == "p10-test-v1"
    assert first["robustness"]["scenario_count"] == 27
    assert first["deadline_finalization"]["status"] == "monitoring"
    assert first["set_piece_summary"]["model_version"] == (
        "p12-set-piece-transition-v1"
    )

    path = persist_shadow_snapshot(first, tmp_path)
    assert persist_shadow_snapshot(first, tmp_path) == path
    assert latest_shadow_snapshot(tmp_path)["decision_hash"] == first["decision_hash"]

    changed_recommendation = _recommendation()
    changed_recommendation["squad"][-1]["element_id"] = 20
    changed_recommendation["captain_id"] = 2
    changed = build_shadow_snapshot(
        changed_recommendation, captured_at="2026-08-08T09:00:00Z"
    )
    drift = compare_snapshots(first, changed)
    assert drift["changed"]
    assert drift["players_in"] == [20]
    assert drift["players_out"] == [15]
    assert drift["captain_changed"]


def test_shadow_snapshot_rejects_post_deadline_reconstruction():
    try:
        build_shadow_snapshot(
            _recommendation(), captured_at="2026-08-22T09:00:00Z"
        )
    except ValueError as exc:
        assert "locked after the GW1 deadline" in str(exc)
    else:
        raise AssertionError("post-deadline opening snapshot should be rejected")
