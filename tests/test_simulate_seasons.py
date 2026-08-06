from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fpl_intelligence.chip_simulation import CHIP_MODE_BEAM
from fpl_intelligence.season_benchmark import SeasonBenchmarkResult
from fpl_intelligence.simulate_seasons import (
    DEFAULT_SEASONS,
    PRODUCTION_INITIAL_SQUAD_POLICY,
    _initial_squad_for_preset,
    _parse_args,
    _validate_seasons,
    run_historical_simulation,
)


def _historical_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"season": season, "gameweek": gameweek, "player_id": player_id}
            for season in DEFAULT_SEASONS
            for gameweek in (1, 2)
            for player_id in (1, 2)
        ]
    )


def _result(season: str) -> SeasonBenchmarkResult:
    rows = pd.DataFrame(
        [
            {
                "season": season,
                "gameweek": 1,
                "realistic_net_points": 55.0,
                "net_points": 60.0,
                "realistic_chip_realized_gain": 8.0,
                "chip_selected": True,
                "chip_used": "3xc",
            },
            {
                "season": season,
                "gameweek": 2,
                "realistic_net_points": 45.0,
                "net_points": 50.0,
                "realistic_chip_realized_gain": 0.0,
                "chip_selected": False,
                "chip_used": "none",
            },
        ]
    )
    return SeasonBenchmarkResult(
        season=season,
        strategy_name="deterministic-single-transfer",
        strategy_version="v1",
        model_name="Ridge Regression",
        model_version="r2-consumer-portfolio-v1",
        rows=rows,
        initial_squad=pd.DataFrame(),
        final_squad=pd.DataFrame(),
        total_points=110.0,
        gross_points=110.0,
        realistic_total_points=100.0,
        realistic_gross_points=104.0,
        realistic_captaincy_gap=10.0,
        transfers_made=1,
        total_hit_cost=4,
        max_free_transfers=5,
        initial_bank=0.5,
        final_bank=1.0,
        chip_mode=CHIP_MODE_BEAM,
        chip_points=8.0,
        chips_used=1,
        minutes_mode="binary",
        hit_policy="current_gw",
    )


def test_production_simulation_writes_isolated_reproducible_artifacts(
    tmp_path: Path,
    monkeypatch,
):
    captured = []

    def fake_benchmark(players, season, strategy, **kwargs):
        captured.append((season, strategy, kwargs))
        return _result(season)

    monkeypatch.setattr(
        "fpl_intelligence.simulate_seasons.run_season_benchmark",
        fake_benchmark,
    )
    monkeypatch.setattr(
        "fpl_intelligence.simulate_seasons.get_git_commit",
        lambda: "test-commit",
    )
    monkeypatch.setattr(
        "fpl_intelligence.simulate_seasons._initial_squad_for_preset",
        lambda *args, **kwargs: (
            None,
            PRODUCTION_INITIAL_SQUAD_POLICY,
            "p3-opening-milp-v2-cold-start-safe",
        ),
    )
    first = run_historical_simulation(
        seasons=("2025-26",),
        preset_name="production",
        output_dir=tmp_path / "first",
        generated_at="2026-07-26T13:00:00Z",
        players=_historical_rows(),
    )
    second = run_historical_simulation(
        seasons=("2025-26",),
        preset_name="production",
        output_dir=tmp_path / "second",
        generated_at="2026-07-26T14:00:00Z",
        players=_historical_rows(),
    )

    assert first["manifest"]["simulation_key"] == second["manifest"]["simulation_key"]
    assert first["summary"].iloc[0]["realistic_points"] == 100.0
    assert first["summary"].iloc[0]["realistic_chip_gain"] == 8.0
    assert first["summary"].iloc[0]["chip_sequence"] == "GW1:3xc"
    assert len(first["decisions"]) == 2
    assert set(path.name for path in (tmp_path / "first").iterdir()) == {
        "gameweek_decisions.csv",
        "run_manifest.json",
        "season_summary.csv",
    }
    manifest = json.loads(
        (tmp_path / "first" / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"
    assert manifest["commit_hash"] == "test-commit"
    assert manifest["configuration"]["projection_portfolio"] == {
        "transfer_model": "Ridge Regression",
        "captain_model": "Ridge Regression",
        "chip_model": "Gradient Boosting Regressor",
        "lineup_model": "Ridge Regression",
    }
    assert (
        manifest["configuration"]["initial_squad_policy"]
        == PRODUCTION_INITIAL_SQUAD_POLICY
    )
    assert manifest["artifacts"]["gameweek_decisions"]["rows"] == 2
    _, strategy, kwargs = captured[0]
    assert strategy.name == "deterministic-single-transfer"
    assert kwargs["chip_mode"] == CHIP_MODE_BEAM
    assert kwargs["projection_portfolio"].chip_model == "Gradient Boosting Regressor"
    assert kwargs["initial_squad_mode"] == PRODUCTION_INITIAL_SQUAD_POLICY
    assert kwargs["initial_squad_version"] == "p3-opening-milp-v2-cold-start-safe"


def test_production_opening_policy_falls_back_when_no_prior_season_exists():
    players = pd.DataFrame([{"season": "2023-24", "gameweek": 1, "player_id": 1}])
    sentinel = pd.DataFrame([{"player_id": 1}])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "fpl_intelligence.backtest_transfer_strategy.build_initial_squad",
            lambda *args, **kwargs: sentinel,
        )
        squad, mode, version = _initial_squad_for_preset(
            players,
            "2023-24",
            policy=PRODUCTION_INITIAL_SQUAD_POLICY,
            model_name="Ridge Regression",
        )

    assert squad is sentinel
    assert mode.endswith(":identity_safe_fallback")
    assert version == "identity-safe-preseason-v1"


def test_simulation_refuses_to_overwrite_an_existing_directory(
    tmp_path: Path,
):
    destination = tmp_path / "existing"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        run_historical_simulation(
            seasons=("2025-26",),
            output_dir=destination,
            players=_historical_rows(),
        )


def test_requested_seasons_must_be_unique_available_and_start_at_gw1():
    historical = _historical_rows()

    with pytest.raises(ValueError, match="duplicates"):
        _validate_seasons(historical, ("2025-26", "2025-26"))
    with pytest.raises(ValueError, match="unavailable"):
        _validate_seasons(historical, ("2022-23",))
    with pytest.raises(ValueError, match="GW1"):
        _validate_seasons(
            historical[historical["gameweek"] > 1],
            ("2025-26",),
        )


def test_cli_defaults_to_all_completed_seasons_and_production():
    args = _parse_args([])

    assert tuple(args.seasons) == DEFAULT_SEASONS
    assert args.preset == "production"
