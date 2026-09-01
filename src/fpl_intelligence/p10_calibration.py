"""P10 autosub calibration and live squad robustness utilities."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from fpl_intelligence.initial_squad_championship import (
    GW1_DECISION_PROFILES,
    build_live_opening_projection_bundle,
    optimize_opening_squad,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DECISION_PATHS = (
    PROJECT_ROOT
    / "data/processed/simulations/performance-recovery-production-2023-24/gameweek_decisions.csv",
    PROJECT_ROOT
    / "data/processed/simulations/chip-save-value-repair-2024-2026/gameweek_decisions.csv",
)
P10_OUTPUT = PROJECT_ROOT / "data/processed/p10_calibration_report.json"
HISTORICAL_PATH = PROJECT_ROOT / "data/processed/historical_player_gw.csv"
CALIBRATION_REFERENCE_PATH = PROJECT_ROOT / "data/reference/autosub_calibration.json"
P10_SCHEMA_VERSION = "p10-calibration-v1"
P10_DECISION_ENGINE_VERSION = "p10-gw1-calibrated-robustness-v1"


def parse_player_ids(value: Any) -> list[int]:
    if pd.isna(value) or str(value).strip().lower() in {"", "nan"}:
        return []
    return [int(float(item)) for item in str(value).split("+") if item]


def calibrate_autosubs(decisions: pd.DataFrame) -> dict[str, Any]:
    frame = decisions[
        decisions.get("chip_used", pd.Series("", index=decisions.index))
        .fillna("")
        .astype(str)
        .str.lower()
        .ne("bboost")
    ]
    slot_uses = [0, 0, 0, 0]
    substitutions: list[int] = []
    seasons: dict[str, dict[str, float]] = {}
    for row in frame.to_dict("records"):
        autosubs = set(parse_player_ids(row.get("realistic_autosub_ids")))
        bench = parse_player_ids(row.get("selected_bench_ids"))
        substitutions.append(len(autosubs))
        for index, player_id in enumerate(bench[:4]):
            slot_uses[index] += int(player_id in autosubs)
    gameweeks = len(substitutions)
    for season, rows in frame.groupby("season"):
        counts = [len(parse_player_ids(value)) for value in rows["realistic_autosub_ids"]]
        seasons[str(season)] = {
            "gameweeks": len(counts),
            "any_autosub_rate": round(sum(value > 0 for value in counts) / len(counts), 4),
            "mean_autosubs": round(sum(counts) / len(counts), 4),
        }
    mean_autosubs = sum(substitutions) / gameweeks
    return {
        "gameweeks": gameweeks,
        "any_autosub_rate": round(sum(value > 0 for value in substitutions) / gameweeks, 4),
        "starter_nonappearance_rate": round(mean_autosubs / 11.0, 4),
        "mean_autosubs": round(mean_autosubs, 4),
        "mean_bench_slot_activation": round(mean_autosubs / 4.0, 4),
        "bench_slot_activation": [round(value / gameweeks, 4) for value in slot_uses],
        "seasons": seasons,
    }


def calibrate_nonappearance_bands(
    decisions: pd.DataFrame,
    history: pd.DataFrame,
) -> dict[str, Any]:
    history_rows = history.set_index(["season", "gameweek", "player_id"])
    groups: dict[str, list[bool]] = {}
    positions: dict[str, list[bool]] = {}
    for row in decisions.to_dict("records"):
        selected = parse_player_ids(row.get("selected_starting_ids"))
        final = set(parse_player_ids(row.get("realistic_starting_ids")))
        for player_id in selected:
            key = (row["season"], int(row["gameweek"]), player_id)
            if key not in history_rows.index:
                continue
            player = history_rows.loc[key]
            if isinstance(player, pd.DataFrame):
                player = player.iloc[0]
            minutes = float(player.get("minutes_last_3") or 0.0)
            available_games = max(1.0, float(player.get("prior_games_available_last_3") or 0.0))
            reliability = minutes / (90.0 * available_games)
            band = "high" if reliability >= 0.8 else "medium" if reliability >= 0.4 else "low"
            missed = player_id not in final
            groups.setdefault(band, []).append(missed)
            positions.setdefault(str(player.get("position") or "unknown"), []).append(missed)
    def summarise(values: list[bool]) -> dict[str, Any]:
        return {
            "selections": len(values),
            "nonappearance_rate": round(sum(values) / len(values), 4),
        }
    return {
        "by_reliability_band": {
            key: summarise(values) for key, values in sorted(groups.items())
        },
        "by_position": {
            key: summarise(values) for key, values in sorted(positions.items())
        },
    }


def load_autosub_calibration(paths: tuple[Path, ...] | None = None) -> dict[str, Any]:
    paths = DECISION_PATHS if paths is None else paths
    missing = [path for path in paths if not path.exists()]
    if missing:
        if paths != DECISION_PATHS:
            raise FileNotFoundError(
                "Autosub decision artifacts are missing: "
                + ", ".join(str(path) for path in missing)
            )
        return json.loads(CALIBRATION_REFERENCE_PATH.read_text(encoding="utf-8"))

    frames = [pd.read_csv(path) for path in paths]
    decisions = pd.concat(frames, ignore_index=True)
    result = calibrate_autosubs(decisions)
    result["nonappearance"] = calibrate_nonappearance_bands(
        decisions,
        pd.read_csv(HISTORICAL_PATH),
    )
    return result


def scenario_players(
    projected_players: list[dict[str, Any]],
    *,
    bps_multiplier: float,
    role_multiplier: float,
    set_piece_multiplier: float | None = None,
) -> list[dict[str, Any]]:
    output = json.loads(json.dumps(projected_players))
    effective_set_piece_multiplier = (
        role_multiplier if set_piece_multiplier is None else set_piece_multiplier
    )
    for player in output:
        for gameweek in player.get("projections", []):
            total = 0.0
            for fixture in gameweek.get("fixtures", []):
                adjustment = fixture.get("scoring_regime_adjustment", {})
                start = float(fixture.get("start_likelihood") or 0.0)
                base_bps = float(adjustment.get("bps_v2_penalty") or 0.0)
                base_role = float(adjustment.get("role_transition_penalty") or 0.0)
                delta = (
                    base_bps * (bps_multiplier - 1.0)
                    + base_role * (role_multiplier - 1.0)
                ) * start
                set_piece = fixture.get("set_piece_adjustment", {})
                set_piece_delta = float(
                    set_piece.get("total_adjustment") or 0.0
                ) * (effective_set_piece_multiplier - 1.0) * start
                fixture["projected_points"] = round(
                    max(
                        0.0,
                        float(fixture["projected_points"])
                        - delta
                        + set_piece_delta,
                    ),
                    3,
                )
                total += fixture["projected_points"]
            gameweek["projected_points"] = round(total, 3)
    return output


def run_robustness_tournament(
    projected_players: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    autosub_rates: tuple[float, ...] = (0.12, 0.17, 0.24),
    bps_multipliers: tuple[float, ...] = (0.75, 1.0, 1.25),
    role_multipliers: tuple[float, ...] = (0.6, 1.0, 1.4),
) -> dict[str, Any]:
    selections: dict[int, int] = {}
    names: dict[int, str] = {}
    rows = []
    for bps_multiplier in bps_multipliers:
        for role_multiplier in role_multipliers:
            players = scenario_players(
                projected_players,
                bps_multiplier=bps_multiplier,
                role_multiplier=role_multiplier,
            )
            bundle = build_live_opening_projection_bundle(players, metadata)
            for autosub_rate in autosub_rates:
                config = replace(
                    GW1_DECISION_PROFILES["balanced"],
                    depth_weight=autosub_rate,
                )
                candidate = optimize_opening_squad(bundle, config)
                ids = sorted(candidate.squad["player_id"].astype(int))
                for record in candidate.squad.to_dict("records"):
                    player_id = int(record["player_id"])
                    selections[player_id] = selections.get(player_id, 0) + 1
                    names[player_id] = str(record["player_name"])
                rows.append(
                    {
                        "bps_multiplier": bps_multiplier,
                        "role_multiplier": role_multiplier,
                        "set_piece_multiplier": role_multiplier,
                        "autosub_rate": autosub_rate,
                        "squad_ids": ids,
                        "projected_points_8": candidate.projected_metrics[
                            "projected_points_8"
                        ],
                    }
                )
    scenario_count = len(rows)
    squad_counts = Counter(tuple(row["squad_ids"]) for row in rows)
    robust_squad, robust_count = squad_counts.most_common(1)[0]
    stability = [
        {
            "player_id": player_id,
            "player_name": names[player_id],
            "selected_scenarios": count,
            "selection_rate": round(count / scenario_count, 4),
            "classification": (
                "locked" if count == scenario_count
                else "stable" if count / scenario_count >= 0.67
                else "fragile"
            ),
        }
        for player_id, count in selections.items()
    ]
    return {
        "scenario_count": scenario_count,
        "distinct_squads": len(squad_counts),
        "robust_squad_ids": list(robust_squad),
        "robust_squad_frequency": robust_count,
        "robust_squad_rate": round(robust_count / scenario_count, 4),
        "scenarios": rows,
        "player_stability": sorted(
            stability, key=lambda row: (-row["selection_rate"], row["player_name"])
        ),
    }


async def _run_live() -> dict[str, Any]:
    from api.live_projection_service import live_projection_rows

    from fpl_intelligence.production_portfolio import get_production_portfolio

    portfolio = get_production_portfolio()
    players, metadata = await live_projection_rows(
        model_name=portfolio.projections.transfer_model,
        start_gameweek=1,
        horizon=8,
    )
    return {
        "schema_version": P10_SCHEMA_VERSION,
        "autosub_calibration": load_autosub_calibration(),
        "robustness": run_robustness_tournament(players, metadata),
        "metadata": metadata,
    }


def persist_report(report: dict[str, Any]) -> None:
    P10_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    P10_OUTPUT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def refresh_calibration_only() -> dict[str, Any]:
    if not P10_OUTPUT.exists():
        raise FileNotFoundError(
            "P10 report does not exist; run the complete tournament first."
        )
    report = json.loads(P10_OUTPUT.read_text(encoding="utf-8"))
    report["schema_version"] = P10_SCHEMA_VERSION
    report["autosub_calibration"] = load_autosub_calibration()
    persist_report(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calibration-only",
        action="store_true",
        help="Refresh historical calibration without rerunning the live MILP tournament.",
    )
    args = parser.parse_args()
    report = (
        refresh_calibration_only()
        if args.calibration_only
        else asyncio.run(_run_live())
    )
    if not args.calibration_only:
        persist_report(report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
