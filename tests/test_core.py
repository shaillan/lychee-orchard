"""核心逻辑与接口冒烟测试：python -m unittest discover -s tests -v"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

# 必须在导入 backend 之前指定临时数据库，避免污染演示数据
_TMP = tempfile.mkdtemp(prefix="orchard-test-")
os.environ["ORCHARD_DB"] = str(Path(_TMP) / "test.db")
os.environ["VISION_PROVIDER"] = "mock"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ai_service import _normalize_class, _normalize_confidence  # noqa: E402
from backend.rules import build_suggestion  # noqa: E402
from backend.traceability import make_batch_no  # noqa: E402


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

    def test_normalize_vlm_class(self):
        self.assertEqual(_normalize_class("荔枝蒂蛀虫（Litchi fruit borer）"), "荔枝蒂蛀虫")
        self.assertEqual(_normalize_class("healthy leaf"), "健康叶片")
        self.assertEqual(_normalize_class("霜疫霉"), "荔枝霜疫霉病")
        self.assertEqual(_normalize_class("完全无关的物体"), "无法判断")

    def test_normalize_confidence(self):
        self.assertAlmostEqual(_normalize_confidence("92%"), 0.92)
        self.assertAlmostEqual(_normalize_confidence(93), 0.93)
        self.assertAlmostEqual(_normalize_confidence(0.8), 0.8)
        self.assertAlmostEqual(_normalize_confidence("abc"), 0.0)


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
        ):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
