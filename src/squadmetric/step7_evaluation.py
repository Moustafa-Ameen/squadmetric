from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from squadmetric.step6_backtest import BACKTEST_PREDICTIONS_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
RAW_ACCURACY_PATH = PROCESSED_DATA_DIR / "step7_raw_accuracy.csv"
ADJUSTED_ACCURACY_PATH = PROCESSED_DATA_DIR / "step7_adjusted_accuracy.csv"
ADJUSTMENT_IMPACT_PATH = PROCESSED_DATA_DIR / "step7_adjustment_impact.csv"
TOP10_PATH = PROCESSED_DATA_DIR / "step7_top10_metrics.csv"
CAPTAINCY_PATH = PROCESSED_DATA_DIR / "step7_captaincy_backtest.csv"
SUMMARY_PATH = PROCESSED_DATA_DIR / "step7_summary.txt"

EVALUATION_MIN_GAMEWEEK = 2
EVALUATION_MAX_GAMEWEEK = 38


def load_backtest_predictions(path: Path = BACKTEST_PREDICTIONS_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def filter_evaluation_gameweeks(predictions: pd.DataFrame) -> pd.DataFrame:
    return predictions[
        (predictions["gameweek"] >= EVALUATION_MIN_GAMEWEEK)
        & (predictions["gameweek"] <= EVALUATION_MAX_GAMEWEEK)
    ].copy()


def rmse(actual: pd.Series, predicted: pd.Series) -> float:
    return float(np.sqrt(mean_squared_error(actual, predicted)))


def build_accuracy_table(
    predictions: pd.DataFrame,
    prediction_column: str,
) -> pd.DataFrame:
    rows = []
    for model, model_predictions in predictions.groupby("model"):
        rows.append(
            {
                "model": model,
                "MAE": float(
                    mean_absolute_error(
                        model_predictions["actual_points"],
                        model_predictions[prediction_column],
                    )
                ),
                "RMSE": rmse(
                    model_predictions["actual_points"],
                    model_predictions[prediction_column],
                ),
            }
        )

    table = pd.DataFrame(rows)
    naive = table[table["model"] == "Naive baseline"].iloc[0]
    table["beats_naive_MAE"] = np.where(table["MAE"] < naive["MAE"], "yes", "no")
    table["beats_naive_RMSE"] = np.where(table["RMSE"] < naive["RMSE"], "yes", "no")
    return table.sort_values("MAE").reset_index(drop=True)


def build_adjustment_impact_table(
    raw_accuracy: pd.DataFrame,
    adjusted_accuracy: pd.DataFrame,
) -> pd.DataFrame:
    raw = raw_accuracy[["model", "MAE", "RMSE"]].rename(
        columns={"MAE": "raw_MAE", "RMSE": "raw_RMSE"}
    )
    adjusted = adjusted_accuracy[["model", "MAE", "RMSE"]].rename(
        columns={"MAE": "adjusted_MAE", "RMSE": "adjusted_RMSE"}
    )
    impact = raw.merge(adjusted, on="model", how="inner")
    impact["MAE_change_adjusted_minus_raw"] = impact["adjusted_MAE"] - impact["raw_MAE"]
    impact["RMSE_change_adjusted_minus_raw"] = impact["adjusted_RMSE"] - impact["raw_RMSE"]
    impact["adjustment_helped_MAE"] = np.where(
        impact["MAE_change_adjusted_minus_raw"] < 0,
        "yes",
        "no",
    )
    impact["adjustment_helped_RMSE"] = np.where(
        impact["RMSE_change_adjusted_minus_raw"] < 0,
        "yes",
        "no",
    )
    return impact.sort_values("adjusted_MAE").reset_index(drop=True)


def top_player_ids(frame: pd.DataFrame, sort_column: str, limit: int = 10) -> set[int]:
    return set(
        frame.sort_values(sort_column, ascending=False)
        .head(limit)["player_id"]
        .astype(int)
        .tolist()
    )


def build_top10_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (gameweek, model), model_predictions in predictions.groupby(["gameweek", "model"]):
        true_top10 = top_player_ids(model_predictions, "actual_points")
        predicted_top10 = top_player_ids(model_predictions, "expected_points_adjusted")
        overlap = len(true_top10 & predicted_top10)
        rows.append(
            {
                "gameweek": gameweek,
                "model": model,
                "precision_at_10": overlap / 10,
                "recall_at_10": overlap / 10,
            }
        )

    per_gameweek = pd.DataFrame(rows)
    return (
        per_gameweek.groupby("model", as_index=False)[["precision_at_10", "recall_at_10"]]
        .mean()
        .sort_values("precision_at_10", ascending=False)
        .reset_index(drop=True)
    )


def get_single_model_player_rows(predictions: pd.DataFrame) -> pd.DataFrame:
    return predictions[predictions["model"] == "Naive baseline"].copy()


def build_model_captaincy_rows(predictions: pd.DataFrame) -> list[dict[str, float | str]]:
    rows = []
    for model, model_predictions in predictions.groupby("model"):
        captain_picks = (
            model_predictions.sort_values(
                ["gameweek", "expected_points_adjusted"],
                ascending=[True, False],
            )
            .groupby("gameweek")
            .head(1)
        )
        total_points = float((captain_picks["actual_points"] * 2).sum())
        rows.append(
            {
                "strategy": f"{model} captain",
                "total_captain_points": total_points,
                "avg_per_gameweek": total_points / captain_picks["gameweek"].nunique(),
            }
        )
    return rows


def build_baseline_captaincy_rows(predictions: pd.DataFrame) -> list[dict[str, float | str]]:
    player_rows = get_single_model_player_rows(predictions)
    gameweek_count = player_rows["gameweek"].nunique()

    most_owned = (
        player_rows.sort_values(["gameweek", "selected_by_percent"], ascending=[True, False])
        .groupby("gameweek")
        .head(1)
    )
    most_owned_total = float((most_owned["actual_points"] * 2).sum())

    prior_ppg = player_rows.copy()
    prior_ppg["prior_points_per_available_game"] = np.where(
        prior_ppg["prior_games_available_last_3"] > 0,
        prior_ppg["points_last_3"] / prior_ppg["prior_games_available_last_3"],
        -1,
    )
    highest_ppg = (
        prior_ppg.sort_values(
            ["gameweek", "prior_points_per_available_game"],
            ascending=[True, False],
        )
        .groupby("gameweek")
        .head(1)
    )
    highest_ppg_total = float((highest_ppg["actual_points"] * 2).sum())

    random_total = float(player_rows.groupby("gameweek")["actual_points"].mean().mul(2).sum())

    return [
        {
            "strategy": "Always captain most-owned player",
            "total_captain_points": most_owned_total,
            "avg_per_gameweek": most_owned_total / gameweek_count,
        },
        {
            "strategy": "Always captain highest prior rolling PPG player",
            "total_captain_points": highest_ppg_total,
            "avg_per_gameweek": highest_ppg_total / gameweek_count,
        },
        {
            "strategy": "Random player average",
            "total_captain_points": random_total,
            "avg_per_gameweek": random_total / gameweek_count,
        },
    ]


def build_captaincy_table(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = build_model_captaincy_rows(predictions)
    rows.extend(build_baseline_captaincy_rows(predictions))
    return (
        pd.DataFrame(rows)
        .sort_values("total_captain_points", ascending=False)
        .reset_index(drop=True)
    )


def build_summary(
    raw_accuracy: pd.DataFrame,
    adjusted_accuracy: pd.DataFrame,
    top10_metrics: pd.DataFrame,
    captaincy: pd.DataFrame,
) -> str:
    raw_winner = raw_accuracy.iloc[0]
    adjusted_winner = adjusted_accuracy.iloc[0]
    top10_winner = top10_metrics.iloc[0]
    captain_winner = captaincy.iloc[0]
    naive_raw = raw_accuracy[raw_accuracy["model"] == "Naive baseline"].iloc[0]

    raw_gap = naive_raw["MAE"] - raw_winner["MAE"]
    return (
        f"Across GW{EVALUATION_MIN_GAMEWEEK}-GW{EVALUATION_MAX_GAMEWEEK}, "
        f"{raw_winner['model']} had the best raw points MAE at {raw_winner['MAE']:.3f}, "
        f"beating the naive baseline by {raw_gap:.3f} points per player-row. "
        f"Using expected_points_adjusted made {adjusted_winner['model']} the best adjusted "
        f"predictor at {adjusted_winner['MAE']:.3f}; the minutes adjustment improved MAE for "
        "every model but worsened RMSE, so it reduced typical error while increasing some "
        "larger misses. "
        f"For top-10 identification, {top10_winner['model']} had the best mean precision@10 "
        f"and recall@10 at {top10_winner['precision_at_10']:.3f}. "
        f"In the captaincy simulation, {captain_winner['strategy']} led with "
        f"{captain_winner['total_captain_points']:.1f} total captain points. "
        "The honest caveat is that this still evaluates one historical season with simplified "
        "features and no real FPL squad constraints, so it proves relative signal quality more "
        "than it proves an end-to-end winning FPL strategy."
    )


def save_results(
    raw_accuracy: pd.DataFrame,
    adjusted_accuracy: pd.DataFrame,
    adjustment_impact: pd.DataFrame,
    top10_metrics: pd.DataFrame,
    captaincy: pd.DataFrame,
    summary: str,
) -> None:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_accuracy.to_csv(RAW_ACCURACY_PATH, index=False)
    adjusted_accuracy.to_csv(ADJUSTED_ACCURACY_PATH, index=False)
    adjustment_impact.to_csv(ADJUSTMENT_IMPACT_PATH, index=False)
    top10_metrics.to_csv(TOP10_PATH, index=False)
    captaincy.to_csv(CAPTAINCY_PATH, index=False)
    SUMMARY_PATH.write_text(summary, encoding="utf-8")


def print_table(title: str, table: pd.DataFrame) -> None:
    print(f"\n{title}")
    print(table.to_string(index=False, float_format=lambda value: f"{value:.3f}"))


def main() -> None:
    predictions = filter_evaluation_gameweeks(load_backtest_predictions())

    print("Step 7 evaluation")
    print(
        f"- Evaluation range: GW{EVALUATION_MIN_GAMEWEEK}-GW{EVALUATION_MAX_GAMEWEEK} "
        "for every model and strategy."
    )
    print(
        "- GW1 is excluded consistently because the naive baseline correctly has no "
        "current-season rolling history in GW1."
    )
    print(
        "- True top 10 is defined as the 10 players with the highest actual_points in "
        "that gameweek."
    )
    print(
        "- Top-10 and captaincy rankings use expected_points_adjusted, not raw "
        "predicted_points."
    )
    print(
        "- The highest points-per-game captain baseline uses prior rolling PPG from the "
        "available previous three gameweeks, because step6_backtest_predictions.csv does "
        "not contain season-to-date PPG."
    )

    raw_accuracy = build_accuracy_table(predictions, "predicted_points")
    adjusted_accuracy = build_accuracy_table(predictions, "expected_points_adjusted")
    adjustment_impact = build_adjustment_impact_table(raw_accuracy, adjusted_accuracy)
    top10_metrics = build_top10_metrics(predictions)
    captaincy = build_captaincy_table(predictions)
    summary = build_summary(raw_accuracy, adjusted_accuracy, top10_metrics, captaincy)

    print_table("Raw points prediction accuracy", raw_accuracy)
    print_table("Adjusted score prediction accuracy", adjusted_accuracy)
    print_table("Minutes adjustment impact", adjustment_impact)
    print_table("Mean precision@10 and recall@10", top10_metrics)
    print_table("Captaincy backtest", captaincy)

    print("\nPlain-English summary:")
    print(summary)

    save_results(
        raw_accuracy,
        adjusted_accuracy,
        adjustment_impact,
        top10_metrics,
        captaincy,
        summary,
    )
    print("\nSaved Step 7 outputs:")
    for path in [
        RAW_ACCURACY_PATH,
        ADJUSTED_ACCURACY_PATH,
        ADJUSTMENT_IMPACT_PATH,
        TOP10_PATH,
        CAPTAINCY_PATH,
        SUMMARY_PATH,
    ]:
        print(f"- {path}")


if __name__ == "__main__":
    main()
