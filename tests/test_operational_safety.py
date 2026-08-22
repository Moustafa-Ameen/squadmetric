from __future__ import annotations

import asyncio
import json

import pandas as pd
import pytest
from api import data_service, fpl_client, readiness
from fastapi import HTTPException

from fpl_intelligence.artifact_contract import ArtifactReadiness


def test_to_records_converts_float_nan_to_json_safe_none():
    records = data_service.to_records(
        pd.DataFrame([{"player": "A", "projection": float("nan")}])
    )

    assert records == [{"player": "A", "projection": None}]
    assert json.dumps(records, allow_nan=False)


def test_fpl_client_invalid_json_is_reported_as_temporary_unavailability(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("invalid JSON")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _path):
            return FakeResponse()

    monkeypatch.setattr(fpl_client.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(HTTPException) as error:
        asyncio.run(fpl_client._get("bootstrap-static/"))

    assert error.value.status_code == 503
    assert error.value.detail == {
        "code": "fpl_api_unavailable",
        "message": fpl_client.UNAVAILABLE_MESSAGE,
    }


def test_readiness_cache_invalidates_when_a_model_artifact_changes(
    monkeypatch,
    tmp_path,
):
    model = tmp_path / "model.joblib"
    model.write_bytes(b"first")
    metadata = tmp_path / "models.json"
    metadata.write_text(
        json.dumps({"artifacts": {"points": {"path": model.name}}}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"model_metadata_path": str(metadata)}),
        encoding="utf-8",
    )
    calls = []

    def validate(**_kwargs):
        calls.append(True)
        return ArtifactReadiness("ready", "2026-27", [], [], {}, True)

    monkeypatch.setattr(readiness, "CURRENT_ARTIFACT_MANIFEST_PATH", manifest)
    monkeypatch.setattr(readiness, "validate_current_artifacts", validate)
    readiness._cached_readiness.cache_clear()

    readiness.artifact_readiness("2026-27", check_models=True)
    readiness.artifact_readiness("2026-27", check_models=True)
    assert len(calls) == 1

    model.write_bytes(b"second-version")
    readiness.artifact_readiness("2026-27", check_models=True)
    assert len(calls) == 2
