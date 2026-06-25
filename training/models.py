from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def default_params(model: str, seed: int) -> dict[str, Any]:
    common = {"random_state": seed}
    if model == "lightgbm":
        return {
            **common,
            "n_estimators": 500,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "verbosity": -1,
        }
    if model == "xgboost":
        return {
            **common,
            "n_estimators": 500,
            "learning_rate": 0.05,
            "max_depth": 6,
            "tree_method": "hist",
            "enable_categorical": True,
            "eval_metric": "logloss",
        }
    if model == "catboost":
        return {
            "random_seed": seed,
            "iterations": 500,
            "learning_rate": 0.05,
            "depth": 6,
            "loss_function": "Logloss",
            "eval_metric": "AUC",
            "verbose": False,
            "allow_writing_files": False,
        }
    raise ValueError(f"Unknown model: {model}")


def imbalance_params(model: str, y_train, mode: str) -> dict[str, Any]:
    if mode == "none":
        return {}
    y = np.asarray(y_train, dtype=int)
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if positives == 0 or negatives == 0:
        return {}
    if model == "xgboost":
        return {"scale_pos_weight": negatives / positives}
    if model == "lightgbm":
        return {"class_weight": "balanced"}
    if model == "catboost":
        return {"auto_class_weights": "Balanced"}
    return {}


def build_model(model: str, params: dict[str, Any]):
    if model == "lightgbm":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(**params)
    if model == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(**params)
    if model == "catboost":
        from catboost import CatBoostClassifier

        return CatBoostClassifier(**params)
    raise ValueError(f"Unknown model: {model}")


def fit_model(
    estimator,
    model: str,
    X_train,
    y_train,
    X_validation,
    y_validation,
    categorical_columns: list[str],
    early_stopping_rounds: int,
):
    if model == "catboost":
        estimator.set_params(early_stopping_rounds=early_stopping_rounds)
        return estimator.fit(
            X_train,
            y_train,
            cat_features=categorical_columns,
            eval_set=(X_validation, y_validation),
        )
    if model == "lightgbm":
        import lightgbm as lgb

        return estimator.fit(
            X_train,
            y_train,
            categorical_feature=categorical_columns,
            eval_set=[(X_validation, y_validation)],
            callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
        )
    if model == "xgboost":
        estimator.set_params(early_stopping_rounds=early_stopping_rounds)
        return estimator.fit(
            X_train,
            y_train,
            eval_set=[(X_validation, y_validation)],
            verbose=False,
        )
    raise ValueError(model)


def fit_final_model(
    estimator,
    model: str,
    X_train,
    y_train,
    categorical_columns: list[str],
):
    """Fit on all training periods without consulting held-out evaluation rows."""
    if model == "catboost":
        return estimator.fit(X_train, y_train, cat_features=categorical_columns)
    if model == "lightgbm":
        return estimator.fit(
            X_train,
            y_train,
            categorical_feature=categorical_columns,
        )
    if model == "xgboost":
        return estimator.fit(X_train, y_train, verbose=False)
    raise ValueError(model)


def predict_probabilities(estimator, X):
    return estimator.predict_proba(X)[:, 1]


def save_model(estimator, model: str, model_dir: str) -> Path:
    destination = Path(model_dir)
    destination.mkdir(parents=True, exist_ok=True)
    if model == "lightgbm":
        path = destination / "model.txt"
        estimator.booster_.save_model(str(path))
    elif model == "xgboost":
        path = destination / "model.ubj"
        estimator.save_model(str(path))
    elif model == "catboost":
        path = destination / "model.cbm"
        estimator.save_model(str(path))
    else:
        raise ValueError(model)
    return path


def suggest_params(trial, model: str) -> dict[str, Any]:
    if model == "lightgbm":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1200),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 255),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 20.0, log=True),
        }
    if model == "xgboost":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1200),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.2, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 20.0),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 20.0, log=True),
        }
    if model == "catboost":
        return {
            "iterations": trial.suggest_int("iterations", 200, 1200),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.2, log=True),
            "depth": trial.suggest_int("depth", 3, 10),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1e-3, 20.0, log=True),
            "random_strength": trial.suggest_float("random_strength", 1e-3, 10.0, log=True),
        }
    raise ValueError(model)
