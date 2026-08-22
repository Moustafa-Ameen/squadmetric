import json
from pathlib import Path

import pytest

from fpl_intelligence.launch_intelligence import (
    availability_probability,
    load_launch_evidence,
)


def test_launch_evidence_respects_season_and_observation_cutoff(tmp_path: Path):
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "season": "2026-27",
                        "player_name": "Example Player",
                        "team_name": "Hull City",
                        "inferred_start_probability": 0.8,
                        "confidence": 0.7,
                        "source_url": "https://example.test/source",
                        "published_at": "2026-07-20T10:00:00Z",
                        "observed_at": "2026-07-21T10:00:00Z",
                        "evidence_type": "official_test",
                        "notes": "Model inference from official evidence",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_launch_evidence(
        path, season="2026-27", cutoff="2026-07-20T12:00:00Z"
    ) == []
    visible = load_launch_evidence(
        path, season="2026-27", cutoff="2026-07-21T12:00:00Z"
    )
    assert len(visible) == 1
    assert visible[0].player_name == "Example Player"


def test_launch_evidence_rejects_duplicate_player_team_keys(tmp_path: Path):
    observation = {
        "season": "2026-27",
        "player_name": "Example Player",
        "team_name": "Hull City",
        "inferred_start_probability": 0.8,
        "confidence": 0.7,
        "source_url": "https://example.test/source",
        "published_at": "2026-07-20T10:00:00Z",
        "observed_at": "2026-07-21T10:00:00Z",
        "evidence_type": "official_test",
        "notes": "Model inference from official evidence",
    }
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps({"observations": [observation, observation]}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_launch_evidence(path)


def test_official_availability_probability_fails_safely():
    assert availability_probability("a", None) == 1.0
    assert availability_probability("d", 75) == 0.75
    assert availability_probability("i", 0) == 0.0
    assert availability_probability("s", None) == 0.0
