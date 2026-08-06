from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from fpl_intelligence.minutes_model import MinutesBandConditionalModel
from fpl_intelligence.season_rules import historical_regime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_PLAYER_GW_PATH = PROJECT_ROOT / "data" / "processed" / "historical_player_gw.csv"
PREDICTIONS_PATH = PROJECT_ROOT / "data" / "processed" / "step4_predictions.csv"
MODELS_DIR = PROJECT_ROOT / "models"
RIDGE_MODEL_PATH = MODELS_DIR / "ridge_points_model.joblib"
MINUTES_MODEL_PATH = MODELS_DIR / "logistic_minutes_model.joblib"
MINUTES_BAND_MODEL_PATH = MODELS_DIR / "minutes_band_conditional_model.joblib"

TRAIN_SEASONS = ["2023-24", "2024-25"]
TEST_SEASON = "2025-26"
NUMERIC_FEATURES = [
    "price_before_deadline",
    "minutes_last_3",
    "points_last_3",
    "opponent_strength",
    "selected_by_percent_before_deadline",
    "market_snapshot_available",
]
CATEGORICAL_FEATURES = ["position", "home_or_away"]
XG_XA_FEATURES = [
    f"{column}_last_{window}"
    for column in ("expected_goals", "expected_assists")
    for window in (1, 3, 5, 8)
] + [f"xgi_per_90_last_{window}" for window in (1, 3, 5, 8)]
DC_FEATURES = [
    "defensive_contribution_last_3",
    "defensive_contribution_per_90_last_3",
]
BASE_FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
XG_XA_FEATURE_COLUMNS = NUMERIC_FEATURES + XG_XA_FEATURES + CATEGORICAL_FEATURES
DC_FEATURE_COLUMNS = NUMERIC_FEATURES + DC_FEATURES + CATEGORICAL_FEATURES
FEATURE_COLUMNS = BASE_FEATURE_COLUMNS
FEATURE_MODES = {
    "baseline": BASE_FEATURE_COLUMNS,
    "xg_xa": XG_XA_FEATURE_COLUMNS,
    "dc": DC_FEATURE_COLUMNS,
}
MINUTES_BAND_NAMES = {0: "0", 1: "1-59", 2: "60+"}


def feature_columns_for_mode(feature_mode: str = "baseline") -> list[str]:
    try:
        return FEATURE_MODES[feature_mode]
    except KeyError as exc:
        raise ValueError(
            f"Unknown feature mode {feature_mode!r}; choose from {', '.join(FEATURE_MODES)}"
        ) from exc


@dataclass(frozen=True)
class Step4Results:
    ridge_mae: float
    ridge_rmse: float
    baseline_mae: float
    baseline_rmse: float
    minutes_accuracy: float
    minutes_precision: float
    minutes_recall: float
    confusion: np.ndarray
    minutes_band_precision: dict[str, float]
    minutes_band_recall: dict[str, float]
    minutes_band_calibration: pd.DataFrame


def minutes_band(minutes: pd.Series | np.ndarray) -> np.ndarray:
    """Map observed minutes to the three FPL-relevant playing-time bands."""
    values = np.asarray(minutes)
    return np.select([values <= 0, values < 60], [0, 1], default=2).astype(int)


def load_historical_player_gameweeks(path: Path = HISTORICAL_PLAYER_GW_PATH) -> pd.DataFrame:
    players = pd.read_csv(path)
    if "bps_rule_version" not in players.columns and "season" in players.columns:
        players["bps_rule_version"] = players["season"].map(
            lambda season: historical_regime(str(season))["bps_rule_version"]
        )
    return players


def build_preprocessor(feature_columns: list[str] | None = None) -> ColumnTransformer:
    selected_features = feature_columns or FEATURE_COLUMNS
    numeric_features = [
        feature for feature in selected_features if feature not in CATEGORICAL_FEATURES
    ]
    categorical_features = [
        feature for feature in selected_features if feature in CATEGORICAL_FEATURES
    ]
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric_features),
            ("categorical", categorical_pipeline, categorical_features),
        ]
    )


def build_ridge_model(feature_columns: list[str] | None = None) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(feature_columns)),
            ("model", Ridge(alpha=1.0)),
        ]
    )


def build_minutes_classifier(feature_columns: list[str] | None = None) -> Pipeline:
    """Build the legacy binary 60+ minutes classifier.

    Older backtests and saved-artifact consumers still use this model.  M2's
    three-class model is provided separately by ``build_minutes_band_classifier``.
    """
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(feature_columns)),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )


def build_minutes_band_classifier(feature_columns: list[str] | None = None) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(feature_columns)),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )


def build_minutes_calibration_table(
    actual_bands: pd.Series | np.ndarray,
    probabilities: np.ndarray,
) -> pd.DataFrame:
    """Return per-band calibration diagnostics on the held-out sample."""
    actual = np.asarray(actual_bands).astype(int)
    rows: list[dict[str, float | int | str]] = []
    for band, name in MINUTES_BAND_NAMES.items():
        observed = (actual == band).astype(float)
        predicted = probabilities[:, band]
        rows.append(
            {
                "band": name,
                "support": int(observed.sum()),
                "predicted_probability_mean": float(predicted.mean()),
                "actual_rate": float(observed.mean()),
                "absolute_calibration_error": float(abs(predicted.mean() - observed.mean())),
                "brier_score": float(np.mean((predicted - observed) ** 2)),
            }
        )
    return pd.DataFrame(rows)


def fit_minutes_band_conditional_model(
    training: pd.DataFrame,
    feature_columns: list[str] | None = None,
) -> MinutesBandConditionalModel:
    """Fit a three-class minutes model and band-specific point expectations."""
    target_bands = minutes_band(training["minutes"])
    counts = np.bincount(target_bands, minlength=3).astype(float)
    fallback = counts / counts.sum() if counts.sum() else np.array([0.0, 0.0, 1.0])

    classifier: Pipeline | None = None
    if len(np.unique(target_bands)) >= 2:
        classifier = build_minutes_band_classifier(feature_columns)
        classifier.fit(training[feature_columns or FEATURE_COLUMNS], target_bands)

    point_models: dict[int, Any | None] = {}
    point_means: dict[int, float] = {}
    for band in range(3):
        band_rows = training.loc[target_bands == band]
        point_means[band] = (
            float(band_rows["next_gameweek_points"].mean()) if not band_rows.empty else 0.0
        )
        # A separate model per band preserves player/context signal while
        # ensuring that E(points | band) is learned from that population only.
        if len(band_rows) >= 5 and band_rows["next_gameweek_points"].nunique() >= 2:
            model = build_ridge_model(feature_columns)
            model.fit(
                band_rows[feature_columns or FEATURE_COLUMNS],
                band_rows["next_gameweek_points"],
            )
            point_models[band] = model
        else:
            point_models[band] = None

    return MinutesBandConditionalModel(
        classifier=classifier,
        fallback_probabilities=fallback,
        band_point_models=point_models,
        conditional_point_means=point_means,
    )


def split_train_test(players: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = players[players["season"].isin(TRAIN_SEASONS)].copy()
    test = players[players["season"] == TEST_SEASON].copy()
    return train, test


def rmse(actual: pd.Series, predicted: np.ndarray | pd.Series) -> float:
    return float(np.sqrt(mean_squared_error(actual, predicted)))


def train_step4_models(
    players: pd.DataFrame,
    feature_mode: str = "baseline",
) -> tuple[Pipeline, Pipeline, MinutesBandConditionalModel, pd.DataFrame, Step4Results]:
    feature_columns = feature_columns_for_mode(feature_mode)
    train, test = split_train_test(players)

    ridge_model = build_ridge_model(feature_columns)
    minutes_model = build_minutes_classifier(feature_columns)

    ridge_model.fit(train[feature_columns], train["next_gameweek_points"])

    train_minutes_target = (train["minutes"] >= 60).astype(int)
    test_minutes_target = (test["minutes"] >= 60).astype(int)
    minutes_model.fit(train[feature_columns], train_minutes_target)
    minutes_band_model = fit_minutes_band_conditional_model(train, feature_columns)

    predictions = test.copy()
    predictions["predicted_points"] = ridge_model.predict(test[feature_columns])
    predictions["naive_points_prediction"] = predictions["points_last_3"] / 3
    predictions["probability_60_plus_minutes"] = minutes_model.predict_proba(
        test[feature_columns]
    )[:, 1]
    predictions["predicted_played_60_plus"] = minutes_model.predict(test[feature_columns])
    predictions["actual_played_60_plus"] = test_minutes_target
    band_probabilities = minutes_band_model.predict_proba(test[feature_columns])
    actual_bands = minutes_band(test["minutes"])
    predictions["probability_0_minutes"] = band_probabilities[:, 0]
    predictions["probability_1_59_minutes"] = band_probabilities[:, 1]
    predictions["probability_60_plus_minutes_v2"] = band_probabilities[:, 2]
    predictions["predicted_minutes_band"] = minutes_band_model.predict(test[feature_columns])
    predictions["actual_minutes_band"] = actual_bands
    conditional_points = minutes_band_model.predict_conditional_points(test[feature_columns])
    for band, name in MINUTES_BAND_NAMES.items():
        predictions[f"conditional_points_{name.replace('-', '_').replace('+', 'plus')}"] = (
            conditional_points[:, band]
        )
    predictions["expected_points_adjusted"] = minutes_band_model.predict_expected_points(
        test[feature_columns]
    )
    band_precision = precision_score(
        actual_bands,
        predictions["predicted_minutes_band"],
        labels=[0, 1, 2],
        average=None,
        zero_division=0,
    )
    band_recall = recall_score(
        actual_bands,
        predictions["predicted_minutes_band"],
        labels=[0, 1, 2],
        average=None,
        zero_division=0,
    )

    results = Step4Results(
        ridge_mae=float(
            mean_absolute_error(
                test["next_gameweek_points"],
                predictions["predicted_points"],
            )
        ),
        ridge_rmse=rmse(test["next_gameweek_points"], predictions["predicted_points"]),
        baseline_mae=float(
            mean_absolute_error(
                test["next_gameweek_points"],
                predictions["naive_points_prediction"],
            )
        ),
        baseline_rmse=rmse(test["next_gameweek_points"], predictions["naive_points_prediction"]),
        minutes_accuracy=float(
            accuracy_score(actual_bands, predictions["predicted_minutes_band"])
        ),
        minutes_precision=float(
            precision_score(
                actual_bands,
                predictions["predicted_minutes_band"],
                average="macro",
                zero_division=0,
            )
        ),
        minutes_recall=float(
            recall_score(
                actual_bands,
                predictions["predicted_minutes_band"],
                average="macro",
                zero_division=0,
            )
        ),
        confusion=confusion_matrix(
            actual_bands,
            predictions["predicted_minutes_band"],
            labels=[0, 1, 2],
        ),
        minutes_band_precision={
            MINUTES_BAND_NAMES[band]: float(value)
            for band, value in zip(range(3), band_precision, strict=True)
        },
        minutes_band_recall={
            MINUTES_BAND_NAMES[band]: float(value)
            for band, value in zip(range(3), band_recall, strict=True)
        },
        minutes_band_calibration=build_minutes_calibration_table(
            actual_bands,
            band_probabilities,
        ),
    )

    return ridge_model, minutes_model, minutes_band_model, predictions, results


def save_artifacts(
    ridge_model: Pipeline,
    minutes_model: Pipeline,
    predictions: pd.DataFrame,
    minutes_band_model: MinutesBandConditionalModel | None = None,
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(ridge_model, RIDGE_MODEL_PATH)
    joblib.dump(minutes_model, MINUTES_MODEL_PATH)
    if minutes_band_model is not None:
        joblib.dump(minutes_band_model, MINUTES_BAND_MODEL_PATH)
    predictions.to_csv(PREDICTIONS_PATH, index=False)


def print_feature_set() -> None:
    print("Step 4 feature set:")
    print(
        "- price_before_deadline: prior observed price snapshot; same-gameweek raw price "
        "is excluded from historical model features because the source is scraped after the GW."
    )
    print("- position: categorical FPL role, because scoring rules differ by position.")
    print("- minutes_last_3: prior 3-gameweek minutes only; captures recent playing time.")
    print("- points_last_3: prior 3-gameweek points only; captures recent FPL output.")
    print("- opponent_strength: venue-adjusted opponent strength from FPL team data.")
    print("- home_or_away: categorical fixture venue flag; H, A, or M for mixed/double GWs.")
    print(
        "- selected_by_percent_before_deadline: prior observed ownership snapshot; same-GW "
        "raw ownership is excluded for the same timing reason."
    )
    print(
        "- market_snapshot_available: distinguishes a prior snapshot from the GW1/imputed "
        "fallback case."
    )


def print_results(results: Step4Results) -> None:
    print("\nRidge Regression points model:")
    print(f"- Ridge MAE: {results.ridge_mae:.3f}")
    print(f"- Ridge RMSE: {results.ridge_rmse:.3f}")
    print(f"- Naive baseline MAE (points_last_3 / 3): {results.baseline_mae:.3f}")
    print(f"- Naive baseline RMSE (points_last_3 / 3): {results.baseline_rmse:.3f}")
    if results.ridge_mae < results.baseline_mae:
        print("- Ridge beats the naive baseline on MAE.")
    else:
        print("- Ridge does not beat the naive baseline on MAE.")

    print("\nMinutes-band model (0, 1-59, 60+) classification:")
    print(f"- Accuracy: {results.minutes_accuracy:.3f}")
    print(f"- Precision: {results.minutes_precision:.3f}")
    print(f"- Recall: {results.minutes_recall:.3f}")
    print("- Confusion matrix (rows=actual, columns=predicted; labels 0, 1-59, 60+):")
    print(results.confusion)
    print("- Per-band precision:", results.minutes_band_precision)
    print("- Per-band recall:", results.minutes_band_recall)
    print("- Calibration diagnostics:")
    print(results.minutes_band_calibration.to_string(index=False))


def print_top_adjusted_predictions(predictions: pd.DataFrame, sample_gameweek: int = 10) -> None:
    sample = predictions[predictions["gameweek"] == sample_gameweek].copy()
    display_columns = [
        "player_name",
        "team",
        "position",
        "price",
        "opponent_team",
        "home_or_away",
        "minutes_last_3",
        "points_last_3",
        "predicted_points",
        "probability_60_plus_minutes_v2",
        "expected_points_adjusted",
        "minutes",
        "next_gameweek_points",
    ]

    top_players = sample.sort_values("expected_points_adjusted", ascending=False).head(10)
    print(f"\nTop 10 by expected_points_adjusted for {TEST_SEASON} GW{sample_gameweek}:")
    print(top_players[display_columns].to_string(index=False))

    low_minutes = top_players[top_players["minutes_last_3"] == 0]
    print("\nSanity check:")
    if low_minutes.empty:
        print("- No top-10 adjusted pick had 0 minutes across the prior three gameweeks.")
    else:
        names = ", ".join(low_minutes["player_name"].tolist())
        print(f"- Prior-3-GW 0-minute players appeared in the top 10: {names}.")


def main() -> None:
    players = load_historical_player_gameweeks()

    print("Season-boundary check:")
    gw1 = players[players["gameweek"] == 1]
    boundary_max = gw1[
        ["prior_games_available_last_3", "minutes_last_3", "points_last_3"]
    ].max()
    print("- Rolling features reset by season and player_id.")
    print(f"- GW1 max prior_games_available_last_3: {boundary_max['prior_games_available_last_3']}")
    print(f"- GW1 max minutes_last_3: {boundary_max['minutes_last_3']}")
    print(f"- GW1 max points_last_3: {boundary_max['points_last_3']}")

    train, test = split_train_test(players)
    print("\nTrain/test split:")
    print(f"- Train seasons: {', '.join(TRAIN_SEASONS)} ({len(train):,} rows)")
    print(f"- Test season: {TEST_SEASON} ({len(test):,} rows)")

    print_feature_set()
    (
        ridge_model,
        minutes_model,
        minutes_band_model,
        predictions,
        results,
    ) = train_step4_models(players)
    print_results(results)
    print_top_adjusted_predictions(predictions)
    save_artifacts(ridge_model, minutes_model, predictions, minutes_band_model)

    print(f"\nSaved Ridge model to {RIDGE_MODEL_PATH}")
    print(f"Saved Logistic Regression minutes model to {MINUTES_MODEL_PATH}")
    print(f"Saved conditional minutes-band model to {MINUTES_BAND_MODEL_PATH}")
    print(f"Saved test predictions to {PREDICTIONS_PATH}")


if __name__ == "__main__":
    main()
