"""Load a slim spatial lot-year feature table into DB_Lake.

Creates/replaces:
  public.spatial_lot_year_slim

This table intentionally excludes geometry_wkt so feature SQL can join
coordinates and area without loading the full multi-GB spatial payload.

Run from project root:
  python scripts/loaders/load_spatial_lot_year_slim.py
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "credentials" / ".env")
KEY_FILE = ROOT / "credentials" / Path(os.environ["SSH_KEY"]).name
DATA_PARQUET_PATH = ROOT / "data" / "spatial_lot_year.parquet"
TMP_PARQUET_PATH = ROOT / "tmp" / "spatial" / "lots_v1" / "spatial_lot_year.parquet"
PARQUET_PATH = DATA_PARQUET_PATH if DATA_PARQUET_PATH.exists() else TMP_PARQUET_PATH


CREATE_TABLE = """
DROP TABLE IF EXISTS public.spatial_lot_year_slim;

CREATE TABLE public.spatial_lot_year_slim (
    shape_year integer NOT NULL,
    mill_code text,
    mill_name text,
    environmental_lot_key text NOT NULL,
    productivity_lot_key text,
    centroid_lon double precision,
    centroid_lat double precision,
    area_ha double precision,
    area_ha_dissolved double precision,
    perimeter_m double precision,
    perimeter_m_dissolved double precision,
    geometry_valid boolean,
    geometry_empty boolean,
    PRIMARY KEY (shape_year, environmental_lot_key)
);

CREATE INDEX spatial_lot_year_slim_lot_key_idx
    ON public.spatial_lot_year_slim (environmental_lot_key);

CREATE INDEX spatial_lot_year_slim_productivity_lot_key_idx
    ON public.spatial_lot_year_slim (productivity_lot_key);

CREATE INDEX spatial_lot_year_slim_mill_idx
    ON public.spatial_lot_year_slim (mill_code, shape_year);
"""


COPY_COLUMNS = [
    "shape_year",
    "mill_code",
    "mill_name",
    "environmental_lot_key",
    "productivity_lot_key",
    "centroid_lon",
    "centroid_lat",
    "area_ha",
    "area_ha_dissolved",
    "perimeter_m",
    "perimeter_m_dissolved",
    "geometry_valid",
    "geometry_empty",
]


def connect():
    tunnel = SSHTunnelForwarder(
        (os.environ["SSH_HOST"], int(os.environ["SSH_PORT"])),
        ssh_username=os.environ["SSH_USER"],
        ssh_pkey=str(KEY_FILE),
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
    return tunnel, conn


def main() -> None:
    print(f"Reading slim columns from {PARQUET_PATH} ...", flush=True)
    spatial = pd.read_parquet(PARQUET_PATH, columns=COPY_COLUMNS)

    # Source extraction contains a few malformed nan-nan keys; keep the
    # table joinable by excluding rows that cannot be keyed to real lots.
    spatial = spatial[
        spatial["environmental_lot_key"].notna()
        & (spatial["environmental_lot_key"].astype(str) != "nan-nan")
    ].copy()

    buffer = io.StringIO()
    spatial.to_csv(buffer, index=False, na_rep="")
    buffer.seek(0)
    print(f"Prepared {len(spatial):,} rows for COPY.", flush=True)

    print("Connecting to DB_Lake ...", flush=True)
    tunnel, conn = connect()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("Creating/replacing table public.spatial_lot_year_slim ...", flush=True)
            cur.execute(CREATE_TABLE)

            print("Loading rows via COPY ...", flush=True)
            cols = ", ".join(COPY_COLUMNS)
            cur.copy_expert(
                f"COPY public.spatial_lot_year_slim ({cols}) "
                "FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
                buffer,
            )

        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    count(*),
                    count(DISTINCT environmental_lot_key),
                    min(shape_year),
                    max(shape_year)
                FROM public.spatial_lot_year_slim
                """
            )
            total, keys, min_year, max_year = cur.fetchone()
        print(
            "Verification: "
            f"spatial_lot_year_slim={total:,} rows | "
            f"keys={keys:,} | shape_year={min_year}-{max_year}",
            flush=True,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        tunnel.stop()


if __name__ == "__main__":
    main()
