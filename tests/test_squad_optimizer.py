import pandas as pd
import pytest

from fpl_intelligence.backtest_transfer_strategy import validate_squad
from fpl_intelligence.squad_optimizer import (
    optimize_squad,
    optimize_starting_xi,
    validate_squad_shape,
    validate_starting_xi,
)
from fpl_intelligence.step4_models import load_historical_player_gameweeks


@pytest.mark.requires_local_artifacts
def test_optimizer_returns_legal_squads_across_multiple_real_gameweeks():
    players = load_historical_player_gameweeks()
    for gameweek in (1, 5, 10, 20, 30):
        pool = players[
            (players["season"] == "2024-25") & (players["gameweek"] == gameweek)
        ].drop_duplicates("player_id").copy()
        pool["predicted_points"] = pool["total_points"]
        squad = optimize_squad(pool, prediction_column="predicted_points")

        assert validate_squad(squad) == []
        assert validate_squad_shape(squad) == []
        assert float(squad["price"].sum()) <= 100.0

        projections = squad.set_index("player_id")["predicted_points"].to_dict()
        lineup = optimize_starting_xi(squad, projections)
        assert validate_starting_xi(squad, lineup.starting_ids) == []
        assert len(lineup.bench_ids) == 4
        assert set(lineup.starting_ids).isdisjoint(lineup.bench_ids)


def test_optimizer_catches_illegal_squad_and_starting_xi_shapes():
    squad = pd.DataFrame(
        [
            {"player_id": index, "position": "MID", "team": "A", "price": 5.0}
            for index in range(15)
        ]
    )
    assert validate_squad_shape(squad)
    assert validate_starting_xi(squad, tuple(range(11)))


def test_optimizer_uses_projection_maximizing_legal_formation():
    rows = []
    player_id = 1
    for position, count in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(count):
            rows.append(
                {
                    "player_id": player_id,
                    "position": position,
                    "team": f"Team {player_id}",
                    "price": 5.0,
                }
            )
            player_id += 1
    squad = pd.DataFrame(rows)
    projections = {player_id: float(player_id) for player_id in squad["player_id"]}
    lineup = optimize_starting_xi(squad, projections)

    assert validate_starting_xi(squad, lineup.starting_ids) == []
    assert max(lineup.starting_ids) in lineup.starting_ids
    assert lineup.bench_ids[-1] in {1, 2}
