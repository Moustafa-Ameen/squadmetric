"""Transparent three-gameweek squad grades for the primary dashboard."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from fpl_intelligence.beam_search import _fast_gameweek_value, _projection_map
from fpl_intelligence.chip_simulation import build_chip_squad
from fpl_intelligence.squad_optimizer import position_group

GRADE_BANDS: tuple[tuple[float, str], ...] = (
    (97.0, "A+"),
    (95.0, "A"),
    (92.0, "A-"),
    (88.0, "B+"),
    (84.0, "B"),
    (80.0, "B-"),
    (75.0, "C+"),
    (70.0, "C"),
    (65.0, "C-"),
    (55.0, "D"),
    (45.0, "E"),
    (0.0, "F"),
)


def grade_for_score(score: float) -> str:
    bounded = max(0.0, min(100.0, float(score)))
    return next(grade for threshold, grade in GRADE_BANDS if bounded >= threshold)


def build_team_rating(
    *,
    squad: pd.DataFrame,
    frames: Mapping[int, pd.DataFrame],
    bank: float,
    horizon: int = 3,
    current_horizon_points: float | None = None,
    recommended_horizon_points: float | None = None,
    provisional: bool = False,
) -> dict[str, Any]:
    """Rate a squad against the strongest legal squad found at the same budget.

    This is deliberately a relative-strength comparison rather than a claimed percentile:
    all legal squads are eligible, but the output does not pretend we know every
    manager's private team state.
    """

    selected_frames = [frames[key] for key in sorted(frames)[: max(1, horizon)]]
    if len(squad) != 15 or not selected_frames:
        raise ValueError("A complete squad and live projections are required for a rating")

    total_budget = round(float(squad["price"].sum()) + float(bank), 1)
    aggregated = selected_frames[0].copy().drop_duplicates("player_id", keep="last")
    totals: dict[int, float] = {}
    for frame in selected_frames:
        for player_id, points in zip(
            frame["player_id"], frame["expected_points_adjusted"], strict=True
        ):
            totals[int(player_id)] = totals.get(int(player_id), 0.0) + float(points or 0.0)
    aggregated["expected_points_adjusted"] = aggregated["player_id"].map(totals).fillna(0.0)
    benchmark_squad = build_chip_squad(
        _benchmark_candidates(aggregated, squad),
        budget=total_budget,
    )

    calculated_current = _horizon_value(squad, selected_frames)
    calculated_benchmark = _horizon_value(benchmark_squad, selected_frames)
    current = (
        float(current_horizon_points) if current_horizon_points is not None else calculated_current
    )
    recommended = (
        float(recommended_horizon_points) if recommended_horizon_points is not None else current
    )
    benchmark = max(calculated_benchmark, current, recommended, 0.01)
    current_score = _score(current, benchmark)
    after_score = _score(recommended, benchmark)
    gap = max(0.0, benchmark - current)

    availability = pd.to_numeric(
        squad.get("probability_60_plus_minutes", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(1.0)
    risky_count = int((availability < 0.75).sum())
    summary = _summary(current_score, gap, risky_count)
    factors = [
        {
            "label": "Projected strength",
            "status": "strong" if current_score >= 88 else "improvable",
            "detail": (
                f"{current:.1f} projected points over the next "
                f"{len(selected_frames)} gameweeks."
            ),
        },
        {
            "label": "Availability",
            "status": "strong" if risky_count == 0 else "warning",
            "detail": (
                "No major minutes risks detected in the 15-player squad."
                if risky_count == 0
                else (
                    f"{risky_count} player{'s' if risky_count != 1 else ''} "
                    f"currently {'carry' if risky_count != 1 else 'carries'} "
                    "a notable minutes risk."
                )
            ),
        },
        {
            "label": "Fair comparison",
            "status": "neutral",
            "detail": (
                "Compared with legal squads built using the same available budget of "
                f"£{total_budget:.1f}m."
            ),
        },
    ]

    return {
        "grade": grade_for_score(current_score),
        "score": round(current_score, 1),
        "after_grade": grade_for_score(after_score),
        "after_score": round(after_score, 1),
        "horizon": len(selected_frames),
        "projected_points": round(current, 2),
        "recommended_projected_points": round(recommended, 2),
        "benchmark_points": round(benchmark, 2),
        "gap_to_best": round(gap, 2),
        "budget": total_budget,
        "provisional": bool(provisional),
        "summary": summary,
        "factors": factors,
        "method": (
            "Three-gameweek projected XI strength, including captaincy, compared with "
            "the strongest legal squad found at the same spendable budget. A small "
            "uncertainty reserve prevents projections from implying perfection."
        ),
    }


def _horizon_value(squad: pd.DataFrame, frames: list[pd.DataFrame]) -> float:
    return float(sum(_fast_gameweek_value(squad, _projection_map(frame))[0] for frame in frames))


def _benchmark_candidates(
    projections: pd.DataFrame,
    current_squad: pd.DataFrame,
) -> pd.DataFrame:
    """Keep the high-value and enabling-price players needed by the rating MILP."""

    working = projections.copy()
    working["_position"] = working["position"].map(position_group)
    price_column = "decision_price" if "decision_price" in working else "price"
    working["_price"] = pd.to_numeric(working[price_column], errors="coerce")
    working["_score"] = pd.to_numeric(
        working["expected_points_adjusted"], errors="coerce"
    ).fillna(0.0)
    working["_value"] = working["_score"] / working["_price"].clip(lower=0.1)
    current_ids = set(int(value) for value in current_squad["player_id"])
    selected = [working[working["player_id"].isin(current_ids)]]
    for position in ("GK", "DEF", "MID", "FWD"):
        pool = working[working["_position"] == position]
        selected.extend(
            [
                pool.nlargest(24, ["_score", "_value"]),
                pool.nlargest(16, ["_value", "_score"]),
                pool.nsmallest(10, ["_price", "player_id"]),
            ]
        )
    return (
        pd.concat(selected, ignore_index=True)
        .drop_duplicates("player_id")
        .drop(columns=["_position", "_price", "_score", "_value"])
    )


def _score(points: float, benchmark: float) -> float:
    if benchmark <= 0:
        return 0.0
    # A top grade should mean genuinely close to the strongest same-budget squad,
    # not merely a good squad. Every percentage point below the benchmark therefore
    # costs four rating points, and even the benchmark is capped below 100.
    deficit_ratio = max(0.0, (float(benchmark) - float(points)) / float(benchmark))
    return max(0.0, min(97.0, 97.0 - deficit_ratio * 400.0))


def _summary(score: float, gap: float, risky_count: int) -> str:
    if score >= 95:
        lead = "This is an elite squad for the next three gameweeks."
    elif score >= 84:
        lead = "This is a strong squad with a small number of useful upgrades."
    elif score >= 70:
        lead = "The core is competitive, but there is clear room to improve."
    else:
        lead = "Several upgrades could materially improve the next three gameweeks."
    risk = " Availability is the first concern." if risky_count else ""
    return f"{lead} The strongest same-budget squad found projects {gap:.1f} points higher.{risk}"
