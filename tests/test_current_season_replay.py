from pathlib import Path

import pandas as pd

from fpl_intelligence.current_season_replay import (
    _deadline_source,
    _validated_finalized_gameweeks,
)
from fpl_intelligence.season_rules import payload_hash


def test_finalized_gameweeks_must_match_official_state():
    live = pd.DataFrame(
        {
            "gameweek": [1, 2],
            "official_finished": [True, True],
            "official_data_checked": [True, True],
        }
    )
    bootstrap = {
        "events": [
            {"id": 1, "finished": True, "data_checked": True},
            {"id": 2, "finished": True, "data_checked": True},
            {"id": 3, "finished": False, "data_checked": False},
        ]
    }

    assert _validated_finalized_gameweeks(live, bootstrap) == [1, 2]


def test_deadline_source_requires_matching_predeadline_snapshot(tmp_path: Path):
    bootstrap = {"events": [{"id": 1}], "elements": []}
    digest = payload_hash(bootstrap)
    timestamp = "20260818T061154.361356"
    bootstrap_path = tmp_path / f"bootstrap-{timestamp}-{digest[:16]}.json"
    bootstrap_path.write_text('{"elements": [], "events": [{"id": 1}]}', encoding="utf-8")
    bootstrap_path.with_name(
        bootstrap_path.name.replace(".json", ".metadata.json")
    ).write_text(
        '{"captured_at": "2026-08-18T06:11:54Z"}',
        encoding="utf-8",
    )
    fixture_path = tmp_path / f"fixtures-{timestamp}-abc.json"
    fixture_path.write_text("[]", encoding="utf-8")
    fixture_path.with_name(
        fixture_path.name.replace(".json", ".metadata.json")
    ).write_text('{"captured_at": "2026-08-18T06:11:54Z"}', encoding="utf-8")
    live = pd.DataFrame(
        {
            "gameweek": [1],
            "predeadline_bootstrap_hash": [digest],
            "deadline": ["2026-08-21T17:30:00Z"],
        }
    )

    source = _deadline_source(live, 1, tmp_path)

    assert source.bootstrap_path == str(bootstrap_path)
    assert source.fixture_path == str(fixture_path)
