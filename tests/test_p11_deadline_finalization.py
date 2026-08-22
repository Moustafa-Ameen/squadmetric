from datetime import UTC, datetime, timedelta

import pandas as pd

from fpl_intelligence.p11_deadline_finalization import (
    build_deadline_gate,
    build_fragile_challenges,
    build_squad_variants,
    player_records,
)
from fpl_intelligence.season_rules import decision_bootstrap_hash


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "element_id": 1,
                "player_name": "Incumbent",
                "position": "MID",
                "price": 6.5,
                "status": "a",
                "chance_of_playing_next_round": 100,
            },
            {
                "element_id": 2,
                "player_name": "Locked",
                "position": "DEF",
                "price": 5.0,
                "status": "a",
                "chance_of_playing_next_round": 100,
            },
            {
                "element_id": 3,
                "player_name": "Challenger",
                "position": "MID",
                "price": 6.0,
                "status": "a",
                "chance_of_playing_next_round": 100,
            },
        ]
    )


def _report() -> dict:
    return {
        "metadata": {"bootstrap_hash": "hash"},
        "robustness": {
            "scenario_count": 3,
            "distinct_squads": 2,
            "robust_squad_ids": [1, 2],
            "robust_squad_frequency": 2,
            "robust_squad_rate": 0.6667,
            "scenarios": [
                {"squad_ids": [1, 2]},
                {"squad_ids": [1, 2]},
                {"squad_ids": [2, 3]},
            ],
            "player_stability": [
                {
                    "player_id": 1,
                    "player_name": "Incumbent",
                    "classification": "fragile",
                    "selection_rate": 0.6667,
                },
                {
                    "player_id": 2,
                    "player_name": "Locked",
                    "classification": "locked",
                    "selection_rate": 1.0,
                },
                {
                    "player_id": 3,
                    "player_name": "Challenger",
                    "classification": "fragile",
                    "selection_rate": 0.3333,
                },
            ],
        },
    }


def test_fragile_challenge_uses_conditional_same_position_replacements():
    result = build_fragile_challenges(_report()["robustness"], player_records(_players()))

    assert len(result) == 1
    assert result[0]["player_name"] == "Incumbent"
    assert result[0]["absent_scenarios"] == 1
    assert result[0]["conditional_alternatives"][0]["player_name"] == "Challenger"
    assert result[0]["conditional_alternatives"][0]["conditional_rate"] == 1.0


def test_squad_variants_preserve_whole_squad_changes():
    result = build_squad_variants(
        _report()["robustness"], player_records(_players()), {1: 30, 2: 20, 3: 28}
    )

    assert result[0]["is_central"]
    assert result[0]["frequency"] == 2
    assert result[1]["players_out"][0]["player_name"] == "Incumbent"
    assert result[1]["players_in"][0]["player_name"] == "Challenger"


def test_deadline_gate_requires_fresh_hash_availability_and_final_news():
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    manifest = {
        "bootstrap_hash": "hash",
        "data_cutoff": (now - timedelta(hours=1)).isoformat(),
    }
    bootstrap = {
        "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}]
    }
    players = player_records(_players())

    monitoring = build_deadline_gate(
        manifest=manifest,
        bootstrap=bootstrap,
        p10_report=_report(),
        players_by_id=players,
        current_squad_ids=[1, 2],
        now=now,
        final_news_reviewed=False,
    )
    ready = build_deadline_gate(
        manifest=manifest,
        bootstrap=bootstrap,
        p10_report=_report(),
        players_by_id=players,
        current_squad_ids=[1, 2],
        now=now,
        final_news_reviewed=True,
    )

    assert monitoring["status"] == "monitoring"
    assert "final_team_news_not_reviewed" in monitoring["timing_blockers"]
    assert ready["status"] == "finalization_ready"
    assert ready["lock_ready"]


def test_deadline_gate_fails_closed_on_hash_or_availability_change():
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    report = _report()
    report["metadata"]["bootstrap_hash"] = "old"
    players = player_records(_players())
    players[1]["status"] = "d"
    result = build_deadline_gate(
        manifest={
            "bootstrap_hash": "new",
            "data_cutoff": now.isoformat(),
        },
        bootstrap={
            "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}]
        },
        p10_report=report,
        players_by_id=players,
        current_squad_ids=[1, 2],
        now=now,
        final_news_reviewed=True,
    )

    assert result["status"] == "blocked"
    assert "p10_bootstrap_hash_mismatch" in result["hard_blockers"]
    assert "selected_player_availability_risk" in result["hard_blockers"]


def test_deadline_gate_ignores_only_volatile_ownership_drift():
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    artifact_bootstrap = {
        "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}],
        "elements": [
            {"id": 1, "now_cost": 65, "selected_by_percent": "10.0"},
            {"id": 2, "now_cost": 50, "selected_by_percent": "20.0"},
        ],
        "total_players": 100,
    }
    live_bootstrap = {
        **artifact_bootstrap,
        "elements": [
            {"id": 1, "now_cost": 65, "selected_by_percent": "11.0"},
            {"id": 2, "now_cost": 50, "selected_by_percent": "19.0"},
        ],
        "total_players": 150,
    }
    report = _report()
    report["metadata"]["bootstrap_hash"] = "different-raw-hash"
    report["metadata"]["bootstrap_contract_hash"] = decision_bootstrap_hash(
        live_bootstrap
    )

    result = build_deadline_gate(
        manifest={
            "bootstrap_hash": "artifact-raw-hash",
            "data_cutoff": now.isoformat(),
        },
        bootstrap=artifact_bootstrap,
        p10_report=report,
        players_by_id=player_records(_players()),
        current_squad_ids=[1, 2],
        now=now,
        final_news_reviewed=True,
    )

    assert "p10_bootstrap_hash_mismatch" not in result["hard_blockers"]
    assert result["data_ready"]
