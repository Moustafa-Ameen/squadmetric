"""Current-season artifact manifest and fail-closed readiness validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from fpl_intelligence.availability import AvailabilityEvent
from fpl_intelligence.launch_intelligence import (
    DEFAULT_LAUNCH_EVIDENCE_PATH,
    load_launch_evidence,
)
from fpl_intelligence.live_model_training import (
    LIVE_MINUTES_BAND_MODEL_PATH,
    LIVE_MODEL_METADATA_PATH,
)
from fpl_intelligence.season_rules import (
    PROMOTED_TEAMS_BY_SEASON,
    RELEGATED_TEAMS_BY_SEASON,
    SeasonRules,
    infer_season_from_bootstrap,
    payload_hash,
    rules_contract_hash,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CURRENT_ARTIFACT_MANIFEST_PATH = PROCESSED_DIR / "current_artifact_manifest.json"
ARTIFACT_SCHEMA_VERSION = "current-artifacts-v2-launch-intelligence"
LIVE_CURRENT_HISTORY_PATH = PROCESSED_DIR / "live_2026_27_player_gw.csv"


@dataclass(frozen=True)
class CurrentArtifactManifest:
    schema_version: str
    season: str
    generated_at: str
    data_cutoff: str
    bootstrap_path: str
    bootstrap_hash: str
    fixtures_path: str
    fixtures_hash: str
    players_current_path: str
    players_current_hash: str
    players_ranked_path: str
    players_ranked_hash: str
    player_count: int
    team_count: int
    rules_version: str
    rules_payload_hash: str
    rules_contract_hash: str
    rules_manifest_path: str
    model_metadata_path: str
    model_metadata_hash: str
    launch_evidence_path: str
    launch_evidence_hash: str
    availability_events_path: str
    availability_events_hash: str
    live_history_path: str | None = None
    live_history_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactReadiness:
    status: str
    season: str
    errors: list[str]
    warnings: list[str]
    manifest: dict[str, Any] | None
    models_checked: bool

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "season": self.season,
            "errors": self.errors,
            "warnings": self.warnings,
            "manifest": self.manifest,
            "models_checked": self.models_checked,
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_current_artifact_manifest(
    *,
    bootstrap: dict[str, Any],
    fixtures_path: Path,
    players_current_path: Path,
    players_ranked_path: Path,
    rules: SeasonRules,
    rules_manifest_path: Path,
    model_metadata_path: Path = LIVE_MODEL_METADATA_PATH,
    launch_evidence_path: Path = DEFAULT_LAUNCH_EVIDENCE_PATH,
    availability_events_path: Path = PROCESSED_DIR / "current_availability_events.json",
    generated_at: str | None = None,
) -> CurrentArtifactManifest:
    season = infer_season_from_bootstrap(bootstrap)
    if season == "unknown":
        raise ValueError("Cannot build an artifact manifest without bootstrap deadlines")
    players = pd.read_csv(players_current_path)
    teams = bootstrap.get("teams") or []
    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return CurrentArtifactManifest(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        season=season,
        generated_at=timestamp,
        data_cutoff=timestamp,
        bootstrap_path=str(RAW_DIR / "bootstrap-static.json"),
        bootstrap_hash=payload_hash(bootstrap),
        fixtures_path=str(fixtures_path),
        fixtures_hash=file_sha256(fixtures_path),
        players_current_path=str(players_current_path),
        players_current_hash=file_sha256(players_current_path),
        players_ranked_path=str(players_ranked_path),
        players_ranked_hash=file_sha256(players_ranked_path),
        player_count=len(players),
        team_count=len(teams),
        rules_version=rules.rules_version,
        rules_payload_hash=rules.payload_hash,
        rules_contract_hash=rules_contract_hash(rules),
        rules_manifest_path=str(rules_manifest_path),
        model_metadata_path=str(model_metadata_path),
        model_metadata_hash=file_sha256(model_metadata_path),
        launch_evidence_path=str(launch_evidence_path),
        launch_evidence_hash=file_sha256(launch_evidence_path),
        availability_events_path=str(availability_events_path),
        availability_events_hash=file_sha256(availability_events_path),
        live_history_path=(
            str(LIVE_CURRENT_HISTORY_PATH)
            if LIVE_CURRENT_HISTORY_PATH.exists()
            else None
        ),
        live_history_hash=(
            file_sha256(LIVE_CURRENT_HISTORY_PATH)
            if LIVE_CURRENT_HISTORY_PATH.exists()
            else None
        ),
    )


def save_current_artifact_manifest(
    manifest: CurrentArtifactManifest,
    path: Path = CURRENT_ARTIFACT_MANIFEST_PATH,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_current_artifact_manifest(
    path: Path = CURRENT_ARTIFACT_MANIFEST_PATH,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_current_artifacts(
    *,
    expected_season: str | None = None,
    manifest_path: Path = CURRENT_ARTIFACT_MANIFEST_PATH,
    check_models: bool = False,
) -> ArtifactReadiness:
    """Validate season/hash/ID/rules/model agreement and fail closed."""

    errors: list[str] = []
    warnings: list[str] = []
    manifest = load_current_artifact_manifest(manifest_path)
    if manifest is None:
        return ArtifactReadiness(
            status="blocked",
            season=expected_season or "unknown",
            errors=[f"Current artifact manifest is missing: {manifest_path}"],
            warnings=[],
            manifest=None,
            models_checked=check_models,
        )

    season = str(manifest.get("season") or "unknown")
    if expected_season and season != expected_season:
        errors.append(f"artifact season {season} does not match live season {expected_season}")

    path_fields = (
        "bootstrap_path",
        "fixtures_path",
        "players_current_path",
        "players_ranked_path",
        "rules_manifest_path",
        "model_metadata_path",
        "launch_evidence_path",
        "availability_events_path",
    )
    paths: dict[str, Path] = {}
    for field in path_fields:
        raw_path = str(manifest.get(field, "")).strip()
        path = Path(raw_path) if raw_path else Path("__missing_artifact_path__")
        paths[field] = path
        if not raw_path or not path.is_file():
            errors.append(f"{field} is missing: {path}")
    if errors:
        return ArtifactReadiness(
            "blocked", season, errors, warnings, manifest, check_models
        )

    bootstrap = json.loads(paths["bootstrap_path"].read_text(encoding="utf-8"))
    bootstrap_season = infer_season_from_bootstrap(bootstrap)
    if bootstrap_season != season:
        errors.append(
            f"bootstrap season {bootstrap_season} does not match manifest season {season}"
        )
    if payload_hash(bootstrap) != manifest.get("bootstrap_hash"):
        errors.append("bootstrap payload hash does not match manifest")

    for path_field, hash_field in (
        ("fixtures_path", "fixtures_hash"),
        ("players_current_path", "players_current_hash"),
        ("players_ranked_path", "players_ranked_hash"),
        ("model_metadata_path", "model_metadata_hash"),
        ("launch_evidence_path", "launch_evidence_hash"),
        ("availability_events_path", "availability_events_hash"),
    ):
        if file_sha256(paths[path_field]) != manifest.get(hash_field):
            errors.append(f"{path_field} hash does not match manifest")

    current = pd.read_csv(paths["players_current_path"])
    ranked = pd.read_csv(paths["players_ranked_path"])
    for label, frame in (("players_current", current), ("players_ranked", ranked)):
        if "element_id" not in frame:
            errors.append(f"{label} is missing stable element_id")
            continue
        ids = pd.to_numeric(frame["element_id"], errors="coerce")
        if ids.isna().any() or ids.duplicated().any():
            errors.append(f"{label} contains missing or duplicate element IDs")
    bootstrap_ids = {
        int(player["id"])
        for player in bootstrap.get("elements", [])
        if player.get("id") is not None
    }
    current_ids = (
        set(pd.to_numeric(current["element_id"], errors="coerce").dropna().astype(int))
        if "element_id" in current
        else set()
    )
    ranked_ids = (
        set(pd.to_numeric(ranked["element_id"], errors="coerce").dropna().astype(int))
        if "element_id" in ranked
        else set()
    )
    if current_ids != bootstrap_ids:
        errors.append("players_current element IDs do not match bootstrap")
    if ranked_ids != bootstrap_ids:
        errors.append("players_ranked element IDs do not match bootstrap")
    if len(current) != int(manifest.get("player_count", -1)):
        errors.append("players_current row count does not match manifest")
    ambiguous_prior_columns = [
        column for column in current.columns if column.endswith(("_x", "_y"))
    ]
    if ambiguous_prior_columns:
        errors.append(
            "players_current contains ambiguous merge columns: "
            + ", ".join(sorted(ambiguous_prior_columns))
        )
    for required_prior in (
        "preseason_minutes_prior",
        "availability_probability",
        "prior_source",
    ):
        if required_prior not in current:
            errors.append(f"players_current is missing launch field {required_prior}")

    try:
        launch_evidence = load_launch_evidence(
            paths["launch_evidence_path"], season=season, cutoff=manifest["data_cutoff"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"launch evidence contract is invalid: {exc}")
        launch_evidence = []
    evidence_names = {item.player_name for item in launch_evidence}
    current_names = set(current.get("player_name", pd.Series(dtype=str)).dropna().astype(str))
    missing_evidence_players = sorted(evidence_names.difference(current_names))
    if missing_evidence_players:
        warnings.append(
            "launch evidence players are not in the current bootstrap: "
            + ", ".join(missing_evidence_players)
        )

    try:
        availability_payload = json.loads(
            paths["availability_events_path"].read_text(encoding="utf-8")
        )
        availability_events = [
            AvailabilityEvent.from_mapping(value)
            for value in availability_payload.get("events", [])
        ]
        unknown_event_ids = sorted(
            {event.player_id for event in availability_events}.difference(bootstrap_ids)
        )
        if unknown_event_ids:
            errors.append("availability events contain unknown player IDs")
        if availability_payload.get("season") != season:
            errors.append("availability-event season does not match manifest")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"availability-event contract is invalid: {exc}")

    teams = {
        str(team.get("name"))
        for team in bootstrap.get("teams", [])
        if team.get("name")
    }
    if len(teams) != int(manifest.get("team_count", -1)) or len(teams) != 20:
        errors.append(f"current bootstrap must contain 20 unique teams, found {len(teams)}")
    for promoted in PROMOTED_TEAMS_BY_SEASON.get(season, ()):
        if promoted not in teams:
            errors.append(f"promoted team missing from current artifacts: {promoted}")
    for relegated in RELEGATED_TEAMS_BY_SEASON.get(season, ()):
        if relegated in teams:
            errors.append(f"relegated team present in current artifacts: {relegated}")

    rules = json.loads(paths["rules_manifest_path"].read_text(encoding="utf-8"))
    if rules.get("season") != season:
        errors.append("rules season does not match current artifact season")
    if rules.get("rules_version") != manifest.get("rules_version"):
        errors.append("rules version does not match current artifact manifest")
    if rules.get("payload_hash") != manifest.get("rules_payload_hash"):
        errors.append("rules payload hash does not match current artifact manifest")
    rules_object = SeasonRules(**rules)
    if rules_contract_hash(rules_object) != manifest.get("rules_contract_hash"):
        errors.append("rules contract hash does not match current artifact manifest")
    chip_names = [str(chip.get("name", "")).lower() for chip in rules.get("chips", [])]
    if season == "2026-27":
        if len(chip_names) != 8:
            errors.append(f"2026-27 requires eight chip slots, found {len(chip_names)}")
        if "assistant_manager" in chip_names:
            errors.append("Assistant Manager must not be active in 2026-27")
        if rules.get("chip_reset_gameweek") != 19:
            errors.append("2026-27 chip reset must occur after the GW19 deadline")
        if rules.get("bps_rule_version") != "bps_v2_2026_27":
            errors.append("2026-27 BPS regime is not active")

    model_metadata = json.loads(
        paths["model_metadata_path"].read_text(encoding="utf-8")
    )
    if model_metadata.get("target_season") != season:
        errors.append("live-model target season does not match artifact season")
    target_in_training = season in set(model_metadata.get("training_seasons", []))
    finalized_rows = int(model_metadata.get("finalized_current_season_rows") or 0)
    finalized_gameweeks = [
        int(value)
        for value in model_metadata.get("finalized_current_season_gameweeks", [])
    ]
    if target_in_training:
        if finalized_rows <= 0 or not finalized_gameweeks:
            errors.append(
                "live-model target-season training lacks finalized Gameweek evidence"
            )
        if finalized_gameweeks and finalized_gameweeks != list(
            range(1, max(finalized_gameweeks) + 1)
        ):
            errors.append("live-model finalized Gameweeks are not contiguous from GW1")
        live_history_path = str(manifest.get("live_history_path") or "").strip()
        if not live_history_path:
            errors.append("artifact manifest is missing finalized live-history path")
        else:
            live_path = Path(live_history_path)
            if not live_path.is_file():
                errors.append(f"finalized live history is missing: {live_path}")
            elif file_sha256(live_path) != manifest.get("live_history_hash"):
                errors.append("finalized live-history hash does not match manifest")
            else:
                live_history = pd.read_csv(live_path)
                if len(live_history) != finalized_rows:
                    errors.append(
                        "finalized live-history row count does not match model metadata"
                    )
                required_flags = {"official_finished", "official_data_checked"}
                if not required_flags.issubset(live_history.columns):
                    errors.append("finalized live history is missing official status flags")
                elif not all(
                    _strict_true(live_history[flag]).all()
                    for flag in required_flags
                ):
                    errors.append("finalized live history contains provisional rows")
                if file_sha256(live_path) != model_metadata.get(
                    "finalized_current_season_hash"
                ):
                    errors.append(
                        "finalized live-history content hash does not match model metadata"
                    )
    for key, artifact in model_metadata.get("artifacts", {}).items():
        artifact_path = paths["model_metadata_path"].parent / str(artifact.get("path"))
        if not artifact_path.exists():
            errors.append(f"model artifact {key} is missing: {artifact_path}")
        elif file_sha256(artifact_path) != artifact.get("sha256"):
            errors.append(f"model artifact {key} hash does not match metadata")

    if check_models and not errors:
        try:
            for artifact in model_metadata.get("artifacts", {}).values():
                joblib.load(
                    paths["model_metadata_path"].parent / str(artifact.get("path"))
                )
        except Exception as exc:  # readiness must turn any deserialization issue into a block
            errors.append(f"production model load failed: {type(exc).__name__}: {exc}")
        if LIVE_MINUTES_BAND_MODEL_PATH.exists():
            model = joblib.load(LIVE_MINUTES_BAND_MODEL_PATH)
            if model.__class__.__module__ == "__main__":
                errors.append("minutes model was serialized from __main__")

    return ArtifactReadiness(
        status="ready" if not errors else "blocked",
        season=season,
        errors=errors,
        warnings=warnings,
        manifest=manifest,
        models_checked=check_models,
    )


def _strict_true(values: pd.Series) -> pd.Series:
    """Interpret only explicit boolean/1/true values as true."""

    return values.astype("string").str.strip().str.lower().isin({"true", "1"})
