import pandas as pd
from api.routers.planner import _decision_payload

from fpl_intelligence.backtest_transfer_strategy import TransferDecision
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
        transfer=TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None),
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
