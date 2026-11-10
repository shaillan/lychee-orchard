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
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | handled | ignored | false_positive
    handled_at      TEXT,
    handle_method   TEXT,                              -- pesticide | operation | ignore | false_positive
    handle_note     TEXT,
    pesticide_record_id INTEGER,                       -- 用药处置回链 pesticide_records.id
    operation_id    INTEGER,                           -- 农事处置回链 farm_operations.id
    patrol_id       TEXT,                              -- 同一次「进园巡拍」共享的批次号
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
    harvest_at      TEXT,                   -- 离树时间；为空时按 harvest_date 06:00 估算
    precooled_at    TEXT,                   -- 预冷完成
    shipped_at      TEXT,                   -- 装车发运
    arrived_at      TEXT,                   -- 到货
    created_at      TEXT NOT NULL
);

-- 农残快检记录：报告图 + 检测项 + 结论，不合格会把批次改为 blocked
CREATE TABLE IF NOT EXISTS residue_tests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER NOT NULL REFERENCES batches(id),
    tested_at   TEXT NOT NULL,
    lab         TEXT,
    conclusion  TEXT NOT NULL,              -- 合格 | 不合格 | 待复检
    items_json  TEXT,                       -- [{name,value,unit,limit,passed}]
    report_url  TEXT,                       -- /static/uploads/xxx.jpg
    operator    TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_residue_batch ON residue_tests(batch_id);

-- 追加式哈希日志：每条记录携带上一条哈希，形成可校验的链
CREATE TABLE IF NOT EXISTS trace_hash_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER NOT NULL REFERENCES batches(id),
    record_hash     TEXT NOT NULL,
    prev_hash       TEXT NOT NULL,
    payload_summary TEXT,
    payload_json    TEXT,                    -- 存证原文，校验时据此重算哈希
    created_at      TEXT NOT NULL
);

-- 通用键值设置：目前只存 weather_region（前端可改的天气地区）
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,                -- JSON 文本
    updated_at TEXT NOT NULL
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
        _migrate(conn)


def _migrate(conn) -> None:
    """轻量迁移：给已存在的旧库补列，无需删库重建。"""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(trace_hash_log)")}
    if "payload_json" not in columns:
        conn.execute("ALTER TABLE trace_hash_log ADD COLUMN payload_json TEXT")

    # 识别→处置闭环：旧库补状态列（status 带默认值，旧行自动回填 pending）
    rec_columns = {row["name"] for row in conn.execute("PRAGMA table_info(recognitions)")}
    if "status" not in rec_columns:
        conn.execute("ALTER TABLE recognitions ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        conn.execute("ALTER TABLE recognitions ADD COLUMN handled_at TEXT")
        conn.execute("ALTER TABLE recognitions ADD COLUMN handle_method TEXT")
        conn.execute("ALTER TABLE recognitions ADD COLUMN handle_note TEXT")
        conn.execute("ALTER TABLE recognitions ADD COLUMN pesticide_record_id INTEGER")
        conn.execute("ALTER TABLE recognitions ADD COLUMN operation_id INTEGER")

    # 巡园批次号：旧库补列 + 索引
    if "patrol_id" not in rec_columns:
        conn.execute("ALTER TABLE recognitions ADD COLUMN patrol_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rec_patrol ON recognitions(patrol_id)")

    # 采后冷链：旧库补四个时间戳
    batch_columns = {row["name"] for row in conn.execute("PRAGMA table_info(batches)")}
    for column in ("harvest_at", "precooled_at", "shipped_at", "arrived_at"):
        if column not in batch_columns:
            conn.execute(f"ALTER TABLE batches ADD COLUMN {column} TEXT")


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
