"""SQLite access layer: connection helpers + schema bootstrap."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("ORCHARD_DB", DATA_DIR / "orchard.db"))

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS plots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    variety       TEXT NOT NULL,
    area_mu       REAL NOT NULL,
    tree_count    INTEGER NOT NULL,
    planting_year INTEGER NOT NULL,
    location      TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS farm_operations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id        INTEGER NOT NULL REFERENCES plots(id),
    operation_type TEXT NOT NULL,
    operator       TEXT NOT NULL,
    operation_date TEXT NOT NULL,
    detail         TEXT,
    images         TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_op_plot_date ON farm_operations(plot_id, operation_date);

-- 用药台账独立建表：合规性字段强制落库，不塞进农事记录 JSON
CREATE TABLE IF NOT EXISTS pesticide_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id             INTEGER NOT NULL REFERENCES plots(id),
    pesticide_name      TEXT NOT NULL,
    cas_no              TEXT,
    dosage              TEXT,
    dilution            TEXT,
    application_method  TEXT,
    operator            TEXT NOT NULL,
    apply_time          TEXT NOT NULL,
    safe_interval_days  INTEGER NOT NULL,
    target_pest         TEXT,
    days_to_harvest     INTEGER,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pest_plot_time ON pesticide_records(plot_id, apply_time);

CREATE TABLE IF NOT EXISTS yield_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id         INTEGER NOT NULL REFERENCES plots(id),
    season          INTEGER NOT NULL,
    estimated_yield REAL,
    actual_yield    REAL,
    UNIQUE(plot_id, season)
);

CREATE TABLE IF NOT EXISTS recognitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plot_id         INTEGER REFERENCES plots(id),
    user_id         TEXT,
    image_url       TEXT,
    detected_class  TEXT,
    confidence      REAL,
    bbox            TEXT,
    suggestion_text TEXT,
    suggestion_json TEXT,
    is_mock         INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rec_created ON recognitions(created_at);

CREATE TABLE IF NOT EXISTS batches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no        TEXT NOT NULL UNIQUE,
    plot_id         INTEGER NOT NULL REFERENCES plots(id),
    variety         TEXT NOT NULL,
    harvest_date    TEXT NOT NULL,
    trace_code      TEXT NOT NULL UNIQUE,
    packaging_seq   INTEGER DEFAULT 1,
    status          TEXT NOT NULL,          -- released | blocked
    block_reason    TEXT,
    detection_report TEXT,
    packaging_info  TEXT,
    logistics       TEXT,
    created_at      TEXT NOT NULL
);

-- 追加式哈希日志：每条记录携带上一条哈希，形成可校验的链
CREATE TABLE IF NOT EXISTS trace_hash_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER NOT NULL REFERENCES batches(id),
    record_hash     TEXT NOT NULL,
    prev_hash       TEXT NOT NULL,
    payload_summary TEXT,
    created_at      TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
