import pandas as pd
from api.manager_state import (
    apply_target_gameweek_transfers,
    build_manager_decision_state,
    current_bank_value,
    infer_free_transfers,
)


def test_free_transfers_roll_and_are_retained_through_wildcard():
    history = {
        "current": [
            {"event": 1, "event_transfers": 0},
            {"event": 2, "event_transfers": 0},
            {"event": 3, "event_transfers": 14},
        ],
        "chips": [{"name": "wildcard", "event": 3}],
    }

    assert infer_free_transfers(
        target_gameweek=4,
        team_history=history,
        transfers=[],
        max_free_transfers=5,
    ) == 2


def test_late_joiner_does_not_receive_pre_entry_free_transfers():
    history = {
        "current": [{"event": 3, "event_transfers": 0}],
        "chips": [],
    }

    assert infer_free_transfers(
        target_gameweek=4,
        team_history=history,
        transfers=[],
        max_free_transfers=5,
    ) == 1


def test_current_gameweek_transfers_update_squad_bank_and_remaining_frees():
    transfers = [
        {
            "event": 4,
            "element_out": 10,
            "element_out_cost": 54,
            "element_in": 12,
            "element_in_cost": 50,
            "time": "2026-09-11T08:00:00Z",
        }
    ]

    assert infer_free_transfers(
        target_gameweek=4,
        team_history={
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0},
            ],
            "chips": [],
        },
        transfers=transfers,
        max_free_transfers=5,
    ) == 2
    assert apply_target_gameweek_transfers(
        picks=[{"element": 10, "position": 1}, {"element": 11, "position": 2}],
        transfers=transfers,
        target_gameweek=4,
    ) == [{"element": 12, "position": 1}, {"element": 11, "position": 2}]
    assert current_bank_value(
        last_deadline_bank=10,
        transfers=transfers,
        target_gameweek=4,
    ) == 1.4


def test_manager_state_uses_transfer_cost_then_opening_price_and_derives_sale():
    state = build_manager_decision_state(
        target_gameweek=4,
        picks=[{"element": 10}, {"element": 11}],
        team_history={"current": [], "chips": []},
        transfers=[
            {
                "event": 2,
                "element_in": 10,
                "element_in_cost": 50,
                "time": "2026-08-22T10:00:00Z",
            }
        ],
        projected_players=[
            {"element_id": 10, "price": 5.4},
            {"element_id": 11, "price": 6.1},
        ],
        serving_history=pd.DataFrame(
            [
                {
                    "season": "2026-27",
                    "gameweek": 1,
                    "player_id": 10,
                    "price_before_deadline": 4.9,
                },
                {
                    "season": "2026-27",
                    "gameweek": 1,
                    "player_id": 11,
                    "price_before_deadline": 6.0,
                },
            ]
        ),
        max_free_transfers=5,
    )

    by_id = {pick["element"]: pick for pick in state.picks}
    assert state.price_basis_complete
    assert by_id[10]["purchase_price"] == 50
    assert by_id[10]["selling_price"] == 52
    assert by_id[11]["purchase_price"] == 60
    assert by_id[11]["selling_price"] == 60
