from __future__ import annotations

import json
import hashlib
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from config import RunConfig
from feature_schema import FeatureSchema
from splits import WalkForwardFold


def write_json(path: str | Path, payload) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, default=str, allow_nan=True),
        encoding="utf-8",
    )


def package_versions() -> dict[str, str]:
    versions = {}
    for package in (
        "pandas",
        "numpy",
        "scikit-learn",
        "lightgbm",
        "xgboost",
        "catboost",
        "optuna",
        "shap",
    ):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def dataset_identity(dataset: str) -> dict:
    path = Path(dataset)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "path": str(path),
            "kind": "file",
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        }
    if path.is_dir():
        parts = sorted(path.glob("*.parquet"))
        digest = hashlib.sha256()
        total_bytes = 0
        for part in parts:
            total_bytes += part.stat().st_size
            digest.update(part.name.encode("utf-8"))
            with part.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        return {
            "path": str(path),
            "kind": "parquet_directory",
            "parts": len(parts),
            "bytes": total_bytes,
            "sha256": digest.hexdigest(),
        }
    return {"path": str(path), "kind": "unavailable"}


def save_run_metadata(
    config: RunConfig,
    schema: FeatureSchema,
    folds: list[WalkForwardFold],
) -> None:
    output = Path(config.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "resolved_config.json", config.to_dict())
    write_json(output / "feature_schema.json", schema.to_dict())
    write_json(
        output / "split_metadata.json",
        [
            {
                "fold": fold.number,
                "train_periods": fold.train_periods,
                "validation_period": fold.validation_period,
                "train_rows": len(fold.train_index),
                "validation_rows": len(fold.validation_index),
            }
            for fold in folds
        ],
    )
    write_json(
        output / "run_manifest.json",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": platform.platform(),
            "packages": package_versions(),
            "dataset": dataset_identity(config.dataset),
        },
    )
