from __future__ import annotations

import math

import numpy as np
import pandas as pd


def threshold_metrics(y_true, probabilities, threshold: float) -> dict[str, float]:
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        fbeta_score,
        precision_score,
        recall_score,
    )

    predictions = (np.asarray(probabilities) >= threshold).astype(int)
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "f2": float(fbeta_score(y_true, predictions, beta=2, zero_division=0)),
        "accuracy_diagnostic_only": float(accuracy_score(y_true, predictions)),
        "alert_rate": float(predictions.mean()),
    }


def probability_metrics(y_true, probabilities) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    y = np.asarray(y_true)
    p = np.asarray(probabilities)
    return {
        "average_precision": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else math.nan,
        "brier_score": float(brier_score_loss(y, p)),
    }


def classification_metrics(y_true, probabilities, threshold: float) -> dict[str, float]:
    return {
        **probability_metrics(y_true, probabilities),
        **threshold_metrics(y_true, probabilities, threshold),
        "rows": int(len(y_true)),
        "positives": int(np.asarray(y_true).sum()),
        "positive_rate": float(np.asarray(y_true).mean()),
    }


def fold_summary(metrics_by_fold: pd.DataFrame) -> dict[str, float]:
    numeric = metrics_by_fold.select_dtypes(include="number")
    result: dict[str, float] = {}
    for column in numeric.columns:
        if column in {"fold", "rows", "positives"}:
            continue
        result[f"mean_{column}"] = float(numeric[column].mean())
        result[f"std_{column}"] = float(numeric[column].std(ddof=0))
    result["folds"] = int(len(metrics_by_fold))
    return result

