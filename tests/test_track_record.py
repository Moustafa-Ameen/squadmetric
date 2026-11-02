import asyncio
import json

from api.main import app
from api.routers import operations as operations_router
from httpx import ASGITransport, AsyncClient

from fpl_intelligence.beam_search import DeterministicBeamPlanner
from fpl_intelligence.track_record import build_track_record, write_track_record

CURRENT = DeterministicBeamPlanner.version
BOOTSTRAP = {
    "elements": [{"id": 411, "web_name": "Haaland"}],
    "events": [
        {"id": gw, "finished": True, "data_checked": True} for gw in range(1, 5)
    ],
}


def _transfer(out_id, in_id):
    return {
        "outgoing_id": out_id,
        "outgoing_name": f"Out {out_id}",
        "incoming_id": in_id,
        "incoming_name": f"In {in_id}",
    }


def _write_gameweek(root, gameweek, branches, selected_id, realized, engine=CURRENT):
    gw_root = root / "2026-27" / f"GW{gameweek:02d}"
    (gw_root / "snapshots").mkdir(parents=True)
    (gw_root / "outcomes").mkdir(parents=True)
    snapshot = {
        "snapshot_hash": f"snap-{gameweek}",
        "deadline": "2026-09-01T17:30:00Z",
        "captured_at": "2026-09-01T10:00:00Z",
        "context": {"decision_engine_version": engine},
        "branches": branches,
    }
    selected_points = realized[selected_id]
    outcome = {
        "status": "finalized",
        "gameweek": gameweek,
        "snapshot_hash": f"snap-{gameweek}",
        "selected_branch_id": selected_id,
        "selected_net_points": selected_points,
        "best_frozen_branch_points": max(realized.values()),
        "selected_regret": max(realized.values()) - selected_points,
        "branches": [{"branch_id": k, "net_points": v} for k, v in realized.items()],
    }
    (gw_root / "snapshots" / "a.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (gw_root / "outcomes" / "a.json").write_text(json.dumps(outcome), encoding="utf-8")


def test_track_record_scores_against_no_action_and_splits_out_chips(tmp_path):
    _write_gameweek(
        tmp_path,
        2,
        [
            {"branch_id": "tc", "transfers": [_transfer(1, 2)], "chip": "3xc", "captain_id": 411},
            {"branch_id": "move", "transfers": [_transfer(1, 2)], "chip": None, "captain_id": 411},
            {"branch_id": "hold", "transfers": [], "chip": None, "captain_id": 411},
        ],
        "tc",
        {"tc": 70.0, "move": 58.0, "hold": 55.0},
    )
    _write_gameweek(
        tmp_path,
        3,
        [
            {"branch_id": "move", "transfers": [_transfer(3, 4)], "chip": None, "captain_id": 411},
            {"branch_id": "hold", "transfers": [], "chip": None, "captain_id": 411},
        ],
        "move",
        {"move": 40.0, "hold": 44.0},
    )

    record = build_track_record(evidence_root=tmp_path, bootstrap=BOOTSTRAP)

    first, second = record["gameweeks"]
    assert first["gain_vs_no_action"] == 15.0
    assert first["chip_gain"] == 12.0
    assert first["recommendation"]["chip"] == "Triple Captain"
    assert first["recommendation"]["captain"] == "Haaland"
    assert first["recommendation"]["transfers"] == [{"out": "Out 1", "in": "In 2"}]
    assert second["gain_vs_no_action"] == -4.0
    assert second["chip_gain"] is None
    assert record["unscored_gameweeks"] == [4]
    assert record["totals"] == {
        "scored": 2,
        "earlier_version_scored": 0,
        "total_gain_vs_no_action": 11.0,
        "total_gain_from_chips": 12.0,
        "average_gain_vs_no_action": 5.5,
        "weeks_ahead": 1,
        "weeks_level": 0,
        "weeks_behind": 1,
    }
    assert "team_id" not in json.dumps(record)


def test_totals_count_only_the_current_engine(tmp_path):
    _write_gameweek(
        tmp_path,
        2,
        [
            {"branch_id": "tc", "transfers": [], "chip": "3xc", "captain_id": 411},
            {"branch_id": "hold", "transfers": [], "chip": None, "captain_id": 411},
        ],
        "tc",
        {"tc": 70.0, "hold": 55.0},
        engine="old-engine",
    )
    _write_gameweek(
        tmp_path,
        3,
        [{"branch_id": "hold", "transfers": [], "chip": None, "captain_id": 411}],
        "hold",
        {"hold": 44.0},
    )

    record = build_track_record(evidence_root=tmp_path, bootstrap=BOOTSTRAP)

    earlier, current = record["gameweeks"]
    assert earlier["current_version"] is False
    assert earlier["chips_considered"] is True
    assert earlier["gain_vs_no_action"] == 15.0
    assert current["current_version"] is True
    assert current["chips_considered"] is False
    assert record["totals"]["scored"] == 1
    assert record["totals"]["earlier_version_scored"] == 1
    assert record["totals"]["total_gain_vs_no_action"] == 0.0
    assert record["totals"]["total_gain_from_chips"] == 0.0


def test_write_track_record_is_stable_when_nothing_changed(tmp_path):
    path = tmp_path / "record.json"
    write_track_record(path, evidence_root=tmp_path, bootstrap=BOOTSTRAP, generated_at="a")
    before = path.read_bytes()
    write_track_record(path, evidence_root=tmp_path, bootstrap=BOOTSTRAP, generated_at="b")
    assert path.read_bytes() == before


def test_track_record_endpoint_serves_the_file(tmp_path, monkeypatch):
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"totals": {"scored": 3}}), encoding="utf-8")
    monkeypatch.setattr(operations_router, "TRACK_RECORD_PATH", path)

    async def get():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/operations/track-record")

    response = asyncio.run(get())
    assert response.status_code == 200
    assert response.json()["totals"]["scored"] == 3
