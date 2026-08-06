from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from fpl_intelligence.initial_squad_championship import (
    CHECKPOINT_FILES,
    P3_BASELINE_NAME,
    P3_CONFIGS,
    OpeningProjectionBundle,
    OpeningSquadCandidate,
    _assert_opening_cutoff,
    _write_checkpoint,
    build_identity_safe_preseason_pool,
    build_live_opening_projection_bundle,
    evaluate_opening_squad,
    evaluate_tournament_acceptance,
    optimize_opening_squad,
    run_initial_squad_tournament,
)
from fpl_intelligence.squad_optimizer import (
    validate_squad_shape,
    validate_starting_xi,
)


def _candidate_pool() -> pd.DataFrame:
    positions = ["GK"] * 4 + ["DEF"] * 10 + ["MID"] * 10 + ["FWD"] * 7
    rows = []
    for player_id, position in enumerate(positions, start=1):
        rows.append(
            {
                "player_id": player_id,
                "player_name": f"Player {player_id}",
                "position": position,
                "position_group": position,
                "team": f"Team {(player_id - 1) % 12 + 1}",
                "price": 4.5 + (player_id % 8) * 0.75,
                "prior_matched": player_id % 7 != 0,
                "unmatched_player": player_id % 7 == 0,
                "promoted_team": player_id % 11 == 0,
                "identity_value_score": 1.0 + player_id / 100,
            }
        )
    return pd.DataFrame(rows)


def _bundle() -> OpeningProjectionBundle:
    candidates = _candidate_pool()
    projections = {}
    for gameweek in range(1, 9):
        projections[gameweek] = pd.DataFrame(
            {
                "player_id": candidates["player_id"],
                "projected_points": (
                    2.0
                    + candidates["player_id"] / 20
                    + (candidates["player_id"] % (gameweek + 2)) / 10
                ),
                "start_probability": (
                    0.95 - (candidates["player_id"] % 5) * 0.05
                ),
            }
        )
    return OpeningProjectionBundle(
        season="2025-26",
        candidates=candidates,
        projections=projections,
        prior_season="2024-25",
        data_cutoff="2025-26:GW00",
        projection_hash="projection-hash",
    )


def test_identity_safe_pool_matches_prior_players_by_name_not_season_local_id():
    prior = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "gameweek": gameweek,
                "player_id": 1,
                "player_name": "Alice Star",
                "position": "MID",
                "team": "Old Team",
                "price": 8.0,
                "minutes": 90,
                "total_points": 10,
            }
            for gameweek in (1, 2)
        ]
        + [
            {
                "season": "2024-25",
                "gameweek": gameweek,
                "player_id": 2,
                "player_name": "Bob Safe",
                "position": "DEF",
                "team": "Other Team",
                "price": 5.0,
                "minutes": 90,
                "total_points": 2,
            }
            for gameweek in (1, 2)
        ]
    )
    current = pd.DataFrame(
        [
            {
                "season": "2025-26",
                "gameweek": 1,
                "feature_cutoff_gameweek": 0,
                "player_id": 1,
                "player_name": "Bob Safe",
                "position": "DEF",
                "team": "Other Team",
                "price": 5.0,
                "price_before_deadline": 0.0,
                "selected_by_percent": 10.0,
            },
            {
                "season": "2025-26",
                "gameweek": 1,
                "feature_cutoff_gameweek": 0,
                "player_id": 2,
                "player_name": "Alice Star",
                "position": "MID",
                "team": "Old Team",
                "price": 8.0,
                "price_before_deadline": 0.0,
                "selected_by_percent": 20.0,
            },
            {
                "season": "2025-26",
                "gameweek": 1,
                "feature_cutoff_gameweek": 0,
                "player_id": 3,
                "player_name": "New Player",
                "position": "FWD",
                "team": "Promoted Team",
                "price": 6.0,
                "price_before_deadline": 0.0,
                "selected_by_percent": 1.0,
            },
        ]
    )

    pool = build_identity_safe_preseason_pool(
        pd.concat([prior, current], ignore_index=True, sort=False),
        season="2025-26",
        prior_season="2024-25",
    ).set_index("player_name")

    assert pool.loc["Alice Star", "prior_points"] == 20
    assert pool.loc["Bob Safe", "prior_points"] == 4
    assert bool(pool.loc["Alice Star", "prior_matched"])
    assert bool(pool.loc["New Player", "unmatched_player"])
    assert bool(pool.loc["New Player", "promoted_team"])


def test_multi_horizon_optimizer_is_legal_and_deterministic():
    bundle = _bundle()
    config = P3_CONFIGS["horizon_8_flexible"]

    first = optimize_opening_squad(bundle, config)
    second = optimize_opening_squad(bundle, config)

    assert not validate_squad_shape(first.squad)
    assert first.squad["price"].sum() <= 100
    assert first.squad["price"].sum() >= config.minimum_spend
    assert set(first.squad["player_id"]) == set(second.squad["player_id"])
    assert first.horizon_lineups == second.horizon_lineups
    assert first.horizon_captains == second.horizon_captains
    assert first.projected_metrics == second.projected_metrics
    for gameweek, starting_ids in first.horizon_lineups.items():
        assert not validate_starting_xi(first.squad, starting_ids)
        assert first.horizon_captains[gameweek] in starting_ids


def test_all_p3_horizons_produce_evaluable_legal_squads():
    bundle = _bundle()

    results = [
        optimize_opening_squad(bundle, config)
        for config in P3_CONFIGS.values()
    ]

    assert {result.projected_metrics["configured_horizon"] for result in results} == {
        3,
        5,
        8,
    }
    assert (
        P3_CONFIGS["horizon_3_attack"].wildcard_scenario_gameweek == 4
    )
    for result in results:
        metrics = evaluate_opening_squad(bundle, result.squad)
        assert metrics["projected_points_3"] > 0
        assert metrics["projected_points_5"] >= metrics["projected_points_3"]
        assert metrics["projected_points_8"] >= metrics["projected_points_5"]


def test_acceptance_requires_two_improved_seasons_and_no_severe_regression():
    continuation = pd.DataFrame(
        [
            {"season": season, "candidate": P3_BASELINE_NAME, "realistic_points": score}
            for season, score in (
                ("2023-24", 2100),
                ("2024-25", 2200),
                ("2025-26", 2250),
            )
        ]
        + [
            {"season": "2023-24", "candidate": "passes", "realistic_points": 2120},
            {"season": "2024-25", "candidate": "passes", "realistic_points": 2230},
            {"season": "2025-26", "candidate": "passes", "realistic_points": 2245},
            {"season": "2023-24", "candidate": "aggregate_trap", "realistic_points": 2300},
            {"season": "2024-25", "candidate": "aggregate_trap", "realistic_points": 2220},
            {"season": "2025-26", "candidate": "aggregate_trap", "realistic_points": 2100},
        ]
    )

    acceptance = evaluate_tournament_acceptance(continuation).set_index("candidate")

    assert bool(acceptance.loc["passes", "passed"])
    assert not bool(acceptance.loc["aggregate_trap", "passed"])
    assert acceptance.loc["aggregate_trap", "aggregate_delta"] > 0
    assert acceptance.loc["aggregate_trap", "severe_regressions"] == 1
    assert json.loads(acceptance.loc["passes", "per_season_deltas"]) == {
        "2023-24": 20.0,
        "2024-25": 30.0,
        "2025-26": -5.0,
    }


def test_cold_start_safe_horizon_8_policy_passes_honest_baseline():
    continuation = pd.DataFrame(
        [
            {
                "season": "2023-24",
                "candidate": P3_BASELINE_NAME,
                "realistic_points": 2321,
            },
            {
                "season": "2024-25",
                "candidate": P3_BASELINE_NAME,
                "realistic_points": 1996,
            },
            {
                "season": "2025-26",
                "candidate": P3_BASELINE_NAME,
                "realistic_points": 2124,
            },
            {
                "season": "2023-24",
                "candidate": "horizon_8_flexible_cold_start_safe",
                "realistic_points": 2321,
            },
            {
                "season": "2024-25",
                "candidate": "horizon_8_flexible_cold_start_safe",
                "realistic_points": 2194,
            },
            {
                "season": "2025-26",
                "candidate": "horizon_8_flexible_cold_start_safe",
                "realistic_points": 2136,
            },
        ]
    )

    result = evaluate_tournament_acceptance(continuation).iloc[0]

    assert bool(result["passed"])
    assert result["improved_seasons"] == 2
    assert result["aggregate_delta"] == 210
    assert result["severe_regressions"] == 0


def test_opening_cutoff_rejects_post_deadline_candidate_state():
    candidates = _candidate_pool()
    candidates["feature_cutoff_gameweek"] = 1

    with pytest.raises(AssertionError, match="post-GW1"):
        _assert_opening_cutoff(candidates, _bundle().projections)


def test_live_bundle_preserves_unmatched_uncertainty_and_fixture_start_probability():
    projected = [
        {
            "element_id": 1,
            "name": "New Player",
            "position": "MID",
            "team": "NEW",
            "team_name": "New Team",
            "price": 7.0,
            "prior_source": "new_player_position_prior",
            "start_likelihood": 0.4,
            "projections": [
                {
                    "gameweek": gameweek,
                    "projected_points": 4.0,
                    "fixtures": [{"start_likelihood": 0.8}],
                }
                for gameweek in range(1, 9)
            ],
        }
    ]
    bundle = build_live_opening_projection_bundle(
        projected,
        {
            "season": "2026-27",
            "data_cutoff": "2026-07-28T00:00:00Z",
        },
    )

    assert bool(bundle.candidates.iloc[0]["unmatched_player"])
    assert bundle.projections[1].iloc[0]["start_probability"] == 0.8
    assert bundle.data_cutoff == "2026-07-28T00:00:00Z"
    assert len(bundle.projection_hash) == 64


def test_tournament_persists_full_season_continuation_and_acceptance(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle()
    champion_squad = optimize_opening_squad(
        bundle,
        P3_CONFIGS["horizon_3_attack"],
    ).squad
    challenger = optimize_opening_squad(
        bundle,
        P3_CONFIGS["horizon_8_flexible"],
    )
    champion = OpeningSquadCandidate(
        name=P3_BASELINE_NAME,
        version="identity-safe-v1",
        squad=champion_squad,
        projected_metrics=evaluate_opening_squad(bundle, champion_squad),
        horizon_lineups={},
        horizon_captains={},
    )
    monkeypatch.setattr(
        "fpl_intelligence.initial_squad_championship.build_opening_projection_bundle",
        lambda *args, **kwargs: bundle,
    )
    monkeypatch.setattr(
        "fpl_intelligence.initial_squad_championship.build_opening_candidates",
        lambda *args, **kwargs: [champion, challenger],
    )

    benchmark_calls = []

    def fake_benchmark(players, season, strategy, **kwargs):
        benchmark_calls.append((season, kwargs["initial_squad_mode"]))
        is_challenger = kwargs["initial_squad_mode"] == challenger.name
        return SimpleNamespace(
            realistic_total_points=2110.0 if is_challenger else 2100.0,
            total_points=2200.0,
            transfers_made=20,
            total_hit_cost=0,
            chips_used=8,
            initial_bank=1.0,
            final_bank=2.0,
            rows=pd.DataFrame([{"initial_squad_hash": f"{season}-hash"}]),
        )

    output_dir = tmp_path / "p3"
    output_dir.mkdir()
    _write_checkpoint(
        output_dir,
        candidates=pd.DataFrame(
            [{"season": "2023-24", "candidate": P3_BASELINE_NAME}]
        ),
        squads=pd.DataFrame(
            [{"season": "2023-24", "candidate": P3_BASELINE_NAME, "player_id": 1}]
        ),
        projected_plan=pd.DataFrame(
            [{"season": "2023-24", "candidate": P3_BASELINE_NAME, "gameweek": 1}]
        ),
        continuation=pd.DataFrame(
            [
                {
                    "season": "2023-24",
                    "candidate": P3_BASELINE_NAME,
                    "realistic_points": 2100.0,
                }
            ]
        ),
        decisions=pd.DataFrame(
            [
                {
                    "season": "2023-24",
                    "candidate": P3_BASELINE_NAME,
                    "gameweek": 1,
                    "initial_squad_hash": "2023-24-hash",
                }
            ]
        ),
    )
    result = run_initial_squad_tournament(
        seasons=("2023-24", "2024-25", "2025-26"),
        players=pd.DataFrame(),
        output_dir=output_dir,
        benchmark_runner=fake_benchmark,
        generated_at="2026-07-28T00:00:00Z",
    )

    assert result.passed
    assert result.selected_candidate == challenger.name
    assert len(result.continuation) == 6
    assert len(result.projected_plan) == 41
    assert len(result.decisions) == 6
    assert ("2023-24", P3_BASELINE_NAME) not in benchmark_calls
    assert (output_dir / "projected_candidates.csv").is_file()
    assert (output_dir / "candidate_squads.csv").is_file()
    assert (output_dir / "projected_plan.csv").is_file()
    assert (output_dir / "full_season_continuation.csv").is_file()
    assert (output_dir / "gameweek_decisions.csv").is_file()
    assert (output_dir / "acceptance.csv").is_file()
    manifest = json.loads(
        (output_dir / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["passed"]
    assert manifest["selected_candidate"] == challenger.name
    assert not any(
        (output_dir / filename).exists()
        for filename in CHECKPOINT_FILES.values()
    )


def test_tournament_reuses_identical_opening_squad_continuation(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle()
    squad = optimize_opening_squad(
        bundle,
        P3_CONFIGS["horizon_3_attack"],
    ).squad
    champion = OpeningSquadCandidate(
        name=P3_BASELINE_NAME,
        version="identity-safe-v1",
        squad=squad.copy(),
        projected_metrics=evaluate_opening_squad(bundle, squad),
        horizon_lineups={},
        horizon_captains={},
    )
    challenger = OpeningSquadCandidate(
        name="horizon_3_attack",
        version="challenger-v1",
        squad=squad.copy(),
        projected_metrics=evaluate_opening_squad(bundle, squad),
        horizon_lineups={},
        horizon_captains={},
    )
    monkeypatch.setattr(
        "fpl_intelligence.initial_squad_championship.build_opening_projection_bundle",
        lambda *args, **kwargs: bundle,
    )
    monkeypatch.setattr(
        "fpl_intelligence.initial_squad_championship.build_opening_candidates",
        lambda *args, **kwargs: [champion, challenger],
    )
    benchmark_calls = []

    def fake_benchmark(players, season, strategy, **kwargs):
        benchmark_calls.append(kwargs["initial_squad_mode"])
        return SimpleNamespace(
            realistic_total_points=2100.0,
            total_points=2200.0,
            transfers_made=20,
            total_hit_cost=0,
            chips_used=5,
            initial_bank=0.0,
            final_bank=1.0,
            rows=pd.DataFrame(
                [
                    {
                        "season": season,
                        "gameweek": 1,
                        "initial_squad_hash": "shared-hash",
                        "initial_squad_mode": kwargs["initial_squad_mode"],
                        "initial_squad_version": kwargs["initial_squad_version"],
                    }
                ]
            ),
        )

    result = run_initial_squad_tournament(
        seasons=("2023-24",),
        players=pd.DataFrame(),
        output_dir=tmp_path / "p3-reuse",
        benchmark_runner=fake_benchmark,
        generated_at="2026-07-28T00:00:00Z",
    )

    assert benchmark_calls == [P3_BASELINE_NAME]
    assert result.continuation["realistic_points"].tolist() == [2100.0, 2100.0]
    assert set(result.decisions["candidate"]) == {
        P3_BASELINE_NAME,
        "horizon_3_attack",
    }
    challenger_rows = result.decisions[
        result.decisions["candidate"] == "horizon_3_attack"
    ]
    assert set(challenger_rows["initial_squad_mode"]) == {"horizon_3_attack"}
    assert set(challenger_rows["initial_squad_version"]) == {"challenger-v1"}
