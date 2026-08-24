import asyncio
from time import monotonic

from api import fpl_client


def test_bootstrap_cache_refreshes_after_artifact_manifest_changes(monkeypatch):
    fresh_payload = {"elements": [{"id": 2}]}
    fpl_client._BOOTSTRAP_CACHE = (monotonic(), 1, {"elements": [{"id": 1}]})

    async def fresh_get(path: str):
        assert path == "bootstrap-static/"
        return fresh_payload

    monkeypatch.setattr(fpl_client, "_artifact_manifest_mtime_ns", lambda: 2)
    monkeypatch.setattr(fpl_client, "_get", fresh_get)

    assert asyncio.run(fpl_client.get_bootstrap()) == fresh_payload


def test_fixture_cache_refreshes_after_artifact_manifest_changes(monkeypatch):
    fresh_payload = [{"id": 2, "event": 1}]
    fpl_client._FIXTURES_CACHE = (monotonic(), 1, [{"id": 1, "event": 1}])

    async def fresh_get(path: str):
        assert path == "fixtures/"
        return fresh_payload

    monkeypatch.setattr(fpl_client, "_artifact_manifest_mtime_ns", lambda: 2)
    monkeypatch.setattr(fpl_client, "_get", fresh_get)

    assert asyncio.run(fpl_client.get_fixtures()) == fresh_payload
