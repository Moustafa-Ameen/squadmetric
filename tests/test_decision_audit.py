from types import SimpleNamespace

import pandas as pd

from fpl_intelligence.decision_audit import (
    ChampionChallengerGate,
    build_champion_challenger_report,
    build_decision_audit,
    build_prediction_audit,
    summarise_prediction_audit,
)


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": "2024-25",
                "gameweek": 1,
                "player_id": 1,
                "next_gameweek_points": 10,
                "minutes": 90,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
            },
            {
                "season": "2024-25",
                "gameweek": 1,
                "player_id": 2,
                "next_gameweek_points": 2,
                "minutes": 90,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
            },
            {
                "season": "2024-25",
                "gameweek": 1,
                "player_id": 3,
                "next_gameweek_points": 0,
                "minutes": 0,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
            },
            {
                "season": "2024-25",
                "gameweek": 1,
                "player_id": 4,
                "next_gameweek_points": 5,
                "minutes": 90,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
            },
            {
                "season": "2024-25",
                "gameweek": 1,
                "player_id": 5,
                "next_gameweek_points": 4,
                "minutes": 90,
                "team": "A",
                "opponent_team": "B",
                "home_or_away": "H",
            },
        ]
    )


def _result(realistic: float, captain_id: int) -> SimpleNamespace:
    rows = pd.DataFrame(
        [
            {
                "season": "2024-25",
                "gameweek": 1,
                "realistic_net_points": realistic,
                "net_points": realistic + 5,
                "realistic_captain_id": captain_id,
                "realistic_vice_captain_id": 4,
                "realistic_captain_actual_points": 10 if captain_id == 1 else 0,
                "realistic_vice_captain_actual_points": 5,
                "realistic_vice_captain_fallback": False,
                "starting_ids": "1+2+4+5",
                "transfers_made": 1,
                "incoming": "New" if realistic > 50 else None,
                "outgoing": "Old" if realistic > 50 else None,
                "chip_used": "none",
            }
        ]
    )
    return SimpleNamespace(rows=rows)


def test_prediction_audit_reports_return_bands_and_top_k_quality():
    predictions = pd.DataFrame(
        {
            "player_id": [1, 2, 3, 4, 5],
            "position": ["MID", "DEF", "FWD", "GK", "MID"],
            "expected_points_adjusted": [9.0, 3.0, 2.0, 4.0, 1.0],
        }
    )
    audit = build_prediction_audit(predictions, _players())
    summary = summarise_prediction_audit(audit, top_k=2)

    assert set(audit["return_band"]) == {"zeros", "blanks", "tickers", "haulers"}
    overall = summary.loc[summary["segment"] == "all"].iloc[0]
    assert overall["row_count"] == 5
    assert overall["top_k_precision"] == 1.0
    assert overall["top_k_recall"] == 1.0


def test_decision_audit_calculates_captain_regret_and_regime():
    result = _result(50, captain_id=2)
    audit = build_decision_audit(result, _players())

    row = audit.iloc[0]
    assert row["regime"] == "blank"
    assert row["captain_effective_actual_points"] == 2
    assert row["best_legal_captain_points"] == 10
    assert row["captain_regret"] == 8
    assert not row["captain_top_two"]


def test_champion_challenger_gate_rejects_severe_season_regression():
    champion = [_result(100, captain_id=1)]
    challenger = [_result(20, captain_id=2)]
    report = build_champion_challenger_report(
        champion,
        challenger,
        _players(),
        gate=ChampionChallengerGate(maximum_season_regression_points=20),
    )

    assert not report.passed
    assert report.season_summary.iloc[0]["realistic_delta"] == -80
    assert any("regression" in reason for reason in report.rejection_reasons)


def test_champion_challenger_gate_requires_two_improved_seasons():
    champion = [_result(100, captain_id=1)]
    challenger = [_result(101, captain_id=1)]
    report = build_champion_challenger_report(champion, challenger, _players())

    assert not report.passed
    assert any("validation seasons improved" in reason for reason in report.rejection_reasons)


def test_report_exposes_transfer_chip_changes_and_blank_double_regime():
    champion = _result(50, captain_id=1)
    challenger = _result(50, captain_id=2)
    challenger.rows.loc[0, "incoming"] = "New Player"
    challenger.rows.loc[0, "outgoing"] = "Old Player"
    challenger.rows.loc[0, "chip_used"] = "wildcard"
    players = _players().copy()
    players.loc[0, "home_or_away"] = "M"
    players.loc[0, "opponent_team"] = "B+C"

    report = build_champion_challenger_report([champion], [challenger], players)

    row = report.per_gameweek.iloc[0]
    assert row["transfer_changed"]
    assert row["chip_changed"]
    assert row["is_blank"] == 1
    assert row["is_double"] == 1
    assert row["regime"] == "blank_double"
