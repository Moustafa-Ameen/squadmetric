"""Immutable live deadline decisions and post-finalization outcome evidence.

This module is intentionally outside the recommendation path.  It records what
the production system knew and considered before a deadline, then settles those
frozen branches only after the official FPL event is both finished and data
checked.  It never executes transfers or changes the selected recommendation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fpl_intelligence.backtest_transfer_strategy import (
    LineupSelection,
    resolve_active_lineup,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = PROJECT_ROOT / "data" / "processed" / "live_decision_evidence"
SNAPSHOT_SCHEMA_VERSION = "live-decision-snapshot-v1"
OUTCOME_SCHEMA_VERSION = "live-decision-outcome-v1"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_planner_snapshot(
    payload: Mapping[str, Any],
    *,
    captured_at: str,
    team_id: int,
) -> dict[str, Any]:
    """Build a frozen in-season snapshot from the evidence-enabled planner API."""

    evidence = payload.get("decision_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("Planner payload is missing decision_evidence")
    branches = evidence.get("branches")
    if not isinstance(branches, list) or not branches:
        raise ValueError("Planner payload contains no candidate branches")
    context = {
        "source": "planner",
        "team_id": int(team_id),
        "horizon": int(payload.get("horizon") or 0),
        "portfolio_version": payload.get("portfolio_version"),
        "decision_engine_version": payload.get("decision_engine_version"),
        "model_versions": {
            "transfer": payload.get("transfer_model"),
            "captain": payload.get("captain_model"),
            "chip": payload.get("chip_model"),
        },
        "planner": evidence.get("planner"),
        "planner_version": evidence.get("planner_version"),
        "planner_config": evidence.get("planner_config"),
        "candidate_set_complete": bool(evidence.get("candidate_set_complete")),
        "candidate_count": int(evidence.get("candidate_count") or len(branches)),
        "baseline": payload.get("baseline", []),
        "squad_news": _squad_news(payload.get("squad", [])),
    }
    return build_deadline_snapshot(
        season=str(payload.get("fpl_api_season") or "unknown"),
        gameweek=int(payload["start_gameweek"]),
        deadline=str(payload.get("deadline") or ""),
        captured_at=captured_at,
        data_cutoff=payload.get("data_cutoff"),
        rules_version=payload.get("rules_version"),
        rules_payload_hash=payload.get("rules_payload_hash"),
        bootstrap_hash=payload.get("bootstrap_hash"),
        fixtures_hash=payload.get("fixtures_hash"),
        selected_branch_id=str(evidence["selected_branch_id"]),
        state_before=dict(evidence.get("state_before") or {}),
        branches=branches,
        context=context,
        source_payload_hash=canonical_hash(payload),
    )


def build_initial_squad_snapshot(
    payload: Mapping[str, Any],
    *,
    captured_at: str,
) -> dict[str, Any]:
    """Build a frozen GW1 snapshot from every configured opening policy profile."""

    alternatives = payload.get("decision_alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        raise ValueError("Initial-squad payload contains no policy alternatives")
    branches = [_opening_branch(row, raw_rank=index) for index, row in enumerate(alternatives, 1)]
    selected = [branch for branch in branches if branch["selected"]]
    if len(selected) != 1:
        raise ValueError("Initial-squad payload must contain exactly one selected profile")
    return build_deadline_snapshot(
        season=str(payload.get("season") or "unknown"),
        gameweek=1,
        deadline=str(payload.get("deadline") or ""),
        captured_at=captured_at,
        data_cutoff=payload.get("data_cutoff"),
        rules_version=payload.get("rules_version"),
        rules_payload_hash=payload.get("rules_payload_hash"),
        bootstrap_hash=payload.get("bootstrap_hash"),
        fixtures_hash=payload.get("fixtures_hash"),
        selected_branch_id=selected[0]["branch_id"],
        state_before={
            "budget": float(payload.get("budget") or 100.0),
            "bank": float(payload.get("budget") or 100.0),
            "free_transfers": 0,
            "remaining_chips": [],
            "used_chips": [],
        },
        branches=branches,
        context={
            "source": "initial_squad",
            "horizon": int(payload.get("horizon") or 8),
            "portfolio_version": payload.get("portfolio_version"),
            "decision_engine_version": payload.get("decision_engine_version"),
            "model_versions": {"opening_squad": payload.get("model")},
            "policy": payload.get("initial_squad_policy"),
            "policy_version": payload.get("initial_squad_policy_version"),
            "risk_profile": payload.get("risk_profile"),
            "candidate_scope": "configured_opening_policy_profiles",
            "candidate_set_complete": True,
            "candidate_count": len(branches),
            "decision_audit": payload.get("decision_audit"),
            "deadline_finalization": payload.get("deadline_finalization"),
            "set_piece_summary": payload.get("set_piece_summary"),
            "squad_news": _squad_news(payload.get("squad", [])),
        },
        source_payload_hash=canonical_hash(payload),
    )


def build_deadline_snapshot(
    *,
    season: str,
    gameweek: int,
    deadline: str,
    captured_at: str,
    data_cutoff: Any,
    rules_version: Any,
    rules_payload_hash: Any,
    bootstrap_hash: Any,
    fixtures_hash: Any,
    selected_branch_id: str,
    state_before: Mapping[str, Any],
    branches: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
    source_payload_hash: str,
) -> dict[str, Any]:
    if season == "unknown" or not 1 <= int(gameweek) <= 38:
        raise ValueError("A supported season and Gameweek are required")
    if not deadline:
        raise ValueError("An official deadline is required")
    if not data_cutoff:
        raise ValueError("A point-in-time data cutoff is required")
    if parse_timestamp(str(data_cutoff)) > parse_timestamp(captured_at):
        raise ValueError("The data cutoff cannot be later than the capture time")
    if parse_timestamp(captured_at) > parse_timestamp(deadline):
        raise ValueError("Shadow evidence must be captured before the official deadline")
    required_contract = {
        "rules_version": rules_version,
        "rules_payload_hash": rules_payload_hash,
        "bootstrap_hash": bootstrap_hash,
        "fixtures_hash": fixtures_hash,
        "source_payload_hash": source_payload_hash,
    }
    missing_contract = [key for key, value in required_contract.items() if not value]
    if missing_contract:
        raise ValueError(
            "Deadline evidence is missing contract metadata: "
            + ", ".join(missing_contract)
        )
    if not bool(context.get("candidate_set_complete")):
        raise ValueError("The frozen candidate set must be explicitly complete")
    normalized = [dict(branch) for branch in branches]
    for branch in normalized:
        _validate_frozen_branch(branch)
    branch_ids = [str(branch.get("branch_id") or "") for branch in normalized]
    if not branch_ids or any(not value for value in branch_ids):
        raise ValueError("Every candidate branch requires a stable branch_id")
    if len(branch_ids) != len(set(branch_ids)):
        raise ValueError("Candidate branch IDs must be unique")
    if selected_branch_id not in branch_ids:
        raise ValueError("The selected branch must exist in the frozen candidate set")
    selected_count = sum(bool(branch.get("selected")) for branch in normalized)
    if selected_count != 1:
        raise ValueError("Exactly one candidate branch must be selected")
    selected_flag_id = next(
        str(branch["branch_id"]) for branch in normalized if branch.get("selected")
    )
    if selected_flag_id != selected_branch_id:
        raise ValueError("selected_branch_id does not match the selected candidate")
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "season": season,
        "gameweek": int(gameweek),
        "deadline": deadline,
        "captured_at": captured_at,
        "captured_before_deadline": True,
        "data_cutoff": data_cutoff,
        "rules_version": rules_version,
        "rules_payload_hash": rules_payload_hash,
        "bootstrap_hash": bootstrap_hash,
        "fixtures_hash": fixtures_hash,
        "source_payload_hash": source_payload_hash,
        "selected_branch_id": selected_branch_id,
        "state_before": dict(state_before),
        "context": dict(context),
        "candidate_count": len(normalized),
        "branches": sorted(normalized, key=lambda branch: int(branch.get("raw_rank") or 0)),
        "automatic_execution": False,
        "outcome_status": "pending_official_finalization",
    }
    snapshot["snapshot_hash"] = canonical_hash(snapshot)
    return snapshot


def persist_snapshot(
    snapshot: Mapping[str, Any],
    root: Path = EVIDENCE_ROOT,
) -> Path:
    directory = _gameweek_root(snapshot, root) / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = str(snapshot["captured_at"]).replace(":", "-")
    path = directory / f"{timestamp}-{str(snapshot['snapshot_hash'])[:16]}.json"
    _write_immutable(path, snapshot)
    return path


def load_latest_snapshot(
    season: str,
    gameweek: int,
    root: Path = EVIDENCE_ROOT,
) -> dict[str, Any] | None:
    directory = root / season / f"GW{int(gameweek):02d}" / "snapshots"
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def official_event_finalization(
    bootstrap: Mapping[str, Any],
    gameweek: int,
) -> dict[str, Any]:
    event = next(
        (
            row
            for row in bootstrap.get("events", [])
            if int(row.get("id") or 0) == int(gameweek)
        ),
        None,
    )
    if event is None:
        return {"ready": False, "reason": "official_event_missing"}
    if not bool(event.get("finished")):
        return {"ready": False, "reason": "official_event_not_finished"}
    if not bool(event.get("data_checked")):
        return {"ready": False, "reason": "official_scoring_not_data_checked"}
    return {
        "ready": True,
        "reason": "official_event_finished_and_data_checked",
        "event": dict(event),
    }


def build_finalized_outcome(
    snapshot: Mapping[str, Any],
    *,
    bootstrap: Mapping[str, Any],
    live_payload: Mapping[str, Any],
    finalized_at: str,
) -> dict[str, Any]:
    gate = official_event_finalization(bootstrap, int(snapshot["gameweek"]))
    if not gate["ready"]:
        raise ValueError(f"Outcome cannot be finalized: {gate['reason']}")
    actual = _official_player_results(live_payload)
    branch_results = [score_frozen_branch(branch, actual) for branch in snapshot["branches"]]
    best_points = max(float(row["net_points"]) for row in branch_results)
    for row in branch_results:
        row["actual_regret_vs_best_frozen_branch"] = round(
            best_points - float(row["net_points"]), 3
        )
    selected = next(row for row in branch_results if row["selected"])
    outcome = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "season": snapshot["season"],
        "gameweek": int(snapshot["gameweek"]),
        "snapshot_hash": snapshot["snapshot_hash"],
        "selected_branch_id": snapshot["selected_branch_id"],
        "finalized_at": finalized_at,
        "official_finalization_reason": gate["reason"],
        "official_event_hash": canonical_hash(gate["event"]),
        "official_live_payload_hash": canonical_hash(live_payload),
        "selected_net_points": selected["net_points"],
        "best_frozen_branch_points": round(best_points, 3),
        "selected_regret": selected["actual_regret_vs_best_frozen_branch"],
        "branches": branch_results,
        "status": "finalized",
    }
    outcome["outcome_hash"] = canonical_hash(outcome)
    return outcome


def score_frozen_branch(
    branch: Mapping[str, Any],
    actual: Mapping[int, Mapping[str, float]],
) -> dict[str, Any]:
    squad_rows = list(branch.get("squad") or [])
    squad_ids = [int(row["player_id"]) for row in squad_rows]
    missing = sorted(set(squad_ids).difference(actual))
    if missing:
        raise ValueError(f"Official live payload is missing player IDs: {missing}")
    points = {player_id: float(actual[player_id]["points"]) for player_id in squad_ids}
    minutes = {player_id: float(actual[player_id]["minutes"]) for player_id in squad_ids}
    starting = tuple(int(value) for value in branch["starting_ids"])
    bench = tuple(int(value) for value in branch["bench_order"])
    squad = pd.DataFrame(squad_rows).rename(columns={"element_id": "player_id"})
    target = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "next_gameweek_points": points[player_id],
                "minutes": minutes[player_id],
            }
            for player_id in squad_ids
        ]
    )
    lineup = LineupSelection(starting, bench, _formation(squad, starting))
    chip = str(branch.get("chip") or "")
    if chip == "bboost":
        active_ids = squad_ids
        autosub_ids: tuple[int, ...] = ()
    else:
        active_ids, autosub_ids = resolve_active_lineup(squad, target, lineup)
    captain_id = int(branch["captain_id"])
    vice_id = int(branch["vice_captain_id"])
    effective_captain = (
        captain_id
        if minutes.get(captain_id, 0.0) > 0
        else vice_id
        if minutes.get(vice_id, 0.0) > 0
        else None
    )
    gross = sum(points[player_id] for player_id in active_ids)
    multiplier_bonus = 0.0
    if effective_captain is not None:
        multiplier_bonus = points[effective_captain] * (2 if chip == "3xc" else 1)
    gross += multiplier_bonus
    hit_cost = int(branch.get("hit_cost") or 0)
    bench_points = sum(points[player_id] for player_id in bench)
    return {
        "branch_id": branch["branch_id"],
        "raw_rank": branch.get("raw_rank"),
        "selected": bool(branch.get("selected")),
        "chip": branch.get("chip"),
        "transfers": branch.get("transfers", []),
        "gross_points": round(gross, 3),
        "hit_cost": hit_cost,
        "net_points": round(gross - hit_cost, 3),
        "effective_captain_id": effective_captain,
        "captain_multiplier_bonus": round(multiplier_bonus, 3),
        "autosub_ids": list(autosub_ids),
        "active_ids": list(active_ids),
        "bench_raw_points": round(bench_points, 3),
        "expected_gameweek_points": branch.get("expected_gameweek_points"),
        "expected_horizon_points": branch.get("expected_horizon_points"),
    }


def persist_outcome(
    outcome: Mapping[str, Any],
    root: Path = EVIDENCE_ROOT,
) -> Path:
    directory = _gameweek_root(outcome, root) / "outcomes"
    directory.mkdir(parents=True, exist_ok=True)
    for existing in sorted(directory.glob("*.json")):
        payload = json.loads(existing.read_text(encoding="utf-8"))
        if (
            payload.get("snapshot_hash") == outcome.get("snapshot_hash")
            and payload.get("official_live_payload_hash")
            == outcome.get("official_live_payload_hash")
        ):
            return existing
    path = directory / (
        f"{str(outcome['snapshot_hash'])[:16]}-"
        f"{str(outcome['official_live_payload_hash'])[:16]}.json"
    )
    _write_immutable(path, outcome)
    return path


def evidence_status(root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    snapshots = list(root.glob("*/GW*/snapshots/*.json")) if root.exists() else []
    outcomes = list(root.glob("*/GW*/outcomes/*.json")) if root.exists() else []
    finalized_snapshot_hashes = {
        json.loads(path.read_text(encoding="utf-8"))["snapshot_hash"] for path in outcomes
    }
    latest_by_gameweek: dict[tuple[str, str], Path] = {}
    for path in sorted(snapshots):
        latest_by_gameweek[(path.parents[2].name, path.parents[1].name)] = path
    rows = []
    for (season, gameweek), path in sorted(latest_by_gameweek.items()):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "season": season,
                "gameweek": int(gameweek.removeprefix("GW")),
                "captured_at": snapshot["captured_at"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "candidate_count": snapshot["candidate_count"],
                "finalized": snapshot["snapshot_hash"] in finalized_snapshot_hashes,
            }
        )
    return {
        "schema_version": "live-decision-evidence-status-v1",
        "root": str(root),
        "snapshot_files": len(snapshots),
        "outcome_files": len(outcomes),
        "gameweeks": rows,
        "automatic_execution": False,
    }


def _opening_branch(value: Mapping[str, Any], raw_rank: int) -> dict[str, Any]:
    squad = [dict(row) for row in value.get("squad", [])]
    core = {
        "profile": value.get("profile"),
        "squad_ids": sorted(int(row["player_id"]) for row in squad),
    }
    return {
        "branch_id": canonical_hash(core)[:20],
        "raw_rank": raw_rank,
        "selected": bool(value.get("selected")),
        "profile": value.get("profile"),
        "chip": None,
        "chip_key": "none",
        "ordinary_transfer_allowed": False,
        "ordinary_transfer_applied": False,
        "transfers": [],
        "transfer_count": 0,
        "hit_cost": 0,
        "squad": squad,
        "starting_ids": list(value.get("starting_ids") or []),
        "bench_order": list(value.get("bench_order") or []),
        "captain_id": int(value["captain_id"]),
        "vice_captain_id": int(value["vice_captain_id"]),
        "bank_before": 100.0,
        "bank_after": float(value.get("bank") or 0.0),
        "free_transfers_before": 0,
        "free_transfers_after_decision": 0,
        "expected_gameweek_points": float(value.get("expected_gw1_points") or 0.0),
        "expected_horizon_points": float(value.get("expected_horizon_points") or 0.0),
        "no_chip_horizon_points": float(value.get("expected_horizon_points") or 0.0),
        "expected_horizon_gain": 0.0,
        "future_opportunity_cost": 0.0,
        "uncertainty_penalty": 0.0,
        "search_score": float(value.get("expected_horizon_points") or 0.0),
        "reason": f"configured opening profile: {value.get('profile')}",
    }


def _validate_frozen_branch(branch: Mapping[str, Any]) -> None:
    squad = list(branch.get("squad") or [])
    squad_ids = [int(row["player_id"]) for row in squad]
    starting = [int(value) for value in branch.get("starting_ids") or []]
    bench = [int(value) for value in branch.get("bench_order") or []]
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        raise ValueError("Every frozen branch requires 15 unique squad players")
    if len(starting) != 11 or len(set(starting)) != 11:
        raise ValueError("Every frozen branch requires 11 unique starters")
    if len(bench) != 4 or len(set(bench)) != 4:
        raise ValueError("Every frozen branch requires an ordered four-player bench")
    if set(starting).intersection(bench) or set(starting).union(bench) != set(squad_ids):
        raise ValueError("Frozen starters and bench must partition the squad")
    for role in ("captain_id", "vice_captain_id"):
        if int(branch.get(role) or 0) not in starting:
            raise ValueError(f"Frozen {role} must be in the starting XI")
    if int(branch["captain_id"]) == int(branch["vice_captain_id"]):
        raise ValueError("Captain and vice-captain must be different players")
    if any(not str(row.get("position") or "").strip() for row in squad):
        raise ValueError("Every frozen squad player requires a position")


def _official_player_results(live_payload: Mapping[str, Any]) -> dict[int, dict[str, float]]:
    output: dict[int, dict[str, float]] = {}
    for element in live_payload.get("elements", []):
        player_id = int(element["id"])
        stats = element.get("stats") or {}
        output[player_id] = {
            "points": float(stats.get("total_points") or 0.0),
            "minutes": float(stats.get("minutes") or 0.0),
        }
    if not output:
        raise ValueError("Official live payload contains no player results")
    return output


def _formation(squad: pd.DataFrame, starting_ids: Sequence[int]) -> str:
    selected = squad[squad["player_id"].isin(starting_ids)]
    positions = selected["position"].astype(str).str.upper().replace({"GKP": "GK"})
    return "-".join(
        str(int((positions == position).sum())) for position in ("DEF", "MID", "FWD")
    )


def _squad_news(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        {
            "player_id": row.get("element_id", row.get("player_id")),
            "status": row.get("status"),
            "chance_of_playing_next_round": row.get("chance_of_playing_next_round"),
            "news": row.get("news"),
            "start_likelihood": row.get("start_likelihood"),
            "set_piece": row.get("set_piece"),
        }
        for row in rows
    ]


def _gameweek_root(value: Mapping[str, Any], root: Path) -> Path:
    return root / str(value["season"]) / f"GW{int(value['gameweek']):02d}"


def _write_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(f"Refusing to overwrite immutable evidence: {path}")
        return
    path.write_text(encoded, encoding="utf-8")


def _capture_live(team_id: int | None, root: Path) -> dict[str, Any]:
    from api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        season_response = client.get("/api/fpl/season-state")
        season_response.raise_for_status()
        season_state = season_response.json()["season_state"]
        if season_state == "pre_season":
            response = client.get(
                "/api/predictions/initial-squad?horizon=8&risk_profile=balanced"
            )
            response.raise_for_status()
            # The recommendation request can refresh live artifacts. Capture the
            # observation time only after the complete payload has arrived so its
            # data cutoff can never legitimately be later than the snapshot.
            captured_at = utc_now()
            snapshot = build_initial_squad_snapshot(
                response.json(), captured_at=captured_at
            )
        else:
            if team_id is None:
                raise ValueError("--team-id is required after the GW1 deadline")
            response = client.get(
                "/api/predictions/planner",
                params={"team_id": team_id, "horizon": 8, "include_evidence": True},
            )
            response.raise_for_status()
            captured_at = utc_now()
            snapshot = build_planner_snapshot(
                response.json(), captured_at=captured_at, team_id=team_id
            )
    path = persist_snapshot(snapshot, root)
    return {
        "status": "captured",
        "path": str(path),
        "snapshot_hash": snapshot["snapshot_hash"],
        "season": snapshot["season"],
        "gameweek": snapshot["gameweek"],
        "candidate_count": snapshot["candidate_count"],
    }


async def _settle_live(season: str, gameweek: int, root: Path) -> dict[str, Any]:
    from api import fpl_client

    snapshot = load_latest_snapshot(season, gameweek, root)
    if snapshot is None:
        raise FileNotFoundError(f"No snapshot exists for {season} GW{gameweek}")
    bootstrap, live_payload = await asyncio.gather(
        fpl_client.get_bootstrap(),
        fpl_client.get_live_gw(gameweek),
    )
    outcome = build_finalized_outcome(
        snapshot,
        bootstrap=bootstrap,
        live_payload=live_payload,
        finalized_at=utc_now(),
    )
    path = persist_outcome(outcome, root)
    return {
        "status": "finalized",
        "path": str(path),
        "outcome_hash": outcome["outcome_hash"],
        "selected_net_points": outcome["selected_net_points"],
        "selected_regret": outcome["selected_regret"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=EVIDENCE_ROOT,
        help="Override the immutable evidence directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="Freeze the current deadline decision")
    capture.add_argument("--team-id", type=int)
    settle = subparsers.add_parser("settle", help="Settle a data-checked official event")
    settle.add_argument("--season", required=True)
    settle.add_argument("--gameweek", required=True, type=int)
    subparsers.add_parser("status", help="Show captured and finalized Gameweeks")
    args = parser.parse_args()
    try:
        if args.command == "capture":
            result = _capture_live(args.team_id, args.root)
        elif args.command == "settle":
            result = asyncio.run(_settle_live(args.season, args.gameweek, args.root))
        else:
            result = evidence_status(args.root)
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc)},
                indent=2,
                sort_keys=True,
            )
        )
        sys.exit(2)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
