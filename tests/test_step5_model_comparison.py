from squadmetric.step5_model_comparison import RegressionModelResult, build_comparison_table


def test_build_comparison_table_marks_naive_beats_correctly():
    results = [
        RegressionModelResult("Naive baseline", None, [], 1.0, 2.0),
        RegressionModelResult("Better model", None, [], 0.9, 1.9),
        RegressionModelResult("Worse model", None, [], 1.1, 2.1),
    ]

    comparison = build_comparison_table(results)
    better = comparison[comparison["model"] == "Better model"].iloc[0]
    worse = comparison[comparison["model"] == "Worse model"].iloc[0]

    assert better["beats_naive_MAE"] == "yes"
    assert better["beats_naive_RMSE"] == "yes"
    assert worse["beats_naive_MAE"] == "no"
    assert worse["beats_naive_RMSE"] == "no"
