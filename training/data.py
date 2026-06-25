from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import RunConfig


def load_dataset(path: str) -> pd.DataFrame:
    dataset_path = Path(path)
    if dataset_path.is_dir():
        parts = sorted(dataset_path.glob("*.parquet"))
        if not parts:
            raise FileNotFoundError(f"No parquet parts found in {dataset_path}")
        return pd.concat((pd.read_parquet(part) for part in parts), ignore_index=True)
    if not dataset_path.exists():
        raise FileNotFoundError(dataset_path)
    if dataset_path.suffix.lower() == ".parquet":
        return pd.read_parquet(dataset_path)
    if dataset_path.suffix.lower() == ".csv":
        return pd.read_csv(dataset_path, low_memory=False)
    raise ValueError("Dataset must be a parquet file, parquet directory, or CSV file")


def validate_dataset(df: pd.DataFrame, config: RunConfig) -> pd.DataFrame:
    required = {
        config.row_id_column,
        config.period_column,
        config.target_column,
        *config.categorical_columns,
        *config.metadata_columns,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    if df[config.row_id_column].isna().any():
        raise ValueError(f"{config.row_id_column} contains missing values")
    if df[config.row_id_column].duplicated().any():
        raise ValueError(f"{config.row_id_column} must uniquely identify prediction rows")

    labeled_periods = set(config.train_periods) | set(config.evaluation_periods)
    labeled = df[df[config.period_column].astype(str).isin(labeled_periods)]
    target = pd.to_numeric(labeled[config.target_column], errors="coerce")
    if target.isna().any():
        raise ValueError("Training/evaluation rows contain missing or non-numeric targets")
    invalid = sorted(set(target.unique()) - {0, 1})
    if invalid:
        raise ValueError(f"Target must be binary 0/1; found {invalid}")

    present_periods = set(df[config.period_column].dropna().astype(str))
    requested = labeled_periods | set(config.scoring_periods)
    missing_periods = sorted(requested - present_periods)
    if missing_periods:
        raise ValueError(f"Requested periods are absent from the dataset: {missing_periods}")

    forbidden_present = sorted(set(config.forbidden_columns) & set(df.columns))
    if forbidden_present:
        raise ValueError(f"Forbidden columns are present: {forbidden_present}")
    return df.copy()

