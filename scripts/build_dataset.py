"""Build ML-ready datasets from SQL feature recipes.

Run from project root:
  python scripts/build_dataset.py --recipe model1_january --version v001
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder


ROOT = Path(__file__).resolve().parents[1]


RECIPE_FILES = {
    "model1_january": [
        ("season_spine", "00_season_spine.sql"),
        ("enso_forecast_features", "10_enso_forecast.sql"),
        ("historical_rainy_climate_features", "20_historical_rainy_climate.sql"),
        ("plague_history_features", "30_plague_history.sql"),
        ("static_productividad_features", "40_static_productividad.sql"),
        ("spatial_features", "50_spatial.sql"),
    ],
}


FINAL_FILES = {
    "model1_january": "90_final_dataset.sql",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", default="model1_january", choices=sorted(RECIPE_FILES))
    parser.add_argument("--version", default="v001")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--limit", type=int, help="Optional row limit for smoke testing.")
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


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_temp_table(conn, table_name: str, sql: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {table_name}")
        cur.execute(f"CREATE TEMP TABLE {table_name} AS {sql}")
        cur.execute(f"SELECT count(*) FROM {table_name}")
        return int(cur.fetchone()[0])


def table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = %s
            )
            """,
            (table,),
        )
        return bool(cur.fetchone()[0])


def summarize_dataset(dataset: pd.DataFrame) -> dict:
    feature_columns = [
        col
        for col in dataset.columns
        if col
        not in {
            "record_id",
            "lot_key",
            "productivity_lot_key",
            "target",
            "target_status",
            "target_year_rules",
            "target_plague_gt_050_raw",
            "target_max_ninfas_raw",
            "target_max_valid_ninfas",
            "first_visit",
            "last_visit",
            "plague_zafras",
            "ingenio",
            "mill_name",
            "n_observations",
            "n_core_rainy_observations",
            "n_edge_month_observations",
            "n_nymph_observations_raw",
            "n_valid_nymph_observations",
            "n_possible_sampling_error",
            "n_extreme_ninfas",
            "n_ninfas_outlier",
        }
    ]
    return {
        "rows": int(len(dataset)),
        "columns": int(len(dataset.columns)),
        "feature_columns": int(len(feature_columns)),
        "target_positive": int(dataset["target"].sum()),
        "target_negative": int((dataset["target"] == 0).sum()),
        "target_rate": float(dataset["target"].mean()),
        "target_years": [
            int(x) for x in sorted(dataset["target_rainy_year"].dropna().unique())
        ],
        "target_status_counts": {
            str(k): int(v) for k, v in dataset["target_status"].value_counts().items()
        },
        "missingness_top20": {
            str(k): float(v)
            for k, v in (
                dataset.isna().mean().sort_values(ascending=False).head(20).items()
            )
        },
    }


def main() -> None:
    args = parse_args()
    recipe_dir = ROOT / "sql" / args.recipe
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not recipe_dir.exists():
        raise FileNotFoundError(recipe_dir)

    output_stem = f"ml_dataset_{args.recipe}_{args.version}"
    output_path = args.output_dir / f"{output_stem}.parquet"
    manifest_path = args.output_dir / f"{output_stem}.manifest.json"

    sql_texts: dict[str, str] = {}
    for view_name, file_name in RECIPE_FILES[args.recipe]:
        sql_texts[file_name] = read_sql(recipe_dir / file_name)
    final_sql = read_sql(recipe_dir / FINAL_FILES[args.recipe])
    sql_texts[FINAL_FILES[args.recipe]] = final_sql

    print("Connecting to DB_Lake ...", flush=True)
    tunnel, conn = connect()
    try:
        if not table_exists(conn, "spatial_lot_year_slim"):
            raise RuntimeError(
                "public.spatial_lot_year_slim is missing. Run "
                "python scripts/loaders/load_spatial_lot_year_slim.py first."
            )

        view_counts = {}
        for view_name, file_name in RECIPE_FILES[args.recipe]:
            print(f"Creating temp table {view_name} from {file_name} ...", flush=True)
            view_counts[view_name] = create_temp_table(conn, view_name, sql_texts[file_name])
            print(f"  {view_counts[view_name]:,} rows", flush=True)

        query = final_sql
        if args.limit:
            query = f"SELECT * FROM ({final_sql}) final_dataset LIMIT {args.limit}"

        print("Reading final dataset ...", flush=True)
        dataset = pd.read_sql_query(query, conn)
    finally:
        conn.close()
        tunnel.stop()

    dataset = dataset.drop(columns=["record_id"], errors="ignore")
    dataset.insert(
        0,
        "record_id",
        dataset["lot_key"] + "__" + dataset["target_rainy_year"].astype(str),
    )
    dataset.to_parquet(output_path, index=False)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "recipe": args.recipe,
        "version": args.version,
        "output_path": str(output_path),
        "view_counts": view_counts,
        "summary": summarize_dataset(dataset),
        "sql_files": {
            file_name: {
                "path": str(recipe_dir / file_name),
                "sha256": sha256_text(sql_text),
            }
            for file_name, sql_text in sql_texts.items()
        },
        "target_contract": {
            "grain": ["lot_key", "target_rainy_year"],
            "target_column": "target",
            "positive_rule": "any valid ninfas_tallo > 0.50 within lot target_rainy_year",
            "excluded_target_rows": "unknown_no_valid_nymph_observation",
            "ignored_observation_flag": "flag_ninfas_posible_error_muestreo",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(f"Dataset: {output_path}", flush=True)
    print(f"Manifest: {manifest_path}", flush=True)
    print(
        f"Rows={manifest['summary']['rows']:,} "
        f"Columns={manifest['summary']['columns']:,} "
        f"Target rate={manifest['summary']['target_rate']:.1%}",
        flush=True,
    )


if __name__ == "__main__":
    main()
