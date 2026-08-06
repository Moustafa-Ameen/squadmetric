"""Live chip recommendations backed by the benchmark decision engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from api.chip_tracking import CHIP_LABELS
from fpl_intelligence.beam_search import BeamAction, DeterministicBeamPlanner
from fpl_intelligence.chip_simulation import ChipState
from fpl_intelligence.season_rules import SeasonRules

LIVE_RULES_SOURCE = "https://fantasy.premierleague.com/api/bootstrap-static/"
MODEL_NAME = "Deterministic beam search"
MODEL_VERSION = DeterministicBeamPlanner.version


def build_live_chip_state(
    rules: SeasonRules,
    chip_status: Mapping[str, Any],
) -> ChipState:
    """Convert the API-facing chip inventory into the benchmark chip state."""

    definitions = {
        f"{str(raw.get('name', '')).lower().replace('_', '')}:{int(raw.get('number') or 1)}": raw
        for raw in rules.chips
    }
    used: list[str] = []
    used_gameweeks: list[tuple[int, str]] = []
    for row in chip_status.get("chips", []):
        if row.get("status") != "used" or row.get("used_gameweek") is None:
            continue
        chip_type = str(row.get("chip_type") or "").lower().replace("_", "")
        number = int(row.get("number") or 1)
        key = f"{chip_type}:{number}"
        if key in definitions and key not in used:
            used.append(key)
            used_gameweeks.append((int(row["used_gameweek"]), key))

    remaining = tuple(key for key in definitions if key not in used)
    return ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=remaining,
        used=tuple(used),
        used_gameweeks=tuple(sorted(used_gameweeks)),
    )


def projection_frames(
    projected_players: Sequence[Mapping[str, Any]],
) -> dict[int, pd.DataFrame]:
    """Convert live multi-gameweek projection dictionaries to benchmark frames."""

    rows_by_gameweek: dict[int, list[dict[str, Any]]] = {}
    for player in projected_players:
        player_id = player.get("element_id")
        if player_id is None:
            continue
        position = _position(player.get("position"))
        team_id = player.get("team_id")
        price = _number(player.get("price"))
        for projection in player.get("projections", []):
            gameweek = projection.get("gameweek")
            if gameweek is None:
                continue
            fixtures = projection.get("fixtures") or []
            start_likelihoods = [
                _number(fixture.get("start_likelihood"))
                for fixture in fixtures
                if fixture.get("start_likelihood") is not None
            ]
            rows_by_gameweek.setdefault(int(gameweek), []).append(
                {
                    "player_id": int(player_id),
                    "player_name": player.get("name") or player.get("web_name") or "Unknown",
                    "position": position,
                    "team": team_id,
                    "price": price,
                    "decision_price": price,
                    "expected_points_adjusted": _number(projection.get("projected_points")),
                    "probability_60_plus_minutes": (
                        sum(start_likelihoods) / len(start_likelihoods)
                        if start_likelihoods
                        else 0.0
                    ),
                }
            )

    return {
        gameweek: pd.DataFrame(rows).drop_duplicates("player_id", keep="last")
        for gameweek, rows in rows_by_gameweek.items()
    }


def squad_frame(
    picks: Sequence[Mapping[str, Any]],
    projected_players: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Build the typed 15-player squad frame required by the planner."""

    by_id = {
        int(player["element_id"]): player
        for player in projected_players
        if player.get("element_id")
    }
    rows = []
    for pick in picks:
        player_id = pick.get("element")
        if player_id is None or int(player_id) not in by_id:
            continue
        player = by_id[int(player_id)]
        rows.append(
            {
                "player_id": int(player_id),
                "player_name": player.get("name") or player.get("web_name") or "Unknown",
                "position": _position(player.get("position")),
                "team": player.get("team_id"),
                "price": _number(player.get("price")),
                "expected_points_adjusted": 0.0,
                "probability_60_plus_minutes": _number(player.get("start_likelihood")),
            }
        )
    return pd.DataFrame(rows)


def recommend_live_chip(
    *,
    target_gameweek: int,
    squad: pd.DataFrame,
    bank: float,
    free_transfers: int,
    chip_state: ChipState,
    rules: SeasonRules,
    frames: Mapping[int, pd.DataFrame],
    data_cutoff: str | None,
    projection_model_name: str = "Gradient Boosting Regressor",
    portfolio_version: str = "unversioned",
) -> dict[str, Any]:
    """Return the live recommendation and short-horizon alternative opportunity."""

    predictions = frames.get(target_gameweek, pd.DataFrame())
    if predictions.empty or len(squad) != 15:
        raise ValueError("Live chip recommendation requires a complete squad and projections")

    future = {
        gameweek: frame.copy()
        for gameweek, frame in frames.items()
        if gameweek > target_gameweek
    }
    planner = DeterministicBeamPlanner()
    action = planner.decide(
        gameweek=target_gameweek,
        squad=squad.copy(),
        bank=float(bank),
        free_transfers=int(free_transfers),
        chip_state=chip_state,
        predictions=predictions.copy(),
        future_predictions=future,
        rules=rules,
    )
    alternatives = _future_alternatives(
        target_gameweek=target_gameweek,
        squad=squad,
        bank=bank,
        free_transfers=free_transfers,
        chip_state=chip_state,
        rules=rules,
        frames=frames,
    )
    return _recommendation_payload(
        action,
        model_version=planner.version,
        counterfactuals=getattr(planner, "last_counterfactuals", ()),
        target_gameweek=target_gameweek,
        alternatives=alternatives,
        chip_state=chip_state,
        rules=rules,
        data_cutoff=data_cutoff,
        projection_model_name=projection_model_name,
        portfolio_version=portfolio_version,
    )


def _future_alternatives(
    *,
    target_gameweek: int,
    squad: pd.DataFrame,
    bank: float,
    free_transfers: int,
    chip_state: ChipState,
    rules: SeasonRules,
    frames: Mapping[int, pd.DataFrame],
) -> list[dict[str, Any]]:
    """Score future save opportunities with the same beam engine.

    A short one-gameweek search keeps the live endpoint bounded while retaining
    the same legality, transfer, chip, bank, and projection semantics as the
    benchmark's primary planner.
    """

    output = []
    future_gameweeks = sorted(gameweek for gameweek in frames if gameweek > target_gameweek)[:5]
    for gameweek in future_gameweeks:
        predictions = frames[gameweek]
        future = {
            future_gameweek: frame.copy()
            for future_gameweek, frame in frames.items()
            if future_gameweek > gameweek
        }
        try:
            action = DeterministicBeamPlanner(
                beam_width=2,
                horizon=1,
                max_transfers=3,
            ).decide(
                gameweek=gameweek,
                squad=squad.copy(),
                bank=float(bank),
                free_transfers=int(free_transfers),
                chip_state=chip_state,
                predictions=predictions.copy(),
                future_predictions=future,
                rules=rules,
            )
        except (ValueError, KeyError, IndexError):
            continue
        if action.chip is None:
            continue
        output.append(
            {
                "gameweek": gameweek,
                "chip_key": action.chip.key,
                "chip": _chip_label(action.chip.name),
                "expected_immediate_gain": _round(
                    action.expected_points - action.no_chip_expected_points
                ),
                "expected_horizon_gain": _round(
                    action.expected_horizon_points - action.no_chip_horizon_points
                ),
                "reason": action.reason,
            }
        )
    return sorted(
        output,
        key=lambda row: (-row["expected_horizon_gain"], row["gameweek"], row["chip_key"]),
    )


def _recommendation_payload(
    action: BeamAction,
    *,
    model_version: str,
    counterfactuals: Sequence[BeamAction],
    target_gameweek: int,
    alternatives: Sequence[Mapping[str, Any]],
    chip_state: ChipState,
    rules: SeasonRules,
    data_cutoff: str | None,
    projection_model_name: str,
    portfolio_version: str,
) -> dict[str, Any]:
    expected_immediate_gain = action.expected_points - action.no_chip_expected_points
    expected_horizon_gain = action.expected_horizon_points - action.no_chip_horizon_points
    best_alternative = alternatives[0] if alternatives else None
    chip = action.chip
    use_chip = chip is not None
    chip_label = _chip_label(chip.name) if chip is not None else None
    recommendation = {
        "action": "use" if use_chip else "save",
        "chip": chip_label,
        "chip_key": chip.key if chip is not None else None,
        "chip_number": chip.number if chip is not None else None,
        "gameweek": target_gameweek,
        "expected_immediate_gain": _round(expected_immediate_gain),
        "expected_horizon_gain": _round(expected_horizon_gain),
        "expected_gameweek_points": _round(action.expected_points),
        "no_chip_gameweek_points": _round(action.no_chip_expected_points),
        "expected_horizon_points": _round(action.expected_horizon_points),
        "no_chip_horizon_points": _round(action.no_chip_horizon_points),
        "uncertainty_penalty": _round(action.uncertainty_penalty),
        "downside_range": {
            "low": _round(action.expected_points - 2 * action.uncertainty_penalty),
            "high": _round(action.expected_points + 2 * action.uncertainty_penalty),
        },
        "confidence": _confidence(expected_horizon_gain, action.uncertainty_penalty),
        "ordinary_transfer_allowed": chip is None or chip.name not in {"wildcard", "freehit"},
        "ordinary_transfer_applied": bool(action.transfer.made),
        "transfer": {
            "outgoing_id": action.transfer.outgoing_id,
            "outgoing_name": action.transfer.outgoing_name,
            "incoming_id": action.transfer.incoming_id,
            "incoming_name": action.transfer.incoming_name,
            "hit_cost": action.transfer.hit_cost,
        },
        "reason": (
            action.reason
            if use_chip
            else "Save chips: no chip branch was selected by the planner."
        ),
        "best_alternative": best_alternative,
    }
    return {
        "model": MODEL_NAME,
        "model_version": model_version,
        "projection_model": projection_model_name,
        "portfolio_version": portfolio_version,
        "chip_mode": "beam_search",
        "rules_version": rules.rules_version,
        "rules_payload_hash": rules.payload_hash,
        "data_cutoff": data_cutoff,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "recommendation": recommendation,
        "counterfactuals": [
            _counterfactual_payload(candidate, action) for candidate in counterfactuals
        ],
        "remaining_chips": list(chip_state.remaining),
        "used_chips": list(chip_state.used),
        "alternatives": list(alternatives),
    }


def _position(value: Any) -> str:
    return {"GKP": "GK", "GK": "GK"}.get(str(value or "").upper(), str(value or "").upper())


def _counterfactual_payload(
    candidate: BeamAction,
    selected: BeamAction,
) -> dict[str, Any]:
    candidate_key = candidate.chip.key if candidate.chip is not None else "none"
    selected_key = selected.chip.key if selected.chip is not None else "none"
    return {
        "chip_key": candidate_key,
        "chip_number": candidate.chip.number if candidate.chip is not None else None,
        "legal": True,
        "selected": candidate_key == selected_key,
        "expected_gameweek_points": _round(candidate.expected_points),
        "no_chip_gameweek_points": _round(candidate.no_chip_expected_points),
        "expected_horizon_points": _round(candidate.expected_horizon_points),
        "no_chip_horizon_points": _round(candidate.no_chip_horizon_points),
        "expected_horizon_gain": _round(
            candidate.expected_horizon_points - candidate.no_chip_horizon_points
        ),
        "future_opportunity_cost": _round(candidate.future_opportunity_cost),
        "uncertainty_penalty": _round(candidate.uncertainty_penalty),
        "reason": (
            selected.reason
            if candidate_key == selected_key
            else "rejected: another legal beam branch had higher guarded value"
        ),
    }


def _chip_label(value: str) -> str:
    return CHIP_LABELS.get(value, value.replace("_", " ").title())


def _confidence(gain: float, uncertainty: float) -> str:
    if gain >= 4 and uncertainty <= max(1.0, gain * 0.25):
        return "high"
    if gain > 0 and uncertainty <= max(2.0, gain * 0.6):
        return "medium"
    return "low"


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round(value: float) -> float:
    return round(float(value), 2)
