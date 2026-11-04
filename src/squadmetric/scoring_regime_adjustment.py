"""Transparent live adjustments for the 2026/27 BPS and role regime."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ScoringRegimeAdjustment:
    bps_v2_penalty: float
    role_transition_penalty: float
    total_penalty: float
    team_changed: bool
    dc_actions_per_90: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bps_v2_adjustment(
    player: dict[str, Any],
    baseline: dict[str, Any],
) -> ScoringRegimeAdjustment:
    """Estimate only the rule/role delta, not a new full point projection.

    DC thresholds are unchanged. The BPS penalty represents reduced CBI overlap,
    while the role penalty discounts only the expected DC component after a club
    move. Both are intentionally capped and exposed in every live fixture row.
    """

    minutes = _number(player.get("previous_minutes"))
    starts = max(1.0, _number(player.get("previous_starts")))
    cbi = _number(player.get("previous_cbi"))
    tackles = _number(player.get("previous_tackles"))
    recoveries = _number(player.get("previous_recoveries"))
    old_bonus = _number(player.get("previous_bonus"))
    position = str(player.get("position") or "")
    recovery_actions = (
        recoveries if position in {"MID", "FWD", "Midfielder", "Forward"} else 0.0
    )
    actions = cbi + tackles + recovery_actions
    actions_per_90 = actions * 90.0 / minutes if minutes > 0 else 0.0
    cbi_per_start = cbi / starts
    old_bonus_per_start = old_bonus / starts

    # The official change reduces CBI BPS by roughly one third. FPL bonus is
    # rank-based, so only the observed old bonus overlapping with CBI is at risk.
    overlap = min(1.0, cbi_per_start / 10.0)
    bps_penalty = min(0.35, old_bonus_per_start * overlap / 3.0)

    prior_team = str(baseline.get("prior_team") or "").casefold()
    current_team = str(player.get("team_name") or player.get("team") or "").casefold()
    team_changed = bool(prior_team and current_team and prior_team != current_team)
    threshold = 10.0 if position in {"DEF", "Defender"} else 12.0
    dc_hit_probability = 1.0 / (1.0 + math.exp(-(actions_per_90 - threshold) / 1.5))
    expected_dc_points = 2.0 * dc_hit_probability
    role_penalty = min(0.5, expected_dc_points * 0.25) if team_changed else 0.0
    total = bps_penalty + role_penalty
    return ScoringRegimeAdjustment(
        bps_v2_penalty=round(bps_penalty, 4),
        role_transition_penalty=round(role_penalty, 4),
        total_penalty=round(total, 4),
        team_changed=team_changed,
        dc_actions_per_90=round(actions_per_90, 4),
    )


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
