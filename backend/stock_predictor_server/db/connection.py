"""SQLite connection manager with WAL mode and low-RAM optimizations."""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_predictor.db"
DB_PATH = Path(os.environ.get("STOCK_PREDICTOR_DB", _DEFAULT_DB_PATH)).expanduser().resolve()
DB_DIR = DB_PATH.parent
DB_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with production-ready pragmas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA foreign_keys = ON;
        PRAGMA temp_store = MEMORY;
        PRAGMA mmap_size = 268435456;  -- 256 MB mmap for index-heavy queries
        """
    )
    return conn


def initialize_database() -> None:
    """Create the database schema if it does not exist yet."""
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    if not schema_path.is_file():
        raise FileNotFoundError(f"Database schema not found: {schema_path}")

    conn = get_connection()
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(predictions)").fetchall()
        }
        migrations = {
            "interval_coverage": "REAL NOT NULL DEFAULT 0.9",
            "interval_method": "TEXT NOT NULL DEFAULT 'legacy'",
            "model_version": "TEXT NOT NULL DEFAULT 'legacy'",
        }
        for column, declaration in migrations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE predictions ADD COLUMN {column} {declaration}")
        conn.commit()
    finally:
        conn.close()


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
