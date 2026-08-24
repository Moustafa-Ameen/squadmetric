import asyncio
import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from api import readiness as readiness_module
from fastapi import HTTPException, Response

from fpl_intelligence.artifact_contract import ArtifactReadiness
from fpl_intelligence.season_rules import (
    build_season_rules,
    payload_hash,
    rules_contract_hash,
)


def _bootstrap(player_ids=(1, 2)):
    return {
        "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}],
        "elements": [{"id": player_id} for player_id in player_ids],
        "teams": [{"id": index} for index in range(1, 21)],
    }


def _stored_readiness(monkeypatch, tmp_path, bootstrap, fixtures, *, cutoff):
    bootstrap_path = tmp_path / "bootstrap.json"
    bootstrap_path.write_text(json.dumps(bootstrap), encoding="utf-8")
    players_path = tmp_path / "players_current.csv"
    pd.DataFrame({"element_id": [row["id"] for row in bootstrap["elements"]]}).to_csv(
        players_path, index=False
    )
    fixtures_path = tmp_path / "fixtures.json"
    fixtures_path.write_text(json.dumps(fixtures), encoding="utf-8")
    manifest = {
        "season": "2026-27",
        "data_cutoff": cutoff,
        "bootstrap_hash": payload_hash(bootstrap),
        "bootstrap_path": str(bootstrap_path),
        "fixtures_path": str(fixtures_path),
        "players_current_path": str(players_path),
        "player_count": len(bootstrap["elements"]),
        "team_count": 20,
        "rules_version": "2026-27-test",
        "rules_contract_hash": rules_contract_hash(
            build_season_rules(
                bootstrap,
                season="2026-27",
                source_url="test",
                retrieved_at=cutoff,
                cutoff_at=cutoff,
            )
        ),
    }
    monkeypatch.setattr(
        readiness_module,
        "artifact_readiness",
        lambda season, check_models: ArtifactReadiness(
            "ready", season, [], [], manifest, check_models
        ),
    )
    return manifest


def test_live_decision_readiness_accepts_identical_current_payloads(
    monkeypatch, tmp_path
):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    bootstrap = _bootstrap()
    fixtures = [{"id": 1, "event": 1, "team_h": 1, "team_a": 2}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        bootstrap,
        fixtures,
        cutoff=(now - timedelta(hours=2)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        bootstrap, fixtures, check_models=True, now=now
    )

    assert result.ready
    assert result.status == "ready"
    assert result.live_data["bootstrap_hash"] == payload_hash(bootstrap)
    assert result.live_data["player_count"] == 2
    assert result.blockers == []


def test_live_decision_readiness_allows_only_volatile_ownership_drift(
    monkeypatch, tmp_path
):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    stored_bootstrap = _bootstrap()
    for player in stored_bootstrap["elements"]:
        player["selected_by_percent"] = "10.0"
    live_bootstrap = json.loads(json.dumps(stored_bootstrap))
    live_bootstrap["total_players"] = 9_000_001
    live_bootstrap["elements"][0]["selected_by_percent"] = "10.1"
    live_bootstrap["elements"][0]["selected_rank"] = 42
    live_bootstrap["elements"][0]["selected_rank_type"] = 12
    live_bootstrap["elements"][0]["transfers_in_event"] = 12
    fixtures = [{"id": 1, "event": 1}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        stored_bootstrap,
        fixtures,
        cutoff=(now - timedelta(hours=1)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        live_bootstrap, fixtures, check_models=True, now=now
    )

    assert result.ready
    assert result.blockers == []
    assert any("ownership" in warning.lower() for warning in result.warnings)


def test_live_decision_readiness_applies_price_drift_without_a_rebuild(monkeypatch, tmp_path):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    stored_bootstrap = _bootstrap()
    stored_bootstrap["elements"][0]["now_cost"] = 50
    live_bootstrap = json.loads(json.dumps(stored_bootstrap))
    live_bootstrap["elements"][0]["now_cost"] = 51
    fixtures = [{"id": 1, "event": 1}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        stored_bootstrap,
        fixtures,
        cutoff=(now - timedelta(hours=1)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        live_bootstrap, fixtures, check_models=True, now=now
    )

    assert result.ready
    assert result.blockers == []
    assert any("prices" in warning.lower() for warning in result.warnings)


def test_live_decision_readiness_onboards_new_player_without_blocking(
    monkeypatch, tmp_path
):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    stored_bootstrap = _bootstrap()
    live_bootstrap = _bootstrap((1, 2, 3))
    fixtures = [{"id": 1, "event": 1}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        stored_bootstrap,
        fixtures,
        cutoff=(now - timedelta(hours=1)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        live_bootstrap, fixtures, check_models=True, now=now
    )
    assert result.ready
    assert result.blockers == []
    assert any("new player" in warning.lower() for warning in result.warnings)


def test_live_decision_readiness_applies_fixture_drift_without_a_rebuild(
    monkeypatch, tmp_path
):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    bootstrap = _bootstrap()
    stored_fixtures = [{"id": 1, "event": 1}]
    live_fixtures = [{"id": 1, "event": 2}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        bootstrap,
        stored_fixtures,
        cutoff=(now - timedelta(hours=1)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        bootstrap, live_fixtures, check_models=False, now=now
    )

    assert result.ready
    assert result.blockers == []
    assert any("fixtures" in warning.lower() for warning in result.warnings)


def test_live_decision_readiness_still_blocks_rules_drift(monkeypatch, tmp_path):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    stored_bootstrap = _bootstrap()
    stored_bootstrap["game_settings"] = {"squad_total_spend": 1000}
    live_bootstrap = json.loads(json.dumps(stored_bootstrap))
    live_bootstrap["game_settings"]["squad_total_spend"] = 1100
    fixtures = [{"id": 1, "event": 1}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        stored_bootstrap,
        fixtures,
        cutoff=(now - timedelta(hours=1)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        live_bootstrap, fixtures, check_models=True, now=now
    )

    assert "rules_contract_drift" in {row["code"] for row in result.blockers}


def test_live_decision_readiness_uses_live_inputs_with_old_model_snapshot(
    monkeypatch, tmp_path
):
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)
    bootstrap = _bootstrap()
    fixtures = [{"id": 1, "event": 1}]
    _stored_readiness(
        monkeypatch,
        tmp_path,
        bootstrap,
        fixtures,
        cutoff=(now - timedelta(hours=25)).isoformat(),
    )

    result = readiness_module.evaluate_live_decision_readiness(
        bootstrap, fixtures, check_models=False, now=now
    )

    assert result.ready
    assert result.blockers == []
    assert any("model snapshot" in warning.lower() for warning in result.warnings)
    assert result.artifact_data["age_hours"] == 25


def test_live_source_outage_returns_displayable_unavailable_state(monkeypatch):
    async def unavailable():
        raise HTTPException(status_code=503, detail="offline")

    monkeypatch.setattr(readiness_module.fpl_client, "get_bootstrap", unavailable)
    monkeypatch.setattr(readiness_module.fpl_client, "get_fixtures", unavailable)
    monkeypatch.setattr(
        readiness_module,
        "artifact_readiness",
        lambda season, check_models: ArtifactReadiness(
            "blocked", season, ["stored artifacts unavailable"], [], None, check_models
        ),
    )

    result, bootstrap, fixtures = asyncio.run(
        readiness_module.live_decision_context(check_models=True)
    )

    assert result.status == "unavailable"
    assert not result.ready
    assert bootstrap is None
    assert fixtures is None
    assert {row["code"] for row in result.blockers} == {
        "bootstrap_unavailable",
        "fixtures_unavailable",
    }


def test_recommendation_dependency_returns_structured_blockers(monkeypatch):
    blocked = readiness_module.LiveDecisionReadiness(
        status="blocked",
        season="2026-27",
        blockers=[{"code": "stale_artifacts", "message": "Artifacts are stale."}],
        warnings=[],
        manifest={},
        live_data={},
        artifact_data={},
        models_checked=True,
    )

    async def blocked_context(*, check_models):
        assert check_models
        return blocked, {}, []

    monkeypatch.setattr(readiness_module, "live_decision_context", blocked_context)

    with pytest.raises(HTTPException) as error:
        asyncio.run(readiness_module.require_current_artifacts(Response()))

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "recommendations_blocked"
    assert error.value.detail["blockers"][0]["code"] == "stale_artifacts"
