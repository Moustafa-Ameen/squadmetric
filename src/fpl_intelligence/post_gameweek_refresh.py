"""Finalized-only, rollback-safe post-Gameweek serving refresh.

This workflow never executes FPL actions. It detects official events that are
both finished and data-checked, builds point-in-time current-season training
rows from pre-deadline snapshots, settles frozen decision evidence, retrains the
already-accepted serving model family, and publishes only after readiness
validation succeeds.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fpl_intelligence.artifact_contract import (
    CURRENT_ARTIFACT_MANIFEST_PATH,
    LIVE_CURRENT_HISTORY_PATH,
)
from fpl_intelligence.live_decision_evidence import (
    EVIDENCE_ROOT,
    build_finalized_outcome,
    canonical_hash,
    load_latest_snapshot,
    persist_outcome,
)
from fpl_intelligence.live_model_training import (
    LIVE_GRADIENT_MODEL_PATH,
    LIVE_MINUTES_BAND_MODEL_PATH,
    LIVE_MINUTES_MODEL_PATH,
    LIVE_MODEL_METADATA_PATH,
    LIVE_RIDGE_MODEL_PATH,
    train_live_models,
)
from fpl_intelligence.refresh_current_season import (
    AVAILABILITY_EVENTS_PATH,
    BOOTSTRAP_PATH,
    FIXTURES_PATH,
    PLAYERS_CURRENT_PATH,
    PLAYERS_RANKED_PATH,
    REFRESH_REPORT_PATH,
    _fetch_json,
    refresh_current_season,
)
from fpl_intelligence.season_rules import (
    build_snapshot_metadata,
    infer_season_from_bootstrap,
    payload_hash,
    save_immutable_snapshot,
)
from fpl_intelligence.step4_models import load_historical_player_gameweeks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_ROOT = PROJECT_ROOT / "data" / "raw" / "snapshots"
RUN_ROOT = PROJECT_ROOT / "data" / "processed" / "post_gameweek_refresh" / "runs"
FPL_EVENT_LIVE_URL = "https://fantasy.premierleague.com/api/event/{gameweek}/live/"
MIN_FINALIZED_PLAYER_ROWS = 50
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def finalized_gameweeks(bootstrap: Mapping[str, Any]) -> tuple[int, ...]:
    """Return only official events safe for outcome ingestion."""

    return tuple(
        sorted(
            int(event["id"])
            for event in bootstrap.get("events", [])
            if event.get("id") is not None
            and bool(event.get("finished"))
            and bool(event.get("data_checked"))
        )
    )


def select_predeadline_bootstrap_snapshot(
    *,
    season: str,
    deadline: str,
    snapshot_root: Path = SNAPSHOT_ROOT,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Load the latest immutable bootstrap whose cutoff is not after deadline."""

    deadline_time = _parse_timestamp(deadline)
    candidates: list[tuple[datetime, Path, dict[str, Any]]] = []
    directory = snapshot_root / season
    for metadata_path in directory.glob("bootstrap-*.metadata.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        cutoff = _parse_timestamp(str(metadata["cutoff_at"]))
        if cutoff <= deadline_time:
            candidates.append((cutoff, metadata_path, metadata))
    if not candidates:
        raise FileNotFoundError(
            f"No immutable {season} bootstrap snapshot exists on or before {deadline}"
        )
    _, metadata_path, metadata = max(candidates, key=lambda value: value[0])
    payload_path = metadata_path.with_name(
        metadata_path.name.replace(".metadata.json", ".json")
    )
    if not payload_path.is_file():
        raise FileNotFoundError(f"Snapshot payload is missing: {payload_path}")
    bootstrap = json.loads(payload_path.read_text(encoding="utf-8"))
    if payload_hash(bootstrap) != metadata.get("payload_hash"):
        raise ValueError(f"Snapshot payload hash does not match metadata: {payload_path}")
    return bootstrap, metadata, payload_path


def build_finalized_gameweek_rows(
    *,
    season: str,
    gameweek: int,
    final_bootstrap: Mapping[str, Any],
    predeadline_bootstrap: Mapping[str, Any],
    predeadline_metadata: Mapping[str, Any],
    fixtures: list[Mapping[str, Any]],
    live_payload: Mapping[str, Any],
    prior_live_history: pd.DataFrame | None = None,
    finalized_at: str,
) -> pd.DataFrame:
    """Create compact live-training rows with deadline-safe features."""

    event = _event(final_bootstrap, gameweek)
    if not bool(event.get("finished")) or not bool(event.get("data_checked")):
        raise ValueError("Gameweek outcomes are not officially finished and data-checked")
    deadline = str(event.get("deadline_time") or "")
    if not deadline:
        raise ValueError(f"Official GW{gameweek} event is missing its deadline")
    cutoff = str(predeadline_metadata.get("cutoff_at") or "")
    if _parse_timestamp(cutoff) > _parse_timestamp(deadline):
        raise ValueError("Pre-deadline snapshot cutoff is after the official deadline")

    teams = {
        int(team["id"]): dict(team)
        for team in predeadline_bootstrap.get("teams", [])
        if team.get("id") is not None
    }
    elements = {
        int(player["id"]): dict(player)
        for player in predeadline_bootstrap.get("elements", [])
        if player.get("id") is not None
    }
    live = {
        int(player["id"]): dict(player.get("stats") or {})
        for player in live_payload.get("elements", [])
        if player.get("id") is not None
    }
    if not elements or not live:
        raise ValueError("Official player payloads are empty")
    event_fixtures = [
        dict(fixture)
        for fixture in fixtures
        if int(fixture.get("event") or 0) == int(gameweek)
    ]
    if not event_fixtures:
        raise ValueError(f"Official fixtures contain no GW{gameweek} matches")
    fixtures_by_team: dict[int, list[dict[str, Any]]] = {}
    for fixture in event_fixtures:
        for key in ("team_h", "team_a"):
            team_id = int(fixture[key])
            fixtures_by_team.setdefault(team_id, []).append(fixture)

    prior = (
        pd.DataFrame()
        if prior_live_history is None
        else prior_live_history.copy()
    )
    rows: list[dict[str, Any]] = []
    for player_id, player in elements.items():
        team_id = int(player.get("team") or 0)
        player_fixtures = fixtures_by_team.get(team_id, [])
        if not player_fixtures:
            continue
        stats = live.get(player_id)
        if stats is None:
            raise ValueError(f"Official live payload is missing player {player_id}")
        opponent_strengths: list[float] = []
        venues: list[str] = []
        for fixture in player_fixtures:
            was_home = int(fixture["team_h"]) == team_id
            opponent_id = int(fixture["team_a"] if was_home else fixture["team_h"])
            opponent = teams.get(opponent_id)
            if opponent is None:
                raise ValueError(f"Pre-deadline snapshot is missing team {opponent_id}")
            strength_key = "strength_overall_away" if was_home else "strength_overall_home"
            opponent_strengths.append(float(opponent.get(strength_key) or 0.0))
            venues.append("H" if was_home else "A")
        player_prior = (
            prior.iloc[0:0]
            if prior.empty
            else prior[
                pd.to_numeric(prior["player_id"], errors="raise")
                .astype(int)
                .eq(player_id)
            ].sort_values("gameweek")
        )
        previous = player_prior.tail(3)
        rows.append(
            {
                "season": season,
                "player_id": player_id,
                "player_name": _player_name(player),
                "gameweek": int(gameweek),
                "feature_cutoff_gameweek": int(gameweek) - 1,
                "price_before_deadline": float(player.get("now_cost") or 0.0) / 10.0,
                "minutes_last_3": float(
                    pd.to_numeric(previous.get("minutes"), errors="coerce").fillna(0).sum()
                )
                if not previous.empty
                else 0.0,
                "points_last_3": float(
                    pd.to_numeric(
                        previous.get("next_gameweek_points"), errors="coerce"
                    ).fillna(0).sum()
                )
                if not previous.empty
                else 0.0,
                "opponent_strength": float(sum(opponent_strengths) / len(opponent_strengths)),
                "selected_by_percent_before_deadline": float(
                    player.get("selected_by_percent") or 0.0
                ),
                "market_snapshot_available": 1,
                "position": POSITION_MAP.get(int(player.get("element_type") or 0), ""),
                "home_or_away": venues[0] if len(set(venues)) == 1 else "M",
                "minutes": float(stats.get("minutes") or 0.0),
                "next_gameweek_points": float(stats.get("total_points") or 0.0),
                "official_finished": True,
                "official_data_checked": True,
                "official_event_hash": canonical_hash(event),
                "official_live_payload_hash": canonical_hash(live_payload),
                "predeadline_bootstrap_hash": payload_hash(predeadline_bootstrap),
                "data_cutoff": cutoff,
                "deadline": deadline,
                "finalized_at": finalized_at,
            }
        )
    output = pd.DataFrame(rows).sort_values("player_id").reset_index(drop=True)
    _validate_gameweek_rows(output, season=season, gameweek=gameweek)
    expected_player_ids = {
        player_id
        for player_id, player in elements.items()
        if int(player.get("team") or 0) in fixtures_by_team
    }
    if set(output["player_id"].astype(int)) != expected_player_ids:
        raise ValueError(
            f"GW{gameweek} finalized rows do not match the pre-deadline fixture pool"
        )
    return output


def merge_finalized_history(
    existing: pd.DataFrame | None,
    new_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, bool]:
    """Idempotently append one finalized GW and reject conflicting outcomes."""

    current = pd.DataFrame() if existing is None else existing.copy()
    if current.empty:
        combined = new_rows.copy()
        _validate_live_history(combined)
        return combined, True
    keys = ["season", "gameweek", "player_id"]
    overlap = current.merge(new_rows, on=keys, how="inner", suffixes=("_old", "_new"))
    if not overlap.empty:
        old_hashes = set(overlap["official_live_payload_hash_old"].astype(str))
        new_hashes = set(overlap["official_live_payload_hash_new"].astype(str))
        if old_hashes != new_hashes or len(overlap) != len(new_rows):
            raise ValueError("Finalized live history conflicts with an existing Gameweek")
        _validate_live_history(current)
        return current, False
    combined = pd.concat([current, new_rows], ignore_index=True, sort=False)
    combined = combined.sort_values(keys).reset_index(drop=True)
    _validate_live_history(combined)
    return combined, True


def publish_transactionally(
    staged_files: Mapping[Path, Path],
    *,
    protected_paths: tuple[Path, ...],
    finalize: Callable[[], Any],
) -> Any:
    """Publish exact files and restore the prior serving bundle on any failure."""

    all_paths = tuple(dict.fromkeys((*protected_paths, *staged_files.values())))
    with tempfile.TemporaryDirectory(prefix="fpl-refresh-backup-") as temporary:
        backup_root = Path(temporary)
        backups: dict[Path, Path | None] = {}
        for index, destination in enumerate(all_paths):
            if destination.exists():
                backup = backup_root / f"{index:03d}-{destination.name}"
                shutil.copy2(destination, backup)
                backups[destination] = backup
            else:
                backups[destination] = None
        try:
            for source, destination in staged_files.items():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary_destination = destination.with_name(
                    f".{destination.name}.publishing"
                )
                shutil.copy2(source, temporary_destination)
                os.replace(temporary_destination, destination)
            return finalize()
        except Exception:
            for destination, backup in backups.items():
                if backup is None:
                    destination.unlink(missing_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary_destination = destination.with_name(
                        f".{destination.name}.restoring"
                    )
                    shutil.copy2(backup, temporary_destination)
                    os.replace(temporary_destination, destination)
            raise


def run_post_gameweek_refresh(
    *,
    season: str = "2026-27",
    bootstrap: dict[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
    live_payloads: Mapping[int, Mapping[str, Any]] | None = None,
    generated_at: str | None = None,
    snapshot_root: Path = SNAPSHOT_ROOT,
    run_root: Path = RUN_ROOT,
    live_history_path: Path = LIVE_CURRENT_HISTORY_PATH,
    evidence_root: Path = EVIDENCE_ROOT,
    publish: bool = True,
    force_model_refresh: bool = False,
    serving_refresh: Callable[..., dict[str, Any]] = refresh_current_season,
) -> dict[str, Any]:
    """Ingest every newly finalized GW and safely refresh serving artifacts."""

    timestamp = generated_at or _utc_now()
    bootstrap_payload = bootstrap or _fetch_json(
        "https://fantasy.premierleague.com/api/bootstrap-static/"
    )
    fixture_payload = fixtures if fixtures is not None else _fetch_json(
        "https://fantasy.premierleague.com/api/fixtures/"
    )
    actual_season = infer_season_from_bootstrap(bootstrap_payload)
    if actual_season != season:
        raise ValueError(
            f"Official bootstrap season {actual_season} does not match expected {season}"
        )
    official_finalized = finalized_gameweeks(bootstrap_payload)
    existing = (
        pd.read_csv(live_history_path) if live_history_path.exists() else pd.DataFrame()
    )
    existing_gameweeks = (
        set(pd.to_numeric(existing["gameweek"], errors="raise").astype(int))
        if not existing.empty
        else set()
    )
    new_gameweeks = tuple(
        gameweek for gameweek in official_finalized if gameweek not in existing_gameweeks
    )
    combined = existing.copy()
    pending_outcomes: list[dict[str, Any]] = []
    warnings: list[str] = []
    snapshot_records: list[dict[str, Any]] = []
    live_payload_by_gameweek: dict[int, Mapping[str, Any]] = {}
    for gameweek in new_gameweeks:
        event = _event(bootstrap_payload, gameweek)
        predeadline, metadata, payload_path = select_predeadline_bootstrap_snapshot(
            season=season,
            deadline=str(event["deadline_time"]),
            snapshot_root=snapshot_root,
        )
        live_payload = (
            dict(live_payloads[gameweek])
            if live_payloads is not None and gameweek in live_payloads
            else _fetch_json(FPL_EVENT_LIVE_URL.format(gameweek=gameweek))
        )
        live_payload_by_gameweek[gameweek] = live_payload
        rows = build_finalized_gameweek_rows(
            season=season,
            gameweek=gameweek,
            final_bootstrap=bootstrap_payload,
            predeadline_bootstrap=predeadline,
            predeadline_metadata=metadata,
            fixtures=fixture_payload,
            live_payload=live_payload,
            prior_live_history=combined,
            finalized_at=timestamp,
        )
        combined, _ = merge_finalized_history(combined, rows)
        snapshot_records.append(
            {
                "gameweek": gameweek,
                "predeadline_bootstrap_path": str(payload_path),
                "predeadline_bootstrap_hash": payload_hash(predeadline),
                "official_live_payload_hash": canonical_hash(live_payload),
                "rows": len(rows),
            }
        )
        snapshot = load_latest_snapshot(season, gameweek, evidence_root)
        if snapshot is None:
            warnings.append(f"No frozen decision snapshot exists for GW{gameweek}")
        else:
            outcome = build_finalized_outcome(
                snapshot,
                bootstrap=bootstrap_payload,
                live_payload=live_payload,
                finalized_at=timestamp,
            )
            pending_outcomes.append(outcome)

    report: dict[str, Any] = {
        "schema_version": "post-gameweek-refresh-v1",
        "season": season,
        "generated_at": timestamp,
        "official_finalized_gameweeks": list(official_finalized),
        "previously_ingested_gameweeks": sorted(existing_gameweeks),
        "new_gameweeks": list(new_gameweeks),
        "settled_evidence": [],
        "source_snapshots": snapshot_records,
        "warnings": warnings,
        "production_model_family_changed": False,
        "automatic_fpl_actions": False,
    }
    if not new_gameweeks and not force_model_refresh:
        report["status"] = "no_new_finalized_gameweek"
        if publish:
            refresh = serving_refresh(
                expected_season=season,
                bootstrap=bootstrap_payload,
                fixtures=fixture_payload,
                generated_at=timestamp,
                train_models=False,
            )
            report["serving_readiness"] = refresh["status"]
            return _persist_run_report(report, root=run_root)
        return report

    _validate_live_history(combined)
    if not publish:
        report.update(
            {
                "status": "validated_not_published",
                "live_history_rows": len(combined),
            }
        )
        return report

    with tempfile.TemporaryDirectory(prefix="fpl-post-gw-stage-") as temporary:
        stage_root = Path(temporary)
        staged_history = stage_root / live_history_path.name
        if not combined.empty:
            combined.to_csv(staged_history, index=False)
        staged_models = stage_root / "models"
        metadata = train_live_models(
            load_historical_player_gameweeks(),
            target_season=season,
            output_dir=staged_models,
            generated_at=timestamp,
            finalized_current_season=(
                pd.read_csv(staged_history) if staged_history.exists() else None
            ),
            finalized_current_season_file_hash=(
                _file_sha256(staged_history) if staged_history.exists() else None
            ),
        )
        stage_to_live: dict[Path, Path] = {
            staged_models / LIVE_RIDGE_MODEL_PATH.name: LIVE_RIDGE_MODEL_PATH,
            staged_models / LIVE_GRADIENT_MODEL_PATH.name: LIVE_GRADIENT_MODEL_PATH,
            staged_models / LIVE_MINUTES_MODEL_PATH.name: LIVE_MINUTES_MODEL_PATH,
            staged_models / LIVE_MINUTES_BAND_MODEL_PATH.name: LIVE_MINUTES_BAND_MODEL_PATH,
            staged_models / LIVE_MODEL_METADATA_PATH.name: LIVE_MODEL_METADATA_PATH,
        }
        if staged_history.exists():
            stage_to_live[staged_history] = live_history_path

        staged_snapshot_root = stage_root / "snapshots"
        for record in snapshot_records:
            live_payload = live_payload_by_gameweek[int(record["gameweek"])]
            live_metadata = build_snapshot_metadata(
                live_payload,
                season=season,
                source_url=FPL_EVENT_LIVE_URL.format(gameweek=record["gameweek"]),
                retrieved_at=timestamp,
                cutoff_at=timestamp,
                schema_version="official-event-live-v1",
            )
            staged_payload, staged_metadata = save_immutable_snapshot(
                live_payload,
                live_metadata,
                root=staged_snapshot_root,
                artifact_name=f"event-{record['gameweek']}-live",
            )
            for staged_path in (staged_payload, staged_metadata):
                destination = snapshot_root / staged_path.relative_to(
                    staged_snapshot_root
                )
                stage_to_live[staged_path] = destination
            record["official_live_snapshot_path"] = str(
                snapshot_root / staged_payload.relative_to(staged_snapshot_root)
            )
            record["official_live_metadata_path"] = str(
                snapshot_root / staged_metadata.relative_to(staged_snapshot_root)
            )

        staged_evidence_root = stage_root / "evidence"
        settled: list[dict[str, Any]] = []
        for outcome in pending_outcomes:
            staged_outcome = persist_outcome(outcome, staged_evidence_root)
            destination = evidence_root / staged_outcome.relative_to(
                staged_evidence_root
            )
            stage_to_live[staged_outcome] = destination
            settled.append(
                {
                    "gameweek": int(outcome["gameweek"]),
                    "outcome_path": str(destination),
                    "outcome_hash": outcome["outcome_hash"],
                }
            )
        protected = (
            live_history_path,
            LIVE_RIDGE_MODEL_PATH,
            LIVE_GRADIENT_MODEL_PATH,
            LIVE_MINUTES_MODEL_PATH,
            LIVE_MINUTES_BAND_MODEL_PATH,
            LIVE_MODEL_METADATA_PATH,
            BOOTSTRAP_PATH,
            FIXTURES_PATH,
            PLAYERS_CURRENT_PATH,
            PLAYERS_RANKED_PATH,
            AVAILABILITY_EVENTS_PATH,
            CURRENT_ARTIFACT_MANIFEST_PATH,
            REFRESH_REPORT_PATH,
        )

        def finalize_serving() -> dict[str, Any]:
            return serving_refresh(
                expected_season=season,
                bootstrap=bootstrap_payload,
                fixtures=fixture_payload,
                generated_at=timestamp,
                train_models=False,
            )

        refresh = publish_transactionally(
            stage_to_live,
            protected_paths=protected,
            finalize=finalize_serving,
        )
    report.update(
        {
            "status": "published",
            "live_history_path": str(live_history_path),
            "live_history_rows": len(combined),
            "live_history_hash": (
                _file_sha256(live_history_path) if live_history_path.exists() else None
            ),
            "model_training_rows": metadata.training_rows,
            "model_training_seasons": metadata.training_seasons,
            "finalized_current_season_gameweeks": (
                metadata.finalized_current_season_gameweeks
            ),
            "serving_readiness": refresh["status"],
            "settled_evidence": settled,
        }
    )
    return _persist_run_report(report, root=run_root)


def _validate_gameweek_rows(
    rows: pd.DataFrame,
    *,
    season: str,
    gameweek: int,
) -> None:
    required = {
        "season",
        "player_id",
        "gameweek",
        "price_before_deadline",
        "minutes_last_3",
        "points_last_3",
        "opponent_strength",
        "selected_by_percent_before_deadline",
        "market_snapshot_available",
        "position",
        "home_or_away",
        "minutes",
        "next_gameweek_points",
        "official_finished",
        "official_data_checked",
    }
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"Finalized GW rows are missing columns: {sorted(missing)}")
    if len(rows) < MIN_FINALIZED_PLAYER_ROWS:
        raise ValueError(
            f"GW{gameweek} has only {len(rows)} player rows; expected at least "
            f"{MIN_FINALIZED_PLAYER_ROWS}"
        )
    if not rows["season"].astype(str).eq(season).all():
        raise ValueError("Finalized GW rows contain the wrong season")
    if not pd.to_numeric(rows["gameweek"], errors="raise").eq(gameweek).all():
        raise ValueError("Finalized GW rows contain the wrong Gameweek")
    if rows["player_id"].duplicated().any():
        raise ValueError("Finalized GW rows contain duplicate player IDs")
    if rows["position"].eq("").any():
        raise ValueError("Finalized GW rows contain unknown positions")
    if not _strict_true(rows["official_finished"]).all() or not _strict_true(
        rows["official_data_checked"]
    ).all():
        raise ValueError("Finalized GW rows contain provisional outcomes")


def _validate_live_history(history: pd.DataFrame) -> None:
    if history.empty:
        return
    if history.duplicated(["season", "gameweek", "player_id"]).any():
        raise ValueError("Live history contains duplicate season/GW/player rows")
    gameweeks = sorted(
        pd.to_numeric(history["gameweek"], errors="raise").astype(int).unique().tolist()
    )
    if gameweeks != list(range(1, max(gameweeks) + 1)):
        raise ValueError("Live history Gameweeks must be contiguous from GW1")
    if not _strict_true(history["official_finished"]).all():
        raise ValueError("Live history contains an unfinished Gameweek")
    if not _strict_true(history["official_data_checked"]).all():
        raise ValueError("Live history contains provisional scoring")
    if (
        pd.to_numeric(history["feature_cutoff_gameweek"], errors="raise")
        >= pd.to_numeric(history["gameweek"], errors="raise")
    ).any():
        raise ValueError("Live history contains a feature-cutoff violation")


def _event(bootstrap: Mapping[str, Any], gameweek: int) -> dict[str, Any]:
    event = next(
        (
            dict(value)
            for value in bootstrap.get("events", [])
            if int(value.get("id") or 0) == int(gameweek)
        ),
        None,
    )
    if event is None:
        raise ValueError(f"Official bootstrap is missing GW{gameweek}")
    return event


def _player_name(player: Mapping[str, Any]) -> str:
    first = str(player.get("first_name") or "").strip()
    second = str(player.get("second_name") or "").strip()
    return " ".join(value for value in (first, second) if value)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must be timezone-aware: {value}")
    return parsed.astimezone(UTC)


def _strict_true(values: pd.Series) -> pd.Series:
    """Interpret only explicit boolean/1/true values as true."""

    return values.astype("string").str.strip().str.lower().isin({"true", "1"})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _persist_run_report(
    report: dict[str, Any],
    *,
    root: Path = RUN_ROOT,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    report.pop("report_hash", None)
    report.pop("report_path", None)
    report["report_hash"] = canonical_hash(report)
    timestamp = str(report["generated_at"]).replace(":", "-")
    path = root / f"{timestamp}-{report['report_hash'][:16]}.json"
    report["report_path"] = str(path)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise FileExistsError(f"Refusing to overwrite refresh report: {path}")
    path.write_text(encoded, encoding="utf-8")
    report["report_path"] = str(path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2026-27")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate new finalized rows without publishing serving artifacts.",
    )
    parser.add_argument(
        "--force-model-refresh",
        action="store_true",
        help="Refit the fixed serving model even when no new Gameweek finalized.",
    )
    args = parser.parse_args()
    try:
        report = run_post_gameweek_refresh(
            season=args.season,
            publish=not args.dry_run,
            force_model_refresh=args.force_model_refresh,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc)},
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2) from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
