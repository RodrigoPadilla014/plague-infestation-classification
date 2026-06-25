"""Run Model 1 season-spine diagnostics against DB_Lake.

This is a diagnostic runner, not a feature dataset builder. It executes the
season-aware spine SQL and writes CSV/JSON summaries that can be reviewed
before approving or changing the v1 target contract.

Run from project root:
  python scripts/diagnostics/run_season_spine_diagnostics.py
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQL = (
    ROOT / "sql" / "model1_january" / "diagnostics" / "01_season_spine.sql"
)
DEFAULT_OUTPUT_DIR = ROOT / "tmp" / "diagnostics_v1_contract"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", type=Path, default=DEFAULT_SQL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def connect():
    load_dotenv(ROOT / "credentials" / ".env")
    key_file = ROOT / "credentials" / Path(os.environ["SSH_KEY"]).name
    tunnel = SSHTunnelForwarder(
        (os.environ["SSH_HOST"], int(os.environ["SSH_PORT"])),
        ssh_username=os.environ["SSH_USER"],
        ssh_pkey=str(key_file),
        remote_bind_address=(os.environ["DB_HOST"], int(os.environ["DB_PORT"])),
    )
    tunnel.start()
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=tunnel.local_bind_port,
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    conn.autocommit = True
    return tunnel, conn


def pct(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return float(numerator) / float(denominator)


def summarize(spine: pd.DataFrame):
    by_year = (
        spine.groupby("target_rainy_year", dropna=False)
        .agg(
            rows=("lot_key", "size"),
            lots=("lot_key", "nunique"),
            trainable_rows=("target_trainable", "sum"),
            positives_raw=("target_plague_gt_050_raw", "sum"),
            positives_clean=("target_plague_gt_050_clean", "sum"),
            unknown_targets=(
                "target_status",
                lambda x: int((x == "unknown_no_valid_nymph_observation").sum()),
            ),
            clean_negative_with_suspicious_measurement=(
                "target_status",
                lambda x: int(
                    (x == "clean_negative_with_suspicious_measurement").sum()
                ),
            ),
            possible_sampling_error_rows=("n_possible_sampling_error", "sum"),
            edge_month_rows=("n_edge_month_observations", "sum"),
            has_core_enso_forecast=("has_core_enso_forecast", "sum"),
            has_prior_rainy_climate_history=("has_prior_rainy_climate_history", "sum"),
            has_target_year_rainy_climate=("has_target_year_rainy_climate", "sum"),
            has_any_productividad=("has_any_productividad", "sum"),
            has_same_label_productividad=("has_same_label_productividad", "sum"),
            has_any_spatial=("has_any_spatial", "sum"),
            has_same_year_spatial=("has_same_year_spatial", "sum"),
        )
        .reset_index()
        .sort_values("target_rainy_year")
    )
    by_year["positive_rate_raw"] = by_year.apply(
        lambda row: pct(row["positives_raw"], row["rows"]), axis=1
    )
    by_year["positive_rate_clean_trainable"] = by_year.apply(
        lambda row: pct(row["positives_clean"], row["trainable_rows"]), axis=1
    )
    by_year["target_delta"] = by_year["positives_raw"] - by_year["positives_clean"]

    mixed_zafra = spine[
        spine["plague_zafras"].astype(str).str.contains(",", regex=False)
    ].copy()
    edge_month = spine[spine["n_edge_month_observations"] > 0].copy()
    sampling_error_target_delta = spine[
        spine["target_plague_gt_050_raw"].fillna(0).astype(int)
        != spine["target_plague_gt_050_clean"].fillna(0).astype(int)
    ].copy()

    total_rows = int(len(spine))
    trainable_rows = int(spine["target_trainable"].fillna(False).astype(bool).sum())
    total_positive_raw = int(spine["target_plague_gt_050_raw"].sum())
    total_positive_clean = int(spine["target_plague_gt_050_clean"].sum())
    target_status_counts = {
        str(k): int(v) for k, v in spine["target_status"].value_counts().items()
    }

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_rows": total_rows,
        "trainable_rows": trainable_rows,
        "distinct_lots": int(spine["lot_key"].nunique()),
        "target_years": [
            int(x) for x in sorted(spine["target_rainy_year"].dropna().unique())
        ],
        "positive_raw": total_positive_raw,
        "positive_clean": total_positive_clean,
        "positive_rate_raw": pct(total_positive_raw, total_rows),
        "positive_rate_clean_trainable": pct(total_positive_clean, trainable_rows),
        "target_status_counts": target_status_counts,
        "target_positive_delta_from_sampling_error_exclusion": int(
            total_positive_raw - total_positive_clean
        ),
        "rows_with_edge_month_observations": int(len(edge_month)),
        "rows_with_multiple_plague_zafras": int(len(mixed_zafra)),
        "rows_where_sampling_error_exclusion_changes_target": int(
            len(sampling_error_target_delta)
        ),
        "join_coverage": {
            column: {
                "rows": int(spine[column].fillna(False).astype(bool).sum()),
                "rate": pct(
                    int(spine[column].fillna(False).astype(bool).sum()), total_rows
                ),
            }
            for column in [
                "has_core_enso_forecast",
                "has_prior_rainy_climate_history",
                "has_target_year_rainy_climate",
                "has_any_productividad",
                "has_same_label_productividad",
                "has_any_spatial",
                "has_same_year_spatial",
            ]
        },
        "by_year": by_year.to_dict(orient="records"),
    }
    return summary, by_year, mixed_zafra, edge_month, sampling_error_target_delta


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sql = args.sql.read_text(encoding="utf-8")

    print("Connecting to DB_Lake ...", flush=True)
    tunnel, conn = connect()
    try:
        print(f"Executing {args.sql} ...", flush=True)
        spine = pd.read_sql_query(sql, conn)
    finally:
        conn.close()
        tunnel.stop()

    spine.to_csv(args.output_dir / "season_spine.csv", index=False)

    summary, by_year, mixed_zafra, edge_month, sampling_delta = summarize(spine)
    by_year.to_csv(args.output_dir / "season_spine_by_year.csv", index=False)
    mixed_zafra.to_csv(args.output_dir / "season_spine_mixed_zafra_rows.csv", index=False)
    edge_month.to_csv(args.output_dir / "season_spine_edge_month_rows.csv", index=False)
    sampling_delta.to_csv(
        args.output_dir / "season_spine_sampling_error_target_delta.csv",
        index=False,
    )
    (args.output_dir / "season_spine_summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Rows: {len(spine):,}", flush=True)
    print(f"Output: {args.output_dir}", flush=True)
    print(
        "Target positives raw vs clean trainable: "
        f"{summary['positive_raw']:,} vs {summary['positive_clean']:,}",
        flush=True,
    )
    print(f"Trainable rows: {summary['trainable_rows']:,}", flush=True)
    print(f"Target statuses: {summary['target_status_counts']}", flush=True)
    print("By target rainy year:", flush=True)
    print(
        by_year[
            [
                "target_rainy_year",
                "rows",
                "trainable_rows",
                "positive_rate_raw",
                "positive_rate_clean_trainable",
                "target_delta",
                "unknown_targets",
                "clean_negative_with_suspicious_measurement",
                "edge_month_rows",
            ]
        ].to_string(index=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
