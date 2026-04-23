"""Apply schema.sql to the configured Postgres database.

Invoked by scripts/demo_start.sh (on empty DB) and scripts/reset_db.sh (always).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connect():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "kaizen_rfp"),
        user=os.environ.get("POSTGRES_USER", "kaizen"),
        password=os.environ.get("POSTGRES_PASSWORD", "kaizen_dev_password"),
    )


def db_is_empty(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'rfps'
            """
        )
        return cur.fetchone()[0] == 0


def apply_schema(force: bool = False) -> None:
    load_dotenv()
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        conn.autocommit = True
        if not force and not db_is_empty(conn):
            print("[migrate] schema already applied; skipping. Use --force to re-run.")
            return
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"[migrate] applied {SCHEMA_PATH.name}")


def drop_all() -> None:
    load_dotenv()
    with _connect() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                    ) LOOP
                        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
                """
            )
    print("[migrate] dropped all public tables")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--reset" in args:
        drop_all()
        apply_schema(force=True)
    elif "--force" in args:
        apply_schema(force=True)
    else:
        apply_schema(force=False)
