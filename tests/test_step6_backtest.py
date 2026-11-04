import pandas as pd

from squadmetric.step6_backtest import get_training_data_for_gameweek


def test_training_data_for_gameweek_excludes_target_and_future_2025_26_rows():
    players = pd.DataFrame(
        {
            "season": ["2023-24", "2024-25", "2025-26", "2025-26", "2025-26"],
            "gameweek": [38, 38, 1, 2, 3],
            "player_id": [1, 1, 1, 1, 1],
        }
    )

    training_data = get_training_data_for_gameweek(players, target_gameweek=3)

    assert set(training_data["season"]) == {"2023-24", "2024-25", "2025-26"}
    assert training_data[training_data["season"] == "2025-26"]["gameweek"].max() == 2
    assert not (
        (training_data["season"] == "2025-26") & (training_data["gameweek"] >= 3)
    ).any()
