from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from config import RunConfig


@dataclass
class FeatureSchema:
    feature_columns: list[str]
    categorical_columns: list[str]
    numeric_columns: list[str]
    metadata_columns: list[str]
    excluded_columns: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_feature_schema(df: pd.DataFrame, config: RunConfig) -> FeatureSchema:
    reserved = {
        config.target_column,
        config.row_id_column,
        config.period_column,
        config.date_column,
        *config.metadata_columns,
        *config.exclude_features,
    }
    feature_columns = [column for column in df.columns if column not in reserved]
    categorical = [column for column in config.categorical_columns if column in feature_columns]
    numeric = [column for column in feature_columns if column not in categorical]
    non_numeric = [
        column
        for column in numeric
        if not pd.api.types.is_numeric_dtype(df[column])
    ]
    if non_numeric:
        raise ValueError(
            "Non-numeric feature columns must be declared categorical: "
            f"{sorted(non_numeric)}"
        )
    return FeatureSchema(
        feature_columns=feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
        metadata_columns=[
            column
            for column in [
                config.row_id_column,
                config.period_column,
                config.date_column,
                *config.metadata_columns,
            ]
            if column in df.columns
        ],
        excluded_columns=sorted(reserved),
    )

