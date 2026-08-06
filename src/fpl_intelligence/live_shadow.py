"""Non-invasive live shadow comparisons and append-only audit records."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_intelligence.production_portfolio import ProductionPortfolio

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHADOW_MODE_ENV_VAR = "FPL_SHADOW_MODE"
SHADOW_AUDIT_PATH_ENV_VAR = "FPL_SHADOW_AUDIT_PATH"
DEFAULT_SHADOW_AUDIT_PATH = PROJECT_ROOT / "data" / "processed" / "live_shadow_audit.jsonl"


def shadow_enabled() -> bool:
    """Return whether non-invasive live challenger comparison is enabled."""

    return str(os.getenv(SHADOW_MODE_ENV_VAR, "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def shadow_audit_path() -> Path:
    configured = os.getenv(SHADOW_AUDIT_PATH_ENV_VAR)
    return Path(configured) if configured else DEFAULT_SHADOW_AUDIT_PATH


def append_shadow_record(record: Mapping[str, Any], path: Path | None = None) -> None:
    """Append one JSON-serialisable audit record without changing decisions."""

    destination = path or shadow_audit_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, default=str) + "\n")


def compare_chip_recommendations(
    *,
    active: Mapping[str, Any],
    control: Mapping[str, Any],
    gameweek: int,
    active_portfolio: ProductionPortfolio,
    control_portfolio: ProductionPortfolio,
    rules_version: str,
    data_cutoff: str | None,
) -> dict[str, Any]:
    active_recommendation = active.get("recommendation", {})
    control_recommendation = control.get("recommendation", {})
    active_chip = active_recommendation.get("chip_key") or "none"
    control_chip = control_recommendation.get("chip_key") or "none"
    return {
        "audit_type": "live_shadow_chip",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "gameweek": gameweek,
        "rules_version": rules_version,
        "data_cutoff": data_cutoff,
        "active_portfolio": active_portfolio.version,
        "control_portfolio": control_portfolio.version,
        "active_chip_key": active_chip,
        "control_chip_key": control_chip,
        "recommendation_changed": active_chip != control_chip,
        "active_expected_horizon_gain": active_recommendation.get("expected_horizon_gain"),
        "control_expected_horizon_gain": control_recommendation.get("expected_horizon_gain"),
        "expected_horizon_gain_delta": _difference(
            active_recommendation.get("expected_horizon_gain"),
            control_recommendation.get("expected_horizon_gain"),
        ),
        "active_model": active.get("projection_model"),
        "control_model": control.get("projection_model"),
    }


def compare_projection_sets(
    *,
    active_players: Sequence[Mapping[str, Any]],
    control_players: Sequence[Mapping[str, Any]],
    start_gameweek: int,
    horizon: int,
    active_portfolio: ProductionPortfolio,
    control_portfolio: ProductionPortfolio,
    rules_version: str,
) -> dict[str, Any]:
    active_values = _projection_values(active_players)
    control_values = _projection_values(control_players)
    keys = set(active_values) | set(control_values)
    deltas = [active_values.get(key, 0.0) - control_values.get(key, 0.0) for key in keys]
    return {
        "audit_type": "live_shadow_projection",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "start_gameweek": start_gameweek,
        "horizon": horizon,
        "rules_version": rules_version,
        "active_portfolio": active_portfolio.version,
        "control_portfolio": control_portfolio.version,
        "active_model": active_portfolio.projections.transfer_model,
        "control_model": control_portfolio.projections.transfer_model,
        "player_gameweek_keys": len(keys),
        "changed_projection_keys": sum(abs(delta) > 1e-9 for delta in deltas),
        "mean_absolute_delta": round(sum(abs(delta) for delta in deltas) / len(deltas), 6)
        if deltas
        else 0.0,
        "total_projection_delta": round(sum(deltas), 6),
    }


def _projection_values(players: Sequence[Mapping[str, Any]]) -> dict[tuple[int, int], float]:
    values: dict[tuple[int, int], float] = {}
    for player in players:
        player_id = player.get("element_id")
        if player_id is None:
            continue
        for projection in player.get("projections", []):
            gameweek = projection.get("gameweek")
            if gameweek is None:
                continue
            values[(int(player_id), int(gameweek))] = float(
                projection.get("projected_points") or 0.0
            )
    return values


def _difference(active: Any, control: Any) -> float | None:
    if active is None or control is None:
        return None
    return round(float(active) - float(control), 6)
