"""Exact legal single-gameweek squad and lineup optimization.

This module deliberately solves only one gameweek at a time.  It does not make
transfer, chip, price, or multi-period decisions.  Squad selection uses a small
binary MILP; lineup selection enumerates the finite legal formations and chooses
the best projected XI for each one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

INITIAL_BUDGET = 100.0
MAX_PLAYERS_PER_TEAM = 3
POSITION_QUOTAS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
POSITION_ORDER = tuple(POSITION_QUOTAS)
VALID_FORMATIONS = (
    (3, 4, 3),
    (3, 5, 2),
    (4, 3, 3),
    (4, 4, 2),
    (4, 5, 1),
    (5, 2, 3),
    (5, 3, 2),
    (5, 4, 1),
)


@dataclass(frozen=True)
class OptimizedLineup:
    starting_ids: tuple[int, ...]
    bench_ids: tuple[int, ...]
    formation: str


def position_group(position: object) -> str:
    value = str(position or "").upper()
    if value in {"GKP", "GOALKEEPER"}:
        return "GK"
    return "MID" if value == "AM" else value


def _formation_name(formation: tuple[int, int, int]) -> str:
    return "-".join(str(value) for value in formation)


def optimize_squad(
    candidates: pd.DataFrame,
    *,
    prediction_column: str = "preseason_value_score",
    budget: float = INITIAL_BUDGET,
) -> pd.DataFrame:
    """Select the highest-scoring legal 15-player squad with a binary MILP."""
    required = {"player_id", "position", "team", "price", prediction_column}
    missing = sorted(required.difference(candidates.columns))
    if missing:
        raise ValueError(f"Squad optimizer is missing columns: {', '.join(missing)}")

    working = candidates.drop_duplicates("player_id").copy()
    working["position_group"] = working["position"].map(position_group)
    working["_price"] = pd.to_numeric(working["price"], errors="coerce")
    working["_score"] = pd.to_numeric(working[prediction_column], errors="coerce").fillna(0.0)
    working = working[working["position_group"].isin(POSITION_QUOTAS)].copy()
    if working.empty:
        raise ValueError("Squad optimizer received no eligible players")

    n_players = len(working)
    objective = -working["_score"].to_numpy(dtype=float)
    position_matrix = np.array(
        [
            (working["position_group"] == position).astype(float).to_numpy()
            for position in POSITION_ORDER
        ]
    )
    club_values = working["team"].astype(str).unique()
    club_matrix = np.array(
        [
            (working["team"].astype(str) == club).astype(float).to_numpy()
            for club in club_values
        ]
    )
    matrix = np.vstack([position_matrix, working["_price"].to_numpy(), club_matrix])
    lower = np.concatenate(
        [
            np.array(list(POSITION_QUOTAS.values()), dtype=float),
            [-np.inf],
            np.full(len(club_values), -np.inf),
        ]
    )
    upper = np.concatenate(
        [
            np.array(list(POSITION_QUOTAS.values()), dtype=float),
            [budget],
            np.full(len(club_values), MAX_PLAYERS_PER_TEAM),
        ]
    )

    result = milp(
        c=objective,
        integrality=np.ones(n_players),
        bounds=Bounds(np.zeros(n_players), np.ones(n_players)),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": 30.0},
    )
    if not result.success or result.x is None:
        raise ValueError(f"Could not find a legal optimized squad: {result.message}")

    selected = working.loc[result.x > 0.5].copy()
    if len(selected) != 15:
        raise ValueError(f"MILP returned {len(selected)} players instead of 15")
    return selected.sort_values(
        ["position_group", "_score", "player_id"],
        ascending=[True, False, True],
    ).drop(columns=["_price", "_score"], errors="ignore").reset_index(drop=True)


def optimize_starting_xi(
    squad: pd.DataFrame,
    projected_points: Mapping[int, float],
) -> OptimizedLineup:
    """Choose the projected-points-maximizing legal formation and bench order."""
    violations = validate_squad_shape(squad)
    if violations:
        raise ValueError(f"Cannot optimize an illegal squad: {'; '.join(violations)}")

    working = squad.copy()
    working["position_group"] = working["position"].map(position_group)
    working["_projection"] = (
        working["player_id"].map(projected_points).fillna(0.0).astype(float)
    )
    best: tuple[float, tuple[int, ...], tuple[int, int, int]] | None = None
    for formation in VALID_FORMATIONS:
        selected: list[int] = []
        feasible = True
        for position, count in zip(POSITION_ORDER, (1, *formation), strict=True):
            pool = working[working["position_group"] == position].sort_values(
                ["_projection", "player_id"], ascending=[False, True]
            )
            if len(pool) < count:
                feasible = False
                break
            selected.extend(int(value) for value in pool.head(count)["player_id"])
        if not feasible:
            continue
        score = float(working[working["player_id"].isin(selected)]["_projection"].sum())
        key = (score, tuple(-player_id for player_id in selected), formation)
        if best is None or key > best:
            best = key

    if best is None:
        raise ValueError("Could not construct a legal starting XI")

    _, selected_key, formation = best
    starting_ids = tuple(-player_id for player_id in selected_key)
    starting_set = set(starting_ids)
    bench = working[~working["player_id"].isin(starting_set)].copy()
    # Put outfield substitutes first, with the reserve goalkeeper last.
    bench = bench.sort_values(
        ["position_group", "_projection", "player_id"],
        ascending=[True, False, True],
        key=lambda column: column.map({"GK": 1, "DEF": 0, "MID": 0, "FWD": 0})
        if column.name == "position_group"
        else column,
    )
    bench_ids = tuple(int(value) for value in bench["player_id"])
    return OptimizedLineup(starting_ids, bench_ids, _formation_name(formation))


def validate_squad_shape(squad: pd.DataFrame) -> list[str]:
    """Return structural squad violations without applying price constraints."""
    violations: list[str] = []
    if len(squad) != 15:
        violations.append(f"squad has {len(squad)} players, expected 15")
    if squad["player_id"].duplicated().any():
        violations.append("squad contains duplicate player IDs")
    positions = squad["position"].map(position_group)
    for position, required in POSITION_QUOTAS.items():
        actual = int((positions == position).sum())
        if actual != required:
            violations.append(f"squad has {actual} {position}, expected {required}")
    club_counts = squad.groupby(squad["team"].astype(str))["player_id"].size()
    if (club_counts > MAX_PLAYERS_PER_TEAM).any():
        violations.append("club limit exceeded")
    return violations


def validate_starting_xi(squad: pd.DataFrame, starting_ids: tuple[int, ...]) -> list[str]:
    """Return starting-XI formation violations."""
    violations: list[str] = []
    if len(starting_ids) != 11 or len(set(starting_ids)) != 11:
        violations.append("starting XI must contain 11 unique players")
        return violations
    selected = squad[squad["player_id"].isin(starting_ids)]
    if len(selected) != 11:
        violations.append("starting XI contains a player outside the squad")
        return violations
    positions = selected["position"].map(position_group)
    counts = positions.value_counts()
    if int(counts.get("GK", 0)) != 1:
        violations.append("starting XI must contain exactly one goalkeeper")
    if not 3 <= int(counts.get("DEF", 0)) <= 5:
        violations.append("starting XI defender count is invalid")
    if not 2 <= int(counts.get("MID", 0)) <= 5:
        violations.append("starting XI midfielder count is invalid")
    if not 1 <= int(counts.get("FWD", 0)) <= 3:
        violations.append("starting XI forward count is invalid")
    if int(counts.get("DEF", 0) + counts.get("MID", 0) + counts.get("FWD", 0)) != 10:
        violations.append("starting XI outfield count must be 10")
    return violations
