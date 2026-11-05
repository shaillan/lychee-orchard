"""核心逻辑与接口冒烟测试：python -m unittest discover -s tests -v"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

# 必须在导入 backend 之前指定临时数据库，避免污染演示数据
_TMP = tempfile.mkdtemp(prefix="orchard-test-")
os.environ["ORCHARD_DB"] = str(Path(_TMP) / "test.db")
os.environ["VISION_PROVIDER"] = "mock"
# 测试不碰外网：天气联动在 /api/todos 里会被调用，必须显式关闭
os.environ["WEATHER_ENABLED"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ai_service import (  # noqa: E402
    _image_url,
    _normalize_class,
    _normalize_confidence,
    _remote_recognize,
)
from backend.rules import build_suggestion  # noqa: E402
from backend.traceability import make_batch_no  # noqa: E402
from backend.weather import evaluate_risk  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_batch_code_format(self):
        self.assertEqual(make_batch_no("P03", "2026-07-02", 1), "LZ-P03-20260702-0001")
        self.assertEqual(make_batch_no("P01", "2026-07-08", 2), "LZ-P01-20260708-0002")

    def test_near_harvest_filters_long_interval_pesticides(self):
        # 蒂蛀虫可用药剂间隔期为 7/14 天，10 天采收应只保留 7 天的药剂
        suggestion = build_suggestion("荔枝蒂蛀虫", 0.92, days_to_harvest=10)
        self.assertTrue(suggestion["warnings"])
        self.assertTrue(suggestion["pesticides"])
        for p in suggestion["pesticides"]:
            self.assertLessEqual(p["safe_interval_days"], 10)

        # 5 天采收时全部药剂都来不及过间隔期，必须清空
        tight = build_suggestion("荔枝蒂蛀虫", 0.92, days_to_harvest=5)
        self.assertEqual(tight["pesticides"], [])

    def test_too_close_to_harvest_has_no_pesticide(self):
        suggestion = build_suggestion("荔枝蒂蛀虫", 0.92, days_to_harvest=1)
        self.assertEqual(suggestion["pesticides"], [])
        self.assertTrue(any("非化学" in w for w in suggestion["warnings"]))

    def test_unknowable_result_never_recommends_pesticide(self):
        suggestion = build_suggestion("无法判断", 0.4)
        self.assertEqual(suggestion["pesticides"], [])
        self.assertTrue(suggestion["warnings"])

    def test_healthy_leaf(self):
        suggestion = build_suggestion("健康叶片", 0.95)
        self.assertEqual(suggestion["kind"], "无异常")
        self.assertEqual(suggestion["pesticides"], [])

    def test_healthy_fruit(self):
        # 健康果实必须有独立类别，否则健康果照片会被硬塞进某个病害
        suggestion = build_suggestion("健康果实", 0.93)
        self.assertEqual(suggestion["kind"], "无异常")
        self.assertEqual(suggestion["pesticides"], [])
        self.assertEqual(suggestion["recommended_action"], "none")

    def test_low_confidence_blocks_action(self):
        suggestion = build_suggestion("荔枝炭疽病", 0.6)
        self.assertTrue(suggestion["low_confidence"])
        self.assertEqual(suggestion["recommended_action"], "none")
        self.assertTrue(any("置信度" in w for w in suggestion["warnings"]))

    def test_disease_wording(self):
        # 病害不能说「虫口基数」
        disease = build_suggestion("荔枝炭疽病", 0.9)
        self.assertIn("病源基数", disease["action_reason"])
        self.assertNotIn("虫口", disease["action_reason"])

        insect = build_suggestion("荔枝蝽", 0.9)
        self.assertIn("虫口基数", insect["action_reason"])

    def test_recommended_action_high_risk(self):
        # 高风险且有合规药剂 → 建议用药
        suggestion = build_suggestion("荔枝蒂蛀虫", 0.92, days_to_harvest=30)
        self.assertEqual(suggestion["recommended_action"], "pesticide")
        self.assertTrue(suggestion["action_reason"])

        # 高风险但来不及过间隔期 → 建议人工清除
        tight = build_suggestion("荔枝蒂蛀虫", 0.92, days_to_harvest=5)
        self.assertEqual(tight["recommended_action"], "operation")

    def test_recommended_action_by_risk(self):
        self.assertEqual(build_suggestion("荔枝蝽", 0.9)["recommended_action"], "operation")
        self.assertEqual(build_suggestion("荔枝瘿螨", 0.9)["recommended_action"], "ignore")
        self.assertEqual(build_suggestion("健康叶片", 0.95)["recommended_action"], "none")
        self.assertEqual(build_suggestion("无法判断", 0.4)["recommended_action"], "none")

    def test_normalize_vlm_class(self):
        self.assertEqual(_normalize_class("荔枝蒂蛀虫（Litchi fruit borer）"), "荔枝蒂蛀虫")
        self.assertEqual(_normalize_class("healthy leaf"), "健康叶片")
        self.assertEqual(_normalize_class("healthy fruit"), "健康果实")
        self.assertEqual(_normalize_class("健康果实"), "健康果实")
        self.assertEqual(_normalize_class("霜疫霉"), "荔枝霜疫霉病")
        self.assertEqual(_normalize_class("完全无关的物体"), "无法判断")

    def test_normalize_confidence(self):
        self.assertAlmostEqual(_normalize_confidence("92%"), 0.92)
        self.assertAlmostEqual(_normalize_confidence(93), 0.93)
        self.assertAlmostEqual(_normalize_confidence(0.8), 0.8)
        self.assertAlmostEqual(_normalize_confidence("abc"), 0.0)


class VisionProviderTest(unittest.TestCase):
    """云端识别走 OpenAI 兼容协议：换服务商只改配置，不改代码。"""

    def test_image_url_formats(self):
        from backend import config

        old = config.VISION_IMAGE_FORMAT
        try:
            config.VISION_IMAGE_FORMAT = "data_uri"
            self.assertTrue(_image_url(b"\xff\xd8").startswith("data:image/jpeg;base64,"))
            config.VISION_IMAGE_FORMAT = "raw"
            self.assertFalse(_image_url(b"\xff\xd8").startswith("data:"))
        finally:
            config.VISION_IMAGE_FORMAT = old

    def test_payload_is_openai_compatible(self):
        from unittest import mock

        from backend import config

        fake = mock.Mock()
        fake.json.return_value = {"choices": [{"message": {"content": (
            '{"evidence":"果实表面有针尖状蛀孔，孔口带褐色虫粪",'
            '"class":"荔枝蒂蛀虫","confidence":0.91}'
        )}}]}
        with mock.patch("httpx.post", return_value=fake) as post:
            pest_class, confidence, model_used = _remote_recognize(b"\xff\xd8jpeg")

        self.assertEqual(pest_class, "荔枝蒂蛀虫")
        self.assertAlmostEqual(confidence, 0.91)
        self.assertEqual(model_used, config.VISION_MODEL)

        call = post.call_args
        self.assertEqual(call.args[0], config.VISION_BASE_URL)
        self.assertEqual(call.kwargs["headers"]["Authorization"], f"Bearer {config.VISION_API_KEY}")
        payload = call.kwargs["json"]
        self.assertEqual(payload["model"], config.VISION_MODEL)
        # 智谱对多模态请求带 max_tokens 会报 1210，必须不带
        self.assertNotIn("max_tokens", payload)
        content = payload["messages"][1]["content"]
        self.assertEqual([part["type"] for part in content], ["image_url", "text"])

    def test_disease_without_evidence_is_downgraded(self):
        """防误报硬闸门：模型说没看到病征（或干脆不写证据）时，不许给出病害结论。"""
        from unittest import mock

        for content in (
            '{"class":"荔枝炭疽病","confidence":0.903,"evidence":"未见异常"}',
            '{"class":"荔枝炭疽病","confidence":0.9}',
        ):
            fake = mock.Mock()
            fake.json.return_value = {"choices": [{"message": {"content": content}}]}
            with mock.patch("httpx.post", return_value=fake):
                pest_class, confidence, _ = _remote_recognize(b"\xff\xd8jpeg")
            self.assertEqual(pest_class, "无法判断", content)
            self.assertLessEqual(confidence, 0.3)


class WeatherTest(unittest.TestCase):
    def test_high_risk_on_heavy_rain(self):
        risk = evaluate_risk([{
            "date": "2026-11-06", "precip_mm": 12, "precip_prob": 85, "humidity": 92,
        }])
        self.assertIsNotNone(risk)
        self.assertEqual(risk["level"], "high")
        self.assertEqual(risk["pest"], "荔枝霜疫霉病")

    def test_medium_risk_on_light_rain(self):
        risk = evaluate_risk([{
            "date": "2026-11-06", "precip_mm": 1, "precip_prob": 60, "humidity": 75,
        }])
        self.assertIsNotNone(risk)
        self.assertEqual(risk["level"], "medium")

    def test_dry_forecast_has_no_risk(self):
        self.assertIsNone(evaluate_risk([
            {"date": "2026-11-06", "precip_mm": 0, "precip_prob": 5, "humidity": 60},
            {"date": "2026-11-07", "precip_mm": 0, "precip_prob": 10, "humidity": 65},
        ]))

    def test_none_input(self):
        self.assertIsNone(evaluate_risk(None))
        self.assertIsNone(evaluate_risk([]))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from backend.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_plots_seeded(self):
        res = self.client.get("/api/plots")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 3)

    def test_demo_recognition(self):
        res = self.client.post("/api/recognitions/demo", json={
            "pest_class": "荔枝蒂蛀虫", "days_to_harvest": 5,
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["pest_class"], "荔枝蒂蛀虫")
        self.assertIn("suggestion", body)

    def test_trace_released_batch(self):
        res = self.client.get("/api/trace/LZ-P03-20260702-0001")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "released")
        self.assertGreaterEqual(len(body["hash_chain"]), 1)
        self.assertIn("planting", body)
        self.assertIn("care", body)
        self.assertIn("sales", body)

    def test_hash_chain_detects_tampering(self):
        from backend.db import get_conn

        code = "LZ-P03-20260702-0001"
        before = self.client.get(f"/api/trace/{code}").json()["chain_verify"]
        self.assertTrue(before["valid"])
        self.assertEqual(before["legacy"], [])

        with get_conn() as conn:
            row = conn.execute(
                "SELECT h.id AS id, h.payload_json AS payload_json FROM trace_hash_log h "
                "JOIN batches b ON b.id = h.batch_id WHERE b.trace_code = ? ORDER BY h.id LIMIT 1",
                (code,),
            ).fetchone()
            self.assertIsNotNone(row)
            record_id, original = row["id"], row["payload_json"]
            payload = json.loads(original)
            payload["__tampered__"] = True
            conn.execute(
                "UPDATE trace_hash_log SET payload_json=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), record_id),
            )

        try:
            after = self.client.get(f"/api/trace/{code}").json()["chain_verify"]
            self.assertFalse(after["valid"])
            self.assertIn(record_id, after["tampered"])

            global_check = self.client.get("/api/trace-verify").json()
            self.assertFalse(global_check["valid"])
            self.assertIn(record_id, global_check["tampered"])
        finally:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE trace_hash_log SET payload_json=? WHERE id=?",
                    (original, record_id),
                )

        restored = self.client.get(f"/api/trace/{code}").json()["chain_verify"]
        self.assertTrue(restored["valid"])

    def test_handle_recognition_writes_pesticide(self):
        from backend.db import get_conn

        rec = self.client.post("/api/recognitions/demo", json={
            "pest_class": "荔枝蒂蛀虫", "plot_id": 1, "days_to_harvest": 30,
        }).json()
        self.assertEqual(rec["status"], "pending")

        res = self.client.post(f"/api/recognitions/{rec['id']}/handle", json={
            "method": "pesticide", "pesticide_name": "氯虫苯甲酰胺",
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "handled")
        self.assertIsNotNone(body["pesticide_record_id"])

        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM pesticide_records WHERE id=?", (body["pesticide_record_id"],)
            ).fetchone()
            self.assertEqual(row["pesticide_name"], "氯虫苯甲酰胺")
            rec_row = conn.execute(
                "SELECT status, handle_method, pesticide_record_id FROM recognitions WHERE id=?",
                (rec["id"],),
            ).fetchone()
            self.assertEqual(rec_row["status"], "handled")
            self.assertEqual(rec_row["handle_method"], "pesticide")
            self.assertEqual(rec_row["pesticide_record_id"], body["pesticide_record_id"])

    def test_handle_ignore_and_false_positive(self):
        rid = None
        for method, expected in (("ignore", "ignored"), ("false_positive", "false_positive")):
            rec = self.client.post("/api/recognitions/demo", json={
                "pest_class": "荔枝蝽", "plot_id": 2,
            }).json()
            res = self.client.post(f"/api/recognitions/{rec['id']}/handle", json={"method": method})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], expected)
            rid = rec["id"]

        # 重复处置应拒绝
        dup = self.client.post(f"/api/recognitions/{rid}/handle", json={"method": "ignore"})
        self.assertEqual(dup.status_code, 409)

    def test_todos_exclude_handled(self):
        from backend.db import get_conn

        # 造一批待处置识别，确保该虫害进入「未处置」待办（聚合只取前 2 类）
        for _ in range(30):
            self.client.post("/api/recognitions/demo", json={"pest_class": "荔枝尺蠖", "plot_id": 1})

        titles = [i["title"] for i in self.client.get("/api/todos").json()]
        self.assertTrue(any("尺蠖" in t and "未处置" in t for t in titles), titles)

        cutoff = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
        with get_conn() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM recognitions WHERE detected_class='荔枝尺蠖' "
                "AND status='pending' AND created_at>=?", (cutoff,)).fetchall()]
        self.assertTrue(ids)
        for rid in ids:
            res = self.client.post(f"/api/recognitions/{rid}/handle", json={"method": "ignore"})
            self.assertEqual(res.status_code, 200)

        titles = [i["title"] for i in self.client.get("/api/todos").json()]
        self.assertFalse(any("尺蠖" in t for t in titles), titles)

    def test_qrcode_png(self):
        res = self.client.get("/api/batches/LZ-P03-20260702-0001/qrcode")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "image/png")
        self.assertTrue(res.content.startswith(b"\x89PNG"))

    def test_pesticide_cas_validation(self):
        res = self.client.post("/api/pesticide-records", json={
            "plot_id": 1, "pesticide_name": "不存在的农药",
        })
        self.assertEqual(res.status_code, 400)

        res2 = self.client.post("/api/pesticide-records", json={
            "plot_id": 1, "pesticide_name": "高效氯氟氰菊酯", "cas_no": "000-00-0",
        })
        self.assertEqual(res2.status_code, 400)

    def test_safety_interval_blocks_harvest_today(self):
        # 种子数据中 P01 区 3 天前施用高效氯氟氰菊酯（间隔期 14 天）
        res = self.client.post("/api/batches", json={
            "plot_id": 1, "harvest_date": date.today().isoformat(), "packaging_seq": 99,
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "blocked")
        self.assertTrue(body["block_reason"])

    def test_dashboard_endpoints(self):
        for path in (
            "/api/dashboard/summary",
            "/api/dashboard/yield-trend",
            "/api/dashboard/pesticide-trend",
            "/api/dashboard/pest-trend",
            "/api/dashboard/pest-heatmap",
            "/api/dashboard/compliance",
        ):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)

    def test_compliance_rows_derive_dates(self):
        apply_day = date.today() - timedelta(days=2)
        created = self.client.post("/api/pesticide-records", json={
            "plot_id": 1, "pesticide_name": "高效氯氟氰菊酯",
            "apply_time": apply_day.isoformat(),
        }).json()
        # 高效氯氟氰菊酯安全间隔期 14 天
        self.assertEqual(created["safe_interval_days"], 14)

        body = self.client.get("/api/dashboard/compliance?limit=500").json()
        self.assertIn("as_of", body)
        row = next(r for r in body["rows"] if r["id"] == created["id"])
        self.assertEqual(row["earliest_harvest_date"],
                         (apply_day + timedelta(days=14)).isoformat())
        self.assertEqual(row["days_remaining"], 12)
        self.assertEqual(row["status"], "waiting")
        self.assertFalse(row["safe"])
        self.assertTrue(row["plot_name"])

    def test_compliance_csv(self):
        res = self.client.get("/api/dashboard/compliance.csv")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/csv"))
        self.assertIn("attachment", res.headers["content-disposition"])
        self.assertEqual(res.content[:3], b"\xef\xbb\xbf")  # UTF-8 BOM

        rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
        self.assertIn("地块", rows[0])
        self.assertIn("最早采收日期", rows[0])
        self.assertIn("安全间隔期(天)", rows[0])
        self.assertTrue(any(r[1] == "高效氯氟氰菊酯" for r in rows[1:]))

    def test_trace_has_pesticide_list(self):
        body = self.client.get("/api/trace/LZ-P03-20260702-0001").json()
        pesticides = body["care"]["pesticides"]
        self.assertIsInstance(pesticides, list)
        for p in pesticides:
            self.assertIn("earliest_harvest_date", p)
            self.assertIn("safe", p)

    def test_recognition_list_filter_and_shape(self):
        rec = self.client.post("/api/recognitions/demo", json={
            "pest_class": "荔枝蝽", "plot_id": 2,
        }).json()

        rows = self.client.get("/api/recognitions?status=pending&limit=300").json()
        self.assertTrue(rows)
        self.assertTrue(all(r["status"] == "pending" for r in rows))
        mine = next(r for r in rows if r["id"] == rec["id"])
        self.assertEqual(json.loads(mine["suggestion_json"])["pest_class"], "荔枝蝽")

        self.client.post(f"/api/recognitions/{rec['id']}/handle", json={"method": "ignore"})
        after = self.client.get("/api/recognitions?status=pending&limit=300").json()
        self.assertFalse(any(r["id"] == rec["id"] for r in after))

        bad = self.client.get("/api/recognitions?status=bogus")
        self.assertEqual(bad.status_code, 400)

    def test_todos_without_weather(self):
        items = self.client.get("/api/todos").json()
        self.assertTrue(all(i.get("type") != "weather" for i in items))


if __name__ == "__main__":
    unittest.main(verbosity=2)
