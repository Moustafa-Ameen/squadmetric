import numpy as np
import pandas as pd

from squadmetric.step4_models import (
    FEATURE_COLUMNS,
    fit_minutes_band_conditional_model,
    minutes_band,
)


def _training_rows() -> pd.DataFrame:
    rows = []
    for band, minutes in enumerate((0, 30, 90)):
        for index in range(5):
            rows.append(
                {
                    "price_before_deadline": 5.0 + band + index / 10,
                    "minutes_last_3": 30.0 * band + index,
                    "points_last_3": float(index + band),
                    "opponent_strength": 1000.0 + 100 * band,
                    "selected_by_percent_before_deadline": 5.0 + index,
                    "market_snapshot_available": 1.0,
                    "position": ("GK", "DEF", "MID", "FWD", "MID")[index],
                    "home_or_away": "H" if index % 2 else "A",
                    "minutes": minutes,
                    "next_gameweek_points": float(index + 3 * band),
                }
            )
    return pd.DataFrame(rows)


def test_minutes_band_model_has_three_classes_and_conditional_expectation():
    training = _training_rows()
    model = fit_minutes_band_conditional_model(training)
    probabilities = model.predict_proba(training[FEATURE_COLUMNS])
    conditional_points = model.predict_conditional_points(training[FEATURE_COLUMNS])

    assert probabilities.shape == (len(training), 3)
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert set(minutes_band(training["minutes"])) == {0, 1, 2}
    assert np.allclose(
        model.predict_expected_points(training[FEATURE_COLUMNS]),
        (probabilities * conditional_points).sum(axis=1),
    )


def test_minutes_band_calibration_diagnostics_cover_all_classes():
    training = _training_rows()
    model = fit_minutes_band_conditional_model(training)
    probabilities = model.predict_proba(training[FEATURE_COLUMNS])
    actual = minutes_band(training["minutes"])

    from squadmetric.step4_models import build_minutes_calibration_table

    calibration = build_minutes_calibration_table(actual, probabilities)
    assert calibration["band"].tolist() == ["0", "1-59", "60+"]
    assert calibration["support"].tolist() == [5, 5, 5]
    assert calibration["brier_score"].notna().all()
