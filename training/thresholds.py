from __future__ import annotations

import numpy as np
import pandas as pd

from metrics import threshold_metrics


def threshold_sweep(y_true, probabilities) -> pd.DataFrame:
    thresholds = np.unique(
        np.concatenate(
            [
                np.linspace(0.01, 0.99, 99),
                np.asarray(probabilities, dtype=float),
            ]
        )
    )
    return pd.DataFrame(
        threshold_metrics(y_true, probabilities, float(threshold))
        for threshold in thresholds
    ).sort_values("threshold")


def choose_threshold(
    sweep: pd.DataFrame,
    strategy: str,
    fixed_threshold: float,
    minimum_recall: float,
) -> float:
    if strategy == "fixed":
        return float(fixed_threshold)
    if strategy == "f2":
        best = sweep.sort_values(["f2", "precision"], ascending=False).iloc[0]
        return float(best["threshold"])
    if strategy == "recall_constraint":
        eligible = sweep[sweep["recall"] >= minimum_recall]
        if eligible.empty:
            return float(sweep.sort_values("recall", ascending=False).iloc[0]["threshold"])
        best = eligible.sort_values(["precision", "threshold"], ascending=False).iloc[0]
        return float(best["threshold"])
    raise ValueError(f"Unknown threshold strategy: {strategy}")

