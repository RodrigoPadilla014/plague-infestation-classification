"""
Load chinche_clean.csv into DB_Lake as table `chinche`.

Creates:
  - public.chinche          (main table, replaces chinche_observation)
  - view chinche_usable     (excludes exact duplicates)
  - view chinche_ml         (excludes duplicates + ninfas sampling errors)

Run from project root:
    python load_chinche.py
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "credentials" / ".env")
KEY_FILE = ROOT / "credentials" / Path(os.environ["SSH_KEY"]).name
CSV_PATH = ROOT / "tmp" / "db_clean" / "v2" / "output" / "chinche_clean.csv"


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS public.chinche (
    record_id                               uuid PRIMARY KEY,
    source_file                             text NOT NULL,
    source_sheet                            text NOT NULL,
    source_row                              integer NOT NULL,

    ingenio_raw                             text,
    fecha_raw                               text,
    zafra_raw                               text,
    estrato_raw                             text,
    codigo_finca_raw                        text,
    finca_raw                               text,
    lote_raw                                text,
    coordenadas_raw                         text,
    area_ha_raw                             text,
    variedad_raw                            text,
    ciclo_corte_raw                         text,
    no_muestreo_raw                         text,
    edad_cana_raw                           text,
    ninfas_tallo_raw                        text,
    adultos_tallo_raw                       text,

    ingenio                                 text,
    fecha                                   date,
    zafra                                   text,
    estrato                                 text,
    estrato_grupo                           text,
    codigo_finca                            text,
    finca_normalizada                       text,
    lote                                    text,
    mill_name                               text,
    environmental_lot_key                   text,
    productivity_lot_key                    text,
    longitude                               double precision,
    latitude                                double precision,
    coordenada_formato                      text,
    area_ha                                 double precision,
    variedad_clave                          text,
    variedad_canonica                       text,
    ciclo_corte                             integer,
    no_muestreo                             integer,
    edad_cana_valor                         double precision,
    edad_cana_unidad                        text,
    habito_crecimiento                      text,
    ninfas_tallo                            double precision,
    adultos_tallo                           double precision,
    nivel_ninfas                            text,
    nivel_adultos                           text,

    lote_candidato_sin_cero_extra           text,
    lote_candidato_repeticiones             integer NOT NULL DEFAULT 0,
    dedupe_fingerprint                      char(64) NOT NULL,
    observation_key                         char(64) NOT NULL,
    cleaning_version                        text NOT NULL,
    ingested_at_utc                         timestamptz NOT NULL,
    qa_flag_count                           integer NOT NULL,
    qa_status                               text NOT NULL,

    flag_columna_sin_nombre_no_duplica_lote boolean NOT NULL DEFAULT false,
    flag_fecha_corregida                    boolean NOT NULL DEFAULT false,
    flag_ninfas_corregida                   boolean NOT NULL DEFAULT false,
    flag_lote_cero_extra_ambiguo            boolean NOT NULL DEFAULT false,
    flag_lote_posible_cero_extra            boolean NOT NULL DEFAULT false,
    flag_fecha_faltante                     boolean NOT NULL DEFAULT false,
    flag_fecha_sospechosa                   boolean NOT NULL DEFAULT false,
    flag_zafra_faltante                     boolean NOT NULL DEFAULT false,
    flag_estrato_faltante                   boolean NOT NULL DEFAULT false,
    flag_codigo_finca_faltante              boolean NOT NULL DEFAULT false,
    flag_ingenio_faltante                   boolean NOT NULL DEFAULT false,
    flag_variedad_faltante                  boolean NOT NULL DEFAULT false,
    flag_area_cero_o_negativa               boolean NOT NULL DEFAULT false,
    flag_area_mayor_100ha                   boolean NOT NULL DEFAULT false,
    flag_coordenada_faltante                boolean NOT NULL DEFAULT false,
    flag_coordenada_invalida                boolean NOT NULL DEFAULT false,
    flag_coordenada_fuera_guatemala         boolean NOT NULL DEFAULT false,
    flag_edad_no_interpretable              boolean NOT NULL DEFAULT false,
    flag_edad_unidad_inferida               boolean NOT NULL DEFAULT false,
    flag_ninfas_outlier                     boolean NOT NULL DEFAULT false,
    flag_adultos_outlier                    boolean NOT NULL DEFAULT false,
    flag_ninfas_posible_error_muestreo      boolean NOT NULL DEFAULT false,
    flag_ninfas_extremo                     boolean NOT NULL DEFAULT false,
    flag_adultos_extremo                    boolean NOT NULL DEFAULT false,
    flag_duplicado_exacto                   boolean NOT NULL DEFAULT false,

    UNIQUE (source_file, source_sheet, source_row)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS chinche_lookup_idx
    ON public.chinche (ingenio, codigo_finca, lote, fecha);
CREATE INDEX IF NOT EXISTS chinche_environmental_lot_key_idx
    ON public.chinche (environmental_lot_key);
CREATE INDEX IF NOT EXISTS chinche_productivity_lot_key_idx
    ON public.chinche (productivity_lot_key);
CREATE INDEX IF NOT EXISTS chinche_key_idx
    ON public.chinche (observation_key);
CREATE INDEX IF NOT EXISTS chinche_dedupe_idx
    ON public.chinche (dedupe_fingerprint);
CREATE INDEX IF NOT EXISTS chinche_geo_idx
    ON public.chinche (longitude, latitude)
    WHERE longitude IS NOT NULL AND latitude IS NOT NULL;
"""

CREATE_VIEWS = """
CREATE OR REPLACE VIEW public.chinche_usable AS
SELECT * FROM public.chinche
WHERE NOT flag_duplicado_exacto;

CREATE OR REPLACE VIEW public.chinche_ml AS
SELECT * FROM public.chinche
WHERE NOT flag_duplicado_exacto
  AND NOT flag_ninfas_posible_error_muestreo
  AND ninfas_tallo IS NOT NULL;
"""

COPY_COLUMNS = [
    "record_id", "source_file", "source_sheet", "source_row",
    "ingenio_raw", "fecha_raw", "zafra_raw", "estrato_raw",
    "codigo_finca_raw", "finca_raw", "lote_raw", "coordenadas_raw",
    "area_ha_raw", "variedad_raw", "ciclo_corte_raw", "no_muestreo_raw",
    "edad_cana_raw", "ninfas_tallo_raw", "adultos_tallo_raw",
    "ingenio", "fecha", "zafra", "estrato", "estrato_grupo",
    "codigo_finca", "finca_normalizada", "lote",
    "mill_name", "environmental_lot_key", "productivity_lot_key",
    "longitude", "latitude", "coordenada_formato", "area_ha",
    "variedad_clave", "variedad_canonica", "ciclo_corte", "no_muestreo",
    "edad_cana_valor", "edad_cana_unidad", "habito_crecimiento",
    "ninfas_tallo", "adultos_tallo", "nivel_ninfas", "nivel_adultos",
    "lote_candidato_sin_cero_extra", "lote_candidato_repeticiones",
    "dedupe_fingerprint", "observation_key", "cleaning_version",
    "ingested_at_utc", "qa_flag_count", "qa_status",
    "flag_columna_sin_nombre_no_duplica_lote", "flag_fecha_corregida",
    "flag_ninfas_corregida", "flag_lote_cero_extra_ambiguo",
    "flag_lote_posible_cero_extra", "flag_fecha_faltante",
    "flag_fecha_sospechosa", "flag_zafra_faltante", "flag_estrato_faltante",
    "flag_codigo_finca_faltante", "flag_ingenio_faltante",
    "flag_variedad_faltante", "flag_area_cero_o_negativa",
    "flag_area_mayor_100ha", "flag_coordenada_faltante",
    "flag_coordenada_invalida", "flag_coordenada_fuera_guatemala",
    "flag_edad_no_interpretable", "flag_edad_unidad_inferida",
    "flag_ninfas_outlier", "flag_adultos_outlier",
    "flag_ninfas_posible_error_muestreo", "flag_ninfas_extremo",
    "flag_adultos_extremo", "flag_duplicado_exacto",
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
    print(f"Reading {CSV_PATH} ...")
    df = pd.read_csv(CSV_PATH, low_memory=False, dtype=str)
    df = df[[c for c in COPY_COLUMNS if c in df.columns]]
    print(f"  {len(df):,} rows, {len(df.columns)} columns")

    # Fill boolean flag columns with False where NULL
    flag_cols = [c for c in df.columns if c.startswith("flag_")]
    df[flag_cols] = df[flag_cols].fillna("false")

    print("Connecting to DB_Lake ...")
    tunnel, conn = connect()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("Creating table public.chinche ...")
            cur.execute(CREATE_TABLE)

            print("Creating indexes ...")
            cur.execute(CREATE_INDEXES)

            print("Loading rows via COPY ...")
            buf = io.StringIO()
            df.to_csv(buf, index=False, na_rep="")
            buf.seek(0)
            cols = ", ".join(COPY_COLUMNS)
            cur.copy_expert(
                f"COPY public.chinche ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
                buf,
            )
            print(f"  Inserted {cur.rowcount:,} rows")

            print("Creating views chinche_usable and chinche_ml ...")
            cur.execute(CREATE_VIEWS)

        conn.commit()
        print("Done.")

        # Verify
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.chinche")
            total = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM public.chinche_ml")
            ml = cur.fetchone()[0]
        print(f"Verification: chinche={total:,} rows | chinche_ml={ml:,} rows")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        tunnel.stop()


if __name__ == "__main__":
    main()
