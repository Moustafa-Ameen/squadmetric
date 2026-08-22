from api import chip_recommendations

from fpl_intelligence.backtest_transfer_strategy import TransferDecision, TransferPlan
from fpl_intelligence.beam_search import BeamAction
from fpl_intelligence.chip_simulation import ChipDefinition, ChipState
from fpl_intelligence.season_rules import build_historical_season_rules


def _projected_players() -> list[dict]:
    rows = []
    player_id = 1
    for position, count in [("GKP", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
        for index in range(count):
            rows.append(
                {
                    "element_id": player_id,
                    "name": f"Player {player_id}",
                    "position": position,
                    "team_id": player_id,
                    "price": 5.0,
                    "projections": [
                        {
                            "gameweek": 2,
                            "projected_points": float(4 + index / 10),
                            "fixtures": [{"start_likelihood": 0.9}],
                        },
                        {
                            "gameweek": 3,
                            "projected_points": 4.0,
                            "fixtures": [{"start_likelihood": 0.9}],
                        },
                    ],
                }
            )
            player_id += 1
    return rows


def _empty_transfer() -> TransferDecision:
    return TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)


def test_live_chip_state_removes_used_slot_and_preserves_second_half_slot():
    rules = build_historical_season_rules("2025-26")
    state = chip_recommendations.build_live_chip_state(
        rules,
        {
            "chips": [
                {"chip_type": "freehit", "number": 1, "status": "used", "used_gameweek": 4}
            ]
        },
    )

    assert "freehit:1" not in state.remaining
    assert "freehit:2" in state.remaining
    assert state.used_gameweeks == ((4, "freehit:1"),)


def test_projection_frames_normalize_gkp_and_retain_deadline_safe_values():
    frames = chip_recommendations.projection_frames(_projected_players())

    assert set(frames) == {2, 3}
    assert set(frames[2]["position"]) == {"GK", "DEF", "MID", "FWD"}
    assert frames[2].loc[0, "expected_points_adjusted"] == 4.0
    assert frames[2].loc[0, "probability_60_plus_minutes"] == 0.9


def test_live_recommendation_exposes_horizon_gain_and_metadata(monkeypatch):
    rules = build_historical_season_rules("2025-26")
    players = _projected_players()
    squad = chip_recommendations.squad_frame(
        [{"element": player["element_id"]} for player in players],
        players,
    )
    frames = chip_recommendations.projection_frames(players)
    bboost = ChipDefinition("bboost", 1, 1, 19, bench_points_included=True)

    class FakePlanner:
        version = "test-beam"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def decide(self, **kwargs):
            gameweek = kwargs["gameweek"]
            chip = bboost if gameweek == 2 else None
            return BeamAction(
                transfer_plan=TransferPlan.from_decision(_empty_transfer()),
                chip=chip,
                chip_squad=None,
                expected_points=70.0 if chip else 60.0,
                search_score=70.0 if chip else 60.0,
                reason="test chip branch" if chip else "test save branch",
                no_chip_expected_points=60.0,
                expected_horizon_points=100.0 if chip else 90.0,
                no_chip_horizon_points=90.0,
                uncertainty_penalty=1.0,
            )

    monkeypatch.setattr(chip_recommendations, "DeterministicBeamPlanner", FakePlanner)
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("bboost:1",),
    )

    result = chip_recommendations.recommend_live_chip(
        target_gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=state,
        rules=rules,
        frames=frames,
        data_cutoff="2025-08-29T17:30:00Z",
        projection_model_name="Gradient Boosting Regressor",
        portfolio_version="r2-consumer-portfolio-v1",
    )

    assert result["model_version"] == "test-beam"
    assert result["projection_model"] == "Gradient Boosting Regressor"
    assert result["portfolio_version"] == "r2-consumer-portfolio-v1"
    assert result["recommendation"]["action"] == "use"
    assert result["recommendation"]["chip"] == "Bench Boost"
    assert result["recommendation"]["expected_immediate_gain"] == 10.0
    assert result["recommendation"]["expected_horizon_gain"] == 10.0
    assert result["recommendation"]["transfers"] == []
    assert result["recommendation"]["transfer_count"] == 0
    assert result["data_cutoff"] == "2025-08-29T17:30:00Z"


def test_live_recommendation_can_return_save_with_future_alternative(monkeypatch):
    rules = build_historical_season_rules("2025-26")
    players = _projected_players()
    squad = chip_recommendations.squad_frame(
        [{"element": player["element_id"]} for player in players],
        players,
    )
    frames = chip_recommendations.projection_frames(players)

    class FakePlanner:
        version = "test-beam"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def decide(self, **kwargs):
            return BeamAction(
                transfer_plan=TransferPlan.from_decision(_empty_transfer()),
                chip=None,
                chip_squad=None,
                expected_points=50.0,
                search_score=50.0,
                reason="test save branch",
                no_chip_expected_points=50.0,
                expected_horizon_points=80.0,
                no_chip_horizon_points=80.0,
            )

    monkeypatch.setattr(chip_recommendations, "DeterministicBeamPlanner", FakePlanner)
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("bboost:1",),
    )

    result = chip_recommendations.recommend_live_chip(
        target_gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=state,
        rules=rules,
        frames=frames,
        data_cutoff=None,
    )

    assert result["recommendation"]["action"] == "save"
    assert result["recommendation"]["chip"] is None
