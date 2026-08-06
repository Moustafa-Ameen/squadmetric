from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fpl_intelligence.points_loss_audit import (
    audit_simulation,
    build_chip_usage,
    build_decision_opportunities,
    build_loss_bucket_summary,
    build_points_loss_gameweeks,
    evaluate_rank_references,
    expand_chip_counterfactuals,
    load_rank_references,
    load_recovery_scorecard,
)


def _players() -> pd.DataFrame:
    positions = [
        "GK",
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
        "FWD",
    ]
    points = [3, 1, 2, 4, 5, 1, 10, 6, 3, 2, 1, 4, 7, 5, 2]
    return pd.DataFrame(
        [
            {
                "season": "2025-26",
                "gameweek": 1,
                "player_id": player_id,
                "player_name": f"Player {player_id}",
                "position": position,
                "team": f"Team {player_id}",
                "price": 5.0,
                "minutes": 90,
                "next_gameweek_points": point,
                "opponent_team": "Opponent",
                "home_or_away": "H",
            }
            for player_id, (position, point) in enumerate(
                zip(positions, points, strict=True),
                start=1,
            )
        ]
    )


def _decision() -> pd.DataFrame:
    selected = (1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14)
    point_map = _players().set_index("player_id")["next_gameweek_points"].to_dict()
    raw_points = sum(point_map[player_id] for player_id in selected)
    gross = raw_points + point_map[3]
    return pd.DataFrame(
        [
            {
                "season": "2025-26",
                "gameweek": 1,
                "realistic_gross_points": gross,
                "realistic_net_points": gross,
                "realistic_cumulative_points": gross,
                "raw_starter_points": raw_points,
                "hit_cost": 0,
                "realistic_captain_id": 3,
                "realistic_vice_captain_id": 4,
                "realistic_vice_captain_fallback": False,
                "realistic_starting_ids": "+".join(map(str, selected)),
                "starting_ids": "+".join(map(str, selected)),
                "selected_bench_ids": "2+7+12+15",
                "realistic_autosub_ids": "",
                "squad_ids": "+".join(str(value) for value in range(1, 16)),
                "transfers_made": 0,
                "outgoing_id": None,
                "incoming_id": None,
                "chip_used": "none",
                "chip_key": "none",
                "chip_expected_gain": 0.0,
                "realistic_chip_realized_gain": 0.0,
                "chip_counterfactuals": json.dumps(
                    [
                        {
                            "chip_key": "none",
                            "status": "selected",
                            "legal": True,
                            "expected_gain": 0.0,
                            "reason": "best guarded branch",
                        },
                        {
                            "chip_key": "3xc:1",
                            "status": "rejected",
                            "legal": True,
                            "expected_gain": 1.5,
                            "reason": "future opportunity cost",
                        },
                    ]
                ),
            }
        ]
    )


def test_gameweek_audit_reconciles_and_labels_hindsight_diagnostics():
    audit = build_points_loss_gameweeks(_decision(), _players())
    row = audit.iloc[0]

    assert row["row_reconciliation_status"] == "exact"
    assert row["cumulative_reconciliation_status"] == "exact"
    assert row["captain_regret"] == 5
    assert row["captain_regret_status"] == "hindsight_upper_bound"
    assert row["lineup_regret"] > 0
    assert row["lineup_regret_status"] == "hindsight_upper_bound"
    assert row["bench_points_left"] == 17
    assert row["bench_points_status"] == "diagnostic_actual_points"

    buckets = build_loss_bucket_summary(audit)
    assert not buckets["additive"].any()
    assert (
        buckets.loc[buckets["bucket"] == "chip_timing_and_preparation", "status"].iloc[0]
        == "unavailable"
    )


def test_legacy_rows_do_not_invent_missing_lineup_or_bench_regret():
    decisions = _decision().drop(
        columns=[
            "realistic_starting_ids",
            "selected_bench_ids",
            "realistic_autosub_ids",
            "squad_ids",
        ]
    )
    audit = build_points_loss_gameweeks(decisions, _players())
    row = audit.iloc[0]

    assert row["captain_lineup_source"] == "legacy_generic_starting_ids"
    assert row["captain_regret_status"] == "hindsight_upper_bound"
    assert row["lineup_regret_status"] == "unavailable_missing_squad_ids"
    assert row["bench_points_status"] == "unavailable_missing_ordered_bench"
    assert pd.isna(row["lineup_regret"])
    assert pd.isna(row["bench_points_left"])


def test_transfer_regret_requires_stable_player_ids():
    decisions = _decision()
    decisions.loc[0, "transfers_made"] = 1
    decisions.loc[0, "outgoing_id"] = 7
    decisions.loc[0, "incoming_id"] = 6
    audit = build_points_loss_gameweeks(decisions, _players())

    row = audit.iloc[0]
    assert row["selected_transfer_one_week_delta"] == -9
    assert row["selected_transfer_regret"] == 9
    assert row["selected_transfer_status"] == "hindsight_partial"

    legacy = decisions.drop(columns=["outgoing_id", "incoming_id"])
    legacy_audit = build_points_loss_gameweeks(legacy, _players())
    assert (
        legacy_audit.iloc[0]["selected_transfer_status"]
        == "unavailable_missing_transfer_ids"
    )


def test_captain_regret_handles_both_captain_and_vice_missing():
    decisions = _decision()
    decisions.loc[0, "realistic_captain_id"] = 2
    decisions.loc[0, "realistic_vice_captain_id"] = 7
    decisions.loc[0, "realistic_captain_actual_points"] = 0
    decisions.loc[0, "realistic_vice_captain_actual_points"] = 0
    audit = build_points_loss_gameweeks(decisions, _players())

    row = audit.iloc[0]
    assert row["captain_regret"] == 7
    assert (
        row["captain_regret_status"]
        == "hindsight_upper_bound_no_effective_captain"
    )


def test_free_hit_audit_uses_selected_active_squad_not_permanent_squad_ids():
    decisions = _decision()
    decisions.loc[0, "chip_used"] = "freehit"
    decisions["selected_starting_ids"] = decisions["realistic_starting_ids"]
    decisions.loc[0, "squad_ids"] = "+".join(str(value) for value in range(101, 116))

    audit = build_points_loss_gameweeks(decisions, _players())

    assert audit.iloc[0]["decision_squad_source"] == "selected_xi_plus_bench"
    assert audit.iloc[0]["lineup_regret_status"] == "hindsight_upper_bound"


def test_audit_zero_fills_owned_player_missing_from_gameweek_rows():
    previous = _players()
    current = _players().copy()
    current["gameweek"] = 2
    current = current[current["player_id"].ne(7)]
    players = pd.concat([previous, current], ignore_index=True)
    decisions = _decision()
    decisions["gameweek"] = 2

    audit = build_points_loss_gameweeks(decisions, players)

    assert audit.iloc[0]["lineup_regret_status"] == "hindsight_upper_bound"


def test_chip_health_diagnostics_expose_zero_save_value_and_free_hit_gain():
    decisions = _decision()
    decisions.loc[0, "chip_used"] = "freehit"
    decisions.loc[0, "chip_key"] = "freehit:1"
    decisions.loc[0, "chip_slot"] = 1
    decisions.loc[0, "chip_expected_gain"] = 8.0
    decisions.loc[0, "realistic_chip_realized_gain"] = 0.0
    decisions.loc[0, "future_opportunity_cost"] = 0.0
    decisions.loc[0, "uncertainty_penalty"] = 0.2
    gameweeks = build_points_loss_gameweeks(decisions, _players())

    chips = build_chip_usage(decisions, gameweeks)
    opportunities = build_decision_opportunities(gameweeks, chips).set_index(
        "decision_area"
    )

    assert chips.iloc[0]["realized_gain_status"] == "exact_incremental_gameweek"
    assert opportunities.loc["chip_future_opportunity_cost", "value"] == 1
    assert opportunities.loc["free_hit_realization", "value"] == 1


def test_recovery_scorecard_loader_selects_only_accepted_candidate(tmp_path: Path):
    cold_dir = tmp_path / "cold"
    tournament_dir = tmp_path / "tournament"
    cold_dir.mkdir()
    tournament_dir.mkdir()
    cold_rows = pd.DataFrame(
        [
            {"season": "2023-24", "gameweek": gameweek, "marker": "cold"}
            for gameweek in range(1, 39)
        ]
    )
    tournament_rows = pd.DataFrame(
        [
            {
                "candidate": candidate,
                "season": season,
                "gameweek": gameweek,
                "marker": candidate,
            }
            for candidate in ("horizon_8_flexible", "identity_safe_value")
            for season in ("2024-25", "2025-26")
            for gameweek in range(1, 39)
        ]
    )
    cold_rows.to_csv(cold_dir / "gameweek_decisions.csv", index=False)
    pd.DataFrame(
        [{"season": "2023-24", "realistic_points": 2321, "hindsight_points": 2575}]
    ).to_csv(cold_dir / "season_summary.csv", index=False)
    (cold_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
    tournament_rows.to_csv(tournament_dir / "gameweek_decisions.csv", index=False)
    pd.DataFrame(
        [
            {
                "candidate": candidate,
                "season": season,
                "realistic_points": points,
                "hindsight_points": points + 200,
            }
            for candidate, points in (
                ("horizon_8_flexible", 2194),
                ("identity_safe_value", 1996),
            )
            for season in ("2024-25", "2025-26")
        ]
    ).to_csv(tournament_dir / "full_season_continuation.csv", index=False)
    (tournament_dir / "run_manifest.json").write_text("{}", encoding="utf-8")

    decisions, summary, paths = load_recovery_scorecard(
        cold_start_dir=cold_dir,
        tournament_dir=tournament_dir,
    )

    assert len(decisions) == 114
    assert set(decisions["marker"]) == {"cold", "horizon_8_flexible"}
    assert len(summary) == 3
    assert len(paths) == 6


def test_rank_reference_uses_bounds_and_keeps_unavailable_seasons_explicit():
    references = load_rank_references()
    summary = pd.DataFrame(
        [
            {"season": "2023-24", "realistic_points": 2500},
            {"season": "2024-25", "realistic_points": 2506},
            {"season": "2025-26", "realistic_points": 2265},
        ]
    )
    result = evaluate_rank_references(summary, references).set_index("season")

    assert result.loc["2023-24", "classification"] == "unavailable"
    assert (
        result.loc["2024-25", "classification"]
        == "inside_unresolved_boundary_bracket"
    )
    assert result.loc["2025-26", "classification"] == "below_verified_outside_score"
    assert result.loc["2025-26", "top_one_percent_rank"] == 131077
    assert result.loc["2025-26", "margin_to_known_inside_points"] == -54
    assert result.loc["2025-26", "minimum_margin_to_verified_boundary_evidence"] == -31


def test_chip_counterfactuals_only_attach_realized_gain_to_selected_branch():
    decisions = _decision()
    expanded = expand_chip_counterfactuals(decisions)

    selected = expanded.loc[expanded["status"] == "selected"].iloc[0]
    rejected = expanded.loc[expanded["status"] == "rejected"].iloc[0]
    assert selected["realized_gain_status"] == "exact_selected"
    assert selected["realized_gain"] == 0
    assert rejected["realized_gain_status"] == "unavailable"
    assert pd.isna(rejected["realized_gain"])


def test_audit_simulation_writes_artifacts_and_rejects_summary_mismatch(
    tmp_path: Path,
):
    simulation_dir = tmp_path / "simulation"
    simulation_dir.mkdir()
    decisions = _decision()
    score = float(decisions["realistic_net_points"].sum())
    decisions.to_csv(simulation_dir / "gameweek_decisions.csv", index=False)
    pd.DataFrame(
        [{"season": "2025-26", "realistic_points": score}]
    ).to_csv(simulation_dir / "season_summary.csv", index=False)
    (simulation_dir / "run_manifest.json").write_text(
        json.dumps({"run_id": "run-1", "simulation_key": "key-1"}),
        encoding="utf-8",
    )
    historical_path = tmp_path / "historical.csv"
    _players().to_csv(historical_path, index=False)

    result = audit_simulation(
        simulation_dir,
        historical_path=historical_path,
        generated_at="2026-07-28T00:00:00Z",
    )

    assert result.manifest["status"] == "complete"
    assert (simulation_dir / "points_loss_audit_manifest.json").is_file()
    assert (simulation_dir / "points_loss_gameweeks.csv").is_file()
    assert (simulation_dir / "points_loss_buckets.csv").is_file()
    assert (simulation_dir / "rank_reference_evaluation.csv").is_file()
    assert (simulation_dir / "chip_counterfactual_audit.csv").is_file()
    assert (simulation_dir / "decision_opportunities.csv").is_file()
    assert (simulation_dir / "chip_usage.csv").is_file()

    pd.DataFrame(
        [{"season": "2025-26", "realistic_points": score + 1}]
    ).to_csv(simulation_dir / "season_summary.csv", index=False)
    with pytest.raises(AssertionError, match="Season score reconciliation failed"):
        audit_simulation(
            simulation_dir,
            historical_path=historical_path,
            write=False,
        )
