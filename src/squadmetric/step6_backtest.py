from __future__ import annotations

from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from squadmetric.step4_models import (
    FEATURE_COLUMNS,
    TEST_SEASON,
    TRAIN_SEASONS,
    build_minutes_classifier,
    build_ridge_model,
    load_historical_player_gameweeks,
)
from squadmetric.step5_model_comparison import (
    build_gradient_boosting_model,
    build_random_forest_model,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKTEST_PREDICTIONS_PATH = (
    PROJECT_ROOT / "data" / "processed" / "step6_backtest_predictions.csv"
)

MODEL_BUILDERS = {
    "Naive baseline": None,
    "Ridge Regression": build_ridge_model,
    "Random Forest Regressor": build_random_forest_model,
    "Gradient Boosting Regressor": build_gradient_boosting_model,
}


def get_training_data_for_gameweek(players: pd.DataFrame, target_gameweek: int) -> pd.DataFrame:
    previous_seasons = players["season"].isin(TRAIN_SEASONS)
    current_season_history = (players["season"] == TEST_SEASON) & (
        players["gameweek"] < target_gameweek
    )
    training_data = players[previous_seasons | current_season_history].copy()

    current_training_rows = training_data[training_data["season"] == TEST_SEASON]
    if not current_training_rows.empty:
        max_current_gameweek = current_training_rows["gameweek"].max()
        assert max_current_gameweek < target_gameweek

    assert not (
        (training_data["season"] == TEST_SEASON)
        & (training_data["gameweek"] >= target_gameweek)
    ).any()

    return training_data


def get_target_data_for_gameweek(players: pd.DataFrame, target_gameweek: int) -> pd.DataFrame:
    target_data = players[
        (players["season"] == TEST_SEASON) & (players["gameweek"] == target_gameweek)
    ].copy()
    assert not target_data.empty
    return target_data


def train_points_model(
    model_name: str,
    model_builder,
    training_data: pd.DataFrame,
) -> Pipeline | None:
    if model_builder is None:
        return None

    model = model_builder()
    model.fit(training_data[FEATURE_COLUMNS], training_data["next_gameweek_points"])
    return model


def predict_points(
    model_name: str,
    model: Pipeline | None,
    target_data: pd.DataFrame,
) -> np.ndarray | pd.Series:
    if model_name == "Naive baseline":
        return target_data["points_last_3"] / 3

    if model is None:
        raise ValueError(f"{model_name} requires a trained model.")

    return model.predict(target_data[FEATURE_COLUMNS])


def train_minutes_model(training_data: pd.DataFrame) -> Pipeline:
    minutes_model = build_minutes_classifier()
    minutes_model.fit(training_data[FEATURE_COLUMNS], (training_data["minutes"] >= 60).astype(int))
    return minutes_model


def build_prediction_rows(
    target_data: pd.DataFrame,
    model_name: str,
    predicted_points: np.ndarray | pd.Series,
    probability_60_plus_minutes: np.ndarray,
    training_row_count: int,
    max_training_current_season_gameweek: int | None,
) -> pd.DataFrame:
    predictions = target_data[
        [
            "season",
            "player_id",
            "player_name",
            "gameweek",
            "price",
            "position",
            "team",
            "opponent_team",
            "opponent_strength",
            "home_or_away",
            "selected_by_percent",
            "minutes_last_3",
            "points_last_3",
            "prior_games_available_last_3",
            "minutes",
            "next_gameweek_points",
        ]
    ].copy()
    predictions["model"] = model_name
    predictions["predicted_points"] = predicted_points
    predictions["probability_60_plus_minutes"] = probability_60_plus_minutes
    predictions["expected_points_adjusted"] = (
        predictions["predicted_points"] * predictions["probability_60_plus_minutes"]
    )
    predictions["actual_points"] = predictions["next_gameweek_points"]
    predictions["actual_minutes"] = predictions["minutes"]
    predictions["actual_played_60_plus"] = (predictions["minutes"] >= 60).astype(int)
    predictions["training_row_count"] = training_row_count
    predictions["max_training_current_season_gameweek"] = max_training_current_season_gameweek

    columns = [
        "season",
        "gameweek",
        "model",
        "player_id",
        "player_name",
        "team",
        "position",
        "price",
        "opponent_team",
        "opponent_strength",
        "home_or_away",
        "selected_by_percent",
        "minutes_last_3",
        "points_last_3",
        "prior_games_available_last_3",
        "predicted_points",
        "probability_60_plus_minutes",
        "expected_points_adjusted",
        "actual_points",
        "actual_minutes",
        "actual_played_60_plus",
        "training_row_count",
        "max_training_current_season_gameweek",
    ]
    return predictions[columns]


def run_rolling_backtest(players: pd.DataFrame) -> pd.DataFrame:
    gameweeks = sorted(players.loc[players["season"] == TEST_SEASON, "gameweek"].unique())
    all_predictions = []

    print("Step 6 rolling/expanding-window backtest")
    print("- Retraining from scratch each gameweek.")
    print(
        "- Reason: scikit-learn Ridge, Random Forest, Gradient Boosting, and Logistic "
        "Regression are not used incrementally here; full retraining is clearer and safer "
        "for a first no-lookahead backtest."
    )

    for gameweek in gameweeks:
        started = perf_counter()
        training_data = get_training_data_for_gameweek(players, int(gameweek))
        target_data = get_target_data_for_gameweek(players, int(gameweek))

        current_training = training_data[training_data["season"] == TEST_SEASON]
        max_current_gameweek = (
            None if current_training.empty else int(current_training["gameweek"].max())
        )

        minutes_model = train_minutes_model(training_data)
        probability_60_plus_minutes = minutes_model.predict_proba(
            target_data[FEATURE_COLUMNS]
        )[:, 1]

        for model_name, model_builder in MODEL_BUILDERS.items():
            points_model = train_points_model(model_name, model_builder, training_data)
            predicted_points = predict_points(model_name, points_model, target_data)
            model_predictions = build_prediction_rows(
                target_data=target_data,
                model_name=model_name,
                predicted_points=predicted_points,
                probability_60_plus_minutes=probability_60_plus_minutes,
                training_row_count=len(training_data),
                max_training_current_season_gameweek=max_current_gameweek,
            )
            all_predictions.append(model_predictions)

        elapsed = perf_counter() - started
        print(
            f"- GW{int(gameweek):02d}: trained on {len(training_data):,} rows, "
            f"predicted {len(target_data):,} players, max 2025-26 train GW "
            f"{max_current_gameweek}, {elapsed:.1f}s"
        )

    return pd.concat(all_predictions, ignore_index=True)


def save_backtest_predictions(
    predictions: pd.DataFrame,
    path: Path = BACKTEST_PREDICTIONS_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(path, index=False)


def print_sanity_checks(predictions: pd.DataFrame) -> None:
    print("\nSanity checks:")
    print(f"- Prediction rows: {len(predictions):,}")
    print(f"- Models: {', '.join(sorted(predictions['model'].unique()))}")
    print(
        "- Gameweek range: "
        f"GW{predictions['gameweek'].min()} to GW{predictions['gameweek'].max()}"
    )
    leakage = predictions[
        predictions["max_training_current_season_gameweek"].fillna(0) >= predictions["gameweek"]
    ]
    assert leakage.empty
    print("- No-lookahead assertion passed: max 2025-26 training gameweek is always < target GW.")

    per_gw_counts = (
        predictions[predictions["model"] == "Naive baseline"]
        .groupby("gameweek")
        .size()
        .sort_index()
    )
    print(
        "- Target row-count range by gameweek: "
        f"{per_gw_counts.min()} to {per_gw_counts.max()} players."
    )
    print(
        "- Practical note: lower row counts usually reflect blanks/postponements or fixture "
        "schedule quirks; Step 7 should keep those gameweeks visible rather than smoothing "
        "them away."
    )

    gw1_naive = predictions[
        (predictions["gameweek"] == 1) & (predictions["model"] == "Naive baseline")
    ]
    if (gw1_naive["predicted_points"] == 0).all():
        print(
            "- Practical note: GW1 naive predictions are all 0 because current-season "
            "rolling history is intentionally empty."
        )


def main() -> None:
    players = load_historical_player_gameweeks()
    predictions = run_rolling_backtest(players)
    save_backtest_predictions(predictions)
    print_sanity_checks(predictions)
    print(f"\nSaved rolling backtest predictions to {BACKTEST_PREDICTIONS_PATH}")


if __name__ == "__main__":
    main()
