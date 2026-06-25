from __future__ import annotations

import numpy as np
import pandas as pd

from config import RunConfig
from feature_schema import FeatureSchema
from metrics import classification_metrics
from model_inputs import prepare_model_inputs
from models import (
    build_model,
    default_params,
    fit_model,
    imbalance_params,
    predict_probabilities,
    suggest_params,
)
from splits import WalkForwardFold


def objective_value(metrics: pd.DataFrame, metric: str, stability_penalty: float) -> float:
    mean = float(metrics[metric].mean())
    std = float(metrics[metric].std(ddof=0))
    return mean - stability_penalty * std


def cross_validated_predictions(
    df: pd.DataFrame,
    schema: FeatureSchema,
    folds: list[WalkForwardFold],
    config: RunConfig,
    params: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prediction_rows = []
    metric_rows = []
    for fold in folds:
        prepared = prepare_model_inputs(
            df.loc[fold.train_index],
            df.loc[fold.validation_index],
            schema,
            config.model,
        )
        y_train = pd.to_numeric(df.loc[fold.train_index, config.target_column]).astype(int)
        y_validation = pd.to_numeric(
            df.loc[fold.validation_index, config.target_column]
        ).astype(int)
        resolved_params = {
            **default_params(config.model, config.random_seed),
            **params,
            **imbalance_params(config.model, y_train, config.imbalance),
        }
        estimator = build_model(config.model, resolved_params)
        fit_model(
            estimator,
            config.model,
            prepared.train,
            y_train,
            prepared.validation,
            y_validation,
            prepared.categorical_columns,
            config.early_stopping_rounds,
        )
        probabilities = predict_probabilities(estimator, prepared.validation)
        fold_metrics = classification_metrics(y_validation, probabilities, 0.5)
        metric_rows.append(
            {
                "fold": fold.number,
                "validation_period": fold.validation_period,
                **fold_metrics,
            }
        )
        metadata_columns = schema.metadata_columns
        predictions = df.loc[fold.validation_index, metadata_columns].copy()
        predictions["fold"] = fold.number
        predictions["actual_target"] = y_validation.to_numpy()
        predictions["predicted_probability"] = probabilities
        prediction_rows.append(predictions)
    return (
        pd.concat(prediction_rows, ignore_index=True),
        pd.DataFrame(metric_rows),
    )


def run_optuna(
    df: pd.DataFrame,
    schema: FeatureSchema,
    folds: list[WalkForwardFold],
    config: RunConfig,
):
    import optuna

    def objective(trial):
        params = suggest_params(trial, config.model)
        _, fold_metrics = cross_validated_predictions(df, schema, folds, config, params)
        return objective_value(
            fold_metrics,
            config.objective_metric,
            config.stability_penalty,
        )

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=config.optuna_trials)
    return study.best_params, study.trials_dataframe(), study

