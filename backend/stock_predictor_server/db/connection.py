"""SQLite connection manager with WAL mode and low-RAM optimizations."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "stock_predictor.db"


def get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with production-ready pragmas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA temp_store = MEMORY;
        PRAGMA mmap_size = 268435456;  -- 256 MB mmap for index-heavy queries
        """
    )
    return conn


def execute(
    query: str,
    params: Optional[Iterable[Any]] = None,
    fetch: bool = False,
) -> Any:
    """Execute a single statement, optionally returning rows."""
    conn = get_connection()
    try:
        cur = conn.execute(query, params or ())
        if fetch:
            rows = cur.fetchall()
            return rows
        conn.commit()
        return cur.lastrowid if cur.lastrowid is not None else cur.rowcount
    finally:
        conn.close()


def executemany(
    query: str,
    params_list: Iterable[Iterable[Any]],
    fetch: bool = False,
) -> Any:
    """Execute a statement many times (e.g., bulk inserts)."""
    conn = get_connection()
    try:
        cur = conn.executemany(query, params_list)
        if fetch:
            return cur.fetchall()
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def fetch_one(query: str, params: Optional[Iterable[Any]] = None) -> Optional[sqlite3.Row]:
    """Fetch a single row."""
    conn = get_connection()
    try:
        cur = conn.execute(query, params or ())
        return cur.fetchone()
    finally:
        conn.close()


def fetch_all(query: str, params: Optional[Iterable[Any]] = None) -> list[sqlite3.Row]:
    """Fetch all rows."""
    conn = get_connection()
    try:
        cur = conn.execute(query, params or ())
        return cur.fetchall()
    finally:
        conn.close()


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
