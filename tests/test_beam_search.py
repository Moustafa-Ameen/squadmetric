import pandas as pd

from fpl_intelligence.beam_search import (
    DeterministicBeamPlanner,
    _aggregate_horizon_predictions,
    _future_opportunity_cost,
    _prune_candidates,
    generate_transfer_options,
)
from fpl_intelligence.chip_simulation import (
    ChipState,
    apply_chip,
    build_chip_squad,
    chip_definitions,
)
from fpl_intelligence.season_rules import build_historical_season_rules


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
                    "team": f"{position} Team {index + 1}",
                    "price": 5.0,
                    "expected_points_adjusted": 1.0,
                    "probability_60_plus_minutes": 1.0,
                }
            )
            player_id += 1
    return pd.DataFrame(rows)


def test_transfer_branch_generation_is_legal_and_includes_control():
    squad = _squad()
    upgrade = squad.iloc[[5]].copy()
    upgrade["player_id"] = 100
    upgrade["player_name"] = "Upgrade"
    upgrade["team"] = "New Team"
    upgrade["expected_points_adjusted"] = 8.0
    predictions = pd.concat([squad, upgrade], ignore_index=True)

    options = generate_transfer_options(
        squad,
        predictions,
        bank=0.0,
        free_transfers=1,
        max_options=4,
    )

    assert options[0].made is False
    assert any(option.incoming_id == 100 for option in options)
    assert all(option.hit_cost == 0 for option in options if option.made)


def test_beam_search_is_reproducible_for_identical_inputs():
    squad = _squad()
    upgrade = squad.iloc[[5]].copy()
    upgrade["player_id"] = 100
    upgrade["player_name"] = "Upgrade"
    upgrade["team"] = "New Team"
    upgrade["expected_points_adjusted"] = 8.0
    predictions = pd.concat([squad, upgrade], ignore_index=True)
    rules = build_historical_season_rules("2025-26")
    chip_state = ChipState(
        season="2025-26",
        rules_version=rules.rules_version,
        remaining=(),
    )
    planner = DeterministicBeamPlanner(beam_width=4, horizon=2, max_transfers=4)

    first = planner.decide(
        gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=chip_state,
        predictions=predictions,
        future_predictions={3: predictions.copy()},
        rules=rules,
    )
    second = planner.decide(
        gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=chip_state,
        predictions=predictions,
        future_predictions={3: predictions.copy()},
        rules=rules,
    )

    assert first.transfer == second.transfer
    assert first.chip == second.chip
    assert first.reason == second.reason


def test_horizon_hit_policy_selects_a_worthwhile_four_point_hit():
    squad = _squad()
    upgrade = squad.iloc[[5]].copy()
    upgrade["player_id"] = 100
    upgrade["player_name"] = "Future Upgrade"
    upgrade["team"] = "New Team"
    upgrade["expected_points_adjusted"] = 2.0
    predictions = pd.concat([squad, upgrade], ignore_index=True)
    future = predictions.copy()
    future.loc[future["player_id"] == 100, "expected_points_adjusted"] = 12.0
    rules = build_historical_season_rules("2025-26")
    chip_state = ChipState(
        season="2025-26",
        rules_version=rules.rules_version,
        remaining=(),
    )

    current_policy = DeterministicBeamPlanner(
        beam_width=4,
        horizon=1,
        max_transfers=8,
        hit_policy="current_gw",
    ).decide(
        gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=0,
        chip_state=chip_state,
        predictions=predictions,
        future_predictions={3: future},
        rules=rules,
    )
    horizon_policy = DeterministicBeamPlanner(
        beam_width=4,
        horizon=1,
        max_transfers=8,
        hit_policy="horizon_value",
    ).decide(
        gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=0,
        chip_state=chip_state,
        predictions=predictions,
        future_predictions={3: future},
        rules=rules,
    )

    assert current_policy.transfer.made is False
    assert horizon_policy.transfer.incoming_id == 100
    assert horizon_policy.transfer.hit_cost == 4
    assert horizon_policy.transfer_expected_horizon_net_gain > 0
    assert horizon_policy.hit_policy == "horizon_value"


def test_wildcard_horizon_aggregation_values_future_fixture_swing():
    current = _squad().copy()
    future_player = current.iloc[[5]].copy()
    future_player["player_id"] = 100
    future_player["player_name"] = "Future Swing"
    current.loc[current["player_id"] == 6, "expected_points_adjusted"] = 1.0
    future_player["expected_points_adjusted"] = 8.0
    current_predictions = pd.concat([current, future_player], ignore_index=True)
    future = future_player.copy()
    future["expected_points_adjusted"] = 12.0

    aggregated = _aggregate_horizon_predictions(
        current_predictions,
        {2: future, 3: future},
        minimum_gameweeks=3,
    )

    future_value = float(
        aggregated.loc[aggregated["player_id"] == 100, "expected_points_adjusted"].iloc[0]
    )
    current_value = float(
        aggregated.loc[aggregated["player_id"] == 6, "expected_points_adjusted"].iloc[0]
    )
    assert future_value == 32.0
    assert current_value == 1.0


def test_candidate_pruning_retains_future_fixture_swing():
    squad = _squad()
    current = squad.copy()
    current["expected_points_adjusted"] = 1.0
    future_player = current.iloc[[5]].copy()
    future_player["player_id"] = 100
    future_player["player_name"] = "Future Swing"
    future_player["expected_points_adjusted"] = 15.0
    predictions = pd.concat([current, future_player], ignore_index=True)

    retained = _prune_candidates(
        predictions,
        squad,
        future_predictions={2: future_player},
        per_position=1,
    )

    assert 100 in set(retained["player_id"])


def test_pruned_wildcard_pool_matches_full_small_pool_oracle():
    squad = _squad()
    predictions = squad.copy()
    future_player = squad.iloc[[5]].copy()
    future_player["player_id"] = 100
    future_player["player_name"] = "Future Swing"
    future_player["expected_points_adjusted"] = 15.0
    predictions = pd.concat([predictions, future_player], ignore_index=True)
    future = {2: future_player}
    full_pool = _aggregate_horizon_predictions(predictions, future, minimum_gameweeks=2)
    pruned_pool = _aggregate_horizon_predictions(
        _prune_candidates(
            predictions,
            squad,
            future_predictions=future,
            per_position=1,
        ),
        future,
        minimum_gameweeks=2,
    )

    full_solution = build_chip_squad(full_pool, budget=75.0)
    pruned_solution = build_chip_squad(pruned_pool, budget=75.0)
    full_score = float(full_solution["expected_points_adjusted"].sum())
    pruned_score = float(pruned_solution["expected_points_adjusted"].sum())

    assert pruned_score == full_score


def test_future_opportunity_cost_values_saving_the_same_bench_boost():
    rules = build_historical_season_rules("2025-26")
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("bboost:1",),
    )
    current_chip_state = apply_chip(state, definitions["bboost:1"], 1, rules)
    squad = _squad()
    future = squad.copy()
    future["expected_points_adjusted"] = 1.0
    future.loc[future["player_id"] == 2, "expected_points_adjusted"] = 12.0

    cost = _future_opportunity_cost(
        state,
        chip=definitions["bboost:1"],
        future={2: future},
        retained_squad=squad,
        next_chip_state=current_chip_state,
        rules=rules,
        current_expected_gain=0.0,
    )

    assert cost > 0.0


def test_future_opportunity_cost_values_saving_the_same_triple_captain():
    rules = build_historical_season_rules("2025-26")
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("3xc:1",),
    )
    current_chip_state = apply_chip(state, definitions["3xc:1"], 1, rules)
    squad = _squad()
    future = squad.copy()
    future["expected_points_adjusted"] = 1.0
    future.loc[future["player_id"] == 8, "expected_points_adjusted"] = 12.0

    cost = _future_opportunity_cost(
        state,
        chip=definitions["3xc:1"],
        future={2: future},
        retained_squad=squad,
        next_chip_state=current_chip_state,
        rules=rules,
        current_expected_gain=1.0,
    )

    assert cost == 11.0


def test_future_opportunity_cost_does_not_borrow_value_from_another_chip():
    rules = build_historical_season_rules("2025-26")
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("bboost:1", "3xc:1"),
    )
    current_chip_state = apply_chip(state, definitions["bboost:1"], 1, rules)
    squad = _squad()
    future = squad.copy()
    future["expected_points_adjusted"] = 0.0
    future.loc[future["player_id"].isin([1, 2]), "expected_points_adjusted"] = 4.0
    future.loc[future["player_id"] == 8, "expected_points_adjusted"] = 20.0

    cost = _future_opportunity_cost(
        state,
        chip=definitions["bboost:1"],
        future={2: future},
        retained_squad=squad,
        next_chip_state=current_chip_state,
        rules=rules,
        current_expected_gain=0.0,
    )

    assert cost == 4.0


def test_future_opportunity_cost_respects_the_same_chip_availability_window():
    rules = build_historical_season_rules("2025-26")
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("bboost:1",),
    )
    current_chip_state = apply_chip(state, definitions["bboost:1"], 19, rules)
    squad = _squad()
    future = squad.copy()
    future["expected_points_adjusted"] = 1.0
    future.loc[future["player_id"] == 2, "expected_points_adjusted"] = 12.0

    cost = _future_opportunity_cost(
        state,
        chip=definitions["bboost:1"],
        future={20: future},
        retained_squad=squad,
        next_chip_state=current_chip_state,
        rules=rules,
        current_expected_gain=0.0,
    )

    assert cost == 0.0


def test_future_opportunity_cost_values_a_saved_free_hit_squad():
    rules = build_historical_season_rules("2025-26")
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("freehit:1",),
    )
    squad = _squad()
    future = squad.copy()
    future["expected_points_adjusted"] = 1.0
    upgrade = squad.iloc[[7]].copy()
    upgrade["player_id"] = 100
    upgrade["player_name"] = "Free Hit Upgrade"
    upgrade["team"] = "Free Hit Team"
    upgrade["expected_points_adjusted"] = 20.0
    future = pd.concat([future, upgrade], ignore_index=True)

    cost = _future_opportunity_cost(
        state,
        chip=definitions["freehit:1"],
        future={3: future},
        retained_squad=squad,
        rules=rules,
        current_expected_gain=0.0,
    )

    assert cost > 0.0


def test_future_opportunity_cost_values_a_saved_wildcard_horizon():
    rules = build_historical_season_rules("2025-26")
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("wildcard:1",),
    )
    squad = _squad()
    future = squad.copy()
    future["expected_points_adjusted"] = 1.0
    upgrade = squad.iloc[[7]].copy()
    upgrade["player_id"] = 100
    upgrade["player_name"] = "Wildcard Upgrade"
    upgrade["team"] = "Wildcard Team"
    upgrade["expected_points_adjusted"] = 10.0
    future = pd.concat([future, upgrade], ignore_index=True)
    later = future.copy()
    later.loc[later["player_id"] == 100, "expected_points_adjusted"] = 15.0

    cost = _future_opportunity_cost(
        state,
        chip=definitions["wildcard:1"],
        future={3: future, 4: later},
        retained_squad=squad,
        rules=rules,
        current_expected_gain=0.0,
    )

    assert cost > 0.0


def test_beam_saves_triple_captain_for_the_stronger_same_chip_window():
    rules = build_historical_season_rules("2025-26")
    chip_state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("3xc:1",),
    )
    squad = _squad()
    current = squad.copy()
    current["expected_points_adjusted"] = 1.0
    future = current.copy()
    future.loc[future["player_id"] == 8, "expected_points_adjusted"] = 12.0
    planner = DeterministicBeamPlanner(beam_width=4, horizon=1, max_transfers=2)

    save_action = planner.decide(
        gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=chip_state,
        predictions=current,
        future_predictions={3: future},
        rules=rules,
    )
    triple_captain_counterfactual = next(
        action
        for action in planner.last_counterfactuals
        if action.chip is not None and action.chip.key == "3xc:1"
    )

    assert save_action.chip is None
    assert triple_captain_counterfactual.future_opportunity_cost == 11.0

    use_action = planner.decide(
        gameweek=3,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=chip_state,
        predictions=future,
        future_predictions={},
        rules=rules,
    )

    assert use_action.chip is not None
    assert use_action.chip.key == "3xc:1"


def test_beam_does_not_double_charge_opportunities_inside_its_search_horizon():
    rules = build_historical_season_rules("2025-26")
    chip_state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("3xc:1",),
    )
    squad = _squad()
    current = squad.copy()
    current["expected_points_adjusted"] = 1.0
    future = current.copy()
    future.loc[future["player_id"] == 8, "expected_points_adjusted"] = 12.0
    planner = DeterministicBeamPlanner(beam_width=4, horizon=2, max_transfers=2)

    action = planner.decide(
        gameweek=2,
        squad=squad,
        bank=0.0,
        free_transfers=1,
        chip_state=chip_state,
        predictions=current,
        future_predictions={3: future},
        rules=rules,
    )
    triple_captain_counterfactual = next(
        candidate
        for candidate in planner.last_counterfactuals
        if candidate.chip is not None and candidate.chip.key == "3xc:1"
    )

    assert action.chip is None
    assert triple_captain_counterfactual.future_opportunity_cost == 0.0


def test_beam_exposes_one_counterfactual_per_legal_chip():
    squad = _squad()
    predictions = squad.copy()
    rules = build_historical_season_rules("2025-26")
    planner = DeterministicBeamPlanner(beam_width=2, horizon=1, max_transfers=2)
    planner.decide(
        gameweek=2,
        squad=squad,
        bank=25.0,
        free_transfers=1,
        chip_state=ChipState(
            season=rules.season,
            rules_version=rules.rules_version,
            remaining=tuple(chip.key for chip in chip_definitions(rules)),
        ),
        predictions=predictions,
        future_predictions={},
        rules=rules,
    )
    keys = {
        candidate.chip.key if candidate.chip else "none"
        for candidate in planner.last_counterfactuals
    }
    assert "none" in keys
    assert "wildcard:1" in keys
    assert "freehit:1" in keys
    assert "bboost:1" in keys
    assert "3xc:1" in keys


def test_beam_keeps_transfer_and_chip_projection_paths_separate():
    squad = _squad()
    transfer_upgrade = squad.iloc[[8]].copy()
    transfer_upgrade["player_id"] = 100
    transfer_upgrade["player_name"] = "Transfer Upgrade"
    transfer_upgrade["team"] = "New Team"
    transfer_upgrade["expected_points_adjusted"] = 8.0
    transfer_predictions = pd.concat([squad, transfer_upgrade], ignore_index=True)

    chip_low = transfer_predictions.copy()
    chip_low["expected_points_adjusted"] = 1.0
    chip_high = chip_low.copy()
    chip_high["expected_points_adjusted"] = 2.0
    rules = build_historical_season_rules("2025-26")
    chip_state = ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=("bboost:1",),
    )

    def run(chip_predictions: pd.DataFrame) -> DeterministicBeamPlanner:
        planner = DeterministicBeamPlanner(beam_width=4, horizon=1, max_transfers=4)
        planner.decide(
            gameweek=2,
            squad=squad,
            bank=0.0,
            free_transfers=1,
            chip_state=chip_state,
            predictions=transfer_predictions,
            future_predictions={},
            chip_predictions=chip_predictions,
            future_chip_predictions={},
            rules=rules,
        )
        return planner

    low_planner = run(chip_low)
    high_planner = run(chip_high)
    low_actions = {
        action.chip.key if action.chip else "none": action
        for action in low_planner.last_counterfactuals
    }
    high_actions = {
        action.chip.key if action.chip else "none": action
        for action in high_planner.last_counterfactuals
    }

    assert low_actions["none"].transfer.incoming_id == 100
    assert high_actions["none"].transfer.incoming_id == 100
    assert low_actions["bboost:1"].expected_points != high_actions["bboost:1"].expected_points
