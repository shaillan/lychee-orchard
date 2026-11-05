"""一物一码：批次编码生成 + 追加式哈希链存证。

编码结构（参考 GS1 思路但为自建规则，不声称符合 GS1 标准）：
    LZ - {地块码} - {采收日期 YYYYMMDD} - {包装序号 4 位}
示例：LZ-P03-20260615-0001
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime


def make_batch_no(plot_code: str, harvest_date: str, seq: int) -> str:
    d = harvest_date.replace("-", "")
    return f"LZ-{plot_code}-{d}-{seq:04d}"


def make_trace_code(batch_no: str) -> str:
    return batch_no


def _canonical_json(payload: dict) -> str:
    """稳定序列化：同样的内容永远得到同样的字符串，哈希才可复算。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_digest(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def append_hash(conn, batch_id: int, payload: dict, summary: str) -> dict:
    """把批次关键溯源信息追加进哈希链，返回本条记录。

    原文（payload_json）一并入库：校验时用它重算哈希，
    只改数据库里的历史存证也会被发现。
    """
    prev = conn.execute(
        "SELECT record_hash FROM trace_hash_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = prev["record_hash"] if prev else "GENESIS"
    record_hash = _payload_digest({"payload": payload, "prev": prev_hash})
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO trace_hash_log"
        "(batch_id, record_hash, prev_hash, payload_summary, payload_json, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (batch_id, record_hash, prev_hash, summary, _canonical_json(payload), now),
    )
    return {"record_hash": record_hash, "prev_hash": prev_hash, "created_at": now}


def verify_chain(conn, batch_id: int | None = None) -> dict:
    """逐条重算哈希，返回链完整性结果。

    检查两件事：
    1. prev_hash 是否等于上一条的 record_hash（防删除、插入、调换）；
    2. 用存证原文 + prev_hash 重算，是否等于 record_hash（防改内容）。

    batch_id 不为空时只统计该批次的记录，但链上下文仍按全表推进。
    历史数据若没有 payload_json（旧版本写入），单独列在 legacy 中，不参与重算。
    """
    rows = conn.execute("SELECT * FROM trace_hash_log ORDER BY id ASC").fetchall()
    prev_hash = "GENESIS"
    broken: list[int] = []
    tampered: list[int] = []
    legacy: list[int] = []
    checked = 0

    for row in rows:
        link_ok = row["prev_hash"] == prev_hash

        payload_ok: bool | None = None
        raw = row["payload_json"]
        if raw:
            try:
                payload = json.loads(raw)
                expect = _payload_digest({"payload": payload, "prev": row["prev_hash"]})
                payload_ok = expect == row["record_hash"]
            except (TypeError, ValueError):
                payload_ok = False

        if batch_id is None or row["batch_id"] == batch_id:
            checked += 1
            if not link_ok:
                broken.append(row["id"])
            if payload_ok is False:
                tampered.append(row["id"])
            elif payload_ok is None:
                legacy.append(row["id"])

        prev_hash = row["record_hash"]

    return {
        "total": checked,
        "broken": broken,
        "tampered": tampered,
        "legacy": legacy,
        "valid": not broken and not tampered,
        "head": rows[-1]["record_hash"] if rows else None,
    }
