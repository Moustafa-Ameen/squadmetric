"""Train immutable live-serving models after historical validation is complete."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd

from fpl_intelligence.season_rules import canonical_json
from fpl_intelligence.step4_models import (
    BASE_FEATURE_COLUMNS,
    build_minutes_classifier,
    build_ridge_model,
    fit_minutes_band_conditional_model,
    load_historical_player_gameweeks,
)
from fpl_intelligence.step5_model_comparison import build_gradient_boosting_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"
LIVE_MODEL_METADATA_PATH = MODELS_DIR / "live_2026_27_models.json"
LIVE_RIDGE_MODEL_PATH = MODELS_DIR / "live_2026_27_ridge_points.joblib"
LIVE_GRADIENT_MODEL_PATH = MODELS_DIR / "live_2026_27_gradient_points.joblib"
LIVE_MINUTES_MODEL_PATH = MODELS_DIR / "live_2026_27_minutes_binary.joblib"
LIVE_MINUTES_BAND_MODEL_PATH = MODELS_DIR / "live_2026_27_minutes_band.joblib"
LIVE_TARGET_SEASON = "2026-27"
LIVE_MODEL_SCHEMA_VERSION = "live-models-v1"


@dataclass(frozen=True)
class LiveModelMetadata:
    schema_version: str
    target_season: str
    training_seasons: list[str]
    training_rows: int
    feature_columns: list[str]
    generated_at: str
    artifacts: dict[str, dict[str, str]]
    validation_source: str
    validation_policy: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_live_models(
    players: pd.DataFrame | None = None,
    *,
    target_season: str = LIVE_TARGET_SEASON,
    output_dir: Path = MODELS_DIR,
    generated_at: str | None = None,
) -> LiveModelMetadata:
    """Fit serving artifacts on every completed season after held-out evaluation.

    This does not overwrite historical evaluation predictions. The existing
    season-based benchmark remains the promotion evidence; this function only
    performs the final fit used for a future, unseen season.
    """

    history = (
        load_historical_player_gameweeks()
        if players is None
        else players.copy()
    )
    required = set(BASE_FEATURE_COLUMNS) | {
        "season",
        "minutes",
        "next_gameweek_points",
    }
    missing = sorted(required - set(history.columns))
    if missing:
        raise ValueError(f"Live-model training data is missing columns: {missing}")

    training = history.dropna(subset=["next_gameweek_points"]).copy()
    training_seasons = sorted(training["season"].astype(str).unique().tolist())
    if not training_seasons:
        raise ValueError("Live-model training requires at least one completed season")
    if target_season in training_seasons:
        raise ValueError(f"Target season {target_season} must remain unseen during live fit")

    ridge = build_ridge_model(BASE_FEATURE_COLUMNS)
    gradient = build_gradient_boosting_model(BASE_FEATURE_COLUMNS)
    minutes = build_minutes_classifier(BASE_FEATURE_COLUMNS)
    minutes_band = fit_minutes_band_conditional_model(training, BASE_FEATURE_COLUMNS)
    features = training[BASE_FEATURE_COLUMNS]
    ridge.fit(features, training["next_gameweek_points"])
    gradient.fit(features, training["next_gameweek_points"])
    minutes.fit(features, (training["minutes"] >= 60).astype(int))

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "ridge": output_dir / LIVE_RIDGE_MODEL_PATH.name,
        "gradient": output_dir / LIVE_GRADIENT_MODEL_PATH.name,
        "minutes_binary": output_dir / LIVE_MINUTES_MODEL_PATH.name,
        "minutes_band": output_dir / LIVE_MINUTES_BAND_MODEL_PATH.name,
    }
    for model, path in (
        (ridge, paths["ridge"]),
        (gradient, paths["gradient"]),
        (minutes, paths["minutes_binary"]),
        (minutes_band, paths["minutes_band"]),
    ):
        joblib.dump(model, path)

    artifacts = {
        key: {
            "path": path.name,
            "sha256": _sha256(path),
            "class": f"{model.__class__.__module__}.{model.__class__.__name__}",
        }
        for key, path, model in (
            ("ridge", paths["ridge"], ridge),
            ("gradient", paths["gradient"], gradient),
            ("minutes_binary", paths["minutes_binary"], minutes),
            ("minutes_band", paths["minutes_band"], minutes_band),
        )
    }
    metadata = LiveModelMetadata(
        schema_version=LIVE_MODEL_SCHEMA_VERSION,
        target_season=target_season,
        training_seasons=training_seasons,
        training_rows=len(training),
        feature_columns=list(BASE_FEATURE_COLUMNS),
        generated_at=generated_at
        or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        artifacts=artifacts,
        validation_source="data/processed/step5_model_comparison.csv and season benchmark history",
        validation_policy=(
            "Serving fit uses all completed seasons only after season-held-out model and "
            "decision evaluation; target-season outcomes are excluded."
        ),
    )
    metadata_path = output_dir / LIVE_MODEL_METADATA_PATH.name
    metadata_path.write_text(
        json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def metadata_hash(metadata: LiveModelMetadata) -> str:
    return hashlib.sha256(canonical_json(asdict(metadata)).encode("utf-8")).hexdigest()


def main() -> None:
    metadata = train_live_models()
    print(
        f"Trained {metadata.training_rows:,} rows from "
        f"{', '.join(metadata.training_seasons)} for {metadata.target_season}."
    )
    print(f"Saved metadata to {LIVE_MODEL_METADATA_PATH}")


if __name__ == "__main__":
    main()
