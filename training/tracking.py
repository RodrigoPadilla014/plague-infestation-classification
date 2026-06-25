from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from config import RunConfig
from feature_schema import FeatureSchema
from splits import WalkForwardFold


def _experiment_name(config: RunConfig) -> str:
    name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "")
    return name if name else Path(config.dataset).stem


class Tracker:
    def __init__(self, config: RunConfig):
        self._config = config
        self._active = False
        try:
            import mlflow
            self._mlflow = mlflow
        except ImportError:
            self._mlflow = None

    def __enter__(self) -> "Tracker":
        if self._mlflow is None:
            return self
        config = self._config
        self._mlflow.set_experiment(_experiment_name(config))
        run_name = f"{config.stage}__{config.model or 'model-independent'}"
        self._mlflow.start_run(run_name=run_name)
        self._mlflow.set_tags({
            "stage": config.stage,
            "model": config.model or "none",
            "dataset": Path(config.dataset).name,
        })
        self._active = True
        return self

    def __exit__(self, *_) -> None:
        if self._mlflow and self._active:
            self._mlflow.end_run()
            self._active = False

    def log_config(self, schema: FeatureSchema, folds: list[WalkForwardFold]) -> None:
        if not self._active:
            return
        config = self._config
        params: dict[str, Any] = {
            "stage": config.stage,
            "model": config.model or "none",
            "dataset": Path(config.dataset).name,
            "train_periods": ",".join(config.train_periods),
            "evaluation_periods": ",".join(config.evaluation_periods),
            "min_train_periods": config.min_train_periods,
            "imbalance": config.imbalance,
            "objective_metric": config.objective_metric,
            "threshold_strategy": config.threshold_strategy,
            "fixed_threshold": config.fixed_threshold,
            "minimum_recall": config.minimum_recall,
            "calibration": config.calibration,
            "n_folds": len(folds),
            "n_features": len(schema.feature_columns),
            "n_categorical": len(schema.categorical_columns),
        }
        for k, v in config.fixed_params.items():
            params[f"fixed_{k}"] = v
        self._mlflow.log_params(params)

    def log_fold_metrics(self, fold_metrics: pd.DataFrame) -> None:
        if not self._active:
            return
        for _, row in fold_metrics.iterrows():
            step = int(row["fold"])
            for col in fold_metrics.columns:
                if col in {"fold", "validation_period"}:
                    continue
                try:
                    self._mlflow.log_metric(f"fold_{col}", float(row[col]), step=step)
                except (TypeError, ValueError):
                    pass

    def log_oof_summary(self, summary: dict[str, Any]) -> None:
        if not self._active:
            return
        metrics = {
            k: float(v)
            for k, v in summary.items()
            if isinstance(v, (int, float)) and k != "folds"
        }
        self._mlflow.log_metrics(metrics)
        self._mlflow.log_metric("n_folds", int(summary.get("folds", 0)))

    def log_best_params(self, params: dict[str, Any]) -> None:
        if not self._active:
            return
        for k, v in params.items():
            try:
                self._mlflow.log_param(f"best_{k}", v)
            except Exception:
                pass

    def log_postprocessing(self, threshold: float, n_calibration_periods: int) -> None:
        if not self._active:
            return
        self._mlflow.log_metrics({
            "selected_threshold": threshold,
            "n_calibration_periods": n_calibration_periods,
        })

    def log_evaluation_metrics(self, metrics: dict[str, Any]) -> None:
        if not self._active:
            return
        self._mlflow.log_metrics({
            f"eval_{k}": float(v)
            for k, v in metrics.items()
            if isinstance(v, (int, float))
        })

    def log_artifacts(self, output_dir: str, model_dir: str | None = None) -> None:
        if not self._active:
            return
        output = Path(output_dir)
        for name in (
            "out_of_fold_predictions.csv",
            "walk_forward_metrics.csv",
            "walk_forward_summary.json",
            "threshold_sweep.csv",
            "selected_threshold.json",
            "temporal_postprocessing_split.json",
            "evaluation_predictions.csv",
            "evaluation_metrics.json",
            "optuna_trials.csv",
            "best_params.json",
            "class_balance_by_period.csv",
            "feature_missingness.csv",
            "walk_forward_fold_diagnostics.csv",
            "resolved_config.json",
            "feature_schema.json",
        ):
            path = output / name
            if path.exists():
                self._mlflow.log_artifact(str(path))
        shap_dir = output / "shap"
        if shap_dir.exists():
            self._mlflow.log_artifacts(str(shap_dir), artifact_path="shap")
        if model_dir:
            model_path = Path(model_dir)
            if model_path.exists():
                self._mlflow.log_artifacts(str(model_path), artifact_path="model")
