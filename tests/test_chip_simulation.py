import pandas as pd
import pytest

from squadmetric.chip_simulation import (
    ChipDefinition,
    DeterministicChipPlanner,
    apply_chip,
    apply_chip_to_score,
    apply_squad_transition,
    assistant_manager_expected_points,
    chip_definitions,
    chip_replaces_ordinary_transfer,
    initial_chip_state,
    legal_chip_options,
)
from squadmetric.season_rules import build_historical_season_rules


def test_historical_chip_inventories_are_manifest_driven():
    rules = build_historical_season_rules("2025-26")
    definitions = chip_definitions(rules)

    assert len(definitions) == 8
    assert {chip.name for chip in definitions} == {"wildcard", "freehit", "bboost", "3xc"}
    assert {chip.number for chip in definitions} == {1, 2}
    assert rules.chip_reset_gameweek == 19


def test_one_chip_per_gameweek_and_used_chips_cannot_return():
    rules = build_historical_season_rules("2025-26")
    state = initial_chip_state(rules)
    chip = next(chip for chip in chip_definitions(rules) if chip.name == "3xc" and chip.number == 1)

    state = apply_chip(state, chip, 1, rules)
    assert state.used == ("3xc:1",)
    assert legal_chip_options(state, 1, rules) == ()
    assert chip.key not in state.remaining
    with pytest.raises(ValueError, match="not available"):
        apply_chip(state, chip, 2, rules)


def test_2026_free_hit_gw19_blocks_the_second_free_hit_in_gw20():
    rules = build_historical_season_rules("2025-26")
    state = initial_chip_state(rules)
    first = next(
        chip
        for chip in chip_definitions(rules)
        if chip.name == "freehit" and chip.number == 1
    )

    state = apply_chip(state, first, 19, rules)
    assert all(
        not (chip.name == "freehit" and chip.number == 2)
        for chip in legal_chip_options(state, 20, rules)
    )


def test_chip_score_effects_are_exact_and_independent():
    triple = ChipDefinition("3xc", 1, 1, 38, captain_multiplier=3)
    bench = ChipDefinition("bboost", 1, 1, 38, bench_points_included=True)

    assert apply_chip_to_score(50, 10, chip=None) == 50
    assert apply_chip_to_score(50, 10, chip=triple) == 60
    assert apply_chip_to_score(50, 10, chip=bench, bench_points=17) == 67


def test_wildcard_is_permanent_and_free_hit_reverts_after_the_gameweek():
    original = pd.DataFrame({"player_id": [1, 2]})
    replacement = pd.DataFrame({"player_id": [3, 4]})
    wildcard = next(
        chip
        for chip in chip_definitions(build_historical_season_rules("2025-26"))
        if chip.name == "wildcard" and chip.number == 1
    )
    free_hit = next(
        chip
        for chip in chip_definitions(build_historical_season_rules("2025-26"))
        if chip.name == "freehit" and chip.number == 1
    )

    _, wildcard_retained = apply_squad_transition(original, replacement, wildcard)
    _, free_hit_retained = apply_squad_transition(original, replacement, free_hit)
    assert wildcard_retained["player_id"].tolist() == [3, 4]
    assert free_hit_retained["player_id"].tolist() == [1, 2]


def test_only_wildcard_and_free_hit_replace_ordinary_transfers():
    definitions = chip_definitions(build_historical_season_rules("2025-26"))
    by_name = {chip.name: chip for chip in definitions if chip.number == 1}

    assert not chip_replaces_ordinary_transfer(None)
    assert chip_replaces_ordinary_transfer(by_name["wildcard"])
    assert chip_replaces_ordinary_transfer(by_name["freehit"])
    assert not chip_replaces_ordinary_transfer(by_name["bboost"])
    assert not chip_replaces_ordinary_transfer(by_name["3xc"])


def test_chip_counterfactuals_explain_selection_and_rejection():
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
                }
            )
            player_id += 1
    squad = pd.DataFrame(rows)
    rules = build_historical_season_rules("2025-26")
    decision, selected, _ = DeterministicChipPlanner().decide(
        initial_chip_state(rules),
        1,
        squad,
        squad.copy(),
        {},
        bank=0.0,
        rules=rules,
        no_chip_squad=squad.copy(),
    )

    assert selected is not None
    assert any(item.status == "selected" for item in decision.counterfactuals)
    assert all(item.reason for item in decision.counterfactuals)
    assert any(item.status == "rejected" for item in decision.counterfactuals)


def test_free_hit_values_a_blank_gameweek_against_the_retained_squad():
    def squad_rows(start_id: int, expected: float) -> list[dict[str, object]]:
        rows = []
        player_id = start_id
        for position, count in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]:
            for index in range(count):
                rows.append(
                    {
                        "player_id": player_id,
                        "player_name": f"Player {player_id}",
                        "position": position,
                        "team": f"{position} Team {start_id}-{index}",
                        "price": 5.0,
                        "expected_points_adjusted": expected,
                        "probability_60_plus_minutes": 1.0,
                    }
                )
                player_id += 1
        return rows

    low = pd.DataFrame(squad_rows(1, 0.0))
    high = pd.DataFrame(squad_rows(101, 5.0))
    future_low = low.copy()
    future_low["expected_points_adjusted"] = 5.0
    rules = build_historical_season_rules("2025-26")
    decision, selected, _ = DeterministicChipPlanner().decide(
        initial_chip_state(rules),
        2,
        low,
        pd.concat([low, high], ignore_index=True),
        {3: future_low, 4: future_low},
        bank=0.0,
        rules=rules,
        no_chip_squad=low,
    )

    assert selected is not None
    assert selected.name == "freehit"
    assert decision.expected_horizon_points > decision.no_chip_horizon_points
    free_hit = next(
        item
        for item in decision.counterfactuals
        if item.chip_key.startswith("freehit:")
    )
    assert free_hit.expected_horizon_points > free_hit.no_chip_horizon_points


def test_assistant_manager_contract_uses_official_components():
    assert assistant_manager_expected_points(
        wins=2,
        draws=1,
        team_goals=3,
        clean_sheets=2,
        table_bonus=15,
    ) == 37.0


def test_missing_bench_points_do_not_become_zero_as_real_points():
    target = pd.DataFrame(
        {
            "player_id": [1, 2],
            "next_gameweek_points": [5.0, pd.NA],
        }
    )
    from squadmetric.chip_simulation import bench_points_not_autosubbed

    assert bench_points_not_autosubbed(target, (1, 2), ()) == 5.0
