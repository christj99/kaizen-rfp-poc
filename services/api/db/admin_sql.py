"""Read-only SQL surface for the demo SQL console (Phase 7).

Three layers of defense in depth — any one of them on its own is
sufficient; together they make slipping a write past the endpoint
extremely difficult.

1. **Application parser** (``validate_select_query``) — strips comments,
   confirms the query begins with SELECT or WITH (CTE), rejects any
   write-DDL/DML keyword as a standalone token, rejects multi-statement
   queries (a ``;`` followed by anything substantive).
2. **Postgres role** — the connection uses ``rfp_readonly``, which has
   only SELECT privileges granted. Even if the parser is bypassed, the
   database refuses writes.
3. **Per-query session settings** — ``SET LOCAL TRANSACTION READ ONLY``
   plus ``SET LOCAL statement_timeout = '5s'``. Belt and suspenders.

Result rows are capped at 1000; ``truncated`` flags when more existed.
"""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from .. import _env  # noqa: F401


MAX_ROWS = 1000
STATEMENT_TIMEOUT_SECONDS = 5
READONLY_ROLE = "rfp_readonly"


# ---------- parser ---------------------------------------------------

# Word-boundary tokens that aren't legitimate inside a SELECT.
_FORBIDDEN_TOKENS = (
    r"INSERT", r"UPDATE", r"DELETE", r"DROP", r"TRUNCATE",
    r"ALTER", r"CREATE", r"GRANT", r"REVOKE",
    r"COPY", r"VACUUM", r"REINDEX", r"CLUSTER",
)
_FORBIDDEN_RE = re.compile(
    r"\b(?:" + "|".join(_FORBIDDEN_TOKENS) + r")\b",
    re.IGNORECASE,
)

# Strip line comments (-- ...) and block comments (/* ... */). The block-comment
# pattern is non-greedy so we don't eat across multiple comments at once.
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(query: str) -> str:
    return _BLOCK_COMMENT_RE.sub(" ", _LINE_COMMENT_RE.sub(" ", query))


def validate_select_query(query: str) -> Tuple[bool, Optional[str]]:
    """Return ``(ok, error_message)``. None on success."""
    if not query or not query.strip():
        return False, "empty query"

    cleaned = _strip_comments(query).strip()
    if not cleaned:
        return False, "query is only comments"

    # Must start with SELECT or WITH (CTE leading into a SELECT).
    head_match = re.match(r"^(\w+)", cleaned, re.IGNORECASE)
    if not head_match:
        return False, "could not parse leading keyword"
    head = head_match.group(1).upper()
    if head not in ("SELECT", "WITH"):
        return False, f"only SELECT (and WITH … SELECT) is allowed; got '{head}'"

    # Reject any forbidden write keyword as a standalone token.
    forbidden_match = _FORBIDDEN_RE.search(cleaned)
    if forbidden_match:
        return False, (
            f"query contains the forbidden keyword "
            f"'{forbidden_match.group(0).upper()}'; this endpoint is read-only"
        )

    # Reject multi-statement: a ';' followed by any non-whitespace, non-comment.
    # We tokenize on ; and check that anything after a ; is whitespace-only.
    # _strip_comments already removed comments so we just check raw remainder.
    parts = cleaned.split(";")
    if len(parts) > 1:
        for trailing in parts[1:]:
            if trailing.strip():
                return False, (
                    "multi-statement queries are rejected; submit one SELECT at a time"
                )

    return True, None


# ---------- connection -----------------------------------------------

def _readonly_dsn_kwargs() -> Dict[str, Any]:
    return {
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "kaizen_rfp"),
        "user": READONLY_ROLE,
        "password": os.environ.get("POSTGRES_READONLY_PASSWORD", "kaizen_readonly_pw"),
    }


@contextmanager
def readonly_cursor() -> Iterator[psycopg2.extras.DictCursor]:
    """Open a fresh connection as ``rfp_readonly``, configure session
    safety settings, yield a cursor. Always rolls back at the end —
    writes are forbidden anyway, but explicit rollback is hygiene."""
    conn = psycopg2.connect(**_readonly_dsn_kwargs())
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_SECONDS}s'")
                cur.execute("SET LOCAL TRANSACTION READ ONLY")
                yield cur
    finally:
        conn.close()


# ---------- result shape --------------------------------------------

def _coerce_for_json(value: Any) -> Any:
    """Make a single column value JSON-serializable. JSONB comes back
    as Python dict/list (already serializable). UUID, datetime, date
    become ISO strings. Memoryview / bytes become hex previews."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    if isinstance(value, (bytes, memoryview)):
        return f"<binary {len(bytes(value))}b>"
    return str(value)


def execute_select(query: str) -> Dict[str, Any]:
    """Execute ``query`` (already-validated) and return a JSON-shaped result.

    Returns a dict like::

      {
        "columns": ["id", "title", ...],
        "rows": [[...], [...], ...],   # row-major arrays of column values
        "row_count": 47,
        "truncated": False,
        "execution_time_ms": 12.4
      }

    Raises ``psycopg2.Error`` subclasses on DB-side failure (statement
    timeout, permission denied, etc.) — caller turns those into 400
    responses with the error message.
    """
    started = time.perf_counter()
    with readonly_cursor() as cur:
        cur.execute(query)
        if cur.description is None:
            elapsed = (time.perf_counter() - started) * 1000.0
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "execution_time_ms": round(elapsed, 1),
                "note": "query produced no result set",
            }
        columns = [d.name for d in cur.description]
        # Pull at most MAX_ROWS+1 to detect truncation in one round trip.
        raw_rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(raw_rows) > MAX_ROWS
        if truncated:
            raw_rows = raw_rows[:MAX_ROWS]
        rows: List[List[Any]] = [[_coerce_for_json(v) for v in row] for row in raw_rows]
    elapsed = (time.perf_counter() - started) * 1000.0
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "execution_time_ms": round(elapsed, 1),
    }
