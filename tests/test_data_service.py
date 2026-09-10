import pandas as pd
from api import data_service


def test_serving_history_combines_historical_and_current_rows(monkeypatch):
    historical = pd.DataFrame(
        [{"season": "2025-26", "gameweek": 38, "total_points": 2}]
    )
    live = pd.DataFrame(
        [{"season": "2026-27", "gameweek": 1, "next_gameweek_points": 7}]
    )
    monkeypatch.setattr(data_service, "historical_player_gw", lambda: historical.copy())
    monkeypatch.setattr(data_service, "live_current_player_gw", lambda: live.copy())

    result = data_service.serving_player_gw()

    assert list(result["season"]) == ["2025-26", "2026-27"]
    assert result.iloc[-1]["total_points"] == 7
