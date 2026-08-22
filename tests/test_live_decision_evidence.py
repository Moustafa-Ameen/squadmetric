import json

import pytest

from fpl_intelligence.live_decision_evidence import (
    build_deadline_snapshot,
    build_finalized_outcome,
    canonical_hash,
    evidence_status,
    official_event_finalization,
    persist_outcome,
    persist_snapshot,
    score_frozen_branch,
)


def _squad() -> list[dict]:
    positions = [
        "GK",
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
        "FWD",
    ]
    return [
        {"player_id": index, "position": position, "team": f"T{index}", "price": 5.0}
        for index, position in enumerate(positions, start=1)
    ]


def _branch(*, branch_id: str = "selected", chip: str | None = None) -> dict:
    return {
        "branch_id": branch_id,
        "raw_rank": 1,
        "selected": branch_id == "selected",
        "chip": chip,
        "chip_key": chip or "none",
        "transfers": [],
        "hit_cost": 0,
        "squad": _squad(),
        "starting_ids": [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15],
        "bench_order": [2, 6, 7, 12],
        "captain_id": 8,
        "vice_captain_id": 9,
        "expected_gameweek_points": 60.0,
        "expected_horizon_points": 180.0,
    }


def _snapshot(branches: list[dict] | None = None) -> dict:
    branches = branches or [_branch()]
    return build_deadline_snapshot(
        season="2026-27",
        gameweek=2,
        deadline="2026-08-28T17:30:00Z",
        captured_at="2026-08-28T16:00:00Z",
        data_cutoff="2026-08-28T15:55:00Z",
        rules_version="rules-v1",
        rules_payload_hash="rules-hash",
        bootstrap_hash="bootstrap-hash",
        fixtures_hash="fixtures-hash",
        selected_branch_id="selected",
        state_before={"bank": 0.5, "free_transfers": 1},
        branches=branches,
        context={"source": "planner", "candidate_set_complete": True},
        source_payload_hash="source-hash",
    )


def _actual() -> dict[int, dict[str, float]]:
    return {
        player_id: {"points": float(player_id), "minutes": 90.0}
        for player_id in range(1, 16)
    }


def _live_payload() -> dict:
    return {
        "elements": [
            {"id": player_id, "stats": {"total_points": player_id, "minutes": 90}}
            for player_id in range(1, 16)
        ]
    }


def test_snapshot_is_deterministic_and_rejects_post_deadline_capture():
    first = _snapshot()
    repeated = _snapshot()
    assert first["snapshot_hash"] == repeated["snapshot_hash"]
    assert first["candidate_count"] == 1
    assert first["automatic_execution"] is False

    with pytest.raises(ValueError, match="before the official deadline"):
        build_deadline_snapshot(
            season="2026-27",
            gameweek=2,
            deadline="2026-08-28T17:30:00Z",
            captured_at="2026-08-28T17:31:00Z",
            data_cutoff="2026-08-28T17:00:00Z",
            rules_version="rules",
            rules_payload_hash="rules-hash",
            bootstrap_hash="bootstrap",
            fixtures_hash="fixtures",
            selected_branch_id="selected",
            state_before={},
            branches=[_branch()],
            context={},
            source_payload_hash="source",
        )

    with pytest.raises(ValueError, match="data cutoff cannot be later"):
        build_deadline_snapshot(
            season="2026-27",
            gameweek=2,
            deadline="2026-08-28T17:30:00Z",
            captured_at="2026-08-28T16:00:00Z",
            data_cutoff="2026-08-28T16:01:00Z",
            rules_version="rules",
            rules_payload_hash="rules-hash",
            bootstrap_hash="bootstrap",
            fixtures_hash="fixtures",
            selected_branch_id="selected",
            state_before={},
            branches=[_branch()],
            context={"candidate_set_complete": True},
            source_payload_hash="source",
        )


def test_snapshot_and_outcome_files_are_immutable_and_status_is_reconciled(tmp_path):
    snapshot = _snapshot()
    snapshot_path = persist_snapshot(snapshot, tmp_path)
    assert persist_snapshot(snapshot, tmp_path) == snapshot_path

    outcome = build_finalized_outcome(
        snapshot,
        bootstrap={"events": [{"id": 2, "finished": True, "data_checked": True}]},
        live_payload=_live_payload(),
        finalized_at="2026-08-31T12:00:00Z",
    )
    outcome_path = persist_outcome(outcome, tmp_path)
    assert persist_outcome(outcome, tmp_path) == outcome_path
    repeated_outcome = build_finalized_outcome(
        snapshot,
        bootstrap={"events": [{"id": 2, "finished": True, "data_checked": True}]},
        live_payload=_live_payload(),
        finalized_at="2026-08-31T13:00:00Z",
    )
    assert persist_outcome(repeated_outcome, tmp_path) == outcome_path
    assert json.loads(outcome_path.read_text(encoding="utf-8"))["status"] == "finalized"

    status = evidence_status(tmp_path)
    assert status["snapshot_files"] == 1
    assert status["outcome_files"] == 1
    assert status["gameweeks"][0]["finalized"]


def test_finalization_requires_finished_and_data_checked():
    assert official_event_finalization(
        {"events": [{"id": 2, "finished": False, "data_checked": False}]}, 2
    )["reason"] == "official_event_not_finished"
    assert official_event_finalization(
        {"events": [{"id": 2, "finished": True, "data_checked": False}]}, 2
    )["reason"] == "official_scoring_not_data_checked"

    with pytest.raises(ValueError, match="official_scoring_not_data_checked"):
        build_finalized_outcome(
            _snapshot(),
            bootstrap={"events": [{"id": 2, "finished": True, "data_checked": False}]},
            live_payload=_live_payload(),
            finalized_at="2026-08-31T12:00:00Z",
        )


def test_frozen_branch_scores_autosubs_and_vice_captain_fallback():
    branch = _branch()
    actual = _actual()
    actual[8]["minutes"] = 0.0
    actual[8]["points"] = 0.0
    actual[3]["minutes"] = 0.0
    actual[3]["points"] = 0.0

    result = score_frozen_branch(branch, actual)

    assert result["effective_captain_id"] == 9
    assert 6 in result["autosub_ids"]
    assert 7 in result["autosub_ids"]
    expected_active = set(branch["starting_ids"]) - {3, 8} | {6, 7}
    expected = sum(actual[player_id]["points"] for player_id in expected_active) + 9
    assert result["net_points"] == expected


def test_bench_boost_and_triple_captain_use_exact_incremental_scoring():
    actual = _actual()
    normal = score_frozen_branch(_branch(), actual)
    bench_boost = score_frozen_branch(_branch(chip="bboost"), actual)
    triple = score_frozen_branch(_branch(chip="3xc"), actual)

    assert bench_boost["net_points"] - normal["net_points"] == sum(
        actual[player_id]["points"] for player_id in [2, 6, 7, 12]
    )
    assert triple["net_points"] - normal["net_points"] == actual[8]["points"]


def test_finalized_outcome_preserves_every_counterfactual_and_selected_regret():
    alternative = _branch(branch_id="alternative")
    alternative["selected"] = False
    alternative["captain_id"] = 15
    snapshot = _snapshot([_branch(), alternative])

    outcome = build_finalized_outcome(
        snapshot,
        bootstrap={"events": [{"id": 2, "finished": True, "data_checked": True}]},
        live_payload=_live_payload(),
        finalized_at="2026-08-31T12:00:00Z",
    )

    assert len(outcome["branches"]) == 2
    assert outcome["selected_regret"] == 7.0
    assert outcome["outcome_hash"] == canonical_hash(
        {key: value for key, value in outcome.items() if key != "outcome_hash"}
    )
