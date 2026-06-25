"""Run categorical QA for an ML dataset parquet.

Checks cardinality, missingness, rare levels, year drift, and simple
normalization collisions for string/category-like columns.

Run from project root:
  python scripts/diagnostics/run_categorical_qa.py --dataset data/ml_dataset_model1_january_v001.parquet
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data" / "ml_dataset_model1_january_v001.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "tmp" / "diagnostics_v1_contract" / "categorical_qa"

METADATA_STRING_COLUMNS = {
    "record_id",
    "lot_key",
    "productivity_lot_key",
    "plague_zafras",
    "ingenio",
    "mill_name",
    "first_visit",
    "last_visit",
    "target_status",
    "target_year_rules",
    "prod_source_zafra",
    "prod_cierre_date",
    "crop_start_date",
}

CATEGORICAL_FEATURE_COLUMNS = {
    "prod_variedad",
    "prod_grupo_de_suelo",
    "prod_familia_de_suelo",
    "prod_grupo_de_humedad",
    "prod_codigo_zae",
    "prod_no_corte",
    "prod_estrato",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rare-threshold", type=int, default=5)
    return parser.parse_args()


def normalize_category(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text or None


def categorical_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for col in CATEGORICAL_FEATURE_COLUMNS:
        if col in df.columns:
            cols.append(col)
    return sorted(cols)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(args.dataset)
    cat_cols = categorical_columns(df)

    summary_rows = []
    top_value_rows = []
    rare_value_rows = []
    normalization_rows = []
    drift_rows = []

    for col in cat_cols:
        series = df[col]
        counts = series.value_counts(dropna=False)
        non_null = series.dropna()
        rare = non_null.value_counts()
        rare = rare[rare <= args.rare_threshold]

        summary_rows.append(
            {
                "column": col,
                "dtype": str(series.dtype),
                "rows": len(series),
                "missing": int(series.isna().sum()),
                "missing_rate": float(series.isna().mean()),
                "cardinality": int(non_null.nunique()),
                "rare_level_count": int(len(rare)),
                "rare_row_count": int(rare.sum()),
                "top_value": None if counts.empty else str(counts.index[0]),
                "top_count": 0 if counts.empty else int(counts.iloc[0]),
                "top_rate": 0.0 if counts.empty else float(counts.iloc[0] / len(series)),
            }
        )

        for value, count in counts.head(25).items():
            top_value_rows.append(
                {
                    "column": col,
                    "value": None if pd.isna(value) else str(value),
                    "count": int(count),
                    "rate": float(count / len(series)),
                }
            )

        for value, count in rare.sort_index().items():
            rare_value_rows.append(
                {
                    "column": col,
                    "value": str(value),
                    "count": int(count),
                }
            )

        norm = (
            non_null.astype(str)
            .map(lambda x: (normalize_category(x), x))
            .dropna()
            .tolist()
        )
        norm_map: dict[str, set[str]] = {}
        for normalized, original in norm:
            if normalized is None:
                continue
            norm_map.setdefault(normalized, set()).add(original)
        for normalized, originals in sorted(norm_map.items()):
            if len(originals) > 1:
                normalization_rows.append(
                    {
                        "column": col,
                        "normalized_value": normalized,
                        "variant_count": len(originals),
                        "variants": " | ".join(sorted(originals)[:25]),
                    }
                )

        if "target_rainy_year" in df.columns:
            grouped = (
                df.groupby("target_rainy_year")[col]
                .agg(
                    rows="size",
                    missing=lambda x: int(x.isna().sum()),
                    cardinality=lambda x: int(x.nunique(dropna=True)),
                )
                .reset_index()
            )
            for row in grouped.to_dict(orient="records"):
                row["column"] = col
                drift_rows.append(row)

    summary = pd.DataFrame(summary_rows).sort_values(
        ["cardinality", "missing_rate"], ascending=[False, False]
    )
    top_values = pd.DataFrame(top_value_rows)
    rare_values = pd.DataFrame(rare_value_rows)
    normalization = pd.DataFrame(normalization_rows)
    drift = pd.DataFrame(drift_rows)

    summary.to_csv(args.output_dir / "categorical_summary.csv", index=False)
    top_values.to_csv(args.output_dir / "categorical_top_values.csv", index=False)
    rare_values.to_csv(args.output_dir / "categorical_rare_values.csv", index=False)
    normalization.to_csv(args.output_dir / "categorical_normalization_collisions.csv", index=False)
    drift.to_csv(args.output_dir / "categorical_year_drift.csv", index=False)

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset),
        "rows": int(len(df)),
        "categorical_columns": cat_cols,
        "summary": summary.to_dict(orient="records"),
        "normalization_collision_count": int(len(normalization)),
        "columns_with_normalization_collisions": sorted(
            normalization["column"].unique().tolist() if len(normalization) else []
        ),
    }
    (args.output_dir / "categorical_qa_summary.json").write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Dataset: {args.dataset}", flush=True)
    print(f"Rows: {len(df):,}", flush=True)
    print(f"Categorical columns: {len(cat_cols)}", flush=True)
    print(summary.to_string(index=False), flush=True)
    print(f"Normalization collisions: {len(normalization):,}", flush=True)
    print(f"Output: {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
