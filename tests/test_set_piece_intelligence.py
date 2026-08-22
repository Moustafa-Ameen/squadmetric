import pandas as pd

from fpl_intelligence.fetch_fpl import load_players
from fpl_intelligence.set_piece_intelligence import (
    build_set_piece_context,
    normalized_role_shares,
    set_piece_transition_adjustment,
)


def _row(
    code: int,
    *,
    team_code: int = 10,
    penalty_order: int | None = None,
    corner_order: int | None = None,
) -> dict:
    return {
        "player_code": code,
        "team_code": team_code,
        "position": "MID",
        "status": "a",
        "start_likelihood": 1.0,
        "availability_probability": 1.0,
        "penalties_order": penalty_order,
        "direct_freekicks_order": None,
        "corners_and_indirect_freekicks_order": corner_order,
    }


def _bootstrap(elements: list[dict], *, team_code: int = 10) -> dict:
    return {
        "teams": [{"id": 1, "code": team_code, "name": "Team", "short_name": "TST"}],
        "element_types": [
            {"id": 3, "singular_name": "Midfielder", "singular_name_short": "MID"}
        ],
        "elements": [
            {
                "id": index,
                "code": row["code"],
                "team": 1,
                "element_type": 3,
                "status": "a",
                "penalties_order": row.get("penalties_order"),
                "direct_freekicks_order": row.get("direct_freekicks_order"),
                "corners_and_indirect_freekicks_order": row.get("corner_order"),
            }
            for index, row in enumerate(elements, start=1)
        ],
    }


def test_raw_order_is_normalized_within_team_and_category():
    roles = normalized_role_shares(
        [_row(101, corner_order=5), _row(102, corner_order=6)],
        "corners_indirect_free_kicks",
        availability_adjusted=True,
    )

    assert roles[101]["raw_order"] == 5
    assert roles[101]["normalized_rank"] == 1
    assert roles[102]["normalized_rank"] == 2
    assert roles[101]["role_share"] > roles[102]["role_share"]


def test_unchanged_primary_penalty_role_is_not_double_counted():
    previous = _bootstrap(
        [
            {"code": 101, "penalties_order": 1},
            {"code": 102, "penalties_order": 2},
        ]
    )
    current = [_row(101, penalty_order=1), _row(102, penalty_order=2)]
    context = build_set_piece_context(current, previous)

    adjustment = set_piece_transition_adjustment(current[0], context)

    assert adjustment.available
    assert adjustment.penalty_adjustment == 0.0
    assert adjustment.total_adjustment == 0.0


def test_new_primary_role_receives_positive_transition_adjustment():
    previous = _bootstrap(
        [
            {"code": 101, "penalties_order": None},
            {"code": 102, "penalties_order": 1},
        ]
    )
    current = [_row(101, penalty_order=1), _row(102, penalty_order=2)]
    context = build_set_piece_context(current, previous)

    adjustment = set_piece_transition_adjustment(current[0], context)

    assert adjustment.penalty_adjustment > 0
    assert adjustment.roles["penalties"]["current_rank"] == 1
    assert adjustment.roles["penalties"]["previous_rank"] is None


def test_promoted_team_without_prior_contract_remains_unadjusted():
    previous = _bootstrap([{"code": 999, "penalties_order": 1}], team_code=10)
    player = _row(201, team_code=20, penalty_order=1)
    context = build_set_piece_context([player], previous)

    adjustment = set_piece_transition_adjustment(player, context)

    assert not adjustment.available
    assert adjustment.reason == "promoted_team_prior_unavailable"
    assert adjustment.total_adjustment == 0.0


def test_bootstrap_normalization_preserves_orders_and_missing_values():
    bootstrap = {
        "elements": [
            {
                "id": 1,
                "code": 101,
                "first_name": "Penalty",
                "second_name": "Taker",
                "team": 1,
                "element_type": 3,
                "now_cost": 80,
                "web_name": "Taker",
                "total_points": 100,
                "points_per_game": "5.0",
                "form": "0.0",
                "minutes": 2000,
                "selected_by_percent": "10.0",
                "penalties_order": 1,
                "direct_freekicks_order": None,
                "corners_and_indirect_freekicks_order": 5,
            }
        ],
        "teams": [{"id": 1, "name": "Team", "short_name": "TST"}],
        "element_types": [{"id": 3, "singular_name": "Midfielder"}],
    }

    players = load_players(bootstrap)

    assert players.loc[0, "player_code"] == 101
    assert players.loc[0, "penalties_order"] == 1
    assert pd.isna(players.loc[0, "direct_freekicks_order"])
    assert players.loc[0, "corners_and_indirect_freekicks_order"] == 5
