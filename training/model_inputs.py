from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from feature_schema import FeatureSchema

MISSING_CATEGORY = "__MISSING__"


@dataclass
class PreparedInputs:
    train: pd.DataFrame
    validation: pd.DataFrame
    categorical_columns: list[str]


def _clean_numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.replace([np.inf, -np.inf], np.nan, inplace=True)


def prepare_model_inputs(
    X_train: pd.DataFrame,
    X_validation: pd.DataFrame,
    schema: FeatureSchema,
    model: str,
) -> PreparedInputs:
    train = X_train[schema.feature_columns].copy()
    validation = X_validation[schema.feature_columns].copy()
    _clean_numeric(train, schema.numeric_columns)
    _clean_numeric(validation, schema.numeric_columns)

    for column in schema.categorical_columns:
        train[column] = train[column].astype("string").fillna(MISSING_CATEGORY)
        validation[column] = validation[column].astype("string").fillna(MISSING_CATEGORY)
        if model in {"lightgbm", "xgboost"}:
            # The union aligns internal category codes without learning category
            # frequencies or target statistics from validation.
            categories = pd.Index(train[column]).append(
                pd.Index(validation[column])
            ).unique().tolist()
            dtype = pd.CategoricalDtype(categories=categories)
            train[column] = train[column].astype(dtype)
            validation[column] = validation[column].astype(dtype)

    return PreparedInputs(train, validation, schema.categorical_columns)

