import pandas as pd

from squadmetric.step7_evaluation import build_accuracy_table, filter_evaluation_gameweeks


def test_filter_evaluation_gameweeks_excludes_gw1():
    predictions = pd.DataFrame({"gameweek": [1, 2, 38, 39]})

    filtered = filter_evaluation_gameweeks(predictions)

    assert filtered["gameweek"].tolist() == [2, 38]


def test_build_accuracy_table_marks_models_that_beat_naive():
    predictions = pd.DataFrame(
        {
            "model": ["Naive baseline", "Naive baseline", "Better model", "Better model"],
            "actual_points": [1, 3, 1, 3],
            "predicted_points": [0, 4, 1, 3],
        }
    )

    table = build_accuracy_table(predictions, "predicted_points")
    better = table[table["model"] == "Better model"].iloc[0]

    assert better["beats_naive_MAE"] == "yes"
    assert better["beats_naive_RMSE"] == "yes"
