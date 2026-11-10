"""演示种子数据：保证现场演示时四个模块都有内容可看。"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

from .db import get_conn
from .rules import PEST_CLASSES, PESTICIDES, PESTICIDE_BY_NAME
from .traceability import append_hash, make_batch_no

RNG = random.Random(20260615)
NOW = datetime.now()


def _d(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _dt(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


PLOTS = [
    {"code": "P01", "name": "东风果园 A 区", "variety": "妃子笑", "area_mu": 32.5,
     "tree_count": 620, "planting_year": 2012, "location": "广东省广州市从化区太平镇东风村 南坡"},
    {"code": "P02", "name": "东风果园 B 区", "variety": "桂味", "area_mu": 26.0,
     "tree_count": 480, "planting_year": 2015, "location": "广东省广州市从化区太平镇东风村 东坡"},
    {"code": "P03", "name": "东风果园 C 区", "variety": "糯米糍", "area_mu": 18.5,
     "tree_count": 350, "planting_year": 2009, "location": "广东省广州市从化区太平镇东风村 西坡"},
]

OPERATION_TYPES = ["施肥", "灌溉", "修剪", "疏花疏果", "巡检", "清园"]
OPERATORS = ["陈伯", "李姐", "黄师傅", "周工"]


def seed_if_empty() -> bool:
    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM plots").fetchone()["c"]
        if existing:
            return False
        _seed(conn)
        return True


def _seed(conn) -> None:
    plot_ids: dict[str, int] = {}
    for p in PLOTS:
        cur = conn.execute(
            "INSERT INTO plots(code, name, variety, area_mu, tree_count, planting_year, location, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (p["code"], p["name"], p["variety"], p["area_mu"], p["tree_count"],
             p["planting_year"], p["location"], _dt(500)),
        )
        plot_ids[p["code"]] = cur.lastrowid

    # ---- 产量记录：2022-2026，体现荔枝大小年 ----
    yield_profile = {
        "P01": {2022: (15500, 16200), 2023: (9200, 8700), 2024: (16800, 17300),
                2025: (9800, 9300), 2026: (17600, 18100)},
        "P02": {2022: (11200, 11800), 2023: (6800, 6400), 2024: (12400, 12900),
                2025: (7100, 6800), 2026: (13100, 13600)},
        "P03": {2022: (8600, 9000), 2023: (5100, 4800), 2024: (9400, 9900),
                2025: (5400, 5100), 2026: (10200, 10700)},
    }
    for code, seasons in yield_profile.items():
        for season, (est, act) in seasons.items():
            conn.execute(
                "INSERT INTO yield_records(plot_id, season, estimated_yield, actual_yield) VALUES (?,?,?,?)",
                (plot_ids[code], season, est, act),
            )

    # ---- 农事记录：近 365 天 ----
    detail_pool = {
        "施肥": {"fertilizer": "复合肥(15-15-15)", "amount_kg": 40, "method": "环状沟施"},
        "灌溉": {"method": "滴灌", "duration_min": 60},
        "修剪": {"scope": "结果母枝回缩", "labor": 2},
        "疏花疏果": {"scope": "疏除弱花穗", "labor": 3},
        "巡检": {"result": "未见大面积异常", "scope": "全园巡园"},
        "清园": {"scope": "清理落果病枝", "labor": 2},
    }
    for code, pid in plot_ids.items():
        for i in range(36):
            days_ago = 5 + i * 10 + RNG.randint(0, 4)
            op_type = OPERATION_TYPES[RNG.randrange(len(OPERATION_TYPES))]
            detail = dict(detail_pool[op_type])
            detail["remark"] = f"{code} 区常规作业"
            conn.execute(
                "INSERT INTO farm_operations(plot_id, operation_type, operator, operation_date, detail, images, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (pid, op_type, OPERATORS[RNG.randrange(len(OPERATORS))], _d(days_ago),
                 json.dumps(detail, ensure_ascii=False), json.dumps([]), _dt(days_ago)),
            )

    # ---- 用药台账：近 12 个月，每月 1 次左右 ----
    for code, pid in plot_ids.items():
        for m in range(12):
            days_ago = 10 + m * 30 + RNG.randint(0, 5)
            pesticide = PESTICIDES[RNG.randrange(0, 9)] if m % 3 else PESTICIDES[9 + (m % 4)]
            # 最近一次用药：P01 在 3 天前施用高风险药，用于演示「采收拦截」
            if code == "P01" and m == 0:
                pesticide = PESTICIDE_BY_NAME["高效氯氟氰菊酯"]
                days_ago = 3
            conn.execute(
                "INSERT INTO pesticide_records(plot_id, pesticide_name, cas_no, dosage, dilution, "
                "application_method, operator, apply_time, safe_interval_days, target_pest, days_to_harvest, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, pesticide["name"], pesticide["cas_no"], pesticide["dosage_hint"],
                 "按标签推荐", "叶面喷雾", OPERATORS[RNG.randrange(len(OPERATORS))],
                 _d(days_ago), pesticide["safe_interval_days"],
                 "、".join(pesticide["targets"]), None, _dt(days_ago)),
            )

    # ---- 识别记录：近 90 天，约 130 条 ----
    for i in range(130):
        days_ago = RNG.randint(0, 89)
        pid = plot_ids[RNG.choice(list(plot_ids))]
        pest = PEST_CLASSES[RNG.randrange(len(PEST_CLASSES))]
        conf = round(RNG.uniform(0.76, 0.97), 4)
        conn.execute(
            "INSERT INTO recognitions(plot_id, user_id, image_url, detected_class, confidence, bbox, "
            "suggestion_text, suggestion_json, is_mock, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, "farmer_01", "", pest, conf, "[120,150,220,220]", "", "", 1, _dt(days_ago)),
        )

    # ---- 采收批次：3 个已放行 + 1 个被拦截 ----
    batch_specs = [
        ("P02", "2026-06-18", 1, "released"),
        ("P03", "2026-07-02", 1, "released"),
        ("P01", "2026-06-25", 1, "released"),
        ("P01", "2026-07-08", 2, "blocked"),
    ]
    for code, harvest_date, seq, status in batch_specs:
        pid = plot_ids[code]
        batch_no = make_batch_no(code, harvest_date, seq)
        block_reason = None
        if status == "blocked":
            block_reason = "最近一次施药（高效氯氟氰菊酯）安全间隔期未满 14 天，禁止生成销售溯源码"
        conn.execute(
            "INSERT INTO batches(batch_no, plot_id, variety, harvest_date, trace_code, packaging_seq, "
            "status, block_reason, detection_report, packaging_info, logistics, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch_no, pid, PLOTS[[p["code"] for p in PLOTS].index(code)]["variety"],
             harvest_date, batch_no, seq, status, block_reason,
             "农残快检合格（模板数据）", "5kg 泡沫箱 · 冷链", "顺丰冷链 · 广州→上海",
             _dt(30)),
        )
        batch_id = conn.execute("SELECT id FROM batches WHERE batch_no=?", (batch_no,)).fetchone()["id"]
        if status == "released":
            append_hash(conn, batch_id,
                        {"batch_no": batch_no, "stage": "种植", "plot": code},
                        "种植档案摘要")
            append_hash(conn, batch_id,
                        {"batch_no": batch_no, "stage": "管护", "operations": "施肥/修剪/防治"},
                        "管护记录摘要")
            append_hash(conn, batch_id,
                        {"batch_no": batch_no, "stage": "销售", "report": "农残快检合格"},
                        "销售检测摘要")


EXTRAS_KEY = "demo_extras_v1"


def seed_extras_if_missing() -> bool:
    """给旧库一次性补齐演示用的冷链与农残数据，只填空值、不覆盖用户录入。"""
    with get_conn() as conn:
        if conn.execute("SELECT value FROM settings WHERE key=?", (EXTRAS_KEY,)).fetchone():
            return False

        extras = {
            "LZ-P03-20260702-0001": {
                "timestamps": {
                    "harvest_at": "2026-07-02 05:30:00",
                    "precooled_at": "2026-07-02 08:10:00",
                    "shipped_at": "2026-07-02 14:00:00",
                },
                "test": {
                    "tested_at": "2026-07-02",
                    "lab": "从化区农产品质量安全检测站",
                    "conclusion": "合格",
                    "items": [
                        {"name": "毒死蜱", "value": "0.008", "unit": "mg/kg", "limit": "0.01", "passed": True},
                        {"name": "氯氰菊酯", "value": "0.021", "unit": "mg/kg", "limit": "0.5", "passed": True},
                    ],
                    "operator": "陈伯",
                    "note": "演示数据",
                },
            },
            "LZ-P01-20260708-0002": {
                "timestamps": {},
                "test": {
                    "tested_at": "2026-07-08",
                    "lab": "从化区农产品质量安全检测站",
                    "conclusion": "不合格",
                    "items": [
                        {"name": "高效氯氟氰菊酯", "value": "0.32", "unit": "mg/kg", "limit": "0.2", "passed": False},
                    ],
                    "operator": "陈伯",
                    "note": "演示数据：与安全间隔期拦截形成双重拦截",
                },
            },
        }

        now = datetime.now().isoformat(timespec="seconds")
        for batch_no, data in extras.items():
            row = conn.execute("SELECT id FROM batches WHERE batch_no=?", (batch_no,)).fetchone()
            if not row:
                continue
            for column, value in data["timestamps"].items():
                conn.execute(
                    f"UPDATE batches SET {column}=? WHERE id=? AND ({column} IS NULL OR {column}='')",
                    (value, row["id"]))
            has_test = conn.execute(
                "SELECT 1 FROM residue_tests WHERE batch_id=? LIMIT 1", (row["id"],)).fetchone()
            if has_test:
                continue
            test = data["test"]
            conn.execute(
                "INSERT INTO residue_tests(batch_id, tested_at, lab, conclusion, items_json, report_url, "
                "operator, note, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (row["id"], test["tested_at"], test["lab"], test["conclusion"],
                 json.dumps(test["items"], ensure_ascii=False), None,
                 test["operator"], test["note"], now),
            )
            label = "合格" if test["conclusion"] == "合格" else "不合格"
            conn.execute(
                "UPDATE batches SET detection_report=? WHERE id=?",
                (f"农残快检{label}（{test['lab']} · {test['tested_at']}）", row["id"]),
            )

        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?,?,?)",
            (EXTRAS_KEY, json.dumps({"seeded_at": now}, ensure_ascii=False), now),
        )
        return True
