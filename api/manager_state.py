"""Reconstruct decision-critical manager state from public FPL history.

The public entry endpoint does not expose the manager's current free-transfer
count or per-player purchase prices.  Both values affect legal transfer advice,
so they are derived from immutable transfer history instead of guessed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from fpl_intelligence.price_economics import fpl_selling_price, live_pick_price


@dataclass(frozen=True)
class ManagerDecisionState:
    free_transfers: int
    picks: tuple[dict[str, Any], ...]
    bank_value: float | None
    price_basis_complete: bool
    bank_basis_complete: bool
    missing_purchase_price_ids: tuple[int, ...]
    provenance: str = "public-transfer-history-v1"


def build_manager_decision_state(
    *,
    target_gameweek: int,
    picks: Sequence[Mapping[str, Any]],
    team_history: Mapping[str, Any] | None,
    transfers: Sequence[Mapping[str, Any]],
    projected_players: Sequence[Mapping[str, Any]],
    serving_history: pd.DataFrame,
    max_free_transfers: int,
    started_event: int | None = None,
    last_deadline_bank: Any = None,
) -> ManagerDecisionState:
    free_transfers = infer_free_transfers(
        target_gameweek=target_gameweek,
        team_history=team_history,
        transfers=transfers,
        max_free_transfers=max_free_transfers,
        started_event=started_event,
    )
    current_picks = apply_target_gameweek_transfers(
        picks=picks,
        transfers=transfers,
        target_gameweek=target_gameweek,
    )
    enriched, missing = enrich_pick_prices(
        picks=current_picks,
        transfers=transfers,
        projected_players=projected_players,
        serving_history=serving_history,
        initial_squad_gameweek=_initial_squad_gameweek(
            team_history, started_event=started_event
        ),
    )
    bank_value = current_bank_value(
        last_deadline_bank=last_deadline_bank,
        transfers=transfers,
        target_gameweek=target_gameweek,
    )
    return ManagerDecisionState(
        free_transfers=free_transfers,
        picks=tuple(enriched),
        bank_value=bank_value,
        price_basis_complete=not missing,
        bank_basis_complete=bank_value is not None,
        missing_purchase_price_ids=tuple(sorted(missing)),
    )


def infer_free_transfers(
    *,
    target_gameweek: int,
    team_history: Mapping[str, Any] | None,
    transfers: Sequence[Mapping[str, Any]],
    max_free_transfers: int,
    started_event: int | None = None,
) -> int:
    """Return free transfers still available in ``target_gameweek``.

    Managers enter GW2 with one free transfer.  Each ordinary gameweek adds one
    after transfers, capped by the current rules.  Wildcard and Free Hit retain
    the entering count rather than granting an extra transfer.
    """

    target = max(1, int(target_gameweek))
    cap = max(1, int(max_free_transfers))
    initial_gameweek = _initial_squad_gameweek(
        team_history, started_event=started_event
    )
    first_transfer_gameweek = max(2, initial_gameweek + 1)
    if target < first_transfer_gameweek:
        return 0
    available = 1
    transfer_counts = Counter(
        int(row.get("event") or 0)
        for row in transfers
        if int(row.get("event") or 0) > 0
    )
    current_rows = (team_history or {}).get("current", [])
    for row in current_rows:
        gameweek = int(row.get("event") or 0)
        if gameweek > 0 and gameweek not in transfer_counts:
            transfer_counts[gameweek] = int(row.get("event_transfers") or 0)
    retained_chip_gameweeks = {
        int(row.get("event") or 0)
        for row in (team_history or {}).get("chips", [])
        if str(row.get("name") or "").casefold().replace("_", "")
        in {"wildcard", "freehit"}
    }
    for gameweek in range(first_transfer_gameweek, target):
        if gameweek in retained_chip_gameweeks:
            continue
        available = min(cap, max(0, available - transfer_counts[gameweek]) + 1)
    if target not in retained_chip_gameweeks:
        available = max(0, available - transfer_counts[target])
    return available


def apply_target_gameweek_transfers(
    *,
    picks: Sequence[Mapping[str, Any]],
    transfers: Sequence[Mapping[str, Any]],
    target_gameweek: int,
) -> list[dict[str, Any]]:
    """Apply already-recorded target-GW moves to the previous deadline squad."""

    output = [dict(pick) for pick in picks]
    for transfer in sorted(transfers, key=lambda item: str(item.get("time") or "")):
        if int(transfer.get("event") or 0) != int(target_gameweek):
            continue
        outgoing = int(transfer.get("element_out") or 0)
        incoming = int(transfer.get("element_in") or 0)
        for pick in output:
            if int(pick.get("element") or 0) == outgoing:
                pick["element"] = incoming
                pick.pop("purchase_price", None)
                pick.pop("selling_price", None)
                break
    return output


def current_bank_value(
    *,
    last_deadline_bank: Any,
    transfers: Sequence[Mapping[str, Any]],
    target_gameweek: int,
) -> float | None:
    """Adjust last deadline's bank for moves already made this Gameweek."""

    if last_deadline_bank is None:
        return None
    bank_tenths = int(last_deadline_bank)
    for transfer in transfers:
        if int(transfer.get("event") or 0) != int(target_gameweek):
            continue
        outgoing_cost = transfer.get("element_out_cost")
        incoming_cost = transfer.get("element_in_cost")
        if outgoing_cost is None or incoming_cost is None:
            return None
        bank_tenths += int(outgoing_cost) - int(incoming_cost)
    return round(bank_tenths / 10, 1)


def enrich_pick_prices(
    *,
    picks: Sequence[Mapping[str, Any]],
    transfers: Sequence[Mapping[str, Any]],
    projected_players: Sequence[Mapping[str, Any]],
    serving_history: pd.DataFrame,
    initial_squad_gameweek: int = 1,
) -> tuple[list[dict[str, Any]], set[int]]:
    """Attach exact purchase/selling prices where public evidence permits."""

    current_prices = {
        int(player["element_id"]): float(player["price"])
        for player in projected_players
        if player.get("element_id") is not None and player.get("price") is not None
    }
    latest_incoming: dict[int, Mapping[str, Any]] = {}
    for row in sorted(transfers, key=lambda item: str(item.get("time") or "")):
        player_id = row.get("element_in")
        if player_id is not None:
            latest_incoming[int(player_id)] = row
    opening_prices = _initial_squad_prices(
        serving_history, gameweek=initial_squad_gameweek
    )

    output: list[dict[str, Any]] = []
    missing: set[int] = set()
    for raw_pick in picks:
        pick = dict(raw_pick)
        player_id = int(pick.get("element") or 0)
        current = current_prices.get(player_id)
        explicit_purchase = live_pick_price(pick.get("purchase_price"))
        incoming = latest_incoming.get(player_id)
        incoming_purchase = (
            live_pick_price(incoming.get("element_in_cost")) if incoming else None
        )
        purchase = explicit_purchase or incoming_purchase or opening_prices.get(player_id)
        if purchase is None or current is None:
            missing.add(player_id)
        else:
            selling = fpl_selling_price(purchase, current)
            pick["purchase_price"] = int(round(purchase * 10))
            pick["selling_price"] = int(round(selling * 10))
        output.append(pick)
    return output, missing


def _initial_squad_gameweek(
    team_history: Mapping[str, Any] | None, *, started_event: int | None = None
) -> int:
    if started_event is not None and int(started_event) > 0:
        return int(started_event)
    events = [
        int(row.get("event") or 0)
        for row in (team_history or {}).get("current", [])
        if int(row.get("event") or 0) > 0
    ]
    return min(events, default=1)


def _initial_squad_prices(history: pd.DataFrame, *, gameweek: int) -> dict[int, float]:
    required = {"season", "gameweek", "player_id", "price_before_deadline"}
    if history.empty or not required.issubset(history.columns):
        return {}
    rows = history.copy()
    rows["gameweek"] = pd.to_numeric(rows["gameweek"], errors="coerce")
    rows["player_id"] = pd.to_numeric(rows["player_id"], errors="coerce")
    rows["price_before_deadline"] = pd.to_numeric(
        rows["price_before_deadline"], errors="coerce"
    )
    rows = rows[rows["season"] == rows["season"].max()]
    rows = rows[rows["gameweek"] == int(gameweek)].dropna(
        subset=["player_id", "price_before_deadline"]
    )
    return {
        int(row.player_id): float(row.price_before_deadline)
        for row in rows.itertuples()
    }
