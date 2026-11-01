"""Koneksi SQLite, transaksi, dan inisialisasi database."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from . import settings
from .migrations import apply_migrations

_active_path: Path | None = None


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_load(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def active_path() -> Path:
    return _active_path or settings.DB_PATH


def set_path(path: str | Path) -> Path:
    global _active_path
    _active_path = Path(path).resolve()
    _active_path.parent.mkdir(parents=True, exist_ok=True)
    return _active_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(active_path()), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Transaksi tunggal; commit bila sukses, rollback bila gagal."""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(sql, params).fetchone())


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def init_db(path: str | Path | None = None) -> Path:
    """Siapkan database, jalankan migrasi, dan isi roster awal (idempoten)."""
    resolved = set_path(path) if path else set_path(settings.DB_PATH)
    settings.ensure_directories()
    with transaction() as conn:
        apply_migrations(conn)
    from .seed import seed

    with transaction() as conn:
        seed(conn)
    return resolved
