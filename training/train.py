from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

from artifacts import save_run_metadata, write_json
from calibration import (
    ProbabilityCalibrator,
    temporal_postprocessing_split,
)
from config import RunConfig, parse_config
from data import load_dataset, validate_dataset
from diagnostics import run_diagnostics
from feature_schema import resolve_feature_schema
from metrics import classification_metrics, fold_summary
from model_inputs import prepare_model_inputs
from models import (
    build_model,
    default_params,
    fit_final_model,
    fit_model,
    imbalance_params,
    predict_probabilities,
    save_model,
)
from shap_utils import save_shap_artifacts
from splits import walk_forward_splits
from thresholds import choose_threshold, threshold_sweep
from tracking import Tracker
from tuning import cross_validated_predictions, run_optuna


def log(message: str) -> None:
    print(message, flush=True)


def period_index(df: pd.DataFrame, config: RunConfig, periods: list[str]) -> pd.Index:
    return df.index[df[config.period_column].astype(str).isin(periods)]


def final_fit_and_evaluate(
    df: pd.DataFrame,
    schema,
    config: RunConfig,
    params: dict,
    calibrator: ProbabilityCalibrator,
    threshold: float,
):
    if not config.evaluation_periods:
        return None, pd.DataFrame(), {}
    train_index = period_index(df, config, config.train_periods)
    evaluation_index = period_index(df, config, config.evaluation_periods)
    prepared = prepare_model_inputs(
        df.loc[train_index],
        df.loc[evaluation_index],
        schema,
        config.model,
    )
    y_train = pd.to_numeric(df.loc[train_index, config.target_column]).astype(int)
    y_evaluation = pd.to_numeric(
        df.loc[evaluation_index, config.target_column]
    ).astype(int)
    resolved_params = {
        **default_params(config.model, config.random_seed),
        **params,
        **imbalance_params(config.model, y_train, config.imbalance),
    }
    estimator = build_model(config.model, resolved_params)
    fit_final_model(
        estimator,
        config.model,
        prepared.train,
        y_train,
        prepared.categorical_columns,
    )
    raw_probabilities = predict_probabilities(estimator, prepared.validation)
    probabilities = calibrator.predict(raw_probabilities)
    metrics = classification_metrics(y_evaluation, probabilities, threshold)
    predictions = df.loc[evaluation_index, schema.metadata_columns].copy()
    predictions["actual_target"] = y_evaluation.to_numpy()
    predictions["predicted_probability_raw"] = raw_probabilities
    predictions["predicted_probability"] = probabilities
    predictions["predicted_class"] = (probabilities >= threshold).astype(int)
    return estimator, predictions, metrics


def run(config: RunConfig) -> None:
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    Path(config.model_dir).mkdir(parents=True, exist_ok=True)
    log(f"Loading dataset: {config.dataset}")
    df = validate_dataset(load_dataset(config.dataset), config)
    schema = resolve_feature_schema(df, config)
    folds = walk_forward_splits(
        df[config.period_column],
        config.train_periods,
        config.min_train_periods,
    )
    save_run_metadata(config, schema, folds)

    with Tracker(config) as tracker:
        tracker.log_config(schema, folds)

        if config.stage == "diagnostics":
            log("Running model-independent diagnostics")
            run_diagnostics(df, schema, folds, config, config.output_dir)
            tracker.log_artifacts(config.output_dir)
            log("Diagnostics complete")
            return

        params = dict(config.fixed_params)
        if config.stage == "optuna":
            log(f"Tuning one model: {config.model}")
            params, trials, _ = run_optuna(df, schema, folds, config)
            trials.to_csv(Path(config.output_dir) / "optuna_trials.csv", index=False)
            write_json(Path(config.output_dir) / "best_params.json", params)
            tracker.log_best_params(params)
        else:
            log(f"Running baseline for one model: {config.model}")

        oof, fold_metrics = cross_validated_predictions(df, schema, folds, config, params)
        tracker.log_fold_metrics(fold_metrics)

        validation_periods = [fold.validation_period for fold in folds]
        postprocessing_split = temporal_postprocessing_split(
            oof,
            config.period_column,
            validation_periods,
            config.calibration,
        )
        calibration_mask = oof[config.period_column].astype(str).isin(
            postprocessing_split.calibration_periods
        )
        threshold_mask = (
            oof[config.period_column].astype(str)
            == postprocessing_split.threshold_period
        )

        calibrator = ProbabilityCalibrator(config.calibration)
        if config.calibration != "none":
            calibrator.fit(
                oof.loc[calibration_mask, "predicted_probability"],
                oof.loc[calibration_mask, "actual_target"],
            )

        oof["predicted_probability_raw"] = oof["predicted_probability"]
        oof["predicted_probability"] = calibrator.predict(
            oof["predicted_probability_raw"]
        )
        oof["postprocessing_role"] = "model_validation_only"
        oof.loc[calibration_mask, "postprocessing_role"] = "calibration_fit"
        oof.loc[threshold_mask, "postprocessing_role"] = "threshold_selection"

        threshold_rows = oof.loc[threshold_mask]
        sweep = threshold_sweep(
            threshold_rows["actual_target"],
            threshold_rows["predicted_probability"],
        )
        threshold = choose_threshold(
            sweep,
            config.threshold_strategy,
            config.fixed_threshold,
            config.minimum_recall,
        )
        oof["predicted_class"] = (oof["predicted_probability"] >= threshold).astype(int)
        oof.to_csv(Path(config.output_dir) / "out_of_fold_predictions.csv", index=False)
        fold_metrics.to_csv(Path(config.output_dir) / "walk_forward_metrics.csv", index=False)
        sweep.to_csv(Path(config.output_dir) / "threshold_sweep.csv", index=False)

        summary = fold_summary(fold_metrics)
        write_json(Path(config.output_dir) / "walk_forward_summary.json", summary)
        write_json(Path(config.output_dir) / "selected_threshold.json", {"threshold": threshold})
        write_json(
            Path(config.output_dir) / "temporal_postprocessing_split.json",
            {
                **postprocessing_split.to_dict(),
                "calibration_method": config.calibration,
                "threshold_strategy": config.threshold_strategy,
                "calibration_rows": int(calibration_mask.sum()),
                "threshold_selection_rows": int(threshold_mask.sum()),
                "threshold_selection_metrics": classification_metrics(
                    threshold_rows["actual_target"],
                    threshold_rows["predicted_probability"],
                    threshold,
                ),
            },
        )
        tracker.log_oof_summary(summary)
        tracker.log_postprocessing(threshold, len(postprocessing_split.calibration_periods))

        estimator, evaluation_predictions, evaluation_metrics = final_fit_and_evaluate(
            df,
            schema,
            config,
            params,
            calibrator,
            threshold,
        )
        if estimator is not None:
            evaluation_predictions.to_csv(
                Path(config.output_dir) / "evaluation_predictions.csv",
                index=False,
            )
            write_json(Path(config.output_dir) / "evaluation_metrics.json", evaluation_metrics)
            save_model(estimator, config.model, config.model_dir)
            with (Path(config.model_dir) / "calibrator.pkl").open("wb") as handle:
                pickle.dump(calibrator, handle)
            write_json(
                Path(config.model_dir) / "serving_config.json",
                {
                    "model": config.model,
                    "threshold": threshold,
                    "calibration": config.calibration,
                    "calibration_periods": postprocessing_split.calibration_periods,
                    "threshold_selection_period": postprocessing_split.threshold_period,
                    "categorical_columns": schema.categorical_columns,
                    "feature_columns": schema.feature_columns,
                },
            )
            tracker.log_evaluation_metrics(evaluation_metrics)
            if config.shap:
                log("Generating bounded SHAP artifacts")
                evaluation_index = period_index(df, config, config.evaluation_periods)
                prepared = prepare_model_inputs(
                    df.loc[period_index(df, config, config.train_periods)],
                    df.loc[evaluation_index],
                    schema,
                    config.model,
                )
                save_shap_artifacts(
                    estimator,
                    prepared.validation,
                    config.output_dir,
                    config.shap_sample_size,
                    config.random_seed,
                )

        tracker.log_artifacts(config.output_dir, config.model_dir)
        log(f"{config.stage} complete")


if __name__ == "__main__":
    run(parse_config())
