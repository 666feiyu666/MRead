"""SQLite persistence.

Everything that must survive a page reload lives here: cases, assets, agent profiles,
workflows, runs, step records, and human decisions. Structured payloads are stored as
JSON text; asset bytes live on disk under the data directory.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    text_content TEXT NOT NULL DEFAULT '',
    stored_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role_instructions TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    expected_response TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    workflow_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS step_records (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    output TEXT NOT NULL DEFAULT '{}',
    raw_output TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, step_id)
);

CREATE INDEX IF NOT EXISTS idx_assets_case ON assets(case_id);
CREATE INDEX IF NOT EXISTS idx_records_run ON step_records(run_id, ordinal);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default if default is not None else {}


def row_to_dict(row: sqlite3.Row, json_fields: tuple[str, ...] = ()) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    for field in json_fields:
        data[field] = loads(data.get(field), {})
    return data
