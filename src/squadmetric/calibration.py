"""Standalone calibration and uncertainty diagnostics for M10 models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.stats import poisson
from sklearn.isotonic import IsotonicRegression

CALIBRATION_VERSION = "m10-calibration-v1"


@dataclass
class ProbabilityCalibrator:
    """Optional monotonic calibration fit only on a pre-declared training set."""

    model: IsotonicRegression | None
    training_cutoff: str
    fitted_sample_count: int
    version: str = CALIBRATION_VERSION

    def predict(self, probabilities: np.ndarray | list[float]) -> np.ndarray:
        values = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
        if self.model is None:
            return values
        return np.clip(self.model.predict(values), 0.0, 1.0)


def fit_probability_calibrator(
    actual: np.ndarray | pd.Series,
    predicted_probability: np.ndarray | pd.Series,
    *,
    training_cutoff: str,
    min_samples: int = 30,
) -> ProbabilityCalibrator:
    """Fit isotonic calibration, falling back to identity for sparse samples."""

    observed = np.asarray(actual, dtype=float)
    predicted = np.clip(np.asarray(predicted_probability, dtype=float), 0.0, 1.0)
    if observed.shape != predicted.shape:
        raise ValueError("actual and predicted_probability must have the same shape")
    valid = np.isfinite(observed) & np.isfinite(predicted)
    observed = np.clip(observed[valid], 0.0, 1.0)
    predicted = predicted[valid]
    model: IsotonicRegression | None = None
    if len(predicted) >= min_samples and len(np.unique(predicted)) >= 3:
        model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        model.fit(predicted, observed)
    return ProbabilityCalibrator(model, training_cutoff, int(len(predicted)))


def binary_calibration_report(
    actual: np.ndarray | pd.Series,
    predicted_probability: np.ndarray | pd.Series,
    *,
    bins: int = 10,
) -> dict[str, Any]:
    """Return Brier/log-loss and a reliability table for a binary event."""

    observed = np.asarray(actual, dtype=float)
    predicted = np.clip(np.asarray(predicted_probability, dtype=float), 1e-8, 1 - 1e-8)
    if observed.shape != predicted.shape:
        raise ValueError("actual and predicted_probability must have the same shape")
    valid = np.isfinite(observed) & np.isfinite(predicted)
    observed = np.clip(observed[valid], 0.0, 1.0)
    predicted = predicted[valid]
    if not len(predicted):
        return {
            "sample_count": 0,
            "brier_score": math.nan,
            "log_loss": math.nan,
            "reliability": pd.DataFrame(),
        }
    edges = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.minimum(np.digitize(predicted, edges[1:-1], right=False), bins - 1)
    rows = []
    for index in range(bins):
        mask = bucket == index
        if not mask.any():
            continue
        rows.append(
            {
                "bin": index,
                "lower_probability": float(edges[index]),
                "upper_probability": float(edges[index + 1]),
                "support": int(mask.sum()),
                "predicted_mean": float(predicted[mask].mean()),
                "observed_rate": float(observed[mask].mean()),
                "absolute_calibration_error": float(
                    abs(predicted[mask].mean() - observed[mask].mean())
                ),
            }
        )
    return {
        "sample_count": int(len(predicted)),
        "brier_score": float(np.mean((predicted - observed) ** 2)),
        "log_loss": float(
            -np.mean(observed * np.log(predicted) + (1 - observed) * np.log(1 - predicted))
        ),
        "reliability": pd.DataFrame(rows),
    }


def poisson_calibration_report(
    actual_goals: np.ndarray | pd.Series,
    predicted_goals: np.ndarray | pd.Series,
    *,
    interval_coverage: float = 0.8,
) -> dict[str, float | int]:
    """Return point-error, Poisson log loss, and central interval coverage."""

    actual = np.asarray(actual_goals, dtype=float)
    predicted = np.maximum(np.asarray(predicted_goals, dtype=float), 1e-8)
    if actual.shape != predicted.shape:
        raise ValueError("actual_goals and predicted_goals must have the same shape")
    valid = np.isfinite(actual) & np.isfinite(predicted)
    actual = np.maximum(actual[valid], 0.0)
    predicted = predicted[valid]
    if not len(actual):
        return {
            "sample_count": 0,
            "mae": math.nan,
            "rmse": math.nan,
            "poisson_log_loss": math.nan,
            "interval_coverage": math.nan,
        }
    alpha = (1.0 - interval_coverage) / 2.0
    lower = poisson.ppf(alpha, predicted)
    upper = poisson.ppf(1.0 - alpha, predicted)
    return {
        "sample_count": int(len(actual)),
        "mae": float(np.mean(np.abs(actual - predicted))),
        "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
        "poisson_log_loss": float(
            np.mean(predicted - actual * np.log(predicted) + gammaln(actual + 1))
        ),
        "interval_coverage": float(np.mean((actual >= lower) & (actual <= upper))),
    }
