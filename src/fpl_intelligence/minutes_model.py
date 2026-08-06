"""Stable, importable model classes used by persisted planner artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class MinutesBandConditionalModel:
    """Minutes-band probabilities plus conditional point expectations.

    This class deliberately lives outside an executable training module. Joblib
    artifacts therefore reference ``fpl_intelligence.minutes_model`` instead of
    ``__main__`` and remain loadable by FastAPI.
    """

    classifier: Any | None
    fallback_probabilities: np.ndarray
    band_point_models: dict[int, Any | None]
    conditional_point_means: dict[int, float]

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        probabilities = np.tile(self.fallback_probabilities, (len(features), 1))
        if self.classifier is None:
            return probabilities

        probabilities = np.zeros((len(features), 3), dtype=float)
        raw = self.classifier.predict_proba(features)
        for column, label in enumerate(self.classifier.classes_):
            probabilities[:, int(label)] = raw[:, column]
        return probabilities

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return self.predict_proba(features).argmax(axis=1)

    def predict_conditional_points(self, features: pd.DataFrame) -> np.ndarray:
        predictions = np.zeros((len(features), 3), dtype=float)
        for band in range(3):
            model = self.band_point_models.get(band)
            if model is None:
                predictions[:, band] = self.conditional_point_means.get(band, 0.0)
            else:
                predictions[:, band] = model.predict(features)
        return predictions

    def predict_expected_points(self, features: pd.DataFrame) -> np.ndarray:
        probabilities = self.predict_proba(features)
        conditional_points = self.predict_conditional_points(features)
        return (probabilities * conditional_points).sum(axis=1)
