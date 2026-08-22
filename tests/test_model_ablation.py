from pathlib import Path

import pandas as pd
import pytest

from fpl_intelligence.model_ablation import (
    BASELINE_VARIANT,
    AblationRegistry,
    AblationVariant,
    MultiSeasonAblationResult,
    evaluate_acceptance_bar,
    evaluate_strategy_acceptance_bar,
    run_multi_season_ablation,
    update_history_validation_status,
)
from fpl_intelligence.season_benchmark import (
    DeterministicTransferStrategy,
    NoTransfersStrategy,
    SeasonBenchmarkResult,
    load_historical_player_gameweeks,
)


def _fake_ablation_players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": "2023-24",
                "gameweek": 1,
                "team": "Team A",
                "opponent_team": "Team B",
                "home_or_away": "H",
            }
        ]
    )


def _fake_ablation_result(season: str, strategy: object) -> SeasonBenchmarkResult:
    strategy_name = str(strategy.name)
    rows = pd.DataFrame(
        [
            {
                "gameweek": 1,
                "transfers_made": 0,
                "net_points": 10.0,
                "realistic_net_points": 9.0,
            }
        ]
    )
    return SeasonBenchmarkResult(
        season=season,
        strategy_name=strategy_name,
        strategy_version="test",
        model_name="test",
        model_version="test",
        rows=rows,
        initial_squad=pd.DataFrame(),
        final_squad=pd.DataFrame(),
        total_points=10.0,
        gross_points=10.0,
        realistic_total_points=9.0,
        realistic_gross_points=9.0,
        realistic_captaincy_gap=1.0,
        transfers_made=0,
        total_hit_cost=0,
        max_free_transfers=5,
        initial_bank=0.0,
        final_bank=0.0,
    )


def _fake_variant() -> AblationVariant:
    return AblationVariant(
        name="fake",
        description="Synthetic persistence test variant.",
        runner=lambda players, season, strategy, **kwargs: _fake_ablation_result(
            season, strategy
        ),
    )


def test_ablation_runner_defaults_to_no_persistence(tmp_path: Path, monkeypatch):
    history_path = tmp_path / "history.csv"
    monkeypatch.setattr("fpl_intelligence.model_ablation.HISTORY_PATH", history_path)
    registry = AblationRegistry((_fake_variant(),))

    run_multi_season_ablation(
        _fake_ablation_players(),
        seasons=("2023-24",),
        strategies=(NoTransfersStrategy(),),
        registry=registry,
        variant_names=("fake",),
    )

    assert not history_path.exists()


def test_ablation_runner_persists_one_row_per_result_combination(tmp_path: Path):
    history_path = tmp_path / "history.csv"
    registry = AblationRegistry((_fake_variant(),))
    result = run_multi_season_ablation(
        _fake_ablation_players(),
        seasons=("2023-24",),
        strategies=(NoTransfersStrategy(), DeterministicTransferStrategy()),
        registry=registry,
        variant_names=("fake",),
        persist=True,
        history_path=history_path,
        run_id="suite-1",
        commit_hash="commit-1",
    )

    history = pd.read_csv(history_path)
    assert len(history) == 2
    assert history["run_id"].eq("suite-1").all()
    assert history["optimizer_version"].eq("m3.5-milp-v1").all()
    assert history[["run_id", "variant_name", "season", "strategy_name"]].duplicated().sum() == 0
    assert result.run_id == "suite-1"
    assert result.history_path == history_path
    assert result.decision_history_path == history_path.with_name("history_decisions.csv")
    decision_history = pd.read_csv(result.decision_history_path)
    assert len(decision_history) == 2
    assert decision_history["run_id"].eq("suite-1").all()
    assert decision_history["variant_name"].eq("fake").all()


def test_ablation_runner_forwards_chip_mode_to_persisted_variants(tmp_path: Path):
    seen: dict[str, str] = {}

    def runner(players, season, strategy, **kwargs):
        seen["chip_mode"] = kwargs["chip_mode"]
        return _fake_ablation_result(season, strategy)

    registry = AblationRegistry(
        (
            AblationVariant(
                name="beam",
                description="Synthetic beam persistence test variant.",
                runner=runner,
            ),
        )
    )
    run_multi_season_ablation(
        _fake_ablation_players(),
        seasons=("2023-24",),
        strategies=(NoTransfersStrategy(),),
        registry=registry,
        variant_names=("beam",),
        persist=True,
        history_path=tmp_path / "history.csv",
        chip_mode="beam_search",
    )

    assert seen["chip_mode"] == "beam_search"


def test_validation_status_update_is_scoped_to_run_id(tmp_path: Path):
    history_path = tmp_path / "history.csv"
    pd.DataFrame(
        [
            {
                "run_id": "old-run",
                "variant_name": "candidate",
                "strategy_name": "deterministic-single-transfer",
                "validation_status": "provisional",
            },
            {
                "run_id": "current-run",
                "variant_name": "candidate",
                "strategy_name": "deterministic-single-transfer",
                "validation_status": "provisional",
            },
        ]
    ).to_csv(history_path, index=False)

    decision = evaluate_acceptance_bar(
        _synthetic_ablation_result((101.0, 101.0)),
        "candidate",
        history_path=history_path,
        run_id="current-run",
    )
    history = pd.read_csv(history_path).set_index("run_id")

    assert decision.passed is True
    assert history.loc["old-run", "validation_status"] == "provisional"
    assert history.loc["current-run", "validation_status"] == "validated"


def test_strategy_acceptance_compares_candidate_to_control_per_variant(tmp_path: Path):
    comparison_rows = []
    regime_rows = []
    for variant, improvement in (("baseline", 1.0), ("baseline+xg_xa", 2.0)):
        for season in ("2023-24", "2024-25"):
            for strategy, points in (
                ("deterministic-single-transfer", 100.0),
                ("two-gameweek-lookahead", 100.0 + improvement),
            ):
                comparison_rows.append(
                    {
                        "variant_name": variant,
                        "season": season,
                        "strategy_name": strategy,
                        "realistic_points": points,
                    }
                )
                for regime in ("blank", "double"):
                    regime_rows.append(
                        {
                            "variant_name": variant,
                            "season": season,
                            "strategy_name": strategy,
                            "regime": regime,
                            "gameweek_count": 2,
                            "realistic_points": 20.0 + improvement,
                        }
                    )
    result = MultiSeasonAblationResult(
        comparison=pd.DataFrame(comparison_rows),
        regime_breakdown=pd.DataFrame(regime_rows),
        dc_states=pd.DataFrame(),
    )

    baseline = evaluate_strategy_acceptance_bar(result, "baseline")
    xg_xa = evaluate_strategy_acceptance_bar(result, "baseline+xg_xa")

    assert baseline.passed is True
    assert xg_xa.passed is True
    assert baseline.metrics["season_realistic_deltas"] == {
        "2023-24": 1.0,
        "2024-25": 1.0,
    }
    assert xg_xa.metrics["aggregate_realistic_delta"] == 4.0


@pytest.mark.requires_local_artifacts
def test_multi_season_baseline_reproduces_identity_safe_no_chip_totals():
    result = run_multi_season_ablation(
        load_historical_player_gameweeks(),
        variant_names=("baseline",),
    )
    comparison = result.comparison.set_index(["season", "strategy_name"])

    expected = {
        ("2023-24", "no-transfers"): (772.0, 669.0),
        # Transfer totals use FPL selling value: half of price-rise profit,
        # rounded down to GBP 0.1m, with price losses realised in full.
        ("2023-24", "deterministic-single-transfer"): (2201.0, 1992.0),
        ("2024-25", "no-transfers"): (2174.0, 1963.0),
        ("2024-25", "deterministic-single-transfer"): (2298.0, 2080.0),
    }
    for key, (hindsight, realistic) in expected.items():
        row = comparison.loc[key]
        assert row["variant_name"] == "baseline"
        assert row["hindsight_points"] == hindsight
        assert row["realistic_points"] == realistic

    assert {"blank", "double", "post_transfer", "no_recent_transfer"}.issubset(
        set(result.regime_breakdown["regime"])
    )


@pytest.mark.requires_local_artifacts
def test_dc_variant_is_explicitly_not_applicable_before_rule_start():
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("DC runner must not run before the DC rule existed")

    registry = AblationRegistry((BASELINE_VARIANT,))
    registry.register(
        AblationVariant(
            name="fake_dc",
            description="Synthetic DC-dependent test variant.",
            runner=should_not_run,
            dc_dependent=True,
        )
    )
    result = run_multi_season_ablation(
        load_historical_player_gameweeks(),
        seasons=("2023-24",),
        strategies=(NoTransfersStrategy(),),
        registry=registry,
        variant_names=("fake_dc",),
    )

    row = result.comparison.iloc[0]
    assert row["dc_status"] == "not_applicable"
    assert pd.isna(row["realistic_points"])
    assert called is False


def _synthetic_ablation_result(improved_points: tuple[float, float]) -> MultiSeasonAblationResult:
    comparison = pd.DataFrame(
        [
            {
                "variant_name": "baseline",
                "season": "2023-24",
                "strategy_name": "deterministic-single-transfer",
                "realistic_points": 100.0,
                "dc_status": "not_required",
            },
            {
                "variant_name": "baseline",
                "season": "2024-25",
                "strategy_name": "deterministic-single-transfer",
                "realistic_points": 100.0,
                "dc_status": "not_required",
            },
            {
                "variant_name": "candidate",
                "season": "2023-24",
                "strategy_name": "deterministic-single-transfer",
                "realistic_points": improved_points[0],
                "dc_status": "not_required",
            },
            {
                "variant_name": "candidate",
                "season": "2024-25",
                "strategy_name": "deterministic-single-transfer",
                "realistic_points": improved_points[1],
                "dc_status": "not_required",
            },
        ]
    )
    regimes = pd.DataFrame(
        [
            {
                "variant_name": variant,
                "season": season,
                "strategy_name": "deterministic-single-transfer",
                "regime": regime,
                "gameweek_count": 2,
                "realistic_points": 20.0 if variant == "baseline" else 20.0,
            }
            for variant in ("baseline", "candidate")
            for season in ("2023-24", "2024-25")
            for regime in ("blank", "double")
        ]
    )
    return MultiSeasonAblationResult(
        comparison=comparison,
        regime_breakdown=regimes,
        dc_states=pd.DataFrame(),
    )


def test_acceptance_bar_has_pass_and_fail_outcomes():
    passed = evaluate_acceptance_bar(
        _synthetic_ablation_result((101.0, 101.0)),
        "candidate",
    )
    failed = evaluate_acceptance_bar(
        _synthetic_ablation_result((101.0, 90.0)),
        "candidate",
    )

    assert passed.passed is True
    assert passed.validation_status == "validated"
    assert passed.acceptance_result == "pass"
    assert failed.passed is False
    assert failed.validation_status == "provisional"
    assert failed.acceptance_result == "fail"
    assert "regressed" in failed.reason


def test_acceptance_bar_updates_history_status(tmp_path: Path):
    history_path = tmp_path / "history.csv"
    pd.DataFrame(
        [
            {
                "run_id": "current-run",
                "variant_name": "candidate",
                "strategy_name": "deterministic-single-transfer",
                "validation_status": "provisional",
            }
        ]
    ).to_csv(history_path, index=False)

    decision = evaluate_acceptance_bar(
        _synthetic_ablation_result((101.0, 101.0)),
        "candidate",
        history_path=history_path,
        run_id="current-run",
    )
    updated = pd.read_csv(history_path).iloc[0]

    assert decision.passed is True
    assert updated["validation_status"] == "validated"
    assert updated["acceptance_result"] == "pass"
    assert update_history_validation_status(history_path, decision, run_id="current-run") == 1
