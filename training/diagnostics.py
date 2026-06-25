from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import RunConfig
from feature_schema import FeatureSchema
from splits import WalkForwardFold


def run_diagnostics(
    df: pd.DataFrame,
    schema: FeatureSchema,
    folds: list[WalkForwardFold],
    config: RunConfig,
    output_dir: str,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    train_mask = df[config.period_column].astype(str).isin(config.train_periods)
    train = df.loc[train_mask]

    balance = (
        train.assign(_target=pd.to_numeric(train[config.target_column]))
        .groupby(config.period_column, dropna=False)["_target"]
        .agg(rows="size", positives="sum", positive_rate="mean")
        .reset_index()
    )
    balance.to_csv(output / "class_balance_by_period.csv", index=False)

    missing = pd.DataFrame(
        {
            "feature": schema.feature_columns,
            "missing_count": [int(train[column].isna().sum()) for column in schema.feature_columns],
            "missing_rate": [float(train[column].isna().mean()) for column in schema.feature_columns],
            "dtype": [str(train[column].dtype) for column in schema.feature_columns],
        }
    ).sort_values(["missing_rate", "feature"], ascending=[False, True])
    missing.to_csv(output / "feature_missingness.csv", index=False)

    category_rows = []
    for column in schema.categorical_columns:
        counts = train[column].astype("string").fillna("__MISSING__").value_counts(dropna=False)
        category_rows.append(
            {
                "feature": column,
                "categories": int(len(counts)),
                "rare_categories_below_1pct": int((counts / len(train) < 0.01).sum()),
                "most_common_rate": float(counts.iloc[0] / len(train)) if len(train) else np.nan,
            }
        )
    pd.DataFrame(category_rows).to_csv(output / "categorical_cardinality.csv", index=False)

    numeric = train[schema.numeric_columns].replace([np.inf, -np.inf], np.nan)
    if not numeric.empty:
        numeric.describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).T.reset_index(
            names="feature"
        ).to_csv(output / "numeric_distributions.csv", index=False)
        numeric.corr(method="spearman").to_csv(output / "spearman_correlation.csv")

    fold_rows = []
    for fold in folds:
        y_train = pd.to_numeric(df.loc[fold.train_index, config.target_column])
        y_validation = pd.to_numeric(df.loc[fold.validation_index, config.target_column])
        fold_rows.append(
            {
                "fold": fold.number,
                "train_periods": ",".join(fold.train_periods),
                "validation_period": fold.validation_period,
                "train_rows": int(len(y_train)),
                "train_positives": int(y_train.sum()),
                "train_positive_rate": float(y_train.mean()),
                "validation_rows": int(len(y_validation)),
                "validation_positives": int(y_validation.sum()),
                "validation_positive_rate": float(y_validation.mean()),
                "viable_two_class_train": bool(y_train.nunique() == 2),
                "viable_two_class_validation": bool(y_validation.nunique() == 2),
            }
        )
    pd.DataFrame(fold_rows).to_csv(output / "walk_forward_fold_diagnostics.csv", index=False)

