"""FPL purchase, market and selling-price accounting.

FPL does not let a manager spend the full current market value of a player who
has risen in price.  A manager receives GBP 0.1m for each complete GBP 0.2m of
profit, while price falls are absorbed in full.  Keeping these three prices
separate is therefore part of the decision state, not merely presentation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

PURCHASE_PRICE_COLUMN = "purchase_price"
CURRENT_PRICE_COLUMN = "current_price"
SELLING_PRICE_COLUMN = "selling_price"


def _to_tenths(value: float) -> int:
    """Convert a GBP-million price to integer tenths without float drift."""

    return int(round(float(value) * 10))


def fpl_selling_price(purchase_price: float, current_price: float) -> float:
    """Return the official FPL selling price in GBP millions.

    Price losses are realised in full.  For a price rise, only one tenth is
    banked for every complete two-tenths rise.
    """

    purchase = _to_tenths(purchase_price)
    current = _to_tenths(current_price)
    if current <= purchase:
        return current / 10
    return (purchase + (current - purchase) // 2) / 10


def initialise_squad_economics(squad: pd.DataFrame) -> pd.DataFrame:
    """Attach a complete economic state to newly purchased squad rows.

    Existing explicit purchase/current/selling columns are respected.  This
    lets the same function normalise both historical squads and live FPL picks.
    The legacy ``price`` column is retained as the spendable selling value so
    existing optimizer code cannot accidentally use full market value.
    """

    output = squad.copy()
    if "price" not in output:
        raise ValueError("Squad economics require a price column")

    base = pd.to_numeric(output["price"], errors="coerce")
    if base.isna().any():
        raise ValueError("Squad economics require numeric player prices")

    if PURCHASE_PRICE_COLUMN in output:
        purchase = pd.to_numeric(output[PURCHASE_PRICE_COLUMN], errors="coerce").fillna(base)
    else:
        purchase = base
    if CURRENT_PRICE_COLUMN in output:
        current = pd.to_numeric(output[CURRENT_PRICE_COLUMN], errors="coerce").fillna(base)
    else:
        current = base

    derived_selling = pd.Series(
        [fpl_selling_price(bought, now) for bought, now in zip(purchase, current, strict=True)],
        index=output.index,
        dtype=float,
    )
    if SELLING_PRICE_COLUMN in output:
        explicit_selling = pd.to_numeric(output[SELLING_PRICE_COLUMN], errors="coerce")
        selling = explicit_selling.fillna(derived_selling)
    else:
        selling = derived_selling

    output[PURCHASE_PRICE_COLUMN] = purchase.round(1)
    output[CURRENT_PRICE_COLUMN] = current.round(1)
    output[SELLING_PRICE_COLUMN] = selling.round(1)
    output["price"] = output[SELLING_PRICE_COLUMN]
    return output


def refresh_squad_prices(
    squad: pd.DataFrame,
    current_prices: Mapping[int, float],
) -> pd.DataFrame:
    """Refresh market and selling values without changing purchase prices."""

    output = initialise_squad_economics(squad)
    mapped = output["player_id"].map(current_prices)
    output[CURRENT_PRICE_COLUMN] = (
        pd.to_numeric(mapped, errors="coerce").fillna(output[CURRENT_PRICE_COLUMN]).round(1)
    )
    output[SELLING_PRICE_COLUMN] = [
        fpl_selling_price(bought, now)
        for bought, now in zip(
            output[PURCHASE_PRICE_COLUMN],
            output[CURRENT_PRICE_COLUMN],
            strict=True,
        )
    ]
    output["price"] = output[SELLING_PRICE_COLUMN]
    return output


def initialise_incoming_player(row: pd.Series, acquisition_price: float) -> pd.Series:
    """Return a transferred-in player with a fresh cost basis."""

    incoming = row.copy()
    price = round(float(acquisition_price), 1)
    incoming[PURCHASE_PRICE_COLUMN] = price
    incoming[CURRENT_PRICE_COLUMN] = price
    incoming[SELLING_PRICE_COLUMN] = price
    incoming["price"] = price
    return incoming


def squad_market_value(squad: pd.DataFrame) -> float:
    """Return the current market value of all owned players."""

    normalised = initialise_squad_economics(squad)
    return round(float(normalised[CURRENT_PRICE_COLUMN].sum()), 1)


def squad_selling_value(squad: pd.DataFrame) -> float:
    """Return the amount available if every owned player were sold."""

    normalised = initialise_squad_economics(squad)
    return round(float(normalised[SELLING_PRICE_COLUMN].sum()), 1)


def live_pick_price(value: Any) -> float | None:
    """Convert an FPL API price in tenths to GBP millions when present."""

    if value is None or value == "":
        return None
    return round(float(value) / 10, 1)
