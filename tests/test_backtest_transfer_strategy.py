import pandas as pd
import pytest

from fpl_intelligence.backtest_transfer_strategy import (
    TwoGameweekLookaheadStrategy,
    build_initial_squad,
    build_preseason_scores,
    choose_transfer,
    score_gameweek,
    select_starting_xi,
    validate_squad,
)
from fpl_intelligence.season_benchmark import StrategyContext
from fpl_intelligence.step4_models import load_historical_player_gameweeks


def _squad_rows() -> list[dict[str, object]]:
    rows = []
    player_id = 1
    for position, count in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for index in range(count):
            rows.append(
                {
                    "player_id": player_id,
                    "player_name": f"Player {player_id}",
                    "position": position,
                    "team": f"{position} Team {index + 1}",
                    "price": 5.0,
                }
            )
            player_id += 1
    return rows


def test_preseason_scores_match_players_by_name_not_season_local_id():
    rows = []
    prior_players = [
        (1, "Alice Star", "MID", "A", 10),
        (2, "Bob Role", "MID", "B", 2),
    ]
    for player_id, name, position, team, points in prior_players:
        for gameweek in (1, 2):
            rows.append(
                {
                    "season": "2024-25",
                    "gameweek": gameweek,
                    "player_id": player_id,
                    "player_name": name,
                    "position": position,
                    "team": team,
                    "price": 5.0,
                    "price_before_deadline": 5.0,
                    "selected_by_percent": 1.0,
                    "total_points": points,
                    "minutes": 90,
                }
            )
    # The IDs are deliberately swapped in the following season.
    rows.extend(
        [
            {
                "season": "2025-26",
                "gameweek": 1,
                "player_id": 1,
                "player_name": "Bob Role",
                "position": "MID",
                "team": "B",
                "price": 5.0,
                "price_before_deadline": 5.0,
                "selected_by_percent": 1.0,
                "total_points": 0,
                "minutes": 0,
            },
            {
                "season": "2025-26",
                "gameweek": 1,
                "player_id": 2,
                "player_name": "Alice Star",
                "position": "MID",
                "team": "A",
                "price": 5.0,
                "price_before_deadline": 5.0,
                "selected_by_percent": 1.0,
                "total_points": 0,
                "minutes": 0,
            },
        ]
    )

    scored = build_preseason_scores(
        pd.DataFrame(rows),
        season="2025-26",
        prior_season="2024-25",
    ).set_index("player_id")

    assert scored.loc[2, "prior_player_id"] == 1
    assert scored.loc[1, "prior_player_id"] == 2
    assert scored.loc[2, "prior_points"] > scored.loc[1, "prior_points"]
    assert (
        scored.loc[2, "preseason_value_score"]
        > scored.loc[1, "preseason_value_score"]
    )


def _lookahead_context(future_player_101_points: float) -> StrategyContext:
    squad = pd.DataFrame(_squad_rows())
    current = squad.copy()
    current["expected_points_adjusted"] = 1.0
    current["decision_price"] = 5.0
    current = pd.concat(
        [
            current,
            pd.DataFrame(
                [
                    {
                        "player_id": 100,
                        "player_name": "Immediate Upgrade",
                        "position": "MID",
                        "team": "New Team",
                        "price": 5.0,
                        "decision_price": 5.0,
                        "expected_points_adjusted": 3.0,
                    },
                    {
                        "player_id": 101,
                        "player_name": "Future Upgrade",
                        "position": "MID",
                        "team": "Future Team",
                        "price": 5.0,
                        "decision_price": 5.0,
                        "expected_points_adjusted": 0.0,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    future = current.copy()
    future["expected_points_adjusted"] = 1.0
    future.loc[future["player_id"] == 100, "expected_points_adjusted"] = 3.0
    future.loc[future["player_id"] == 101, "expected_points_adjusted"] = future_player_101_points
    future["gameweek"] = 11
    future_2 = future.copy()
    future_2["gameweek"] = 12
    return StrategyContext(
        season="2024-25",
        gameweek=10,
        squad=squad,
        predictions=current,
        bank=0.0,
        free_transfers=1,
        available_data=pd.DataFrame(),
        free_transfer_cap=5,
        future_predictions={11: future, 12: future_2},
    )


def test_lookahead_banks_when_a_better_future_transfer_is_visible():
    decision = TwoGameweekLookaheadStrategy().decide(_lookahead_context(8.0))

    assert not decision.made


def test_lookahead_transfers_when_now_is_better_than_waiting():
    decision = TwoGameweekLookaheadStrategy().decide(_lookahead_context(0.0))

    assert decision.made
    assert decision.incoming_id == 100


def test_validate_squad_accepts_fpl_roster_shape_and_budget():
    squad = pd.DataFrame(_squad_rows())

    assert validate_squad(squad) == []


def test_validate_squad_reports_position_and_budget_violations():
    squad = pd.DataFrame(_squad_rows())
    squad.loc[0, "position"] = "DEF"
    squad.loc[1, "price"] = 100.0

    violations = validate_squad(squad)

    assert any("GK" in violation for violation in violations)
    assert any("above" in violation for violation in violations)


def test_choose_transfer_uses_adjusted_projection_and_budget():
    squad = pd.DataFrame(_squad_rows())
    incoming = {
        "player_id": 100,
        "player_name": "Upgrade",
        "position": "MID",
        "team": "New Team",
        "price": 5.5,
        "expected_points_adjusted": 6.0,
    }
    predictions = pd.concat(
        [
            squad.assign(expected_points_adjusted=1.0),
            pd.DataFrame([incoming]),
        ],
        ignore_index=True,
    )

    decision = choose_transfer(
        squad,
        predictions,
        bank=0.5,
        free_transfers=1,
        gain_threshold=2.0,
    )

    assert decision.made
    assert decision.incoming_id == 100
    assert decision.projected_gain == 5.0
    assert decision.hit_cost == 0


def test_choose_transfer_rejects_over_budget_move():
    squad = pd.DataFrame(_squad_rows())
    incoming = {
        "player_id": 100,
        "player_name": "Too Expensive",
        "position": "MID",
        "team": "New Team",
        "price": 6.0,
        "expected_points_adjusted": 8.0,
    }
    predictions = pd.concat(
        [
            squad.assign(expected_points_adjusted=1.0),
            pd.DataFrame([incoming]),
        ],
        ignore_index=True,
    )

    decision = choose_transfer(
        squad,
        predictions,
        bank=0.0,
        free_transfers=1,
        gain_threshold=2.0,
    )

    assert not decision.made


def test_score_gameweek_doubles_highest_scoring_starter_and_excludes_bench():
    squad = pd.DataFrame(_squad_rows())
    projections = {int(player_id): 1.0 for player_id in squad["player_id"]}
    lineup = select_starting_xi(squad, projections)
    target = squad[["player_id"]].copy()
    target["minutes"] = 90
    target["next_gameweek_points"] = 0
    target.loc[target["player_id"] == lineup.starting_ids[0], "next_gameweek_points"] = 5
    target.loc[target["player_id"].isin(lineup.starting_ids[1:]), "next_gameweek_points"] = 2
    target.loc[target["player_id"].isin(lineup.bench_ids), "next_gameweek_points"] = 100

    score = score_gameweek(squad, target, projections)

    assert score.raw_starter_points == 25
    assert score.points == 30
    assert score.captain_id == lineup.starting_ids[0]
    assert score.autosub_ids == ()


def test_score_gameweek_autosubs_a_non_playing_goalkeeper():
    squad = pd.DataFrame(_squad_rows())
    projections = {int(player_id): 1.0 for player_id in squad["player_id"]}
    lineup = select_starting_xi(squad, projections)
    bench_goalkeeper = next(
        player_id
        for player_id in lineup.bench_ids
        if squad.loc[squad["player_id"] == player_id, "position"].iloc[0] == "GK"
    )
    target = squad[["player_id"]].copy()
    target["minutes"] = 90
    target["next_gameweek_points"] = 1
    starting_goalkeeper = next(
        player_id
        for player_id in lineup.starting_ids
        if squad.loc[squad["player_id"] == player_id, "position"].iloc[0] == "GK"
    )
    target.loc[target["player_id"] == starting_goalkeeper, "minutes"] = 0
    target.loc[target["player_id"] == starting_goalkeeper, "next_gameweek_points"] = 0
    target.loc[target["player_id"] == bench_goalkeeper, "next_gameweek_points"] = 4

    score = score_gameweek(squad, target, projections)

    assert score.autosub_ids == (bench_goalkeeper,)
    assert bench_goalkeeper in score.starting_ids
    assert score.raw_starter_points == 14
    assert score.points == 18


@pytest.mark.requires_local_artifacts
def test_initial_squad_excludes_players_below_preseason_minutes_floor():
    players = load_historical_player_gameweeks()

    squad = build_initial_squad(players)

    assert (squad["prior_minutes"] >= 900).all()
