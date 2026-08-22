import pandas as pd
import pytest
from api.chip_recommendations import squad_frame

from fpl_intelligence.backtest_transfer_strategy import choose_transfer
from fpl_intelligence.chip_simulation import (
    apply_squad_transition,
    chip_definitions,
)
from fpl_intelligence.price_economics import (
    fpl_selling_price,
    initialise_incoming_player,
    initialise_squad_economics,
    refresh_squad_prices,
    squad_market_value,
    squad_selling_value,
)
from fpl_intelligence.season_rules import build_historical_season_rules


@pytest.mark.parametrize(
    ("purchase", "current", "expected"),
    [
        (5.0, 5.0, 5.0),
        (5.0, 5.1, 5.0),
        (5.0, 5.2, 5.1),
        (5.0, 5.3, 5.1),
        (5.0, 5.4, 5.2),
        (5.0, 4.9, 4.9),
        (5.0, 4.7, 4.7),
    ],
)
def test_fpl_selling_price_uses_half_profit_and_full_loss(
    purchase: float,
    current: float,
    expected: float,
):
    assert fpl_selling_price(purchase, current) == expected


def test_refresh_preserves_cost_basis_and_separates_market_from_selling_value():
    squad = pd.DataFrame(
        [
            {"player_id": 1, "price": 5.0},
            {"player_id": 2, "price": 6.0},
        ]
    )

    refreshed = refresh_squad_prices(
        initialise_squad_economics(squad),
        {1: 5.3, 2: 5.8},
    )

    first = refreshed.set_index("player_id").loc[1]
    second = refreshed.set_index("player_id").loc[2]
    assert first["purchase_price"] == 5.0
    assert first["current_price"] == 5.3
    assert first["selling_price"] == 5.1
    assert first["price"] == 5.1
    assert second["purchase_price"] == 6.0
    assert second["current_price"] == 5.8
    assert second["selling_price"] == 5.8
    assert squad_market_value(refreshed) == 11.1
    assert squad_selling_value(refreshed) == 10.9


def test_transfer_in_resets_purchase_price_to_the_acquisition_price():
    incoming = initialise_incoming_player(
        pd.Series({"player_id": 9, "price": 7.2}),
        7.0,
    )

    assert incoming["purchase_price"] == 7.0
    assert incoming["current_price"] == 7.0
    assert incoming["selling_price"] == 7.0
    assert incoming["price"] == 7.0


def test_transfer_budget_uses_selling_price_not_full_market_price():
    rows = []
    player_id = 1
    for position, count in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for index in range(count):
            rows.append(
                {
                    "player_id": player_id,
                    "player_name": f"Player {player_id}",
                    "position": position,
                    "team": f"{position} {index}",
                    "price": 5.0,
                }
            )
            player_id += 1
    squad = refresh_squad_prices(initialise_squad_economics(pd.DataFrame(rows)), {1: 5.4})
    predictions = squad.assign(expected_points_adjusted=1.0, decision_price=squad["price"])
    upgrade = pd.DataFrame(
        [
            {
                "player_id": 100,
                "player_name": "Unaffordable upgrade",
                "position": "GK",
                "team": "New club",
                "price": 5.3,
                "decision_price": 5.3,
                "expected_points_adjusted": 20.0,
            }
        ]
    )
    predictions = pd.concat([predictions, upgrade], ignore_index=True)

    decision = choose_transfer(
        squad,
        predictions,
        bank=0.0,
        free_transfers=1,
        gain_threshold=0.0,
    )

    assert squad.loc[squad["player_id"] == 1, "current_price"].iloc[0] == 5.4
    assert squad.loc[squad["player_id"] == 1, "selling_price"].iloc[0] == 5.2
    assert not decision.made


def test_live_squad_prefers_explicit_fpl_purchase_and_selling_prices():
    picks = [
        {
            "element": 10,
            "purchase_price": 50,
            "selling_price": 51,
        }
    ]
    players = [
        {
            "element_id": 10,
            "name": "Player Ten",
            "position": "MID",
            "team_id": 2,
            "price": 5.3,
            "start_likelihood": 0.9,
        }
    ]

    squad = squad_frame(picks, players)
    row = squad.iloc[0]

    assert row["purchase_price"] == 5.0
    assert row["current_price"] == 5.3
    assert row["selling_price"] == 5.1
    assert row["price"] == 5.1


def test_free_hit_restores_cost_basis_while_wildcard_keeps_new_cost_basis():
    rules = build_historical_season_rules("2023-24")
    definitions = {chip.name: chip for chip in chip_definitions(rules)}
    original = refresh_squad_prices(
        initialise_squad_economics(pd.DataFrame([{"player_id": 1, "price": 5.0}])),
        {1: 5.4},
    )
    replacement = initialise_squad_economics(pd.DataFrame([{"player_id": 2, "price": 5.3}]))

    _, free_hit_retained = apply_squad_transition(
        original,
        replacement,
        definitions["freehit"],
    )
    _, wildcard_retained = apply_squad_transition(
        original,
        replacement,
        definitions["wildcard"],
    )

    assert free_hit_retained.iloc[0]["purchase_price"] == 5.0
    assert free_hit_retained.iloc[0]["current_price"] == 5.4
    assert free_hit_retained.iloc[0]["selling_price"] == 5.2
    assert wildcard_retained.iloc[0]["purchase_price"] == 5.3
    assert wildcard_retained.iloc[0]["selling_price"] == 5.3
