import asyncio
import json
from pathlib import Path

import pandas as pd
from api import fpl_client
from api import live_projection_service as projection_service
from api.routers import predictions as predictions_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_live_projection_cache_reuses_identical_data_hashes(monkeypatch):
    bootstrap = {
        "events": [{"id": 1, "is_next": True, "deadline_time": "2026-08-21T18:00:00Z"}],
        "elements": [],
        "teams": [],
        "element_types": [],
    }
    fixtures = [{"id": 1, "event": 1, "team_h": 1, "team_a": 2}]
    project_calls = 0

    async def fake_bootstrap():
        return bootstrap

    async def fake_fixtures():
        return fixtures

    def fake_project_players(*args, **kwargs):
        nonlocal project_calls
        project_calls += 1
        return [{"element_id": 1, "name": "Cached Player", "projections": []}]

    monkeypatch.setattr(projection_service.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(projection_service.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(projection_service, "current_player_rows", lambda payload: [])
    monkeypatch.setattr(projection_service, "load_planner_models", lambda model: {})
    monkeypatch.setattr(projection_service, "project_players", fake_project_players)
    monkeypatch.setattr(
        projection_service.data_service,
        "serving_player_gw",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        projection_service,
        "load_current_artifact_manifest",
        lambda: {"rules_version": "rules-v1"},
    )
    projection_service.clear_projection_cache()

    first, first_metadata = asyncio.run(
        projection_service.live_projection_rows(model_name="Ridge Regression")
    )
    first[0]["name"] = "Mutated by consumer"
    second, second_metadata = asyncio.run(
        projection_service.live_projection_rows(model_name="Ridge Regression")
    )

    assert project_calls == 1
    assert second[0]["name"] == "Cached Player"
    assert first_metadata["projection_bootstrap_hash"] == second_metadata[
        "projection_bootstrap_hash"
    ]
    assert first_metadata["projection_fixtures_hash"] == second_metadata[
        "projection_fixtures_hash"
    ]
    assert second_metadata["live_data_checked_at"] >= first_metadata[
        "live_data_checked_at"
    ]


def test_projection_cache_ignores_live_score_noise_but_keeps_metadata_fresh(
    monkeypatch,
):
    bootstrap = {
        "events": [
            {"id": 1, "is_current": True, "deadline_time": "2026-08-21T18:00:00Z"},
            {"id": 2, "is_next": True, "deadline_time": "2026-08-28T18:00:00Z"},
        ],
        "elements": [
            {
                "id": 1,
                "team": 1,
                "element_type": 3,
                "now_cost": 75,
                "selected_by_percent": "10.1",
                "event_points": 2,
                "bps": 7,
            }
        ],
        "teams": [{"id": 1, "name": "Home", "short_name": "HOM"}],
        "element_types": [{"id": 3, "singular_name_short": "MID"}],
    }
    fixtures = [
        {
            "id": 1,
            "event": 1,
            "team_h": 1,
            "team_a": 2,
            "team_h_score": 1,
            "team_a_score": 0,
        },
        {"id": 2, "event": 2, "team_h": 1, "team_a": 2},
    ]
    project_calls = 0

    async def fake_bootstrap():
        return bootstrap

    async def fake_fixtures():
        return fixtures

    def fake_project_players(*args, **kwargs):
        nonlocal project_calls
        project_calls += 1
        return [{"element_id": 1, "projections": []}]

    monkeypatch.setattr(projection_service.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(projection_service.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(projection_service, "current_player_rows", lambda payload: [])
    monkeypatch.setattr(projection_service, "load_planner_models", lambda model: {})
    monkeypatch.setattr(projection_service, "project_players", fake_project_players)
    monkeypatch.setattr(
        projection_service.data_service,
        "serving_player_gw",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        projection_service,
        "load_current_artifact_manifest",
        lambda: {"rules_version": "rules-v1"},
    )
    projection_service.clear_projection_cache()

    _, first_metadata = asyncio.run(
        projection_service.live_projection_rows(model_name="Ridge Regression")
    )
    bootstrap["elements"][0]["event_points"] = 9
    bootstrap["elements"][0]["bps"] = 42
    fixtures[0]["team_h_score"] = 4
    _, second_metadata = asyncio.run(
        projection_service.live_projection_rows(model_name="Ridge Regression")
    )

    assert project_calls == 1
    assert first_metadata["start_gameweek"] == 2
    assert first_metadata["bootstrap_hash"] != second_metadata["bootstrap_hash"]
    assert first_metadata["fixtures_hash"] != second_metadata["fixtures_hash"]
    assert (
        first_metadata["projection_bootstrap_hash"]
        == second_metadata["projection_bootstrap_hash"]
    )
    assert (
        first_metadata["projection_fixtures_hash"]
        == second_metadata["projection_fixtures_hash"]
    )


def test_projection_cache_invalidates_on_actionable_live_changes(monkeypatch):
    bootstrap = {
        "events": [{"id": 2, "is_next": True}],
        "elements": [
            {
                "id": 1,
                "team": 1,
                "element_type": 3,
                "now_cost": 75,
                "status": "a",
                "selected_by_percent": "10.0",
            }
        ],
        "teams": [{"id": 1}],
        "element_types": [{"id": 3, "singular_name_short": "MID"}],
    }
    fixtures = [{"id": 2, "event": 2, "team_h": 1, "team_a": 2}]
    project_calls = 0

    async def fake_bootstrap():
        return bootstrap

    async def fake_fixtures():
        return fixtures

    def fake_project_players(*args, **kwargs):
        nonlocal project_calls
        project_calls += 1
        return []

    monkeypatch.setattr(projection_service.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(projection_service.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(projection_service, "current_player_rows", lambda payload: [])
    monkeypatch.setattr(projection_service, "load_planner_models", lambda model: {})
    monkeypatch.setattr(projection_service, "project_players", fake_project_players)
    monkeypatch.setattr(
        projection_service.data_service,
        "serving_player_gw",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        projection_service,
        "load_current_artifact_manifest",
        lambda: {"rules_version": "rules-v1"},
    )
    projection_service.clear_projection_cache()

    asyncio.run(projection_service.live_projection_rows(model_name="Ridge Regression"))
    bootstrap["elements"][0]["status"] = "d"
    asyncio.run(projection_service.live_projection_rows(model_name="Ridge Regression"))
    fixtures[0]["event"] = 3
    asyncio.run(projection_service.live_projection_rows(model_name="Ridge Regression"))

    assert project_calls == 3


def test_fixture_client_uses_short_warm_cache(monkeypatch):
    calls = 0

    async def fake_get(path):
        nonlocal calls
        calls += 1
        assert path == "fixtures/"
        return [{"id": 1}]

    monkeypatch.setattr(fpl_client, "_get", fake_get)
    fpl_client.clear_fixtures_cache()

    assert asyncio.run(fpl_client.get_fixtures()) == [{"id": 1}]
    assert asyncio.run(fpl_client.get_fixtures()) == [{"id": 1}]
    assert calls == 1
    fpl_client.clear_fixtures_cache()


def test_overview_payload_is_compact_and_reuses_projection_run(monkeypatch):
    projection_calls = 0
    projected = [
        {
            "element_id": player_id,
            "name": f"Player {player_id}",
            "team": f"T{player_id}",
            "position": "MID",
            "price": 6.0,
            "start_likelihood": 0.9,
            "projections": [
                {
                    "gameweek": 1,
                    "projected_points": float(10 - player_id),
                    "blank": False,
                    "double": False,
                    "fixtures": [
                        {
                            "predicted_points": float(11 - player_id),
                            "start_likelihood": 0.9,
                        }
                    ],
                }
            ],
        }
        for player_id in range(1, 6)
    ]
    metadata = {
        "season": "2026-27",
        "bootstrap_hash": "bootstrap-hash",
        "rules_version": "rules-v1",
        "data_cutoff": "2026-08-17T00:00:00Z",
        "model": "Ridge Regression",
        "start_gameweek": 1,
    }
    ranked = pd.DataFrame(
        [
            {
                "element_id": player_id,
                "player_name": f"Player {player_id}",
                "web_name": f"P{player_id}",
                "team_name": f"Team {player_id}",
                "team_code": player_id,
                "position": "Midfielder",
                "price": 6.0,
                "total_points": 0,
                "points_per_game": 0.0,
                "form": 0.0,
                "minutes_security": 0.9,
                "value_score": 1.0,
                "captain_score": float(10 - player_id),
                "transfer_score": float(10 - player_id),
                "selected_by_percent": 5.0,
                "defensive_contribution": 0,
                "defensive_contribution_per_90": 0.0,
                "safety_tier": "Safe",
            }
            for player_id in range(1, 6)
        ]
    )

    async def fake_projection_rows(**kwargs):
        nonlocal projection_calls
        projection_calls += 1
        return projected, {**metadata, "model": kwargs["model_name"]}

    async def fake_ticker(range=5):  # noqa: A002
        return [{"team": "Team 1", "team_short": "T1", "fixtures": []}]

    monkeypatch.setattr(predictions_router, "BEST_MODEL", "Ridge Regression")
    monkeypatch.setattr(predictions_router, "CAPTAINCY_MODEL", "Ridge Regression")
    monkeypatch.setattr(predictions_router, "live_projection_rows", fake_projection_rows)
    monkeypatch.setattr(predictions_router, "ticker", fake_ticker)
    monkeypatch.setattr(
        predictions_router.data_service,
        "players",
        lambda: ranked.copy(),
    )
    monkeypatch.setattr(predictions_router.backtest_router, "accuracy", lambda: [])

    payload = asyncio.run(predictions_router.overview())

    assert projection_calls == 1
    assert payload["player_count"] == 5
    assert len(payload["predictions"]) == 5
    assert len(json.dumps(payload).encode("utf-8")) < 200_000


def test_web_shell_has_no_artificial_route_delay_and_uses_same_origin_proxy():
    shell = (PROJECT_ROOT / "frontend" / "components" / "AppShell.tsx").read_text(
        encoding="utf-8"
    )
    api_client = (PROJECT_ROOT / "frontend" / "lib" / "api.ts").read_text(
        encoding="utf-8"
    )
    next_config = (PROJECT_ROOT / "frontend" / "next.config.ts").read_text(
        encoding="utf-8"
    )

    assert "LogoLoader" not in shell
    assert "5600" not in shell
    assert 'const CLIENT_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? ""' in api_client
    assert 'source: "/api/:path*"' in next_config


def test_draft_workspace_uses_live_rules_and_compact_player_metrics(monkeypatch):
    async def fake_initial_squad(**kwargs):
        return {"squad": [{"element_id": 1}], "horizon": kwargs["horizon"]}

    async def fake_projection_rows(**kwargs):
        return (
            [
                {
                    "element_id": 1,
                    "name": "Draft Player",
                    "web_name": "Draft",
                    "team": "ARS",
                    "team_id": 1,
                    "team_code": 3,
                    "position": "MID",
                    "price": 7.5,
                    "start_likelihood": 0.9,
                    "availability_probability": 1.0,
                    "status": "a",
                    "projections": [
                        {"gameweek": gameweek, "projected_points": float(gameweek)}
                        for gameweek in range(1, 4)
                    ],
                }
            ],
            {
                "season": "2026-27",
                "bootstrap_hash": "bootstrap-hash",
                "fixtures_hash": "fixtures-hash",
                "rules_version": "rules-v1",
                "data_cutoff": "2026-08-17T00:00:00Z",
                "model": kwargs["model_name"],
            },
        )

    async def fake_bootstrap():
        return {
            "game_settings": {
                "ui_currency_multiplier": 10,
                "squad_total_spend": 1000,
                "squad_squadsize": 15,
                "squad_squadplay": 11,
                "squad_team_limit": 3,
            },
            "element_types": [
                {"singular_name_short": "GKP", "squad_select": 2},
                {"singular_name_short": "DEF", "squad_select": 5},
                {"singular_name_short": "MID", "squad_select": 5},
                {"singular_name_short": "FWD", "squad_select": 3},
            ],
        }

    monkeypatch.setattr(predictions_router, "initial_squad", fake_initial_squad)
    monkeypatch.setattr(predictions_router, "live_projection_rows", fake_projection_rows)
    monkeypatch.setattr(predictions_router.fpl_client, "get_bootstrap", fake_bootstrap)

    payload = asyncio.run(predictions_router.draft_workspace(horizon=3, risk_profile="balanced"))

    assert payload["constraints"]["budget"] == 100.0
    assert payload["constraints"]["position_counts"] == {
        "GKP": 2,
        "DEF": 5,
        "MID": 5,
        "FWD": 3,
    }
    assert payload["player_pool"][0]["gw1_points"] == 1.0
    assert payload["player_pool"][0]["horizon_points"] == 6.0
    assert "projections" not in payload["player_pool"][0]
