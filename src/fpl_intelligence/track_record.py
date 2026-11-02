"""Public track record built from settled deadline evidence.

Each scored Gameweek compares the plan SquadMetric froze before the deadline with
the frozen legal no-action branch (no transfers, no chip), using official
finalized points. Only plans from the current decision engine count toward the
totals; older plans stay listed, labelled as an earlier version. The summary omits
the tracked team ID and squad so it can be committed and served publicly.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_intelligence.beam_search import DeterministicBeamPlanner
from fpl_intelligence.live_decision_evidence import EVIDENCE_ROOT, PROJECT_ROOT
from fpl_intelligence.refresh_current_season import BOOTSTRAP_PATH

TRACK_RECORD_PATH = PROJECT_ROOT / "data" / "processed" / "track_record_2026_27.json"

CHIP_NAMES = {
    "3xc": "Triple Captain",
    "bboost": "Bench Boost",
    "freehit": "Free Hit",
    "wildcard": "Wildcard",
}


def _latest_json(directory: Path) -> dict[str, Any] | None:
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def _player_names(bootstrap: Mapping[str, Any]) -> dict[int, str]:
    return {
        int(row["id"]): str(row.get("web_name") or row.get("second_name") or row["id"])
        for row in bootstrap.get("elements", [])
    }


def _finalized_gameweeks(bootstrap: Mapping[str, Any]) -> list[int]:
    return sorted(
        int(event["id"])
        for event in bootstrap.get("events", [])
        if event.get("finished") and event.get("data_checked")
    )


def _moves(branch: Mapping[str, Any]) -> list[tuple[Any, Any]]:
    return sorted(
        (t.get("outgoing_id"), t.get("incoming_id")) for t in branch.get("transfers", [])
    )


def score_gameweek(
    snapshot: Mapping[str, Any],
    outcome: Mapping[str, Any],
    names: Mapping[int, str],
    current_engine: str = DeterministicBeamPlanner.version,
) -> dict[str, Any] | None:
    """Summarize one settled Gameweek, or None when it has no no-action branch."""

    realized = {
        str(branch["branch_id"]): float(branch["net_points"])
        for branch in outcome.get("branches", [])
    }
    branches = list(snapshot.get("branches", []))
    selected = next(
        (b for b in branches if b["branch_id"] == outcome["selected_branch_id"]), None
    )
    hold = next((b for b in branches if not b.get("transfers") and not b.get("chip")), None)
    if selected is None or hold is None or hold["branch_id"] not in realized:
        return None
    recommended_points = float(outcome["selected_net_points"])
    hold_points = realized[hold["branch_id"]]
    captain_id = selected.get("captain_id")
    engine = (snapshot.get("context") or {}).get("decision_engine_version")
    # A chip can be played once, so report how much of the gain it supplied,
    # using the same transfers without the chip.
    chip_gain = None
    if selected.get("chip"):
        moves = _moves(selected)
        unchipped = next(
            (
                b
                for b in branches
                if not b.get("chip") and _moves(b) == moves and b["branch_id"] in realized
            ),
            None,
        )
        if unchipped is not None:
            chip_gain = round(recommended_points - realized[unchipped["branch_id"]], 1)
    return {
        "gameweek": int(outcome["gameweek"]),
        "engine": engine,
        "current_version": engine == current_engine,
        "chips_considered": any(b.get("chip") for b in branches),
        "deadline": snapshot.get("deadline"),
        "captured_at": snapshot.get("captured_at"),
        "recommendation": {
            "transfers": [
                {"out": t.get("outgoing_name"), "in": t.get("incoming_name")}
                for t in selected.get("transfers", [])
            ],
            "hit_cost": int(selected.get("hit_cost") or 0),
            "chip": CHIP_NAMES.get(str(selected.get("chip")), selected.get("chip")),
            "captain": names.get(int(captain_id)) if captain_id is not None else None,
        },
        "recommended_points": recommended_points,
        "no_action_points": hold_points,
        "gain_vs_no_action": round(recommended_points - hold_points, 1),
        "chip_gain": chip_gain,
        "best_option_points": float(outcome["best_frozen_branch_points"]),
        "points_left_on_table": float(outcome["selected_regret"]),
        "options_considered": len(branches),
    }


def build_track_record(
    *,
    season: str = "2026-27",
    evidence_root: Path = EVIDENCE_ROOT,
    bootstrap: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if bootstrap is None:
        bootstrap = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    names = _player_names(bootstrap)
    scored: list[dict[str, Any]] = []
    season_root = evidence_root / season
    for gameweek_root in sorted(season_root.glob("GW*")) if season_root.exists() else []:
        snapshot_outcome = _latest_json(gameweek_root / "outcomes")
        if snapshot_outcome is None or snapshot_outcome.get("status") != "finalized":
            continue
        snapshots = {
            json.loads(path.read_text(encoding="utf-8"))["snapshot_hash"]: path
            for path in (gameweek_root / "snapshots").glob("*.json")
        }
        snapshot_path = snapshots.get(snapshot_outcome["snapshot_hash"])
        if snapshot_path is None:
            continue
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        row = score_gameweek(snapshot, snapshot_outcome, names)
        if row is not None:
            scored.append(row)

    scored_gameweeks = {row["gameweek"] for row in scored}
    # GW1 is the opening-squad decision, which is scored separately.
    finalized = [gw for gw in _finalized_gameweeks(bootstrap) if gw >= 2]
    current = [row for row in scored if row["current_version"]]
    gains = [row["gain_vs_no_action"] for row in current]
    chip_gains = [row["chip_gain"] or 0.0 for row in current]
    return {
        "schema_version": "track-record-v1",
        "season": season,
        "generated_at": generated_at
        or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "method": (
            "Before each deadline SquadMetric saves its recommended plan and every "
            "alternative it considered. After official scores are final, each plan "
            "is scored with real points against keeping the squad unchanged. Totals "
            "count only plans from the current version of SquadMetric."
        ),
        "gameweeks": scored,
        "unscored_gameweeks": [gw for gw in finalized if gw not in scored_gameweeks],
        "totals": {
            "scored": len(current),
            "earlier_version_scored": len(scored) - len(current),
            "total_gain_vs_no_action": round(sum(gains), 1),
            "total_gain_from_chips": round(sum(chip_gains), 1),
            "average_gain_vs_no_action": round(sum(gains) / len(gains), 1) if gains else None,
            "weeks_ahead": sum(1 for gain in gains if gain > 0),
            "weeks_level": sum(1 for gain in gains if gain == 0),
            "weeks_behind": sum(1 for gain in gains if gain < 0),
        },
    }


def write_track_record(path: Path = TRACK_RECORD_PATH, **kwargs: Any) -> dict[str, Any]:
    record = build_track_record(**kwargs)
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    # Keep the file byte-stable when nothing was scored, so refreshes stay quiet.
    if previous is not None:
        unchanged = {k: v for k, v in previous.items() if k != "generated_at"} == {
            k: v for k, v in record.items() if k != "generated_at"
        }
        if unchanged:
            return previous
    encoded = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(encoded, encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2026-27")
    args = parser.parse_args()
    record = write_track_record(season=args.season)
    print(json.dumps(record["totals"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
