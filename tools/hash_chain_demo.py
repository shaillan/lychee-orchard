"""哈希链篡改演示工具（仅用于本地答辩演示，请勿对生产数据使用）。

用法：
    python tools/hash_chain_demo.py tamper LZ-P03-20260702-0001
    # 刷新 http://127.0.0.1:8000/trace?code=LZ-P03-20260702-0001，应看到「链校验失败」
    python tools/hash_chain_demo.py restore
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "orchard.db"
BACKUP_PATH = BASE_DIR / "data" / "tamper_backup.json"


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(f"找不到数据库：{DB_PATH}，请先执行 python run.py 生成演示数据")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def tamper(code: str) -> None:
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT h.id AS id, h.payload_json AS payload_json FROM trace_hash_log h "
            "JOIN batches b ON b.id = h.batch_id WHERE b.trace_code = ? ORDER BY h.id LIMIT 1",
            (code,),
        ).fetchone()
        if not row or not row["payload_json"]:
            raise SystemExit(f"溯源码 {code} 没有可篡改的存证记录")

        BACKUP_PATH.write_text(
            json.dumps({"id": row["id"], "payload_json": row["payload_json"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        payload = json.loads(row["payload_json"])
        payload["stage"] = "被篡改（演示）"
        conn.execute(
            "UPDATE trace_hash_log SET payload_json=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), row["id"]),
        )

    print(f"已篡改第 {row['id']} 条存证，原值备份在 {BACKUP_PATH}")
    print(f"刷新溯源页查看红字：http://127.0.0.1:8000/trace?code={code}")


def restore() -> None:
    if not BACKUP_PATH.exists():
        raise SystemExit("没有找到备份，无需恢复")

    data = json.loads(BACKUP_PATH.read_text(encoding="utf-8"))
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE trace_hash_log SET payload_json=? WHERE id=?",
            (data["payload_json"], data["id"]),
        )
    BACKUP_PATH.unlink()
    print(f"已恢复第 {data['id']} 条存证，刷新页面应显示校验通过")


def main() -> None:
    parser = argparse.ArgumentParser(description="哈希链篡改演示（仅用于本地演示）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    tamper_cmd = sub.add_parser("tamper", help="篡改指定溯源码的一条存证")
    tamper_cmd.add_argument("code", help="溯源码，如 LZ-P03-20260702-0001")
    sub.add_parser("restore", help="恢复上次被篡改的存证")
    args = parser.parse_args()

    if args.cmd == "tamper":
        tamper(args.code)
    else:
        restore()


if __name__ == "__main__":
    main()
