"""Official set-piece roles and transition-aware live projection adjustments."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_BOOTSTRAP_ROOT = PROJECT_ROOT / "data/raw/snapshots/2025-26"
SET_PIECE_SOURCE = "https://fplchallenge.premierleague.com/the-scout/set-piece-takers"
SET_PIECE_MODEL_VERSION = "p12-set-piece-transition-v1"

CATEGORY_FIELDS = {
    "penalties": "penalties_order",
    "direct_free_kicks": "direct_freekicks_order",
    "corners_indirect_free_kicks": "corners_and_indirect_freekicks_order",
}
CATEGORY_DECAY = {
    "penalties": 3.0,
    "direct_free_kicks": 1.0,
    "corners_indirect_free_kicks": 0.5,
}
GOAL_POINTS = {"GK": 10.0, "GKP": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
PENALTY_EVENT_RATE_PER_TEAM_FIXTURE = 0.13
PENALTY_CONVERSION_RATE = 0.78
DIRECT_FREE_KICK_POINTS_POOL = 0.10
CORNER_INDIRECT_POINTS_POOL = 0.12


@dataclass(frozen=True)
class SetPieceContext:
    current_roles: dict[str, dict[int, dict[str, Any]]]
    previous_roles: dict[str, dict[int, dict[str, Any]]]
    previous_player_codes: frozenset[int]
    previous_team_codes: frozenset[int]


@dataclass(frozen=True)
class SetPieceAdjustment:
    model_version: str
    source_url: str
    available: bool
    reason: str
    penalty_adjustment: float
    direct_free_kick_adjustment: float
    corner_adjustment: float
    total_adjustment: float
    roles: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "source_url": self.source_url,
            "available": self.available,
            "reason": self.reason,
            "penalty_adjustment": self.penalty_adjustment,
            "direct_free_kick_adjustment": self.direct_free_kick_adjustment,
            "corner_adjustment": self.corner_adjustment,
            "total_adjustment": self.total_adjustment,
            "roles": self.roles,
        }


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _player_code(row: dict[str, Any]) -> int | None:
    value = row.get("player_code", row.get("code"))
    parsed = _number(value)
    return int(parsed) if parsed is not None else None


def _appearance_probability(row: dict[str, Any]) -> float:
    if row.get("status") not in {None, "a"}:
        chance = _number(row.get("chance_of_playing_next_round"))
        if chance is not None and chance <= 0:
            return 0.0
    start = _number(row.get("start_likelihood"))
    availability = _number(row.get("availability_probability"))
    if availability is None:
        chance = _number(row.get("chance_of_playing_next_round"))
        availability = chance / 100.0 if chance is not None else 1.0
    if start is None or start <= 0:
        start = 0.5 * availability
    return max(0.0, min(1.0, start, availability))


def normalized_role_shares(
    rows: Iterable[dict[str, Any]],
    category: str,
    *,
    availability_adjusted: bool,
) -> dict[int, dict[str, Any]]:
    """Normalize FPL's sortable order within every team/category.

    Raw values are not literal category ranks. For example, an order of five
    may still be the lowest value—and therefore first choice—for that team.
    """

    field = CATEGORY_FIELDS[category]
    grouped: dict[int, list[tuple[float, dict[str, Any]]]] = {}
    for row in rows:
        code = _player_code(row)
        team_code = _number(row.get("team_code"))
        order = _number(row.get(field))
        if code is None or team_code is None or order is None:
            continue
        grouped.setdefault(int(team_code), []).append((order, row))

    output: dict[int, dict[str, Any]] = {}
    for team_code, ordered in grouped.items():
        ordered.sort(key=lambda item: (item[0], _player_code(item[1]) or 0))
        weighted: list[tuple[int, float, float, int]] = []
        for rank, (raw_order, row) in enumerate(ordered, start=1):
            code = _player_code(row)
            if code is None:
                continue
            appearance = _appearance_probability(row) if availability_adjusted else 1.0
            weight = math.exp(-CATEGORY_DECAY[category] * (rank - 1)) * appearance
            weighted.append((code, weight, raw_order, rank))
        for code, _weight, raw_order, rank in weighted:
            base_weight = math.exp(-CATEGORY_DECAY[category] * (rank - 1))
            denominator = base_weight + sum(
                other_weight
                for other_code, other_weight, _, _ in weighted
                if other_code != code
            )
            output[code] = {
                "team_code": team_code,
                "raw_order": raw_order,
                "normalized_rank": rank,
                # Conditional on this player appearing. Their own minutes
                # probability is applied once by the projection engine; only
                # competing takers' availability dilutes the role here.
                "role_share": (
                    round(base_weight / denominator, 4) if denominator > 0 else 0.0
                ),
            }
    return output


def _bootstrap_rows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    teams = {int(team["id"]): team for team in bootstrap.get("teams", [])}
    positions = {
        int(position["id"]): position
        for position in bootstrap.get("element_types", [])
    }
    rows = []
    for player in bootstrap.get("elements", []):
        team = teams.get(int(player.get("team") or 0), {})
        position = positions.get(int(player.get("element_type") or 0), {})
        rows.append(
            {
                **player,
                "player_code": player.get("code"),
                "team_code": team.get("code"),
                "position": position.get("singular_name_short")
                or position.get("singular_name"),
                "start_likelihood": 1.0,
                "availability_probability": 1.0,
            }
        )
    return rows


@lru_cache(maxsize=1)
def load_previous_bootstrap() -> dict[str, Any]:
    path = previous_bootstrap_path()
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def previous_bootstrap_path() -> Path | None:
    paths = sorted(
        path
        for path in PREVIOUS_BOOTSTRAP_ROOT.glob("bootstrap-*.json")
        if ".metadata." not in path.name
    )
    return paths[-1] if paths else None


def previous_bootstrap_audit() -> dict[str, Any] | None:
    path = previous_bootstrap_path()
    if path is None:
        return None
    return {
        "season": "2025-26",
        "snapshot": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build_set_piece_context(
    current_rows: Iterable[dict[str, Any]],
    previous_bootstrap: dict[str, Any] | None = None,
) -> SetPieceContext:
    current = list(current_rows)
    previous = previous_bootstrap if previous_bootstrap is not None else load_previous_bootstrap()
    previous_rows = _bootstrap_rows(previous) if previous else []
    current_roles = {
        category: normalized_role_shares(
            current, category, availability_adjusted=True
        )
        for category in CATEGORY_FIELDS
    }
    previous_roles = {
        category: normalized_role_shares(
            previous_rows, category, availability_adjusted=False
        )
        for category in CATEGORY_FIELDS
    }
    return SetPieceContext(
        current_roles=current_roles,
        previous_roles=previous_roles,
        previous_player_codes=frozenset(
            code for row in previous_rows if (code := _player_code(row)) is not None
        ),
        previous_team_codes=frozenset(
            int(team["code"])
            for team in previous.get("teams", [])
            if team.get("code") is not None
        ),
    )


def _category_pool(category: str, position: str) -> float:
    if category == "penalties":
        goal_points = GOAL_POINTS.get(position, 4.5)
        net_points = (
            PENALTY_CONVERSION_RATE * goal_points
            + (1.0 - PENALTY_CONVERSION_RATE) * -2.0
        )
        return PENALTY_EVENT_RATE_PER_TEAM_FIXTURE * net_points
    if category == "direct_free_kicks":
        return DIRECT_FREE_KICK_POINTS_POOL
    return CORNER_INDIRECT_POINTS_POOL


def set_piece_transition_adjustment(
    player: dict[str, Any],
    context: SetPieceContext,
) -> SetPieceAdjustment:
    code = _player_code(player)
    team_code_value = _number(player.get("team_code"))
    position = str(player.get("position") or "")
    if code is None or team_code_value is None:
        return SetPieceAdjustment(
            SET_PIECE_MODEL_VERSION,
            SET_PIECE_SOURCE,
            False,
            "stable_player_or_team_id_missing",
            0.0,
            0.0,
            0.0,
            0.0,
            {},
        )
    team_code = int(team_code_value)
    if code not in context.previous_player_codes and team_code not in context.previous_team_codes:
        return SetPieceAdjustment(
            SET_PIECE_MODEL_VERSION,
            SET_PIECE_SOURCE,
            False,
            "promoted_team_prior_unavailable",
            0.0,
            0.0,
            0.0,
            0.0,
            {},
        )

    roles: dict[str, dict[str, Any]] = {}
    adjustments: dict[str, float] = {}
    for category in CATEGORY_FIELDS:
        current = context.current_roles[category].get(code, {})
        previous = context.previous_roles[category].get(code, {})
        current_share = float(current.get("role_share") or 0.0)
        previous_share = float(previous.get("role_share") or 0.0)
        adjustment = (current_share - previous_share) * _category_pool(
            category, position
        )
        adjustments[category] = adjustment
        roles[category] = {
            "current_rank": current.get("normalized_rank"),
            "current_raw_order": current.get("raw_order"),
            "current_share": round(current_share, 4),
            "previous_rank": previous.get("normalized_rank"),
            "previous_raw_order": previous.get("raw_order"),
            "previous_share": round(previous_share, 4),
            "transition_delta": round(current_share - previous_share, 4),
        }
    penalty = adjustments["penalties"]
    direct = adjustments["direct_free_kicks"]
    corner = adjustments["corners_indirect_free_kicks"]
    total = max(-0.75, min(0.75, penalty + direct + corner))
    return SetPieceAdjustment(
        SET_PIECE_MODEL_VERSION,
        SET_PIECE_SOURCE,
        True,
        "official_current_role_minus_official_2025_26_role",
        round(penalty, 4),
        round(direct, 4),
        round(corner, 4),
        round(total, 4),
        roles,
    )
