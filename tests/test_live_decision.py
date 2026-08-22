import pandas as pd
from api.routers.planner import _decision_center_payload, _decision_payload

from fpl_intelligence.backtest_transfer_strategy import TransferDecision, TransferPlan
from fpl_intelligence.beam_search import BeamAction


def _squad() -> pd.DataFrame:
    rows = []
    player_id = 1
    for position, count in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for index in range(count):
            rows.append(
                {
                    "player_id": player_id,
                    "player_name": f"Player {player_id}",
                    "position": position,
                    "team": f"Team {index + 1}",
                    "price": 5.0,
                    "expected_points_adjusted": float(player_id),
                    "probability_60_plus_minutes": 1.0,
                }
            )
            player_id += 1
    return pd.DataFrame(rows)


def test_decision_payload_contains_complete_recommendation_state():
    squad = _squad()
    action = BeamAction(
        transfer_plan=TransferPlan.from_decision(
            TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)
        ),
        chip=None,
        chip_squad=None,
        expected_points=20.0,
        search_score=20.0,
        reason="test control",
        expected_horizon_points=60.0,
        no_chip_horizon_points=60.0,
    )

    result = _decision_payload(action, squad, squad)

    assert len(result["starting_ids"]) == 11
    assert len(result["bench_order"]) == 4
    assert result["captain_id"] in result["starting_ids"]
    assert result["vice_captain_id"] in result["starting_ids"]
    assert result["chip"] is None
    assert result["transfer"]["hit_selected"] is False
    assert result["transfers"] == []
    assert result["transfer_count"] == 0
    assert result["total_hit_cost"] == 0


def _decision_center_fixture(include_no_action: bool = True) -> dict:
    players = [
        {
            "element_id": player_id,
            "name": f"Player {player_id}",
            "web_name": f"P{player_id}",
            "team": f"T{player_id % 5}",
            "position": (
                "GKP"
                if player_id <= 2
                else "DEF"
                if player_id <= 7
                else "MID"
                if player_id <= 12
                else "FWD"
            ),
            "price": 5.0,
            "start_likelihood": 0.9,
            "projections": [
                {
                    "gameweek": 2,
                    "projected_points": float(player_id),
                    "blank": False,
                    "double": False,
                }
            ],
        }
        for player_id in range(1, 16)
    ]
    selected = {
        "branch_id": "selected",
        "selected": True,
        "chip": None,
        "chip_key": "none",
        "transfers": [
            {
                "outgoing_id": 1,
                "outgoing_name": "Player 1",
                "incoming_id": 16,
                "incoming_name": "Player 16",
                "projected_gain": 3.0,
                "hit_cost": 4,
            }
        ],
        "transfer_count": 1,
        "hit_cost": 4,
        "starting_ids": list(range(1, 12)),
        "bench_order": [12, 13, 14, 15],
        "captain_id": 11,
        "vice_captain_id": 10,
        "expected_gameweek_points": 70.0,
        "expected_horizon_points": 190.0,
        "future_opportunity_cost": 1.0,
        "uncertainty_penalty": 0.4,
        "search_score": 188.6,
        "reason": "Best legal full-state branch.",
    }
    no_action = {
        **selected,
        "branch_id": "no-action",
        "selected": False,
        "transfers": [],
        "transfer_count": 0,
        "hit_cost": 0,
        "expected_gameweek_points": 66.0,
        "expected_horizon_points": 184.0,
        "search_score": 184.0,
        "reason": "Keep the current squad and roll.",
    }
    return {
        "team_id": 123,
        "season_state": "in_season",
        "start_gameweek": 2,
        "horizon": 3,
        "rules_version": "rules-v1",
        "data_cutoff": "2026-08-17T00:00:00Z",
        "deadline": "2026-08-21T18:00:00Z",
        "squad": players,
        "player_pool": [],
        "decision": {"transfer_count": 1},
        "decision_evidence": {
            "state_before": {
                "bank": 1.5,
                "free_transfers": 1,
                "remaining_chips": ["wc1", "fh1"],
                "used_chips": [],
            },
            "branches": [selected, *([no_action] if include_no_action else [])],
        },
    }


def test_decision_center_compares_selected_branch_with_exact_no_action_control():
    result = _decision_center_payload(_decision_center_fixture())

    assert result["status"] == "ready"
    assert result["recommendation"]["transfer_count"] == 1
    assert result["recommendation"]["hit_recommended"] is True
    assert result["recommendation"]["gain_vs_no_action"] == 6.0
    assert result["recommendation"]["confidence"] == "high"
    assert len(result["recommendation"]["starting_xi"]) == 11
    assert len(result["recommendation"]["bench_order"]) == 4
    assert result["no_action"]["expected_horizon_points"] == 184.0


def test_decision_center_fails_closed_without_no_action_control():
    result = _decision_center_payload(_decision_center_fixture(include_no_action=False))

    assert result["status"] == "unavailable"
    assert "no-action branch" in result["message"]
    assert "recommendation" not in result
