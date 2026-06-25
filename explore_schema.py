"""
Inspect DB_Lake tables relevant to the chinche ML pipeline.

Answers:
  - What tables exist?
  - What columns does each key table have?
  - What lot-key formats exist in stac_indices, radar, clima_lote_pentada_new,
    productividad, and chinche_observation?
  - What date ranges does each table cover?
  - Is chinche_observation already loaded?

Run from project root:
    python explore_schema.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "credentials" / ".env")

KEY_FILE = ROOT / "credentials" / Path(os.environ["SSH_KEY"]).name


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
    conn.autocommit = True
    return tunnel, conn


def q(conn, sql: str, params=None) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def get_columns(conn, table: str) -> list[str]:
    df = q(
        conn,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        params=(table,),
    )
    return df["column_name"].tolist()


def table_exists(conn, table: str) -> bool:
    df = q(
        conn,
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s) AS exists",
        params=(table,),
    )
    return bool(df["exists"].iloc[0])


def inspect_table(conn, table: str) -> None:
    banner(table)

    if not table_exists(conn, table):
        print(f"  TABLE DOES NOT EXIST")
        return

    cols = get_columns(conn, table)
    print(f"Columns ({len(cols)}): {', '.join(cols)}")

    # row count
    cnt = q(conn, f"SELECT count(*) AS row_count FROM public.{table}")
    print(f"Row count: {cnt['row_count'].iloc[0]:,}")

    # detect date column (pick first plausible one)
    date_candidates = [c for c in cols if any(
        tok in c.lower() for tok in ["fecha", "date", "inicio", "cierre"]
    )]
    if date_candidates:
        dc = date_candidates[0]
        try:
            rng = q(conn, f"""
                SELECT
                    min({dc}::date) AS date_min,
                    max({dc}::date) AS date_max
                FROM public.{table}
                WHERE {dc} IS NOT NULL
            """)
            print(f"Date range ({dc}): {rng['date_min'].iloc[0]}  →  {rng['date_max'].iloc[0]}")
        except Exception as e:
            print(f"  Date range query failed ({dc}): {e}")

    # detect lot key column
    lot_candidates = [c for c in cols if c in ("lote", "cod_cg", "lot_id")]
    if lot_candidates:
        lc = lot_candidates[0]
        try:
            stat = q(conn, f"""
                SELECT
                    count(DISTINCT trim({lc}::text)) AS distinct_lots,
                    min(length(trim({lc}::text))) AS key_len_min,
                    max(length(trim({lc}::text))) AS key_len_max
                FROM public.{table}
                WHERE {lc} IS NOT NULL
            """)
            print(f"Lot key column: {lc}  |  distinct={stat['distinct_lots'].iloc[0]:,}  "
                  f"|  key length min={stat['key_len_min'].iloc[0]}  max={stat['key_len_max'].iloc[0]}")

            sample = q(conn, f"""
                SELECT DISTINCT trim({lc}::text) AS lot_key
                FROM public.{table}
                WHERE {lc} IS NOT NULL
                ORDER BY lot_key
                LIMIT 20
            """)
            print(f"Sample keys: {', '.join(sample['lot_key'].tolist())}")
        except Exception as e:
            print(f"  Lot key query failed: {e}")
    else:
        print(f"  No obvious lot key column found in: {cols}")


def inspect_chinche(conn) -> None:
    banner("chinche_observation  (our spine)")

    if not table_exists(conn, "chinche_observation"):
        print("TABLE DOES NOT EXIST YET — needs to be loaded via schema + load SQL")
        return

    cols = get_columns(conn, "chinche_observation")
    print(f"Columns ({len(cols)}): {', '.join(cols)}")

    summary = q(conn, """
        SELECT
            count(*) AS total_rows,
            count(*) FILTER (WHERE NOT flag_duplicado_exacto) AS no_dup,
            count(*) FILTER (
                WHERE NOT flag_duplicado_exacto
                  AND NOT flag_ninfas_posible_error_muestreo
                  AND ninfas_tallo IS NOT NULL
            ) AS ml_eligible,
            min(fecha) AS date_min,
            max(fecha) AS date_max
        FROM public.chinche_observation
    """)
    print(summary.to_string(index=False))

    print("\nDistinct ingenios + lot counts:")
    ing = q(conn, """
        SELECT ingenio,
               count(*) AS rows,
               count(DISTINCT lote) AS distinct_lotes,
               count(DISTINCT codigo_finca) AS distinct_fincas
        FROM public.chinche_observation
        GROUP BY ingenio ORDER BY ingenio
    """)
    print(ing.to_string(index=False))

    print("\nSample lot keys (lote):")
    sample = q(conn, """
        SELECT DISTINCT trim(lote::text) AS lot_key
        FROM public.chinche_observation
        WHERE lote IS NOT NULL
        ORDER BY lot_key LIMIT 20
    """)
    print(sample.to_string(index=False))

    print("\nSample combined keys (codigo_finca + '-' + lote):")
    combo = q(conn, """
        SELECT DISTINCT
            trim(codigo_finca::text) || '-' || trim(lote::text) AS combined_key
        FROM public.chinche_observation
        WHERE codigo_finca IS NOT NULL AND lote IS NOT NULL
        ORDER BY combined_key LIMIT 20
    """)
    print(combo.to_string(index=False))


def cross_match(conn) -> None:
    banner("LOT KEY CROSS-MATCH  (chinche.lote  vs  other tables)")

    if not table_exists(conn, "chinche_observation"):
        print("chinche_observation not loaded — skipping cross-match")
        return

    for table, lot_col in [
        ("productividad", "lote"),
        ("stac_indices", "lote"),
        ("radar", "lote"),
        ("clima_lote_pentada_new", "cod_cg"),
    ]:
        if not table_exists(conn, table):
            print(f"  {table}: not found")
            continue
        try:
            match = q(conn, f"""
                WITH c AS (
                    SELECT DISTINCT trim(lote::text) AS k
                    FROM public.chinche_observation WHERE lote IS NOT NULL
                ),
                o AS (
                    SELECT DISTINCT trim({lot_col}::text) AS k
                    FROM public.{table} WHERE {lot_col} IS NOT NULL
                )
                SELECT
                    (SELECT count(DISTINCT k) FROM c) AS chinche_lots,
                    (SELECT count(DISTINCT k) FROM o) AS other_lots,
                    count(DISTINCT c.k) FILTER (WHERE o.k IS NOT NULL) AS exact_matches,
                    count(DISTINCT c.k) FILTER (WHERE o.k IS NULL)     AS chinche_only,
                    count(DISTINCT o.k) FILTER (WHERE c.k IS NULL)     AS other_only
                FROM c FULL OUTER JOIN o USING (k)
            """)
            print(f"\n{table} (join on {lot_col}):")
            print(match.to_string(index=False))
        except Exception as e:
            print(f"  {table} cross-match failed: {e}")


def main() -> None:
    print("Connecting to DB_Lake via SSH tunnel...")
    tunnel, conn = connect()
    print("Connected.\n")

    try:
        banner("ALL TABLES IN public SCHEMA")
        tables = q(conn, """
            SELECT
                table_name,
                pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS size
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        print(tables.to_string(index=False))

        for table in [
            "productividad",
            "stac_indices",
            "radar",
            "clima_lote_pentada_new",
            "enso",
        ]:
            try:
                inspect_table(conn, table)
            except Exception as exc:
                print(f"  [ERROR inspecting {table}]: {exc}")

        inspect_chinche(conn)
        cross_match(conn)

    finally:
        conn.close()
        tunnel.stop()
        print("\n\nDone. Tunnel closed.")


if __name__ == "__main__":
    main()
