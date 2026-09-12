"""Build an official, explicitly identified SquadMetric team scorecard."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from fpl_intelligence.season_rules import infer_season_from_bootstrap

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "model_team_performance"
FPL_API = "https://fantasy.premierleague.com/api"


def build_model_team_report(
    *,
    team_id: int,
    entry: dict[str, Any],
    history: dict[str, Any],
    bootstrap: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    """Compare the named model team's completed Gameweeks with official averages."""

    averages = {
        int(event["id"]): int(event.get("average_entry_score") or 0)
        for event in bootstrap.get("events", [])
        if event.get("id") is not None
        and bool(event.get("finished"))
        and bool(event.get("data_checked"))
    }
    rows = []
    for result in history.get("current", []):
        gameweek = int(result.get("event") or 0)
        if gameweek not in averages:
            continue
        points = int(result.get("points") or 0)
        average = averages[gameweek]
        delta = points - average
        rows.append(
            {
                "gameweek": gameweek,
                "points": points,
                "official_average": average,
                "delta": delta,
                "relative_result": (
                    "above_average"
                    if delta > 0
                    else "below_average"
                    if delta < 0
                    else "equal_average"
                ),
                "overall_rank_after_gameweek": result.get("overall_rank"),
                "transfers": int(result.get("event_transfers") or 0),
                "transfer_cost": int(result.get("event_transfers_cost") or 0),
                "bench_points": int(result.get("points_on_bench") or 0),
            }
        )
    rows.sort(key=lambda row: row["gameweek"])
    return {
        "schema_version": "model-team-performance-v1",
        "generated_at": generated_at,
        "season": infer_season_from_bootstrap(bootstrap),
        "team_id": int(team_id),
        "team_name": entry.get("name"),
        "explicitly_model_managed": True,
        "personal_team_results_included": False,
        "total_points": int(entry.get("summary_overall_points") or 0),
        "overall_rank": entry.get("summary_overall_rank"),
        "completed_gameweeks": rows,
        "all_completed_gameweeks_below_average": bool(rows)
        and all(row["delta"] < 0 for row in rows),
        "total_delta_vs_official_average": sum(row["delta"] for row in rows),
        "sources": {
            "entry": f"{FPL_API}/entry/{int(team_id)}/",
            "history": f"{FPL_API}/entry/{int(team_id)}/history/",
            "bootstrap": f"{FPL_API}/bootstrap-static/",
        },
    }


def fetch_model_team_report(team_id: int) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    entry = _get_json(f"{FPL_API}/entry/{team_id}/")
    history = _get_json(f"{FPL_API}/entry/{team_id}/history/")
    bootstrap = _get_json(f"{FPL_API}/bootstrap-static/")
    return build_model_team_report(
        team_id=team_id,
        entry=entry,
        history=history,
        bootstrap=bootstrap,
        generated_at=generated_at,
    )


def persist_model_team_report(
    report: dict[str, Any], root: Path = OUTPUT_ROOT
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{report['season']}-team-{report['team_id']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Official FPL endpoint returned a non-object payload: {url}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record official performance for an explicitly identified model team."
    )
    parser.add_argument("--team-id", type=int, required=True)
    args = parser.parse_args()
    report = fetch_model_team_report(args.team_id)
    path = persist_model_team_report(report)
    print(json.dumps({**report, "report_path": str(path)}, indent=2))


if __name__ == "__main__":
    main()
