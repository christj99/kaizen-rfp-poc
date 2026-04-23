"""Thin psycopg2 helpers. Intentionally minimal — no ORM, no Alembic.

Expand this module as downstream agents need structured persistence
(save_rfp, get_rfp, etc.). Phase 1 only needs audit-log writes so the
LLM client can record token usage.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Iterator, Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from ..models.audit import AuditEntry

load_dotenv()


def _connect():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "kaizen_rfp"),
        user=os.environ.get("POSTGRES_USER", "kaizen"),
        password=os.environ.get("POSTGRES_PASSWORD", "kaizen_dev_password"),
    )


@contextlib.contextmanager
def db_cursor() -> Iterator[psycopg2.extras.DictCursor]:
    """Auto-committing cursor context manager. Rolls back on exception."""
    conn = _connect()
    try:
        with conn:  # commits on clean exit, rolls back otherwise
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                yield cur
    finally:
        conn.close()


def write_audit(entry: AuditEntry) -> None:
    """Persist a single audit record. Callers should swallow errors here if
    the audit write is truly non-critical to their path (e.g. LLM client)."""
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log
                (id, entity_type, entity_id, action, actor, details, created_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                str(entry.id),
                entry.entity_type,
                str(entry.entity_id) if entry.entity_id else None,
                entry.action,
                entry.actor,
                json.dumps(entry.details, default=str),
                entry.created_at,
            ),
        )


def ping() -> bool:
    """True if the DB is reachable — used by /health once wired up."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False
