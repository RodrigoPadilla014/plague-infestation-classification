from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STAGES = ("diagnostics", "baseline", "optuna")
MODELS = ("lightgbm", "xgboost", "catboost")
CALIBRATION_METHODS = ("none", "sigmoid", "isotonic")
THRESHOLD_STRATEGIES = ("fixed", "f2", "recall_constraint")


def csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class RunConfig:
    stage: str
    dataset: str
    output_dir: str
    model_dir: str
    model: str | None = None
    target_column: str = "target"
    period_column: str = "zafra"
    date_column: str = "prediction_date"
    row_id_column: str = "record_id"
    train_periods: list[str] = field(default_factory=list)
    evaluation_periods: list[str] = field(default_factory=list)
    scoring_periods: list[str] = field(default_factory=list)
    categorical_columns: list[str] = field(default_factory=list)
    metadata_columns: list[str] = field(default_factory=list)
    forbidden_columns: list[str] = field(default_factory=list)
    exclude_features: list[str] = field(default_factory=list)
    min_train_periods: int = 1
    imbalance: str = "balanced"
    objective_metric: str = "average_precision"
    stability_penalty: float = 0.0
    threshold_strategy: str = "fixed"
    fixed_threshold: float = 0.5
    minimum_recall: float = 0.85
    calibration: str = "none"
    optuna_trials: int = 20
    early_stopping_rounds: int = 50
    shap: bool = True
    shap_sample_size: int = 1000
    random_seed: int = 42
    fixed_params: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"Unknown stage: {self.stage}")
        if self.stage != "diagnostics" and self.model not in MODELS:
            raise ValueError(f"--model is required for {self.stage}; choose from {MODELS}")
        if self.stage == "diagnostics" and self.model:
            raise ValueError("--model is not used by the diagnostics stage")
        if not self.train_periods:
            raise ValueError("At least one --train-period is required")
        if self.min_train_periods < 1:
            raise ValueError("--min-train-periods must be at least 1")
        if self.min_train_periods >= len(self.train_periods):
            raise ValueError("--min-train-periods must leave at least one validation period")
        overlap = set(self.train_periods) & set(self.evaluation_periods)
        if overlap:
            raise ValueError(f"Train and evaluation periods overlap: {sorted(overlap)}")
        if self.threshold_strategy not in THRESHOLD_STRATEGIES:
            raise ValueError(f"Unknown threshold strategy: {self.threshold_strategy}")
        if self.calibration not in CALIBRATION_METHODS:
            raise ValueError(f"Unknown calibration method: {self.calibration}")
        if not 0.0 <= self.fixed_threshold <= 1.0:
            raise ValueError("--fixed-threshold must be between 0 and 1")
        if not 0.0 <= self.minimum_recall <= 1.0:
            raise ValueError("--minimum-recall must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-stage, one-model binary-classification training pipeline."
    )
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-dir", default="/opt/ml/output/data")
    parser.add_argument("--model-dir", default="/opt/ml/model")
    parser.add_argument("--target-column", default="target")
    parser.add_argument("--period-column", default="zafra")
    parser.add_argument("--date-column", default="prediction_date")
    parser.add_argument("--row-id-column", default="record_id")
    parser.add_argument("--train-periods", required=True)
    parser.add_argument("--evaluation-periods", default="")
    parser.add_argument("--scoring-periods", default="")
    parser.add_argument("--categorical-columns", default="")
    parser.add_argument("--metadata-columns", default="")
    parser.add_argument("--forbidden-columns", default="")
    parser.add_argument("--exclude-features", default="")
    parser.add_argument("--min-train-periods", type=int, default=1)
    parser.add_argument("--imbalance", choices=("none", "balanced"), default="balanced")
    parser.add_argument(
        "--objective-metric",
        choices=("average_precision", "roc_auc", "f2", "recall"),
        default="average_precision",
    )
    parser.add_argument("--stability-penalty", type=float, default=0.0)
    parser.add_argument("--threshold-strategy", choices=THRESHOLD_STRATEGIES, default="fixed")
    parser.add_argument("--fixed-threshold", type=float, default=0.5)
    parser.add_argument("--minimum-recall", type=float, default=0.85)
    parser.add_argument("--calibration", choices=CALIBRATION_METHODS, default="none")
    parser.add_argument("--optuna-trials", type=int, default=20)
    parser.add_argument("--early-stopping-rounds", type=int, default=50)
    parser.add_argument("--shap", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--shap-sample-size", type=int, default=1000)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--fixed-params-json", default="")
    parser.add_argument("--config-json", help="Optional JSON file whose values act as defaults.")
    return parser


def parse_config(argv: list[str] | None = None) -> RunConfig:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config-json")
    pre_args, _ = pre_parser.parse_known_args(argv)
    parser = build_parser()
    if pre_args.config_json:
        defaults = json.loads(Path(pre_args.config_json).read_text(encoding="utf-8"))
        parser.set_defaults(**{key.replace("-", "_"): value for key, value in defaults.items()})
    args = parser.parse_args(argv)
    fixed_params = json.loads(args.fixed_params_json) if args.fixed_params_json else {}
    config = RunConfig(
        stage=args.stage,
        model=args.model,
        dataset=args.dataset,
        output_dir=args.output_dir,
        model_dir=args.model_dir,
        target_column=args.target_column,
        period_column=args.period_column,
        date_column=args.date_column,
        row_id_column=args.row_id_column,
        train_periods=csv_list(args.train_periods),
        evaluation_periods=csv_list(args.evaluation_periods),
        scoring_periods=csv_list(args.scoring_periods),
        categorical_columns=csv_list(args.categorical_columns),
        metadata_columns=csv_list(args.metadata_columns),
        forbidden_columns=csv_list(args.forbidden_columns),
        exclude_features=csv_list(args.exclude_features),
        min_train_periods=args.min_train_periods,
        imbalance=args.imbalance,
        objective_metric=args.objective_metric,
        stability_penalty=args.stability_penalty,
        threshold_strategy=args.threshold_strategy,
        fixed_threshold=args.fixed_threshold,
        minimum_recall=args.minimum_recall,
        calibration=args.calibration,
        optuna_trials=args.optuna_trials,
        early_stopping_rounds=args.early_stopping_rounds,
        shap=args.shap,
        shap_sample_size=args.shap_sample_size,
        random_seed=args.random_seed,
        fixed_params=fixed_params,
    )
    config.validate()
    return config

