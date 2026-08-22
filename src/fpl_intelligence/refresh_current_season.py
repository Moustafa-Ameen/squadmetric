"""One-command, fail-closed refresh of all live 2026/27 serving artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from fpl_intelligence.artifact_contract import (
    LIVE_CURRENT_HISTORY_PATH,
    PROCESSED_DIR,
    RAW_DIR,
    build_current_artifact_manifest,
    file_sha256,
    load_current_artifact_manifest,
    save_current_artifact_manifest,
    validate_current_artifacts,
)
from fpl_intelligence.availability import bootstrap_availability_events
from fpl_intelligence.fetch_fpl import (
    FPL_BOOTSTRAP_URL,
    load_players,
    save_bootstrap_contract,
    save_json,
    save_players,
)
from fpl_intelligence.live_model_training import (
    LIVE_MODEL_METADATA_PATH,
    train_live_models,
)
from fpl_intelligence.rank_players import (
    add_preseason_priors,
    add_rule_based_scores,
    save_ranked_players,
)
from fpl_intelligence.season_rules import (
    RULES_SCHEMA_VERSION,
    build_season_rules,
    build_snapshot_metadata,
    infer_season_from_bootstrap,
    payload_hash,
    rules_contract_hash,
    save_immutable_snapshot,
    validate_bootstrap_onboarding,
)
from fpl_intelligence.step4_models import load_historical_player_gameweeks

FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"
BOOTSTRAP_PATH = RAW_DIR / "bootstrap-static.json"
FIXTURES_PATH = RAW_DIR / "fixtures.json"
PLAYERS_CURRENT_PATH = PROCESSED_DIR / "players_current.csv"
PLAYERS_RANKED_PATH = PROCESSED_DIR / "players_ranked.csv"
REFRESH_REPORT_PATH = PROCESSED_DIR / "current_season_refresh_report.json"
AVAILABILITY_EVENTS_PATH = PROCESSED_DIR / "current_availability_events.json"


def _fetch_json(url: str) -> Any:
    import requests

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def refresh_current_season(
    *,
    expected_season: str = "2026-27",
    bootstrap: dict[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
    train_models: bool = True,
    accept_rule_change: bool = False,
) -> dict[str, Any]:
    """Refresh source snapshots, serving tables, models, and manifest as one unit."""

    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    bootstrap_payload = bootstrap or _fetch_json(FPL_BOOTSTRAP_URL)
    fixture_payload = fixtures if fixtures is not None else _fetch_json(FPL_FIXTURES_URL)
    season = infer_season_from_bootstrap(bootstrap_payload)
    if season != expected_season:
        raise ValueError(
            f"Official bootstrap season {season} does not match expected {expected_season}"
        )
    onboarding_errors = validate_bootstrap_onboarding(
        bootstrap_payload, season=expected_season
    )
    if onboarding_errors:
        raise ValueError("Bootstrap onboarding failed: " + "; ".join(onboarding_errors))
    if len(bootstrap_payload.get("teams", [])) != 20:
        raise ValueError("Official bootstrap must contain exactly 20 teams")
    if not bootstrap_payload.get("elements"):
        raise ValueError("Official bootstrap contains no players")
    if any(player.get("now_cost") in {None, 0} for player in bootstrap_payload["elements"]):
        raise ValueError("One or more current players has no official FPL price")

    rules = build_season_rules(
        bootstrap_payload,
        season=season,
        source_url=FPL_BOOTSTRAP_URL,
        retrieved_at=timestamp,
        cutoff_at=timestamp,
    )
    previous_manifest = load_current_artifact_manifest()
    previous_contract_hash = (
        previous_manifest.get("rules_contract_hash")
        if previous_manifest and previous_manifest.get("season") == season
        else None
    )
    current_contract_hash = rules_contract_hash(rules)
    if (
        previous_contract_hash
        and previous_contract_hash != current_contract_hash
        and not accept_rule_change
    ):
        raise RuntimeError(
            "Decision-relevant FPL rules changed. Review the new contract and rerun "
            "with --accept-rule-change before rebuilding serving artifacts."
        )

    save_json(bootstrap_payload, BOOTSTRAP_PATH)
    save_json(fixture_payload, FIXTURES_PATH)
    _, bootstrap_metadata_path, rules_manifest_path = save_bootstrap_contract(
        bootstrap_payload,
        season=season,
        retrieved_at=timestamp,
        cutoff_at=timestamp,
    )
    fixture_metadata = build_snapshot_metadata(
        fixture_payload,
        season=season,
        source_url=FPL_FIXTURES_URL,
        retrieved_at=timestamp,
        cutoff_at=timestamp,
        schema_version=RULES_SCHEMA_VERSION,
    )
    fixture_snapshot_path, fixture_metadata_path = save_immutable_snapshot(
        fixture_payload,
        fixture_metadata,
        artifact_name="fixtures",
    )
    players = load_players(bootstrap_payload)
    players["season"] = season
    players["bootstrap_hash"] = payload_hash(bootstrap_payload)
    players["data_cutoff"] = timestamp
    history = load_historical_player_gameweeks()
    players = add_preseason_priors(players, history)
    ranked = add_rule_based_scores(players)
    save_players(players, PLAYERS_CURRENT_PATH)
    save_ranked_players(ranked, PLAYERS_RANKED_PATH)
    availability_events = bootstrap_availability_events(
        bootstrap_payload["elements"],
        observed_at=timestamp,
        source=FPL_BOOTSTRAP_URL,
    )
    AVAILABILITY_EVENTS_PATH.write_text(
        json.dumps(
            {
                "schema_version": "current-availability-events-v1",
                "season": season,
                "generated_at": timestamp,
                "bootstrap_hash": payload_hash(bootstrap_payload),
                "events": [event.to_record() for event in availability_events],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if train_models:
        finalized_current = (
            pd.read_csv(LIVE_CURRENT_HISTORY_PATH)
            if LIVE_CURRENT_HISTORY_PATH.exists()
            else None
        )
        model_metadata = train_live_models(
            history,
            target_season=season,
            generated_at=timestamp,
            finalized_current_season=finalized_current,
            finalized_current_season_file_hash=(
                file_sha256(LIVE_CURRENT_HISTORY_PATH)
                if LIVE_CURRENT_HISTORY_PATH.exists()
                else None
            ),
        )
        model_metadata_payload = {
            "training_seasons": model_metadata.training_seasons,
            "training_rows": model_metadata.training_rows,
        }
    elif not LIVE_MODEL_METADATA_PATH.exists():
        raise FileNotFoundError(
            "Live-model metadata is missing and train_models=False was requested"
        )
    else:
        model_metadata = None
        model_metadata_payload = json.loads(
            LIVE_MODEL_METADATA_PATH.read_text(encoding="utf-8")
        )

    manifest = build_current_artifact_manifest(
        bootstrap=bootstrap_payload,
        fixtures_path=FIXTURES_PATH,
        players_current_path=PLAYERS_CURRENT_PATH,
        players_ranked_path=PLAYERS_RANKED_PATH,
        rules=rules,
        rules_manifest_path=rules_manifest_path,
        availability_events_path=AVAILABILITY_EVENTS_PATH,
        generated_at=timestamp,
    )
    manifest_path = save_current_artifact_manifest(manifest)
    readiness = validate_current_artifacts(
        expected_season=season,
        check_models=True,
    )
    report = {
        "status": readiness.status,
        "season": season,
        "generated_at": timestamp,
        "player_count": len(players),
        "team_count": len(bootstrap_payload.get("teams", [])),
        "fixture_count": len(fixture_payload),
        "bootstrap_hash": payload_hash(bootstrap_payload),
        "rules_version": rules.rules_version,
        "rules_payload_hash": rules.payload_hash,
        "rules_contract_hash": current_contract_hash,
        "chip_count": len(rules.chips),
        "chip_reset_gameweek": rules.chip_reset_gameweek,
        "dc_rule_version": rules.dc_rule_version,
        "bps_rule_version": rules.bps_rule_version,
        "training_seasons": (
            model_metadata_payload.get("training_seasons")
        ),
        "training_rows": (
            model_metadata_payload.get("training_rows")
        ),
        "paths": {
            "bootstrap": str(BOOTSTRAP_PATH),
            "bootstrap_metadata": str(bootstrap_metadata_path),
            "fixture_snapshot": str(fixture_snapshot_path),
            "fixture_metadata": str(fixture_metadata_path),
            "players_current": str(PLAYERS_CURRENT_PATH),
            "players_ranked": str(PLAYERS_RANKED_PATH),
            "rules_manifest": str(rules_manifest_path),
            "artifact_manifest": str(manifest_path),
            "model_metadata": str(LIVE_MODEL_METADATA_PATH),
            "launch_evidence": str(manifest.launch_evidence_path),
            "availability_events": str(AVAILABILITY_EVENTS_PATH),
        },
        "errors": readiness.errors,
        "warnings": readiness.warnings,
        "availability_event_count": len(availability_events),
    }
    REFRESH_REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not readiness.ready:
        raise RuntimeError(
            "Current-season refresh failed readiness: " + "; ".join(readiness.errors)
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-27")
    parser.add_argument(
        "--skip-model-training",
        action="store_true",
        help="Reuse an already-built live model bundle.",
    )
    parser.add_argument(
        "--accept-rule-change",
        action="store_true",
        help="Acknowledge a reviewed change to decision-relevant FPL rules.",
    )
    args = parser.parse_args()
    report = refresh_current_season(
        expected_season=args.season,
        train_models=not args.skip_model_training,
        accept_rule_change=args.accept_rule_change,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
