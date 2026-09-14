import asyncio
import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from api.main import app
from api.readiness import (
    LiveDecisionReadiness,
    require_current_artifacts,
    require_live_artifacts,
)
from api.routers import chips as chips_router
from api.routers import fpl_live
from api.routers import operations as operations_router
from api.routers import planner as planner_router
from api.routers import player_catalog as player_catalog_router
from api.routers import players as players_router
from api.routers import predictions as predictions_router
from api.routers.fixtures import TEAM_SHORT_NAMES, TEAM_STRENGTH, _ticker_from_named_fixtures
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

app.dependency_overrides[require_live_artifacts] = lambda: None
app.dependency_overrides[require_current_artifacts] = lambda: None


async def _get(path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_health_returns_ok():
    response = asyncio.run(_get("/api/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_official_player_catalog_remains_available_without_model_artifacts(monkeypatch):
    async def fake_bootstrap():
        return {
            "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS", "code": 3}],
            "element_types": [{"id": 3, "singular_name_short": "MID"}],
            "elements": [{
                "id": 101,
                "first_name": "Example",
                "second_name": "Player",
                "web_name": "Example",
                "team": 1,
                "element_type": 3,
                "now_cost": 75,
                "total_points": 10,
                "points_per_game": "5.0",
                "form": "6.2",
                "selected_by_percent": "12.4",
                "status": "a",
                "chance_of_playing_next_round": None,
            }],
        }

    monkeypatch.setattr(player_catalog_router.fpl_client, "get_bootstrap", fake_bootstrap)
    response = asyncio.run(_get("/api/player-catalog"))

    assert response.status_code == 200
    assert response.json() == [{
        "element_id": 101,
        "name": "Example Player",
        "web_name": "Example",
        "team": "Arsenal",
        "team_code": 3,
        "position": "MID",
        "price": 7.5,
        "total_points": 10,
        "ppg": 5.0,
        "form": 6.2,
        "start_likelihood": 1.0,
        "value": 0.667,
        "captain_rank_score": 0.0,
        "transfer_rank_score": 0.0,
        "selected_by_percent": 12.4,
        "metrics_available": False,
        "catalog_source": "official_fpl_bootstrap",
    }]


def test_portfolio_status_exposes_active_and_rollback_configs(monkeypatch):
    monkeypatch.delenv("FPL_SHADOW_MODE", raising=False)

    response = asyncio.run(_get("/api/operations/portfolio"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"]["version"] == "r2-consumer-portfolio-v1"
    assert payload["active"]["transfer_model"] == "Ridge Regression"
    assert payload["active"]["chip_model"] == "Gradient Boosting Regressor"
    assert payload["rollback"]["version"] == "m8.6.1-ridge-control-v1"
    assert payload["shadow_mode"] is False
    assert payload["automatic_execution"] is False


def test_deadline_readiness_requires_current_shadow_and_reviewed_news(
    monkeypatch, tmp_path
):
    now = datetime.now(UTC)
    bootstrap_path = tmp_path / "bootstrap.json"
    bootstrap_path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "id": 1,
                        "deadline_time": (now + timedelta(days=10)).isoformat(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    p11_path = tmp_path / "p11.json"
    p11_path.write_text(
        json.dumps(
            {
                "bootstrap_hash": "current",
                "gate": {
                    "status": "monitoring",
                    "data_ready": True,
                    "lock_ready": False,
                    "final_news_reviewed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    p12_path = tmp_path / "p12.json"
    p12_path.write_text(
        json.dumps(
            {
                "bootstrap_hash": "current",
                "model_version": "p12-set-piece-transition-v1",
                "source_url": "https://example.com/official-set-pieces",
                "category_coverage": {"penalties": 20},
                "primary_penalty_takers": [{"player_id": 1}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        operations_router,
        "load_current_artifact_manifest",
        lambda: {
            "season": "2026-27",
            "data_cutoff": now.isoformat(),
            "bootstrap_hash": "current",
        },
    )
    monkeypatch.setattr(operations_router, "BOOTSTRAP_PATH", bootstrap_path)
    monkeypatch.setattr(operations_router, "P11_OUTPUT", p11_path)
    monkeypatch.setattr(operations_router, "P12_OUTPUT", p12_path)
    monkeypatch.setattr(
        operations_router,
        "latest_shadow_snapshot",
        lambda: {
            "captured_at": now.isoformat(),
            "decision_hash": "old-decision",
            "expected_gw1_points": 60.0,
            "bootstrap_hash": "old",
        },
    )

    payload = operations_router.gw1_deadline_readiness()
    checklist = {row["key"]: row["passed"] for row in payload["checklist"]}

    assert payload["p11"]["data_ready"]
    assert not payload["latest_shadow"]["current"]
    assert checklist["robustness_current"]
    assert checklist["set_piece_roles_current"]
    assert payload["p12"]["primary_penalty_takers"] == 1
    assert not checklist["shadow_captured"]
    assert not checklist["final_team_news"]


@pytest.mark.requires_local_artifacts
def test_players_returns_plain_english_fields():
    response = asyncio.run(_get("/api/players"))

    assert response.status_code == 200
    players = response.json()
    assert isinstance(players, list)
    assert len(players) > 0
    assert "name" in players[0]
    assert "element_id" in players[0]
    assert "player_name" not in players[0]


@pytest.mark.requires_local_artifacts
def test_captains_returns_ten_players():
    response = asyncio.run(_get("/api/players/captains"))

    assert response.status_code == 200
    assert len(response.json()) == 10


@pytest.mark.requires_local_artifacts
def test_transfers_includes_rotation_risk_boolean():
    response = asyncio.run(_get("/api/players/transfers"))

    assert response.status_code == 200
    transfers = response.json()
    assert len(transfers) > 0
    assert isinstance(transfers[0]["rotation_risk"], bool)
    assert "defensive_contribution_per_90" in transfers[0]
    assert "safety_tier" in transfers[0]


def test_player_comparison_returns_selected_players_and_fixture_average(monkeypatch):
    ranked_players = pd.DataFrame(
        [
            {
                "element_id": 1,
                "player_name": "Example Forward",
                "web_name": "Example",
                "team_name": "Arsenal",
                "position": "Forward",
                "team_code": 3,
                "price": 8.0,
                "total_points": 100,
                "points_per_game": 5.2,
                "form": 6.0,
                "minutes_security": 0.9,
                "value_score": 10.0,
                "captain_score": 6.4,
                "transfer_score": 0.7,
                "selected_by_percent": 12.0,
                "defensive_contribution": 4,
                "defensive_contribution_per_90": 1.4,
            },
            {
                "element_id": 2,
                "player_name": "Example Midfielder",
                "web_name": "Example Mid",
                "team_name": "Chelsea",
                "position": "Midfielder",
                "team_code": 8,
                "price": 7.0,
                "total_points": 90,
                "points_per_game": 4.8,
                "form": 5.0,
                "minutes_security": 0.8,
                "value_score": 9.0,
                "captain_score": 5.8,
                "transfer_score": 0.6,
                "selected_by_percent": 9.0,
                "defensive_contribution": 7,
                "defensive_contribution_per_90": 2.1,
            },
        ]
    )

    async def fake_bootstrap():
        return {"events": [{"id": 1, "is_current": True, "finished": False}]}

    async def fake_fixture_source_state():
        return {
            "source": "FPL Fantasy API",
            "season": "2025-26",
            "difficulty_source": "Official FPL FDR",
            "freshness": "live",
        }

    async def fake_ticker(range: int = 8):  # noqa: A002
        return [
            {
                "team": "Arsenal",
                "team_short": "ARS",
                "fixtures": [
                    {"gw": 1, "opponent": "CHE", "home": True, "difficulty": 2},
                    {"gw": 2, "opponent": "LIV", "home": False, "difficulty": 4},
                    {"gw": 3, "opponent": "EVE", "home": True, "difficulty": 3},
                ],
            },
            {
                "team": "Chelsea",
                "team_short": "CHE",
                "fixtures": [
                    {"gw": 1, "opponent": "FUL", "home": False, "difficulty": 4},
                    {"gw": 2, "opponent": "BHA", "home": True, "difficulty": 3},
                ],
            },
        ]

    async def fake_live_projection_rows(**kwargs):
        return (
            [
                {
                    "element_id": 1,
                    "projections": [
                        {
                            "gameweek": 1,
                            "projected_points": 5.7,
                            "fixtures": [{"predicted_points": 6.4}],
                        }
                    ],
                },
                {
                    "element_id": 2,
                    "projections": [
                        {
                            "gameweek": 1,
                            "projected_points": 5.1,
                            "fixtures": [{"predicted_points": 5.8}],
                        }
                    ],
                },
            ],
            {"start_gameweek": 1},
        )

    monkeypatch.setattr(players_router, "_load_players", lambda: (ranked_players.copy(), []))
    monkeypatch.setattr(players_router.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(players_router, "fixture_source_state", fake_fixture_source_state)
    monkeypatch.setattr(players_router, "ticker", fake_ticker)
    monkeypatch.setattr(
        players_router,
        "live_projection_rows",
        fake_live_projection_rows,
    )

    response = asyncio.run(_get("/api/players/compare?ids=1,2"))

    assert response.status_code == 200
    payload = response.json()
    assert [player["element_id"] for player in payload["players"]] == [1, 2]
    assert payload["players"][0]["captain_rank_score"] == 6.4
    assert payload["players"][0]["raw_xp"] == 6.4
    assert payload["players"][0]["expected_points"] == 5.7
    assert payload["players"][0]["defensive_contribution_per_90"] == 1.4
    assert payload["players"][0]["average_fixture_difficulty"] == 3.0
    assert payload["players"][1]["average_fixture_difficulty"] == 3.5
    assert payload["players"][0]["live_metrics_available"] is True


def test_player_comparison_nulls_live_metrics_during_season_transition(monkeypatch):
    ranked_players = pd.DataFrame(
        [
            {
                "element_id": 1,
                "player_name": "Example Forward",
                "web_name": "Example",
                "team_name": "Arsenal",
                "position": "Forward",
                "team_code": 3,
                "price": 8.0,
                "points_per_game": 5.2,
                "form": 6.0,
                "minutes_security": 0.9,
                "value_score": 10.0,
                "captain_score": 6.4,
                "transfer_score": 0.7,
                "selected_by_percent": 12.0,
                "defensive_contribution_per_90": 1.4,
            },
            {
                "element_id": 2,
                "player_name": "Example Midfielder",
                "web_name": "Example Mid",
                "team_name": "Chelsea",
                "position": "Midfielder",
                "team_code": 8,
                "price": 7.0,
                "points_per_game": 4.8,
                "form": 5.0,
                "minutes_security": 0.8,
                "value_score": 9.0,
                "captain_score": 5.8,
                "transfer_score": 0.6,
                "selected_by_percent": 9.0,
                "defensive_contribution_per_90": 2.1,
            },
        ]
    )

    async def fake_bootstrap():
        return {"events": [{"id": 38, "finished": True}]}

    async def fake_fixture_source_state():
        return {
            "source": "Official PL fixture release",
            "season": "2026-27",
            "difficulty_source": "App-estimated difficulty",
            "freshness": "static official release",
            "next_kickoff": "2026-08-21T19:00:00Z",
        }

    async def fake_ticker(range: int = 8):  # noqa: A002
        return []

    monkeypatch.setattr(players_router, "_load_players", lambda: (ranked_players.copy(), []))
    monkeypatch.setattr(players_router.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(players_router, "fixture_source_state", fake_fixture_source_state)
    monkeypatch.setattr(players_router, "ticker", fake_ticker)

    response = asyncio.run(_get("/api/players/compare?ids=1,2"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["season_state"] == "season_ended_preseason"
    assert payload["fixture_season"] == "2026-27"
    for player in payload["players"]:
        assert player["points_per_game"] is not None
        assert player["form"] is None
        assert player["captain_rank_score"] is None
        assert player["transfer_rank_score"] is None
        assert player["raw_xp"] is None
        assert player["expected_points"] is None
        assert player["minutes_security"] is None
        assert player["live_metrics_available"] is False
        assert "season starts" in player["live_metrics_unavailable_reason"]


def test_players_form_falls_back_to_recent_history_when_snapshot_is_zero(monkeypatch):
    ranked_players = pd.DataFrame(
        [
            {
                "element_id": 1,
                "player_name": "Example Forward",
                "web_name": "Example",
                "team_name": "Arsenal",
                "team_code": 3,
                "position": "Forward",
                "price": 7.5,
                "total_points": 100,
                "points_per_game": 4.0,
                "form": 0.0,
                "minutes": 1000,
                "selected_by_percent": 10.0,
                "value_score": 13.3,
                "minutes_security": 0.8,
                "ownership_risk": 0.9,
                "captain_score": 0.5,
                "transfer_score": 0.4,
            }
        ]
    )
    history = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "player_name": "Example Forward",
                "player_id": 1,
                "gameweek": 35,
                "total_points": 4,
            },
            {
                "season": "2025-26",
                "player_name": "Example Forward",
                "player_id": 1,
                "gameweek": 36,
                "total_points": 8,
            },
            {
                "season": "2025-26",
                "player_name": "Example Forward",
                "player_id": 1,
                "gameweek": 37,
                "total_points": 6,
            },
            {
                "season": "2025-26",
                "player_name": "Example Forward",
                "player_id": 1,
                "gameweek": 38,
                "total_points": 10,
            },
        ]
    )

    monkeypatch.setattr(players_router.data_service, "players", lambda: ranked_players.copy())
    monkeypatch.setattr(players_router.data_service, "serving_player_gw", lambda: history.copy())

    response = asyncio.run(_get("/api/players?sort_by=form&limit=1"))

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["form"] == 8.0


def test_form_fallback_diverges_from_season_ppg_in_both_directions(monkeypatch):
    ranked_players = pd.DataFrame(
        [
            {
                "element_id": 1,
                "player_name": "Out Of Form",
                "web_name": "Out",
                "team_name": "Arsenal",
                "team_code": 3,
                "position": "Forward",
                "price": 8.0,
                "total_points": 120,
                "points_per_game": 8.0,
                "form": 0.0,
                "minutes": 1200,
                "selected_by_percent": 10.0,
                "value_score": 15.0,
                "minutes_security": 0.9,
                "ownership_risk": 0.9,
                "captain_score": 0.8,
                "transfer_score": 0.5,
            },
            {
                "element_id": 2,
                "player_name": "In Form",
                "web_name": "In",
                "team_name": "Chelsea",
                "team_code": 8,
                "position": "Midfielder",
                "price": 6.0,
                "total_points": 45,
                "points_per_game": 3.0,
                "form": 0.0,
                "minutes": 900,
                "selected_by_percent": 10.0,
                "value_score": 7.5,
                "minutes_security": 0.9,
                "ownership_risk": 0.9,
                "captain_score": 0.5,
                "transfer_score": 0.6,
            },
        ]
    )
    history = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "player_id": 1,
                "player_name": "Out Of Form",
                "gameweek": 36,
                "total_points": 2,
            },
            {
                "season": "2025-26",
                "player_id": 1,
                "player_name": "Out Of Form",
                "gameweek": 37,
                "total_points": 3,
            },
            {
                "season": "2025-26",
                "player_id": 1,
                "player_name": "Out Of Form",
                "gameweek": 38,
                "total_points": 1,
            },
            {
                "season": "2025-26",
                "player_id": 2,
                "player_name": "In Form",
                "gameweek": 36,
                "total_points": 7,
            },
            {
                "season": "2025-26",
                "player_id": 2,
                "player_name": "In Form",
                "gameweek": 37,
                "total_points": 8,
            },
            {
                "season": "2025-26",
                "player_id": 2,
                "player_name": "In Form",
                "gameweek": 38,
                "total_points": 6,
            },
        ]
    )

    monkeypatch.setattr(players_router.data_service, "players", lambda: ranked_players.copy())
    monkeypatch.setattr(players_router.data_service, "serving_player_gw", lambda: history.copy())

    response = asyncio.run(_get("/api/players?sort_by=name&limit=2"))

    assert response.status_code == 200
    by_name = {row["name"]: row for row in response.json()}
    assert by_name["Out Of Form"]["form"] == 2.0
    assert by_name["Out Of Form"]["form"] < by_name["Out Of Form"]["ppg"]
    assert by_name["In Form"]["form"] == 7.0
    assert by_name["In Form"]["form"] > by_name["In Form"]["ppg"]


def test_captaincy_predictions_use_current_season_projection(monkeypatch):
    async def fake_live_projection_rows(**kwargs):
        return (
            [
                {
                    "element_id": 101,
                    "name": "Current Captain",
                    "team": "MCI",
                    "position": "FWD",
                    "price": 15.5,
                    "start_likelihood": 0.9,
                    "projections": [
                        {
                            "gameweek": 1,
                            "projected_points": 8.4,
                            "blank": False,
                            "double": False,
                            "fixtures": [
                                {
                                    "predicted_points": 9.0,
                                    "start_likelihood": 0.93,
                                }
                            ],
                        }
                    ],
                }
            ],
            {
                "season": "2026-27",
                "bootstrap_hash": "bootstrap-hash",
                "rules_version": "rules-v1",
                "data_cutoff": "2026-07-26T00:00:00Z",
                "model": kwargs["model_name"],
                "start_gameweek": 1,
            },
        )

    monkeypatch.setattr(
        predictions_router,
        "live_projection_rows",
        fake_live_projection_rows,
    )

    response = asyncio.run(_get("/api/predictions/captaincy?gw=1&limit=1"))

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["name"] == "Current Captain"
    assert payload[0]["season"] == "2026-27"
    assert payload[0]["element_id"] == 101
    assert payload[0]["model"] == "Ridge Regression"
    assert payload[0]["raw_xp"] == 9.0
    assert payload[0]["expected_points"] == 8.4
    assert payload[0]["start_adjusted_xp"] == 8.4
    assert payload[0]["captain_expected_points"] == 16.8
    assert payload[0]["captaincy_score"] == 8.4
    assert payload[0]["projection_contract_version"] == "w2-v1"
    assert "predicted_pts" not in payload[0]
    assert "adjusted_pts" not in payload[0]


def test_initial_squad_uses_current_projections_and_is_fpl_legal(
    monkeypatch, tmp_path
):
    positions = ["GKP"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    projected = []
    for index, position in enumerate(positions, start=1):
        projected.append(
            {
                "element_id": index,
                "name": f"Player {index}",
                "web_name": f"P{index}",
                "team": f"T{(index - 1) // 3 + 1}",
                "position": position,
                "price": 6.6,
                "status": "a",
                "availability_probability": 1.0,
                "start_likelihood": 0.8,
                "prior_source": "official_2025-26_stats",
                "projections": [
                    {
                        "gameweek": gameweek,
                        "projected_points": round(2.0 + index / 10, 2),
                        "blank": False,
                        "double": False,
                        "fixtures": [],
                    }
                    for gameweek in range(1, 9)
                ],
            }
        )
    projected[0]["projections"][0]["fixtures"] = [
        {
            "set_piece_adjustment": {
                "model_version": "p12-set-piece-transition-v1",
                "source_url": "https://example.com/official-set-pieces",
                "available": True,
                "reason": "official_current_role_minus_official_2025_26_role",
                "total_adjustment": 0.2,
                "roles": {
                    "penalties": {"current_rank": 1},
                    "direct_free_kicks": {"current_rank": None},
                    "corners_indirect_free_kicks": {"current_rank": 2},
                },
            }
        }
    ]

    async def fake_live_projection_rows(**kwargs):
        assert kwargs["start_gameweek"] == 1
        assert kwargs["horizon"] == 8
        return projected, {
            "season": "2026-27",
            "bootstrap_hash": "bootstrap-hash",
            "rules_version": "rules-v1",
            "data_cutoff": "2026-07-26T00:00:00Z",
            "model": kwargs["model_name"],
            "start_gameweek": 1,
        }

    monkeypatch.setattr(
        predictions_router,
        "live_projection_rows",
        fake_live_projection_rows,
    )
    report_path = tmp_path / "p10-report.json"
    report_path.write_text(
        json.dumps(
            {
                "metadata": {"bootstrap_hash": "bootstrap-hash"},
                "robustness": {
                    "scenario_count": 27,
                    "distinct_squads": 7,
                    "robust_squad_rate": 0.2963,
                    "player_stability": [
                        {
                            "player_id": 1,
                            "classification": "locked",
                            "selection_rate": 1.0,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(predictions_router, "P10_OUTPUT", report_path)
    p11_path = tmp_path / "p11-report.json"
    p11_path.write_text(
        json.dumps(
            {
                "bootstrap_hash": "bootstrap-hash",
                "gate": {
                    "status": "monitoring",
                    "data_ready": True,
                    "lock_ready": False,
                    "hours_to_deadline": 100.0,
                    "final_news_reviewed": False,
                    "timing_blockers": ["outside_final_24h_window"],
                },
                "recommendation": {
                    "verdict": "retain_central_squad_pending_final_news"
                },
                "squad_variants": [
                    {"is_central": True, "scenario_rate": 0.6},
                    {
                        "is_central": False,
                        "scenario_rate": 0.4,
                        "players_out": [{"player_name": "Player 1"}],
                        "players_in": [{"player_name": "Challenger"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(predictions_router, "P11_OUTPUT", p11_path)

    response = asyncio.run(_get("/api/predictions/initial-squad?horizon=8"))

    assert response.status_code == 200
    payload = response.json()
    squad = payload["squad"]
    starters = [player for player in squad if player["is_starter"]]
    position_counts = pd.Series([player["position"] for player in squad]).value_counts()
    team_counts = pd.Series([player["team"] for player in squad]).value_counts()
    assert payload["season"] == "2026-27"
    assert len(squad) == 15
    assert len(starters) == 11
    assert payload["cost"] == 99.0
    assert payload["bank"] == 1.0
    assert payload["initial_squad_policy"] == "horizon_8_flexible_cold_start_safe"
    assert payload["initial_squad_policy_version"] == (
        "p3-opening-milp-v2-cold-start-safe"
    )
    assert payload["policy_status"] == "production_default"
    assert payload["decision_engine_version"] == (
        "p10-gw1-calibrated-robustness-v1"
    )
    assert payload["robustness"]["scenario_count"] == 27
    assert payload["robustness"]["autosub_activation_probability"] == 0.17
    assert payload["deadline_finalization"]["status"] == "monitoring"
    assert payload["deadline_finalization"]["primary_challenger"] == {
        "scenario_rate": 0.4,
        "players_out": ["Player 1"],
        "players_in": ["Challenger"],
    }
    assert next(player for player in squad if player["element_id"] == 1)[
        "robustness_class"
    ] == "locked"
    assert position_counts.to_dict() == {"DEF": 5, "MID": 5, "FWD": 3, "GKP": 2}
    assert int(team_counts.max()) == 3
    assert payload["captain_id"] in {player["element_id"] for player in starters}
    assert payload["vice_captain_id"] in {player["element_id"] for player in starters}
    assert all(player["status"] == "a" for player in squad)
    assert all(player["availability_probability"] == 1.0 for player in squad)
    assert payload["risk_profile"] == "balanced"
    assert {row["profile"] for row in payload["decision_alternatives"]} == {
        "maximum_points",
        "balanced",
        "safe",
    }
    assert sum(row["selected"] for row in payload["decision_alternatives"]) == 1
    assert payload["decision_audit"]["availability_clear"]
    assert payload["decision_audit"]["low_reliability_starters"] == []
    assert payload["decision_audit"]["low_reliability_bench"] == []
    assert payload["decision_audit"]["captain_start_probability"] == 0.8
    assert payload["decision_audit"]["requires_deadline_refresh"]
    assert next(player for player in squad if player["element_id"] == 1)[
        "set_piece"
    ]["penalties_rank"] == 1
    assert payload["set_piece_summary"]["model_version"] == (
        "p12-set-piece-transition-v1"
    )


def test_fixture_ticker_rows_include_source_metadata():
    rows = _ticker_from_named_fixtures(
        [
            {
                "event": 1,
                "team_h_short": "ARS",
                "team_a_short": "CHE",
                "team_h_difficulty": 4,
                "team_a_difficulty": 5,
            }
        ],
        requested_range=3,
    )

    arsenal = next(row for row in rows if row["team_short"] == "ARS")
    assert arsenal["range"] == 3
    assert arsenal["source"] == "Official PL fixture release"
    assert arsenal["season"] == "2026-27"
    assert arsenal["difficulty_source"] == "App-estimated difficulty"
    assert arsenal["fixtures"][0]["opponent"] == "CHE"


def test_2026_27_team_maps_cover_current_membership():
    expected_shorts = {
        "ARS", "AVL", "BOU", "BRE", "BHA", "CHE", "COV", "CRY", "EVE", "FUL",
        "HUL", "IPS", "LEE", "LIV", "MCI", "MUN", "NEW", "NFO", "SUN", "TOT",
    }

    assert set(TEAM_SHORT_NAMES.values()) == expected_shorts
    assert set(TEAM_STRENGTH) == expected_shorts


def test_season_state_returns_central_source_metadata(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [
                {"id": 1, "deadline_time": "2025-08-15T17:30:00Z", "is_current": True},
                {"id": 2, "deadline_time": "2025-08-22T17:30:00Z", "is_next": True},
            ]
        }

    async def fake_fixture_source_state(_fixture_rows):
        return {
            "source": "Official PL fixture release",
            "season": "2026-27",
            "difficulty_source": "App-estimated difficulty",
            "freshness": "static official release",
            "next_kickoff": None,
        }

    async def fake_live_decision_context(*, check_models):
        bootstrap = await fake_bootstrap()
        return (
            LiveDecisionReadiness(
                status="ready",
                season="2025-26",
                blockers=[],
                warnings=[],
                manifest={"season": "2025-26"},
                live_data={
                    "checked_at": "2025-08-01T00:00:00Z",
                    "bootstrap_hash": "live",
                    "fixtures_hash": "fixtures",
                    "player_count": 0,
                    "team_count": 0,
                },
                artifact_data={
                    "data_cutoff": "2025-08-01T00:00:00Z",
                    "age_hours": 1,
                    "bootstrap_hash": "live",
                    "fixtures_hash": "fixtures",
                    "player_count": 0,
                    "team_count": 0,
                    "rules_version": "test",
                },
                models_checked=check_models,
            ),
            bootstrap,
            [],
        )

    monkeypatch.setattr(fpl_live, "live_decision_context", fake_live_decision_context)
    monkeypatch.setattr(fpl_live, "fixture_source_state", fake_fixture_source_state)

    response = asyncio.run(_get("/api/fpl/season-state"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["fpl_api_season"] == "2025-26"
    assert payload["fixture_source"] == "Official PL fixture release"
    assert payload["fixture_season"] == "2026-27"
    assert payload["difficulty_source"] == "App-estimated difficulty"
    assert payload["current_gw"] == 1
    assert payload["next_gw"] == 2
    assert payload["season_state"] == "in_season"


def test_season_state_detection_covers_transition_cases():
    mid_season = {
        "events": [
            {"id": 1, "finished": True},
            {"id": 2, "is_current": True, "finished": False},
            {"id": 3, "is_next": True, "finished": False},
        ]
    }
    ended_with_fixtures = {
        "events": [{"id": 38, "finished": True, "is_current": True}],
    }
    ended_without_fixtures = {
        "events": [{"id": 38, "finished": True}],
    }

    assert fpl_live._detect_season_state(mid_season, {"season": "2025-26"}) == "in_season"
    assert (
        fpl_live._detect_season_state(
            ended_with_fixtures,
            {"season": "2026-27", "next_kickoff": "2026-08-21T19:00:00Z"},
        )
        == "season_ended_preseason"
    )
    assert (
        fpl_live._detect_season_state(
            ended_without_fixtures,
            {"season": "unknown", "next_kickoff": None},
        )
        == "season_ended_no_next_data"
    )


def test_finished_season_has_no_next_gameweek():
    bootstrap = {"events": [{"id": 38, "finished": True}]}

    assert fpl_live._current_gameweek_from_bootstrap(bootstrap) == 38
    assert fpl_live._next_gameweek_from_bootstrap(bootstrap) is None


def test_squad_endpoint_distinguishes_unavailable_public_picks(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [{"id": 1}],
            "elements": [],
            "teams": [],
            "element_types": [],
        }

    async def missing_picks(_team_id, _gw):
        raise HTTPException(
            status_code=404,
            detail={"code": "fpl_resource_not_found", "message": "not found"},
        )

    monkeypatch.setattr(fpl_live.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(fpl_live.fpl_client, "get_team_picks", missing_picks)

    response = asyncio.run(_get("/api/fpl/team/123/squad?gw=1"))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "squad_unavailable"


def test_planner_requires_connected_team():
    response = asyncio.run(_get("/api/predictions/planner?horizon=3"))

    assert response.status_code == 400
    assert "team ID" in response.json()["detail"]


def test_planner_rejects_unsupported_horizon_before_fetching_data():
    response = asyncio.run(_get("/api/predictions/planner?team_id=5605168&horizon=4"))

    assert response.status_code == 400
    assert response.json()["detail"] == "horizon must be one of 3, 5, or 8"


def test_planner_returns_squad_and_baseline(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [
                {"id": 1, "is_current": True},
                {"id": 2, "is_next": True},
            ],
            "teams": [{"id": 1, "name": "Example FC", "short_name": "EXM", "code": 1}],
            "element_types": [{"id": 3, "singular_name_short": "MID"}],
            "elements": [
                {
                    "id": 10,
                    "first_name": "Example",
                    "second_name": "Midfielder",
                    "web_name": "Example",
                    "team": 1,
                    "element_type": 3,
                    "now_cost": 60,
                    "selected_by_percent": "10.0",
                }
            ],
            "game_settings": {"max_extra_free_transfers": 4},
        }

    async def fake_team(team_id):
        return {"last_deadline_bank": 15, "free_transfers": 1}

    async def fake_picks(team_id, gw):
        return {"picks": [{"element": 10, "position": 1, "is_captain": True}]}

    async def fake_history(team_id):
        return {"chips": []}

    async def fake_transfers(team_id):
        return []

    async def fake_fixtures():
        return []

    async def fake_fixture_source_state(fixture_rows=None):
        return {
            "source": "FPL Fantasy API",
            "season": "2025-26",
            "difficulty_source": "Official FPL FDR",
            "freshness": "live",
            "next_kickoff": None,
        }

    projected = [
        {
            "element_id": 10,
            "name": "Example Midfielder",
            "web_name": "Example",
            "team": "EXM",
            "team_code": 1,
            "position": "MID",
            "price": 6.0,
            "start_likelihood": 0.8,
            "projections": [
                {
                    "gameweek": 2,
                    "projected_points": 4.2,
                    "blank": False,
                    "double": False,
                    "fixtures": [],
                }
            ],
        }
    ]

    async def fake_live_projection_rows(**kwargs):
        return projected, {"model": kwargs["model_name"]}

    monkeypatch.setattr(planner_router.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(planner_router.fpl_client, "get_team", fake_team)
    monkeypatch.setattr(planner_router.fpl_client, "get_team_picks", fake_picks)
    monkeypatch.setattr(planner_router.fpl_client, "get_team_history", fake_history)
    monkeypatch.setattr(planner_router.fpl_client, "get_team_transfers", fake_transfers)
    monkeypatch.setattr(planner_router.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(planner_router, "fixture_source_state", fake_fixture_source_state)
    monkeypatch.setattr(
        planner_router.data_service,
        "players",
        lambda: pd.DataFrame([{"player_name": "Example Midfielder"}]),
    )
    monkeypatch.setattr(
        planner_router.data_service,
        "serving_player_gw",
        lambda: pd.DataFrame(
            [
                {
                    "season": "2026-27",
                    "gameweek": 1,
                    "player_id": 10,
                    "price_before_deadline": 6.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        planner_router,
        "load_planner_models",
        lambda *args, **kwargs: (object(), object()),
    )
    monkeypatch.setattr(planner_router, "project_players", lambda *args, **kwargs: projected)
    monkeypatch.setattr(
        planner_router,
        "live_projection_rows",
        fake_live_projection_rows,
    )

    response = asyncio.run(_get("/api/predictions/planner?team_id=10&horizon=3"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["start_gameweek"] == 2
    assert payload["bank_value"] == 1.5
    assert payload["free_transfers_available"] == 1
    assert payload["max_extra_free_transfers"] == 4
    assert payload["transfer_model"] == "Ridge Regression"
    assert payload["chip_model"] == "Gradient Boosting Regressor"
    assert payload["portfolio_version"] == "r2-consumer-portfolio-v1"
    assert payload["squad"][0]["is_starter"] is True
    assert payload["baseline"][0]["projected_points"] == 4.2


def test_planner_returns_transition_state_without_projecting(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [{"id": 38, "finished": True, "deadline_time": "2025-08-15T17:30:00Z"}],
        }

    async def fake_fixtures():
        return []

    async def fake_fixture_source_state(fixture_rows=None):
        return {
            "source": "Official PL fixture release",
            "season": "2026-27",
            "difficulty_source": "App-estimated difficulty",
            "freshness": "static official release",
            "next_kickoff": "2026-08-21T19:00:00Z",
        }

    monkeypatch.setattr(planner_router.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(planner_router.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(planner_router, "fixture_source_state", fake_fixture_source_state)

    response = asyncio.run(_get("/api/predictions/planner?team_id=10&horizon=3"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["season_state"] == "season_ended_preseason"
    assert payload["fixture_season"] == "2026-27"
    assert payload["next_season_start"] == "2026-08-21T19:00:00Z"
    assert payload["baseline"] == []
    assert payload["squad"] == []
    assert payload["decision"] is None


def test_team_summary_reconstructs_free_transfers_from_public_history(monkeypatch):
    async def fake_team(team_id):
        return {
            "name": "Test XI",
            "summary_overall_rank": 100,
            "summary_overall_points": 180,
            "last_deadline_bank": 5,
            "summary_event_points": 60,
            "last_deadline_value": 1005,
        }

    async def fake_bootstrap():
        return {
            "events": [
                {"id": 1, "finished": True, "data_checked": True},
                {"id": 2, "finished": True, "data_checked": True},
                {"id": 3, "is_current": True},
                {"id": 4, "is_next": True},
            ],
            "game_settings": {"max_extra_free_transfers": 4},
        }

    async def fake_history(team_id):
        return {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 12},
            ],
            "chips": [{"name": "wildcard", "event": 3}],
        }

    async def fake_transfers(team_id):
        return []

    monkeypatch.setattr(fpl_live.fpl_client, "get_team", fake_team)
    monkeypatch.setattr(fpl_live.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(fpl_live.fpl_client, "get_team_history", fake_history)
    monkeypatch.setattr(fpl_live.fpl_client, "get_team_transfers", fake_transfers)

    payload = asyncio.run(fpl_live.team(10))

    assert payload["free_transfers_available"] == 2
    assert payload["manager_state_provenance"] == "public-transfer-history-v1"


def test_chip_tips_returns_clear_no_team_state():
    response = asyncio.run(_get("/api/chip-tips"))

    assert response.status_code == 200
    assert response.json()["status"] == "no_team"
    assert response.json()["alerts"] == []


@pytest.mark.requires_local_artifacts
def test_chip_status_without_team_returns_official_inventory(monkeypatch):
    async def fake_bootstrap():
        return players_router.data_service.bootstrap_static()

    async def fake_fixtures():
        return []

    async def fake_fixture_source_state(fixture_rows=None):
        return {
            "source": "Official PL fixture release",
            "season": "2026-27",
            "difficulty_source": "App-estimated difficulty",
            "freshness": "static official release",
            "next_kickoff": "2026-08-22T00:00:00Z",
        }

    monkeypatch.setattr(fpl_live.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(fpl_live.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(fpl_live, "fixture_source_state", fake_fixture_source_state)

    response = asyncio.run(_get("/api/fpl/chips"))

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert len(response.json()["chips"]) == 8
    assert response.json()["fpl_api_season"] == "2026-27"


def test_chip_status_reads_live_history_and_bootstrap_windows(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [{"id": 5, "is_current": True, "finished": False}],
            "chips": [
                {"id": 1, "name": "wildcard", "start_event": 2, "stop_event": 19},
                {"id": 2, "name": "wildcard", "start_event": 20, "stop_event": 38},
                {"id": 3, "name": "freehit", "start_event": 2, "stop_event": 19},
            ],
        }

    async def fake_fixtures():
        return []

    async def fake_history(team_id):
        return {"chips": [{"name": "freehit", "event": 3}]}

    async def fake_fixture_source_state(fixture_rows=None):
        return {
            "source": "FPL Fantasy API",
            "season": "2025-26",
            "difficulty_source": "Official FPL FDR",
            "freshness": "live",
            "next_kickoff": None,
        }

    monkeypatch.setattr(fpl_live.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(fpl_live.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(fpl_live.fpl_client, "get_team_history", fake_history)
    monkeypatch.setattr(fpl_live, "fixture_source_state", fake_fixture_source_state)

    response = asyncio.run(_get("/api/fpl/team/10/chips"))

    assert response.status_code == 200
    payload = response.json()
    by_key = {row["key"]: row for row in payload["chips"]}
    assert payload["status"] == "ready"
    assert by_key["freehit-1"]["status"] == "used"
    assert by_key["wildcard-2"]["status"] == "not_yet_available"


def test_chip_status_resets_previous_usage_in_preseason(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [{"id": 38, "finished": True}],
            "chips": [
                {"id": 1, "name": "wildcard", "start_event": 2, "stop_event": 19},
                {"id": 2, "name": "wildcard", "start_event": 20, "stop_event": 38},
            ],
        }

    async def fake_fixtures():
        return []

    async def fake_fixture_source_state(fixture_rows=None):
        return {
            "source": "Official PL fixture release",
            "season": "2026-27",
            "difficulty_source": "App-estimated difficulty",
            "freshness": "static official release",
            "next_kickoff": "2026-08-21T19:00:00Z",
        }

    async def fail_if_history_called(team_id):
        raise AssertionError("previous-season chip history must not be read in preseason")

    monkeypatch.setattr(fpl_live.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(fpl_live.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(fpl_live.fpl_client, "get_team_history", fail_if_history_called)
    monkeypatch.setattr(fpl_live, "fixture_source_state", fake_fixture_source_state)

    response = asyncio.run(_get("/api/fpl/team/10/chips"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["season_state"] == "season_ended_preseason"
    assert payload["season_reset"] is True
    assert all(row["status"] != "used" for row in payload["chips"])


def test_chip_tips_returns_transition_state_without_projection(monkeypatch):
    async def fake_bootstrap():
        return {
            "events": [{"id": 38, "finished": True, "deadline_time": "2025-08-15T17:30:00Z"}],
        }

    async def fake_fixtures():
        return []

    async def fake_fixture_source_state(fixture_rows=None):
        return {
            "source": "Official PL fixture release",
            "season": "2026-27",
            "difficulty_source": "App-estimated difficulty",
            "freshness": "static official release",
            "next_kickoff": "2026-08-21T19:00:00Z",
        }

    monkeypatch.setattr(chips_router.fpl_client, "get_bootstrap", fake_bootstrap)
    monkeypatch.setattr(chips_router.fpl_client, "get_fixtures", fake_fixtures)
    monkeypatch.setattr(chips_router, "fixture_source_state", fake_fixture_source_state)

    response = asyncio.run(_get("/api/chip-tips?team_id=10"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["season_state"] == "season_ended_preseason"
    assert payload["alerts"] == []
    assert "season" in payload["message"].lower()


@pytest.mark.requires_local_artifacts
def test_backtest_accuracy_uses_plain_english_model_names():
    response = asyncio.run(_get("/api/backtest/accuracy"))

    assert response.status_code == 200
    payload = response.json()
    models = {row["model"] for row in payload}
    assert "FPL Intelligence (best)" in models
    assert "Gradient Boosting Regressor" not in models
    assert "Random Forest Regressor" not in models
    assert "Ridge Regression" not in models
    assert "Naive baseline" not in models
