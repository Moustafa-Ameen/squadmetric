from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_intelligence.season_rules import (
    RULES_SCHEMA_VERSION,
    build_historical_season_rules,
    build_season_rules,
    build_snapshot_metadata,
    historical_regime,
    payload_hash,
    regime_from_rules,
    save_immutable_snapshot,
    save_rules_manifest,
    validate_bootstrap_onboarding,
)


def bootstrap_fixture() -> dict:
    teams = [
        {"id": 1, "name": "Coventry City", "short_name": "COV"},
        {"id": 2, "name": "Ipswich Town", "short_name": "IPS"},
        {"id": 3, "name": "Hull City", "short_name": "HUL"},
    ]
    positions = [
        {
            "id": 1,
            "singular_name": "Goalkeeper",
            "singular_name_short": "GKP",
            "squad_select": 2,
            "squad_min_play": 1,
            "squad_max_play": 1,
        },
        {
            "id": 2,
            "singular_name": "Defender",
            "singular_name_short": "DEF",
            "squad_select": 5,
            "squad_min_play": 3,
            "squad_max_play": 5,
        },
        {
            "id": 3,
            "singular_name": "Midfielder",
            "singular_name_short": "MID",
            "squad_select": 5,
            "squad_min_play": 2,
            "squad_max_play": 5,
        },
        {
            "id": 4,
            "singular_name": "Forward",
            "singular_name_short": "FWD",
            "squad_select": 3,
            "squad_min_play": 1,
            "squad_max_play": 3,
        },
    ]
    chips = [
        {
            "id": index,
            "name": name,
            "number": 1,
            "start_event": 1 if index > 4 else 2,
            "stop_event": 19 if index <= 4 else 38,
            "chip_type": "team",
            "overrides": {},
        }
        for index, name in enumerate(
            ["wildcard", "freehit", "bboost", "3xc"] * 2,
            start=1,
        )
    ]
    return {
        "unknown_future_key": {"preserve": True},
        "events": [{"id": 1}, {"id": 38}],
        "teams": teams,
        "element_types": positions,
        "elements": [
            {"id": 101, "team": 1, "element_type": 3},
            {"id": 102, "team": 2, "element_type": 4},
        ],
        "chips": chips,
        "game_settings": {
            "squad_total_spend": 1000,
            "ui_currency_multiplier": 10,
            "squad_squadsize": 15,
            "squad_squadplay": 11,
            "squad_team_limit": 3,
            "max_extra_free_transfers": 4,
            "transfers_sell_on_fee": 0.5,
        },
        "game_config": {
            "scoring": {
                "assists": 3,
                "defensive_contribution": {"DEF": 2, "MID": 2, "FWD": 2},
            }
        },
    }


def test_payload_hash_is_stable_and_changes_with_payload_content():
    payload = {"b": 2, "a": [1, 2]}
    equivalent = {"a": [1, 2], "b": 2}

    assert payload_hash(payload) == payload_hash(equivalent)
    assert payload_hash(payload) != payload_hash({"a": [1, 3], "b": 2})


def test_2026_27_rules_capture_chips_bps_and_constraints():
    rules = build_season_rules(
        bootstrap_fixture(),
        season="2026-27",
        source_url="https://example.test/bootstrap",
        retrieved_at="2026-07-22T12:00:00Z",
        cutoff_at="2026-07-22T12:00:00Z",
    )

    assert rules.schema_version == RULES_SCHEMA_VERSION
    assert rules.budget == 100.0
    assert rules.squad_size == 15
    assert rules.starting_xi_size == 11
    assert rules.max_players_per_team == 3
    assert rules.transfer_hit_cost == 4
    assert rules.max_free_transfers == 5
    assert len(rules.chips) == 8
    assert rules.chip_reset_gameweek == 19
    assert rules.chip_rules_version == "chips_v4_double_set_2026_27"
    assert rules.dc_rule_version == "dc_v1"
    assert rules.bps_rule_version == "bps_v2_2026_27"
    assert rules.position_limits["DEF"]["squad_select"] == 5
    by_name = {chip["name"]: chip for chip in rules.chips}
    assert by_name["wildcard"]["permanent_transfers"] is True
    assert by_name["freehit"]["free_hit_reversion"] is True
    assert by_name["bboost"]["bench_points_included"] is True
    assert by_name["3xc"]["captain_multiplier"] == 3


def test_historical_regimes_are_explicit_and_separate():
    assert historical_regime("2023-24") == {
        "dc_rule_version": "pre_dc",
        "bps_rule_version": "bps_pre_2025_26",
    }
    assert historical_regime("2024-25")["dc_rule_version"] == "pre_dc"
    assert historical_regime("2025-26") == {
        "dc_rule_version": "dc_v1",
        "bps_rule_version": "bps_v1_2025_26",
    }
    with pytest.raises(ValueError, match="load the versioned rules manifest"):
        historical_regime("2026-27")


def test_historical_manifests_cover_free_transfer_and_chip_eras():
    rules_2324 = build_historical_season_rules("2023-24")
    rules_2425 = build_historical_season_rules("2024-25")
    rules_2526 = build_historical_season_rules("2025-26")

    assert rules_2324.max_free_transfers == 2
    assert rules_2425.max_free_transfers == 5
    assert len(rules_2324.chips) == 5
    assert len(rules_2425.chips) == 6
    assert any(chip["name"] == "assistant_manager" for chip in rules_2425.chips)
    assistant_manager = next(
        chip for chip in rules_2425.chips if chip["name"] == "assistant_manager"
    )
    assert assistant_manager["duration_gameweeks"] == 3
    assert assistant_manager["blocks_other_chips"] is True
    assert len(rules_2526.chips) == 8
    assert rules_2526.chip_reset_gameweek == 19
    assert rules_2526.chip_rules_version == "chips_v3_double_set_2025_26"
    assert not any(chip["name"] == "assistant_manager" for chip in rules_2526.chips)
    assert rules_2324.scoring["status"] == "historical_contract_metadata"


def test_future_regimes_are_read_from_explicit_manifests():
    rules = build_season_rules(
        bootstrap_fixture(),
        season="2026-27",
        source_url="https://example.test/bootstrap",
    )

    assert regime_from_rules(rules) == {
        "dc_rule_version": "dc_v1",
        "bps_rule_version": "bps_v2_2026_27",
    }


def test_all_supported_historical_seasons_have_chip_manifests(tmp_path: Path):
    for season in ("2023-24", "2024-25", "2025-26"):
        rules = build_historical_season_rules(season)
        path = save_rules_manifest(rules, root=tmp_path)

        assert path.exists()
        assert rules.payload_hash
        assert rules.schema_version == RULES_SCHEMA_VERSION
        assert all("duration_gameweeks" in chip for chip in rules.chips)


def test_onboarding_requires_promoted_2026_27_teams_and_valid_references():
    bootstrap = bootstrap_fixture()
    assert validate_bootstrap_onboarding(bootstrap, season="2026-27") == []

    del bootstrap["teams"][2]
    errors = validate_bootstrap_onboarding(bootstrap, season="2026-27")
    assert "missing required 2026-27 team: Hull City" in errors
    assert "player 102 references unknown team 2" not in errors


def test_snapshot_preserves_raw_payload_and_is_immutable(tmp_path: Path):
    payload = bootstrap_fixture()
    metadata = build_snapshot_metadata(
        payload,
        season="2026-27",
        source_url="https://example.test/bootstrap",
        retrieved_at="2026-07-22T12:00:00Z",
        cutoff_at="2026-07-22T12:00:00Z",
    )

    snapshot_path, metadata_path = save_immutable_snapshot(payload, metadata, root=tmp_path / "raw")
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == payload
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["payload_hash"] == metadata[
        "payload_hash"
    ]

    changed_payload = {**payload, "unknown_future_key": {"preserve": False}}
    with pytest.raises(FileExistsError):
        save_immutable_snapshot(changed_payload, metadata, root=tmp_path / "raw")


def test_identical_snapshots_reuse_payload_storage_with_distinct_metadata(tmp_path: Path):
    payload = bootstrap_fixture()
    first_metadata = build_snapshot_metadata(
        payload,
        season="2026-27",
        source_url="https://example.test/bootstrap",
        retrieved_at="2026-07-22T12:00:00Z",
    )
    second_metadata = build_snapshot_metadata(
        payload,
        season="2026-27",
        source_url="https://example.test/bootstrap",
        retrieved_at="2026-07-22T13:00:00Z",
    )

    first_payload, first_meta = save_immutable_snapshot(
        payload, first_metadata, root=tmp_path / "raw"
    )
    second_payload, second_meta = save_immutable_snapshot(
        payload, second_metadata, root=tmp_path / "raw"
    )

    assert first_payload != second_payload
    assert first_meta != second_meta
    assert first_payload.stat().st_ino == second_payload.stat().st_ino
    assert json.loads(second_meta.read_text(encoding="utf-8"))["cutoff_at"] != json.loads(
        first_meta.read_text(encoding="utf-8")
    )["cutoff_at"]


def test_rules_manifest_is_content_addressed(tmp_path: Path):
    rules = build_season_rules(
        bootstrap_fixture(),
        season="2026-27",
        source_url="https://example.test/bootstrap",
        retrieved_at="2026-07-22T12:00:00Z",
        cutoff_at="2026-07-22T12:00:00Z",
    )
    path = save_rules_manifest(rules, root=tmp_path / "rules")
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["payload_hash"] == rules.payload_hash
