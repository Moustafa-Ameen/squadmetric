from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
from api.routers.fpl_live import _detect_season_state

from fpl_intelligence.artifact_contract import (
    CURRENT_ARTIFACT_MANIFEST_PATH,
    validate_current_artifacts,
)
from fpl_intelligence.live_model_training import LIVE_MINUTES_BAND_MODEL_PATH
from fpl_intelligence.rank_players import add_preseason_priors
from fpl_intelligence.season_rules import (
    build_season_rules,
    rules_contract_hash,
    save_rules_manifest,
)


def test_current_2026_27_artifacts_pass_real_readiness():
    readiness = validate_current_artifacts(
        expected_season="2026-27",
        check_models=True,
    )

    assert readiness.ready, readiness.errors
    assert readiness.manifest is not None
    assert readiness.manifest["player_count"] > 500
    assert readiness.manifest["team_count"] == 20


def test_current_teams_are_promoted_and_relegated_correctly():
    manifest = json.loads(
        CURRENT_ARTIFACT_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    bootstrap = json.loads(
        Path(manifest["bootstrap_path"]).read_text(encoding="utf-8")
    )
    teams = {team["name"] for team in bootstrap["teams"]}

    assert {"Coventry City", "Hull City", "Ipswich Town"} <= teams
    assert not {"Burnley", "West Ham United", "Wolverhampton Wanderers"} & teams

    rules = json.loads(
        Path(manifest["rules_manifest_path"]).read_text(encoding="utf-8")
    )
    chips = rules["chips"]
    assert len(chips) == 8
    assert not any(chip["name"] == "assistant_manager" for chip in chips)
    assert rules["chip_reset_gameweek"] == 19
    assert rules["bps_rule_version"] == "bps_v2_2026_27"
    assert rules["dc_rule_version"] == "dc_v1"


def test_live_minutes_artifact_uses_importable_class():
    model = joblib.load(LIVE_MINUTES_BAND_MODEL_PATH)

    assert model.__class__.__module__ == "fpl_intelligence.minutes_model"
    assert model.__class__.__name__ == "MinutesBandConditionalModel"


def test_unstarted_live_bootstrap_is_preseason():
    bootstrap = {
        "events": [
            {
                "id": 1,
                "deadline_time": "2026-08-21T17:30:00Z",
                "is_next": True,
                "finished": False,
            }
        ]
    }
    state = _detect_season_state(
        bootstrap,
        {"season": "2026-27"},
        now=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert state == "pre_season"


def test_preseason_priors_match_names_not_season_local_ids():
    players = pd.DataFrame(
        [
            {
                "element_id": 1,
                "player_name": "Returning Player",
                "position": "Midfielder",
                "status": "a",
                "minutes": 0,
                "total_points": 0,
                "points_per_game": 0.0,
                "form": 0.0,
            },
            {
                "element_id": 9,
                "player_name": "Different New Player",
                "position": "Midfielder",
                "status": "a",
                "minutes": 0,
                "total_points": 0,
                "points_per_game": 0.0,
                "form": 0.0,
            },
        ]
    )
    history = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "player_id": 9,
                "player_name": "Returning Player",
                "position": "MID",
                "gameweek": gameweek,
                "minutes": 90,
                "total_points": points,
            }
            for gameweek, points in ((36, 5), (37, 7), (38, 9))
        ]
    )

    output = add_preseason_priors(players, history).set_index("player_name")

    assert output.loc["Returning Player", "form"] == 7.0
    assert output.loc["Returning Player", "prior_source"] == "returning_player_2025-26"
    assert (
        output.loc["Different New Player", "prior_source"]
        == "new_player_position_prior"
    )
    assert output.loc["Different New Player", "form"] == 3.4


def test_rules_manifest_reuses_identical_payload_across_retrievals(tmp_path: Path):
    bootstrap = {
        "events": [{"id": 1}, {"id": 38}],
        "chips": [],
        "element_types": [],
        "game_settings": {},
        "game_config": {"scoring": {}},
    }
    first = build_season_rules(
        bootstrap,
        season="2025-26",
        source_url="https://example.test",
        retrieved_at="2026-01-01T00:00:00Z",
    )
    second = build_season_rules(
        bootstrap,
        season="2025-26",
        source_url="https://example.test",
        retrieved_at="2026-01-02T00:00:00Z",
    )

    first_path = save_rules_manifest(first, root=tmp_path)
    second_path = save_rules_manifest(second, root=tmp_path)

    assert first_path == second_path
    assert rules_contract_hash(first) == rules_contract_hash(second)

    changed = build_season_rules(
        {
            **bootstrap,
            "game_config": {"scoring": {"transfer_cost": 8}},
        },
        season="2025-26",
        source_url="https://example.test",
    )
    assert rules_contract_hash(first) != rules_contract_hash(changed)
