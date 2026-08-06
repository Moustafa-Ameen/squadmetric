from pathlib import Path

import pandas as pd
import pytest

from fpl_intelligence.backtest_transfer_strategy import TransferDecision, select_starting_xi
from fpl_intelligence.chip_simulation import chip_definitions
from fpl_intelligence.season_benchmark import (
    DeterministicTransferStrategy,
    NoTransfersStrategy,
    StrategyContext,
    _assert_transfer_budget,
    _realized_chip_gain,
    append_decision_rows_to_history,
    append_result_to_history,
    get_training_data_for_season,
    load_historical_player_gameweeks,
    load_max_free_transfers,
    run_season_benchmark,
    score_gameweek,
    score_realistic_gameweek,
    train_future_gameweek_predictions,
    train_gameweek_predictions,
    train_realistic_captain_predictions,
)
from fpl_intelligence.season_rules import build_historical_season_rules


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


def test_strategy_interface_applies_hit_cost_and_budget_rule():
    squad = pd.DataFrame(_squad_rows())
    incoming = {
        "player_id": 100,
        "player_name": "Upgrade",
        "position": "MID",
        "team": "New Team",
        "price": 5.0,
        "expected_points_adjusted": 7.0,
    }
    predictions = pd.concat(
        [squad.assign(expected_points_adjusted=1.0), pd.DataFrame([incoming])],
        ignore_index=True,
    )
    context = StrategyContext(
        season="2024-25",
        gameweek=2,
        squad=squad,
        predictions=predictions,
        bank=0.0,
        free_transfers=0,
        available_data=pd.DataFrame(),
    )

    decision = DeterministicTransferStrategy(gain_threshold=0.0).decide(context)

    assert decision.made
    assert decision.hit_cost == 4
    assert decision.incoming_price <= decision.outgoing_price + context.bank


def test_benchmark_doubles_the_specific_highest_scoring_starter():
    squad = pd.DataFrame(_squad_rows())
    projections = {int(player_id): 1.0 for player_id in squad["player_id"]}
    lineup = select_starting_xi(squad, projections)
    starter_points = [2, 4, 6, 8, 10, 3, 5, 7, 9, 1, 6]
    points = dict(zip(lineup.starting_ids, starter_points, strict=True))
    target = squad[["player_id"]].copy()
    target["minutes"] = 90
    target["next_gameweek_points"] = target["player_id"].map(points).fillna(0)

    score = score_gameweek(squad, target, projections)

    assert score.captain_id == lineup.starting_ids[4]
    assert score.raw_starter_points == sum(starter_points)
    assert score.points == 71


def test_realized_chip_gain_uses_the_correct_counterfactual_squad():
    definitions = {
        chip.name: chip
        for chip in chip_definitions(build_historical_season_rules("2023-24"))
    }

    assert _realized_chip_gain(
        definitions["bboost"],
        scored_points=60.0,
        active_squad_base_points=50.0,
        no_chip_counterfactual_points=40.0,
    ) == 10.0
    assert _realized_chip_gain(
        definitions["freehit"],
        scored_points=60.0,
        active_squad_base_points=60.0,
        no_chip_counterfactual_points=45.0,
    ) == 15.0


def test_benchmark_excludes_deliberately_high_bench_points():
    squad = pd.DataFrame(_squad_rows())
    projections = {int(player_id): 1.0 for player_id in squad["player_id"]}
    lineup = select_starting_xi(squad, projections)
    starter_points = list(range(1, 12))
    bench_points = [15, 16, 17, 18]
    points = dict(zip(lineup.starting_ids, starter_points, strict=True))
    points.update(zip(lineup.bench_ids, bench_points, strict=True))
    target = squad[["player_id"]].copy()
    target["minutes"] = 90
    target["next_gameweek_points"] = target["player_id"].map(points)

    score = score_gameweek(squad, target, projections)

    expected_starter_total = sum(starter_points)
    assert score.raw_starter_points == expected_starter_total
    assert score.points == expected_starter_total + max(starter_points)
    assert score.points < expected_starter_total + sum(bench_points)


def test_benchmark_autosubs_an_eligible_playing_bench_player():
    squad = pd.DataFrame(_squad_rows())
    projections = {int(player_id): 1.0 for player_id in squad["player_id"]}
    lineup = select_starting_xi(squad, projections)
    starting_goalkeeper = next(
        player_id
        for player_id in lineup.starting_ids
        if squad.loc[squad["player_id"] == player_id, "position"].iloc[0] == "GK"
    )
    bench_goalkeeper = next(
        player_id
        for player_id in lineup.bench_ids
        if squad.loc[squad["player_id"] == player_id, "position"].iloc[0] == "GK"
    )
    target = squad[["player_id"]].copy()
    target["minutes"] = 90
    target["next_gameweek_points"] = 1
    target.loc[target["player_id"] == starting_goalkeeper, "minutes"] = 0
    target.loc[target["player_id"] == starting_goalkeeper, "next_gameweek_points"] = 0
    target.loc[target["player_id"] == bench_goalkeeper, "next_gameweek_points"] = 7

    score = score_gameweek(squad, target, projections)

    assert score.autosub_ids == (bench_goalkeeper,)
    assert bench_goalkeeper in score.starting_ids
    assert starting_goalkeeper not in score.starting_ids
    assert score.raw_starter_points == 17
    assert score.points == 24


def test_no_transfer_strategy_runs_a_complete_historical_season(tmp_path: Path):
    from fpl_intelligence.season_benchmark import NoTransfersStrategy

    players = load_historical_player_gameweeks()
    result = run_season_benchmark(
        players,
        "2023-24",
        NoTransfersStrategy(),
        model_version="test",
    )

    assert len(result.rows) == 38
    assert result.transfers_made == 0
    assert result.total_hit_cost == 0
    assert result.total_points > 0
    assert result.realistic_total_points > 0
    assert result.realistic_total_points != result.total_points
    assert result.rows["max_training_current_season_gameweek"].dropna().max() == 37
    assert result.rows["captain_max_training_current_season_gameweek"].dropna().max() == 37

    history_path = tmp_path / "season_benchmark_history.csv"
    assert append_result_to_history(result, history_path, run_id="run-1") is None
    previous = append_result_to_history(result, history_path, run_id="run-2")
    assert previous is not None
    history = pd.read_csv(history_path)
    assert len(history) == 2
    assert {
        "hindsight_total_points",
        "realistic_total_points",
        "captaincy_gap",
        "validation_status",
    }.issubset(history.columns)
    decision_path = append_decision_rows_to_history(
        result,
        history_path=history_path,
        run_id="run-1",
    )
    decision_history = pd.read_csv(decision_path)
    assert len(decision_history) == 38
    assert {
        "chip_counterfactuals",
        "squad_before_hash",
        "post_gameweek_squad_hash",
        "data_cutoff",
        "squad_ids",
        "active_squad_ids",
        "selected_starting_ids",
        "selected_bench_ids",
        "realistic_starting_ids",
        "realistic_autosub_ids",
        "outgoing_id",
        "incoming_id",
        "initial_squad_mode",
        "initial_squad_version",
        "initial_squad_hash",
    }.issubset(decision_history.columns)

    conditional_result = run_season_benchmark(
        players,
        "2023-24",
        NoTransfersStrategy(),
        model_version="test",
        minutes_mode="conditional_bands",
    )
    assert conditional_result.rows["minutes_model_mode"].eq("conditional_bands").all()
    assert conditional_result.realistic_total_points != result.realistic_total_points


def test_append_history_handles_old_narrow_schema(tmp_path: Path):
    players = load_historical_player_gameweeks()
    result = run_season_benchmark(
        players,
        "2023-24",
        NoTransfersStrategy(),
        model_version="test",
    )
    history_path = tmp_path / "old_history.csv"
    pd.DataFrame(
        [{"season": "2022-23", "strategy_name": "no-transfers", "total_points": 1.0}]
    ).to_csv(history_path, index=False)

    append_result_to_history(result, history_path, run_id="new-run")
    history = pd.read_csv(history_path)

    assert len(history) == 2
    assert set(history.columns) >= {
        "run_id",
        "commit_hash",
        "optimizer_version",
        "variant_name",
        "realistic_total_points",
    }
    assert history.iloc[0]["variant_name"] == "baseline"
    assert history.iloc[1]["run_id"] == "new-run"


def test_future_predictions_are_point_in_time_safe_for_both_horizons():
    players = load_historical_player_gameweeks()
    original = train_future_gameweek_predictions(
        players,
        "2024-25",
        10,
        horizons=tuple(range(1, 9)),
    )
    mutated = players.copy()
    future_mask = (mutated["season"] == "2024-25") & (mutated["gameweek"] >= 10)
    for column in (
        "minutes",
        "total_points",
        "next_gameweek_points",
        "expected_goals",
        "expected_assists",
    ):
        mutated.loc[future_mask, column] = 9999.0
    changed = train_future_gameweek_predictions(
        mutated,
        "2024-25",
        10,
        horizons=tuple(range(1, 9)),
    )

    assert set(original) == set(range(11, 19))
    for target_gameweek in (11, 12):
        assert not original[target_gameweek].empty
        assert original[target_gameweek]["as_of_gameweek"].eq(10).all()
        assert original[target_gameweek]["future_target_gameweek"].eq(target_gameweek).all()
        assert original[target_gameweek]["max_training_current_season_gameweek"].eq(9).all()
        assert not {"minutes", "total_points", "next_gameweek_points"}.intersection(
            original[target_gameweek].columns
        )
        pd.testing.assert_series_equal(
            original[target_gameweek]
            .set_index("player_id")["expected_points_adjusted"]
            .sort_index(),
            changed[target_gameweek]
            .set_index("player_id")["expected_points_adjusted"]
            .sort_index(),
            check_names=False,
        )


def test_component_projection_is_selectable_without_changing_control_default():
    players = load_historical_player_gameweeks()
    component_target, training = train_gameweek_predictions(
        players,
        "2024-25",
        10,
        feature_mode="xg_xa",
        projection_mode="components",
    )

    assert not training.empty
    assert component_target["projection_mode"].eq("components").all()
    assert component_target["model"].eq("Component Projection").all()
    assert "component_expected_points" in component_target
    assert component_target["expected_points_adjusted"].ge(0).all()

    control_target, _ = train_gameweek_predictions(players, "2024-25", 10)
    assert control_target["projection_mode"].eq("total_points").all()
    assert control_target["model"].eq("Ridge Regression").all()


def test_m10_team_components_mode_is_opt_in_and_point_in_time_safe():
    players = load_historical_player_gameweeks()
    target, training = train_gameweek_predictions(
        players,
        "2024-25",
        10,
        feature_mode="xg_xa",
        projection_mode="m10_team_components",
    )

    assert not training.empty
    assert target["projection_mode"].eq("m10_team_components").all()
    assert target["model"].eq("M10 Team Components").all()
    assert target["expected_points_adjusted"].ge(0).all()
    assert target["team_forecast_model_version"].eq("m10-team-poisson-v1").all()
    assert target["component_bridge_model_version"].eq("m10-player-components-v1").all()

    mutated = players.copy()
    future_mask = (mutated["season"] == "2024-25") & (mutated["gameweek"] >= 10)
    mutated.loc[future_mask, ["expected_goals", "expected_assists"]] = 9999.0
    changed, _ = train_gameweek_predictions(
        mutated,
        "2024-25",
        10,
        feature_mode="xg_xa",
        projection_mode="m10_team_components",
    )
    pd.testing.assert_series_equal(
        target.set_index("player_id")["expected_points_adjusted"].sort_index(),
        changed.set_index("player_id")["expected_points_adjusted"].sort_index(),
        check_names=False,
    )

    future = train_future_gameweek_predictions(
        players,
        "2024-25",
        10,
        feature_mode="xg_xa",
        projection_mode="m10_team_components",
        horizons=(1, 2),
    )
    assert future[11]["projection_mode"].eq("m10_team_components").all()
    assert future[11]["team_forecast_data_cutoff"].eq("2024-25:GW10").all()


def test_availability_role_mode_exposes_point_in_time_role_probabilities():
    players = load_historical_player_gameweeks()
    target, training = train_gameweek_predictions(
        players,
        "2024-25",
        10,
        minutes_mode="availability_role",
    )

    assert not training.empty
    assert target["minutes_model_mode"].eq("availability_role").all()
    assert target["probability_start"].between(0, 1).all()
    assert target["probability_substitute"].between(0, 1).all()
    assert target["probability_60_plus_minutes"].between(0, 1).all()
    assert target["expected_minutes_if_start"].between(0, 90).all()
    assert int(training[training["season"] == "2024-25"]["gameweek"].max()) == 9


def test_future_availability_role_predictions_freeze_role_features_at_decision():
    players = load_historical_player_gameweeks()
    original = train_future_gameweek_predictions(
        players,
        "2024-25",
        10,
        minutes_mode="availability_role",
        horizons=(1, 2),
    )
    mutated = players.copy()
    future_mask = (mutated["season"] == "2024-25") & (mutated["gameweek"] > 10)
    mutated.loc[future_mask, "minutes"] = 9999.0
    changed = train_future_gameweek_predictions(
        mutated,
        "2024-25",
        10,
        minutes_mode="availability_role",
        horizons=(1, 2),
    )

    for gameweek in (11, 12):
        pd.testing.assert_series_equal(
            original[gameweek].set_index("player_id")["expected_minutes_if_start"].sort_index(),
            changed[gameweek].set_index("player_id")["expected_minutes_if_start"].sort_index(),
            check_names=False,
        )


def test_invalid_transfer_decision_is_represented_explicitly():
    decision = TransferDecision(
        outgoing_id=1,
        incoming_id=2,
        outgoing_name="Out",
        incoming_name="In",
        projected_gain=5.0,
        net_projected_gain=1.0,
        hit_cost=4,
        outgoing_price=4.0,
        incoming_price=6.0,
    )

    with pytest.raises(AssertionError, match="exceeds"):
        _assert_transfer_budget(pd.DataFrame(_squad_rows()), decision, bank=0.0)


def test_historical_transfer_caps_are_rule_versioned():
    assert load_max_free_transfers("2023-24") == 2
    assert load_max_free_transfers("2024-25") == 5
    assert load_max_free_transfers("2025-26") == 5


def test_realistic_captain_model_training_stops_before_target_gameweek():
    players = load_historical_player_gameweeks()
    target_gameweek = 10

    training = get_training_data_for_season(players, "2024-25", target_gameweek)
    captain_predictions = train_realistic_captain_predictions(players, "2024-25", target_gameweek)

    assert int(training[training["season"] == "2024-25"]["gameweek"].max()) == 9
    assert captain_predictions["captain_max_training_current_season_gameweek"].iloc[0] == 9
    assert not ((training["season"] == "2024-25") & (training["gameweek"] >= target_gameweek)).any()


def test_realistic_captaincy_uses_vice_captain_when_captain_does_not_play():
    from fpl_intelligence.backtest_transfer_strategy import select_starting_xi

    squad = pd.DataFrame(_squad_rows())
    projections = {int(player_id): 1.0 for player_id in squad["player_id"]}
    lineup = select_starting_xi(squad, projections)
    captain_id, vice_id = lineup.starting_ids[:2]

    target = squad[["player_id", "position"]].copy()
    target["minutes"] = 90
    target["next_gameweek_points"] = 1.0
    target.loc[target["player_id"] == captain_id, "minutes"] = 0
    target.loc[target["player_id"] == captain_id, "next_gameweek_points"] = 0
    target.loc[target["player_id"] == vice_id, "next_gameweek_points"] = 7

    captain_predictions = target[["player_id"]].copy()
    captain_predictions["captain_predicted_points"] = 1.0
    captain_predictions.loc[
        captain_predictions["player_id"] == captain_id, "captain_predicted_points"
    ] = 10.0
    captain_predictions.loc[
        captain_predictions["player_id"] == vice_id, "captain_predicted_points"
    ] = 9.0

    score = score_realistic_gameweek(
        squad,
        target,
        projections,
        captain_predictions,
    )

    assert score.captain_id == captain_id
    assert score.vice_captain_id == vice_id
    assert score.vice_captain_fallback is True
    assert score.captain_actual_points == 0
    assert score.vice_captain_actual_points == 7
    assert score.bench_ids == lineup.bench_ids
