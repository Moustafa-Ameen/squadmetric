from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

from squadmetric.step4_models import (
    FEATURE_COLUMNS,
    MODELS_DIR,
    TEST_SEASON,
    build_minutes_classifier,
    build_preprocessor,
    build_ridge_model,
    feature_columns_for_mode,
    load_historical_player_gameweeks,
    rmse,
    split_train_test,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_COMPARISON_PATH = PROJECT_ROOT / "data" / "processed" / "step5_model_comparison.csv"
RANDOM_FOREST_MODEL_PATH = MODELS_DIR / "random_forest_points_model.joblib"
GRADIENT_BOOSTING_MODEL_PATH = MODELS_DIR / "gradient_boosting_points_model.joblib"


@dataclass(frozen=True)
class RegressionModelResult:
    name: str
    model: Pipeline | None
    predictions: np.ndarray | pd.Series
    mae: float
    rmse: float


def build_random_forest_model(feature_columns: list[str] | None = None) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(feature_columns)),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=10,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def build_gradient_boosting_model(feature_columns: list[str] | None = None) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(feature_columns)),
            (
                "model",
                GradientBoostingRegressor(
                    random_state=42,
                    n_estimators=150,
                    learning_rate=0.05,
                    max_depth=3,
                ),
            ),
        ]
    )


def evaluate_predictions(
    name: str,
    model: Pipeline | None,
    actual: pd.Series,
    predictions: np.ndarray | pd.Series,
) -> RegressionModelResult:
    return RegressionModelResult(
        name=name,
        model=model,
        predictions=predictions,
        mae=float(mean_absolute_error(actual, predictions)),
        rmse=rmse(actual, predictions),
    )


def train_regression_models(
    players: pd.DataFrame,
    feature_mode: str = "baseline",
) -> tuple[list[RegressionModelResult], Pipeline]:
    feature_columns = feature_columns_for_mode(feature_mode)
    train, test = split_train_test(players)
    actual = test["next_gameweek_points"]

    ridge_model = build_ridge_model(feature_columns)
    random_forest_model = build_random_forest_model(feature_columns)
    gradient_boosting_model = build_gradient_boosting_model(feature_columns)
    minutes_model = build_minutes_classifier(feature_columns)

    ridge_model.fit(train[feature_columns], train["next_gameweek_points"])
    random_forest_model.fit(train[feature_columns], train["next_gameweek_points"])
    gradient_boosting_model.fit(train[feature_columns], train["next_gameweek_points"])
    minutes_model.fit(train[feature_columns], (train["minutes"] >= 60).astype(int))

    results = [
        evaluate_predictions(
            "Naive baseline",
            None,
            actual,
            test["points_last_3"] / 3,
        ),
        evaluate_predictions(
            "Ridge Regression",
            ridge_model,
            actual,
            ridge_model.predict(test[feature_columns]),
        ),
        evaluate_predictions(
            "Random Forest Regressor",
            random_forest_model,
            actual,
            random_forest_model.predict(test[feature_columns]),
        ),
        evaluate_predictions(
            "Gradient Boosting Regressor",
            gradient_boosting_model,
            actual,
            gradient_boosting_model.predict(test[feature_columns]),
        ),
    ]

    return results, minutes_model


def build_comparison_table(results: list[RegressionModelResult]) -> pd.DataFrame:
    naive = next(result for result in results if result.name == "Naive baseline")
    rows = []
    for result in results:
        rows.append(
            {
                "model": result.name,
                "MAE": result.mae,
                "RMSE": result.rmse,
                "beats_naive_MAE": "yes" if result.mae < naive.mae else "no",
                "beats_naive_RMSE": "yes" if result.rmse < naive.rmse else "no",
            }
        )

    return pd.DataFrame(rows).sort_values("MAE").reset_index(drop=True)


def get_feature_importance(model: Pipeline) -> pd.DataFrame:
    preprocessor = model.named_steps["preprocessor"]
    regressor = model.named_steps["model"]
    feature_names = preprocessor.get_feature_names_out()
    importances = regressor.feature_importances_

    return (
        pd.DataFrame(
            {
                "feature": feature_names,
                "importance": importances,
            }
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def aggregate_feature_importance(importance: pd.DataFrame) -> pd.DataFrame:
    mapped = importance.copy()
    mapped["base_feature"] = mapped["feature"].str.replace("numeric__", "", regex=False)
    mapped["base_feature"] = mapped["base_feature"].str.replace(
        r"categorical__position_.*",
        "position",
        regex=True,
    )
    mapped["base_feature"] = mapped["base_feature"].str.replace(
        r"categorical__home_or_away_.*",
        "home_or_away",
        regex=True,
    )
    return (
        mapped.groupby("base_feature", as_index=False)["importance"]
        .sum()
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def get_predictions_for_result(
    result: RegressionModelResult,
    test: pd.DataFrame,
    feature_columns: list[str] | None = None,
) -> np.ndarray | pd.Series:
    if result.model is None:
        return test["points_last_3"] / 3

    return result.model.predict(test[feature_columns or FEATURE_COLUMNS])


def print_top_adjusted_for_best_model(
    players: pd.DataFrame,
    results: list[RegressionModelResult],
    minutes_model: Pipeline,
    sample_gameweek: int = 10,
    feature_mode: str = "baseline",
) -> None:
    feature_columns = feature_columns_for_mode(feature_mode)
    _, test = split_train_test(players)
    best = min(results, key=lambda result: result.mae)
    ridge = next(result for result in results if result.name == "Ridge Regression")

    sample = test[test["gameweek"] == sample_gameweek].copy()
    sample["probability_60_plus_minutes"] = minutes_model.predict_proba(
        sample[feature_columns]
    )[:, 1]
    sample["best_model_predicted_points"] = get_predictions_for_result(
        best, sample, feature_columns
    )
    sample["ridge_predicted_points"] = get_predictions_for_result(
        ridge, sample, feature_columns
    )
    sample["best_expected_points_adjusted"] = (
        sample["best_model_predicted_points"] * sample["probability_60_plus_minutes"]
    )
    sample["ridge_expected_points_adjusted"] = (
        sample["ridge_predicted_points"] * sample["probability_60_plus_minutes"]
    )

    display_columns = [
        "player_name",
        "team",
        "position",
        "price",
        "opponent_team",
        "home_or_away",
        "minutes_last_3",
        "points_last_3",
        "best_model_predicted_points",
        "probability_60_plus_minutes",
        "best_expected_points_adjusted",
        "minutes",
        "next_gameweek_points",
    ]
    best_top = sample.sort_values("best_expected_points_adjusted", ascending=False).head(10)
    ridge_top = sample.sort_values("ridge_expected_points_adjusted", ascending=False).head(10)

    print(f"\nBest model by MAE: {best.name}")
    print(f"\nTop 10 by {best.name} adjusted score for {TEST_SEASON} GW{sample_gameweek}:")
    print(best_top[display_columns].to_string(index=False))

    best_names = best_top["player_name"].tolist()
    ridge_names = ridge_top["player_name"].tolist()
    added_vs_ridge = [name for name in best_names if name not in ridge_names]
    removed_vs_ridge = [name for name in ridge_names if name not in best_names]

    print("\nComparison to Step 4 Ridge-based GW10 list:")
    if not added_vs_ridge and not removed_vs_ridge:
        print("- Same top-10 player set as Ridge, with possible order changes only.")
        return

    print(f"- Added vs Ridge top 10: {', '.join(added_vs_ridge) or 'none'}")
    print(f"- Removed vs Ridge top 10: {', '.join(removed_vs_ridge) or 'none'}")


def save_step5_artifacts(
    results: list[RegressionModelResult],
    comparison: pd.DataFrame,
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_COMPARISON_PATH.parent.mkdir(parents=True, exist_ok=True)

    random_forest = next(result for result in results if result.name == "Random Forest Regressor")
    gradient_boosting = next(
        result for result in results if result.name == "Gradient Boosting Regressor"
    )

    joblib.dump(random_forest.model, RANDOM_FOREST_MODEL_PATH)
    joblib.dump(gradient_boosting.model, GRADIENT_BOOSTING_MODEL_PATH)
    comparison.to_csv(MODEL_COMPARISON_PATH, index=False)


def print_importance_summary(model_result: RegressionModelResult) -> None:
    if model_result.model is None:
        return

    transformed = get_feature_importance(model_result.model).head(8)
    aggregated = aggregate_feature_importance(get_feature_importance(model_result.model)).head(6)
    print(f"\n{model_result.name} feature importance:")
    print("- Top transformed features:")
    print(transformed.to_string(index=False))
    print("- Top original feature groups:")
    print(aggregated.to_string(index=False))


def print_xgboost_lightgbm_recommendation(comparison: pd.DataFrame) -> None:
    naive = comparison[comparison["model"] == "Naive baseline"].iloc[0]
    best_model = comparison.iloc[0]
    mae_gap = naive["MAE"] - best_model["MAE"]

    print("\nXGBoost/LightGBM assessment:")
    if best_model["model"] == "Naive baseline" or mae_gap < 0.02:
        print(
            "- Recommendation: do not add XGBoost or LightGBM yet. The dataset is usable, "
            "but the current models do not create a meaningful MAE gap over the naive "
            "baseline, so extra libraries would mostly add complexity."
        )
    else:
        print(
            "- Recommendation: consider XGBoost/LightGBM later, but not in Step 5. There is "
            "some evidence that non-linear models may help, so a more rigorous Step 6 "
            "backtest should decide whether the added complexity is justified."
        )


def main() -> None:
    players = load_historical_player_gameweeks()
    train, test = split_train_test(players)
    print("Step 5 model comparison")
    print(f"- Train seasons: 2023-24, 2024-25 ({len(train):,} rows)")
    print(f"- Test season: {TEST_SEASON} ({len(test):,} rows)")
    print("- Feature set and target are unchanged from Step 4.")

    results, minutes_model = train_regression_models(players)
    comparison = build_comparison_table(results)

    print("\nComparison table:")
    print(comparison.to_string(index=False, float_format=lambda value: f"{value:.3f}"))

    for result in results:
        if result.name in {"Random Forest Regressor", "Gradient Boosting Regressor"}:
            print_importance_summary(result)

    print_xgboost_lightgbm_recommendation(comparison)
    print_top_adjusted_for_best_model(players, results, minutes_model)
    save_step5_artifacts(results, comparison)

    print(f"\nSaved model comparison to {MODEL_COMPARISON_PATH}")
    print(f"Saved Random Forest model to {RANDOM_FOREST_MODEL_PATH}")
    print(f"Saved Gradient Boosting model to {GRADIENT_BOOSTING_MODEL_PATH}")


if __name__ == "__main__":
    main()
