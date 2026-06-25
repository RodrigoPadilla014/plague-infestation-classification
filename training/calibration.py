from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TemporalPostprocessingSplit:
    calibration_periods: tuple[str, ...]
    threshold_period: str

    def to_dict(self) -> dict:
        return asdict(self)


def temporal_postprocessing_split(
    oof_predictions: pd.DataFrame,
    period_column: str,
    ordered_validation_periods: list[str],
    calibration_method: str,
) -> TemporalPostprocessingSplit:
    present = set(oof_predictions[period_column].astype(str))
    ordered_present = [
        str(period) for period in ordered_validation_periods if str(period) in present
    ]
    if not ordered_present:
        raise ValueError("No OOF validation periods are available for post-processing")
    if len(ordered_present) == 1:
        if calibration_method != "none":
            raise ValueError(
                "Time-ordered calibration requires at least two OOF validation "
                "periods: earlier period(s) to fit calibration and a later period "
                "to select the threshold."
            )
        return TemporalPostprocessingSplit((), ordered_present[0])
    calibration_periods = (
        tuple(ordered_present[:-1]) if calibration_method != "none" else ()
    )
    return TemporalPostprocessingSplit(
        calibration_periods=calibration_periods,
        threshold_period=ordered_present[-1],
    )


class ProbabilityCalibrator:
    def __init__(self, method: str):
        self.method = method
        self.model = None

    def fit(self, probabilities, y_true) -> "ProbabilityCalibrator":
        if self.method == "none":
            return self
        p = np.asarray(probabilities, dtype=float).reshape(-1, 1)
        y = np.asarray(y_true, dtype=int)
        if len(np.unique(y)) < 2:
            raise ValueError(
                f"{self.method} calibration requires both target classes in the "
                "earlier OOF calibration periods"
            )
        if self.method == "sigmoid":
            from sklearn.linear_model import LogisticRegression

            self.model = LogisticRegression(random_state=42).fit(p, y)
        elif self.method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            self.model = IsotonicRegression(out_of_bounds="clip").fit(p.ravel(), y)
        else:
            raise ValueError(f"Unknown calibration method: {self.method}")
        return self

    def predict(self, probabilities):
        p = np.asarray(probabilities, dtype=float)
        if self.method == "none":
            return p
        if self.method == "sigmoid":
            return self.model.predict_proba(p.reshape(-1, 1))[:, 1]
        return self.model.predict(p)

