from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fpl_intelligence.live_model_training import train_live_models
from fpl_intelligence.post_gameweek_refresh import (
    build_finalized_gameweek_rows,
    finalized_gameweeks,
    merge_finalized_history,
    publish_transactionally,
    run_post_gameweek_refresh,
    select_predeadline_bootstrap_snapshot,
)
from fpl_intelligence.season_rules import (
    build_snapshot_metadata,
    save_immutable_snapshot,
)
from fpl_intelligence.step4_models import BASE_FEATURE_COLUMNS

SEASON = "2026-27"
DEADLINE = "2026-08-21T17:30:00Z"
CUTOFF = "2026-08-21T16:30:00Z"
FINALIZED_AT = "2026-08-24T12:00:00Z"


def _payloads(player_count: int = 400) -> tuple[dict, dict, list[dict], dict]:
    teams = [
        {
            "id": team_id,
            "name": f"Team {team_id}",
            "short_name": f"T{team_id:02d}",
            "strength_overall_home": 1000 + team_id,
            "strength_overall_away": 900 + team_id,
        }
        for team_id in range(1, 21)
    ]
    elements = [
        {
            "id": player_id,
            "first_name": "Player",
            "second_name": str(player_id),
            "team": ((player_id - 1) % 20) + 1,
            "element_type": ((player_id - 1) % 4) + 1,
            "now_cost": 45 + (player_id % 80),
            "selected_by_percent": str((player_id % 300) / 10),
        }
        for player_id in range(1, player_count + 1)
    ]
    final_bootstrap = {
        "events": [
            {
                "id": 1,
                "deadline_time": DEADLINE,
                "finished": True,
                "data_checked": True,
            }
        ],
        "teams": teams,
        "elements": elements,
    }
    predeadline_bootstrap = {
        **final_bootstrap,
        "events": [
            {
                "id": 1,
                "deadline_time": DEADLINE,
                "finished": False,
                "data_checked": False,
            }
        ],
    }
    fixtures = [
        {"id": index, "event": 1, "team_h": index, "team_a": index + 10}
        for index in range(1, 11)
    ]
    live = {
        "elements": [
            {
                "id": player["id"],
                "stats": {
                    "minutes": 90 if player["id"] % 5 else 0,
                    "total_points": player["id"] % 11,
                },
            }
            for player in elements
        ]
    }
    return final_bootstrap, predeadline_bootstrap, fixtures, live


def _metadata(bootstrap: dict, cutoff: str = CUTOFF) -> dict:
    return build_snapshot_metadata(
        bootstrap,
        season=SEASON,
        source_url="https://example.test/bootstrap",
        retrieved_at=cutoff,
        cutoff_at=cutoff,
    )


def _rows() -> pd.DataFrame:
    final, predeadline, fixtures, live = _payloads()
    return build_finalized_gameweek_rows(
        season=SEASON,
        gameweek=1,
        final_bootstrap=final,
        predeadline_bootstrap=predeadline,
        predeadline_metadata=_metadata(predeadline),
        fixtures=fixtures,
        live_payload=live,
        finalized_at=FINALIZED_AT,
    )


def _training_rows(season: str, count: int, *, finalized: bool = False) -> pd.DataFrame:
    rows = []
    for index in range(count):
        row = {
            "season": season,
            "gameweek": 1,
            "minutes": (0, 45, 90)[index % 3],
            "next_gameweek_points": float(index % 12),
            "price_before_deadline": 4.0 + (index % 80) / 10,
            "minutes_last_3": float((index % 4) * 90),
            "points_last_3": float(index % 30),
            "opponent_strength": float(900 + index % 200),
            "selected_by_percent_before_deadline": float(index % 50),
            "market_snapshot_available": 1,
            "position": ("GK", "DEF", "MID", "FWD")[index % 4],
            "home_or_away": ("H", "A")[index % 2],
        }
        if finalized:
            row.update(official_finished=True, official_data_checked=True)
        rows.append(row)
    return pd.DataFrame(rows)


def test_finalized_detector_excludes_every_provisional_state():
    bootstrap = {
        "events": [
            {"id": 1, "finished": True, "data_checked": True},
            {"id": 2, "finished": True, "data_checked": False},
            {"id": 3, "finished": False, "data_checked": True},
        ]
    }

    assert finalized_gameweeks(bootstrap) == (1,)


def test_predeadline_snapshot_uses_latest_safe_cutoff_and_checks_hash(tmp_path: Path):
    _, predeadline, _, _ = _payloads()
    earlier = _metadata(predeadline, "2026-08-21T15:00:00Z")
    latest = _metadata(predeadline, CUTOFF)
    save_immutable_snapshot(predeadline, earlier, root=tmp_path)
    expected, _ = save_immutable_snapshot(predeadline, latest, root=tmp_path)
    save_immutable_snapshot(
        predeadline,
        _metadata(predeadline, "2026-08-21T18:00:00Z"),
        root=tmp_path,
    )

    payload, metadata, path = select_predeadline_bootstrap_snapshot(
        season=SEASON,
        deadline=DEADLINE,
        snapshot_root=tmp_path,
    )

    assert payload == predeadline
    assert metadata["cutoff_at"] == CUTOFF
    assert path == expected

    path.write_text(json.dumps({"tampered": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="hash does not match"):
        select_predeadline_bootstrap_snapshot(
            season=SEASON,
            deadline=DEADLINE,
            snapshot_root=tmp_path,
        )


def test_rows_use_deadline_features_and_prior_finalized_gameweeks_only():
    final, predeadline, fixtures, live = _payloads()
    prior = pd.DataFrame(
        [
            {
                "season": SEASON,
                "player_id": 1,
                "gameweek": gameweek,
                "minutes": minutes,
                "next_gameweek_points": points,
            }
            for gameweek, minutes, points in ((1, 90, 5), (2, 80, 7), (3, 70, 9))
        ]
    )
    final["events"][0]["id"] = 4
    final["events"][0]["deadline_time"] = "2026-09-12T17:30:00Z"
    for fixture in fixtures:
        fixture["event"] = 4
    metadata = _metadata(predeadline, "2026-09-12T16:30:00Z")

    rows = build_finalized_gameweek_rows(
        season=SEASON,
        gameweek=4,
        final_bootstrap=final,
        predeadline_bootstrap=predeadline,
        predeadline_metadata=metadata,
        fixtures=fixtures,
        live_payload=live,
        prior_live_history=prior,
        finalized_at=FINALIZED_AT,
    ).set_index("player_id")

    assert rows.loc[1, "price_before_deadline"] == predeadline["elements"][0]["now_cost"] / 10
    assert rows.loc[1, "minutes_last_3"] == 240
    assert rows.loc[1, "points_last_3"] == 21
    assert rows.loc[1, "feature_cutoff_gameweek"] == 3
    assert rows.loc[1, "data_cutoff"] < rows.loc[1, "deadline"]


def test_merge_is_idempotent_and_rejects_conflicting_or_skipped_gameweeks():
    first = _rows()
    merged, changed = merge_finalized_history(None, first)
    repeated, repeated_changed = merge_finalized_history(merged, first)

    assert changed is True
    assert repeated_changed is False
    pd.testing.assert_frame_equal(repeated, merged)

    conflict = first.copy()
    conflict["official_live_payload_hash"] = "different"
    with pytest.raises(ValueError, match="conflicts"):
        merge_finalized_history(merged, conflict)

    skipped = first.copy()
    skipped["gameweek"] = 3
    skipped["feature_cutoff_gameweek"] = 2
    with pytest.raises(ValueError, match="contiguous"):
        merge_finalized_history(merged, skipped)


def test_live_model_fit_accepts_only_strictly_finalized_current_rows(tmp_path: Path):
    history = _training_rows("2025-26", 60)
    current = _training_rows(SEASON, 12, finalized=True)

    metadata = train_live_models(
        history,
        target_season=SEASON,
        output_dir=tmp_path,
        generated_at=FINALIZED_AT,
        finalized_current_season=current,
        finalized_current_season_file_hash="known-hash",
    )

    assert metadata.finalized_current_season_gameweeks == [1]
    assert metadata.finalized_current_season_rows == 12
    assert metadata.finalized_current_season_hash == "known-hash"
    assert SEASON in metadata.training_seasons
    assert set(BASE_FEATURE_COLUMNS) == set(metadata.feature_columns)

    current.loc[0, "official_data_checked"] = False
    with pytest.raises(ValueError, match="official_data_checked=true"):
        train_live_models(
            history,
            target_season=SEASON,
            output_dir=tmp_path / "rejected",
            finalized_current_season=current,
        )


def test_transactional_publish_restores_every_file_after_finalize_failure(tmp_path: Path):
    source = tmp_path / "staged.txt"
    new_source = tmp_path / "new-staged.txt"
    destination = tmp_path / "live.txt"
    created_destination = tmp_path / "new.txt"
    source.write_text("replacement", encoding="utf-8")
    new_source.write_text("new", encoding="utf-8")
    destination.write_text("original", encoding="utf-8")

    with pytest.raises(RuntimeError, match="readiness failed"):
        publish_transactionally(
            {source: destination, new_source: created_destination},
            protected_paths=(destination, created_destination),
            finalize=lambda: (_ for _ in ()).throw(RuntimeError("readiness failed")),
        )

    assert destination.read_text(encoding="utf-8") == "original"
    assert not created_destination.exists()


def test_transactional_publish_commits_all_files_after_success(tmp_path: Path):
    first_source = tmp_path / "first-staged.txt"
    second_source = tmp_path / "second-staged.txt"
    first_destination = tmp_path / "first-live.txt"
    second_destination = tmp_path / "second-live.txt"
    first_source.write_text("first-new", encoding="utf-8")
    second_source.write_text("second-new", encoding="utf-8")
    first_destination.write_text("first-old", encoding="utf-8")

    result = publish_transactionally(
        {
            first_source: first_destination,
            second_source: second_destination,
        },
        protected_paths=(first_destination, second_destination),
        finalize=lambda: {"status": "ready"},
    )

    assert result == {"status": "ready"}
    assert first_destination.read_text(encoding="utf-8") == "first-new"
    assert second_destination.read_text(encoding="utf-8") == "second-new"


def test_dry_run_builds_new_rows_without_writing_history_snapshots_or_outcomes(
    tmp_path: Path,
):
    final, predeadline, fixtures, live = _payloads()
    snapshot_root = tmp_path / "snapshots"
    save_immutable_snapshot(
        predeadline,
        _metadata(predeadline),
        root=snapshot_root,
    )
    live_history = tmp_path / "live.csv"
    evidence_root = tmp_path / "evidence"

    report = run_post_gameweek_refresh(
        season=SEASON,
        bootstrap=final,
        fixtures=fixtures,
        live_payloads={1: live},
        generated_at=FINALIZED_AT,
        snapshot_root=snapshot_root,
        live_history_path=live_history,
        evidence_root=evidence_root,
        publish=False,
    )

    assert report["status"] == "validated_not_published"
    assert report["live_history_rows"] == 400
    assert not live_history.exists()
    assert not evidence_root.exists()
    assert not list((snapshot_root / SEASON).glob("event-*-live-*.json"))
    assert "report_path" not in report


def test_no_new_gameweek_refreshes_sources_without_retraining(tmp_path: Path):
    final, _, fixtures, _ = _payloads()
    final["events"][0]["finished"] = False
    final["events"][0]["data_checked"] = False
    calls: list[dict] = []

    def serving_refresh(**kwargs):
        calls.append(kwargs)
        return {"status": "ready"}

    report = run_post_gameweek_refresh(
        season=SEASON,
        bootstrap=final,
        fixtures=fixtures,
        generated_at=FINALIZED_AT,
        live_history_path=tmp_path / "missing.csv",
        snapshot_root=tmp_path / "snapshots",
        run_root=tmp_path / "runs",
        evidence_root=tmp_path / "evidence",
        publish=True,
        serving_refresh=serving_refresh,
    )

    assert report["status"] == "no_new_finalized_gameweek"
    assert calls[0]["train_models"] is False
