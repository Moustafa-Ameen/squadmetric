import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from fpl_intelligence.consumer_model_tournament import (
    P4_CHAMPION,
    CandidateSeasonRun,
    _evaluate_candidates,
    _load_checkpoint,
    _write_checkpoint,
    candidate_catalog,
    run_consumer_tournament,
)

SEASONS = ("2023-24", "2024-25", "2025-26")


def _players() -> pd.DataFrame:
    rows = []
    for season in SEASONS:
        for gameweek in range(1, 39):
            for player_id in range(1, 21):
                rows.append(
                    {
                        "season": season,
                        "gameweek": gameweek,
                        "player_id": player_id,
                        "team": f"Team {player_id}",
                        "opponent_team": f"Team {(player_id % 20) + 1}",
                        "home_or_away": "H" if player_id % 2 else "A",
                        "next_gameweek_points": 10.0 if player_id == 1 else 2.0,
                        "minutes": 90,
                    }
                )
    return pd.DataFrame(rows)


def _decision_rows(
    season: str,
    *,
    points: float,
    challenger: bool,
    initial_hash: str = "champion-hash",
) -> pd.DataFrame:
    per_gameweek = points / 38
    return pd.DataFrame(
        [
            {
                "season": season,
                "gameweek": gameweek,
                "realistic_net_points": per_gameweek,
                "net_points": per_gameweek,
                "realistic_captain_id": 1,
                "realistic_vice_captain_id": 2,
                "realistic_captain_actual_points": 10.0,
                "realistic_vice_captain_actual_points": 2.0,
                "realistic_vice_captain_fallback": False,
                "starting_ids": "+".join(str(value) for value in range(1, 12)),
                "realistic_starting_ids": "+".join(
                    str(value) for value in range(1, 12)
                ),
                "transfers_made": int(challenger),
                "incoming": "Upgrade" if challenger else None,
                "outgoing": "Control" if challenger else None,
                "chip_used": "none",
                "hit_cost": 0,
                "initial_squad_hash": initial_hash,
            }
            for gameweek in range(1, 39)
        ]
    )


def _run(
    candidate_name: str,
    season: str,
    points: float,
    *,
    challenger: bool,
) -> CandidateSeasonRun:
    candidate = candidate_catalog()[candidate_name]
    rows = _decision_rows(season, points=points, challenger=challenger)
    return CandidateSeasonRun(
        candidate=candidate,
        season=season,
        rows=rows,
        realistic_points=points,
        hindsight_points=points,
        transfers=int(rows["transfers_made"].sum()),
        hit_cost=0,
        chips_used=0,
        initial_squad_hash="champion-hash",
    )


def test_catalog_changes_lineup_without_changing_other_production_consumers():
    catalog = candidate_catalog()
    champion = catalog[P4_CHAMPION]
    lineup = catalog["lineup_gradient"]

    assert lineup.portfolio.lineup_model != champion.portfolio.lineup_model
    assert lineup.portfolio.transfer_model == champion.portfolio.transfer_model
    assert lineup.portfolio.captain_model == champion.portfolio.captain_model
    assert lineup.portfolio.chip_model == champion.portfolio.chip_model


def test_full_gate_rejects_aggregate_gain_that_hides_a_severe_season_regression():
    runs = [
        *[_run(P4_CHAMPION, season, 2000, challenger=False) for season in SEASONS],
        _run("transfer_gradient", "2023-24", 2200, challenger=True),
        _run("transfer_gradient", "2024-25", 2200, challenger=True),
        _run("transfer_gradient", "2025-26", 1900, challenger=True),
    ]

    acceptance, _, _ = _evaluate_candidates(
        runs,
        _players(),
        stage="full",
        expected_seasons=SEASONS,
        skipped_chip_candidates=[],
    )

    row = acceptance.iloc[0]
    assert row["aggregate_delta"] == pytest.approx(300)
    assert not bool(row["passed"])
    assert "regression" in row["reasons"]


def test_screening_skips_chip_model_and_cannot_promote(monkeypatch, tmp_path: Path):
    catalog = candidate_catalog()
    dummy_squad = pd.DataFrame({"player_id": range(1, 16)})
    monkeypatch.setattr(
        "fpl_intelligence.consumer_model_tournament._opening_squads",
        lambda *_: {
            (season, policy): (dummy_squad, policy, "test")
            for season in SEASONS
            for policy in ("horizon_8_flexible_cold_start_safe", "identity_safe_value")
        },
    )

    def fake_benchmark(*args, **kwargs):
        season = args[1]
        candidate = kwargs["model_version"]
        challenger = candidate == catalog["transfer_gradient"].version
        points = 2001.0 if challenger else 2000.0
        rows = _decision_rows(season, points=points, challenger=challenger)
        return SimpleNamespace(
            rows=rows,
            realistic_total_points=points,
            total_points=points,
            transfers_made=int(rows["transfers_made"].sum()),
            total_hit_cost=0,
            chips_used=0,
        )

    monkeypatch.setattr(
        "fpl_intelligence.consumer_model_tournament.run_season_benchmark",
        fake_benchmark,
    )
    result = run_consumer_tournament(
        stage="screening",
        seasons=SEASONS,
        candidate_names=("transfer_gradient", "chip_ridge"),
        output_dir=tmp_path / "p4",
        players=_players(),
        generated_at="2026-08-06T00:00:00Z",
    )

    transfer = result.acceptance.set_index("candidate").loc["transfer_gradient"]
    chip = result.acceptance.set_index("candidate").loc["chip_ridge"]
    assert not bool(transfer["passed"])
    assert "Screening evidence cannot promote" in transfer["reasons"]
    assert chip["promotion_status"] == "not_applicable"
    assert set(result.summary["candidate"]) == {P4_CHAMPION, "transfer_gradient"}


def test_checkpoint_hash_tampering_fails_closed(tmp_path: Path):
    run = _run("transfer_gradient", "2023-24", 2100, challenger=True)
    paths = (tmp_path / "decisions.csv", tmp_path / "metadata.json")
    _write_checkpoint(paths, run=run, config_hash="config")
    metadata = json.loads(paths[1].read_text(encoding="utf-8"))
    paths[0].write_text(paths[0].read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        _load_checkpoint(
            paths,
            candidate=run.candidate,
            season=run.season,
            config_hash=metadata["config_hash"],
        )
