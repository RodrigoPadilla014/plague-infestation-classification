from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def save_shap_artifacts(estimator, X, output_dir: str, sample_size: int, seed: int) -> None:
    import shap

    sample = X.sample(min(sample_size, len(X)), random_state=seed)
    explainer = shap.TreeExplainer(estimator)
    values = explainer.shap_values(sample)
    if isinstance(values, list):
        values = values[-1]
    values = np.asarray(values)
    global_importance = pd.DataFrame(
        {
            "feature": sample.columns,
            "mean_abs_shap": np.abs(values).mean(axis=0),
        }
    ).sort_values("mean_abs_shap", ascending=False)
    output = Path(output_dir)
    global_importance.to_csv(output / "shap_global_importance.csv", index=False)

