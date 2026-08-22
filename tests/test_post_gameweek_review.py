import json

from fpl_intelligence.post_gameweek_review import build_post_gameweek_review


def _bootstrap():
    return {
        "total_players": 10_000_000,
        "events": [
            {"id": 1, "finished": True, "data_checked": True},
            {"id": 2, "finished": True, "data_checked": False},
        ],
    }


def _history():
    return {
        "current": [
            {
                "event": 1,
                "points": 70,
                "event_transfers_cost": 4,
                "total_points": 66,
                "overall_rank": 500_000,
                "points_on_bench": 8,
                "event_transfers": 2,
                "value": 1_005,
                "bank": 5,
            },
            {
                "event": 2,
                "points": 99,
                "event_transfers_cost": 0,
                "total_points": 165,
                "overall_rank": 100_000,
            },
        ]
    }


def test_review_uses_only_officially_data_checked_gameweeks(tmp_path):
    report = build_post_gameweek_review(
        season="2026-27",
        bootstrap=_bootstrap(),
        team_history=_history(),
        evidence_root=tmp_path,
    )

    assert report["reviewed_gameweeks"] == 1
    assert report["gameweeks"][0]["net_points"] == 66
    assert report["gameweeks"][0]["rank_percentile"] == 5
    assert report["summary"]["hit_cost"] == 4
    assert report["rank_mode"]["default_mode"] == "points"
    assert report["rank_mode"]["validated_for_recommendations"] is False


def test_review_reconciles_frozen_decision_outcome(tmp_path):
    directory = tmp_path / "2026-27" / "GW01" / "outcomes"
    directory.mkdir(parents=True)
    (directory / "outcome.json").write_text(
        json.dumps(
            {
                "snapshot_hash": "snapshot",
                "outcome_hash": "outcome",
                "selected_net_points": 64,
                "best_frozen_branch_points": 72,
                "selected_regret": 8,
                "branches": [
                    {
                        "selected": True,
                        "expected_gameweek_points": 67.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_post_gameweek_review(
        season="2026-27",
        bootstrap=_bootstrap(),
        team_history=_history(),
        evidence_root=tmp_path,
    )
    evidence = report["gameweeks"][0]["decision_evidence"]

    assert evidence["status"] == "finalized"
    assert evidence["expected_points"] == 67.5
    assert evidence["selected_regret"] == 8
    assert report["summary"]["decision_regret"] == 8


def test_review_is_empty_before_first_finalized_gameweek(tmp_path):
    report = build_post_gameweek_review(
        season="2026-27",
        bootstrap={"total_players": 1, "events": []},
        team_history={"current": []},
        evidence_root=tmp_path,
    )

    assert report["gameweeks"] == []
    assert report["rank_mode"]["available"] is False
