"""核心逻辑与接口冒烟测试：python -m unittest discover -s tests -v"""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
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
    CONFIRM_SYSTEM_PROMPT,
    _image_url,
    _normalize_class,
    _normalize_confidence,
    _remote_recognize,
    _verify_prediction,
)
from backend.rules import (  # noqa: E402
    PEST_CLASSES,
    PESTICIDES,
    PESTS,
    build_suggestion,
    validate_knowledge,
)
from backend.traceability import make_batch_no  # noqa: E402
from backend import weather  # noqa: E402
from backend.weather import evaluate_risk  # noqa: E402


def _vision_response(content: str) -> mock.Mock:
    """构造一个 OpenAI 兼容的成功响应。"""
    fake = mock.Mock()
    fake.status_code = 200
    fake.json.return_value = {"choices": [{"message": {"content": content}}]}
    return fake


class KnowledgeBaseTest(unittest.TestCase):
    def test_validate_knowledge_clean(self):
        self.assertEqual(validate_knowledge(), [])

    def test_validate_catches_missing_non_chemical(self):
        pests = copy.deepcopy(PESTS)
        pests["荔枝炭疽病"]["non_chemical"] = []
        self.assertTrue(any("non_chemical" in p for p in validate_knowledge(pests=pests)))

    def test_validate_catches_unknown_confusable(self):
        pests = copy.deepcopy(PESTS)
        pests["荔枝炭疽病"]["differential"]["confusable"] = ["不存在的病害"]
        self.assertTrue(any("未知类别" in p for p in validate_knowledge(pests=pests)))

    def test_validate_catches_duplicate_alias(self):
        pests = copy.deepcopy(PESTS)
        pests["荔枝炭疽病"]["aliases"].append("蝽")  # 与荔枝蝽的别名冲突
        self.assertTrue(any("重复" in p for p in validate_knowledge(pests=pests)))

    def test_validate_catches_unknown_pesticide_target(self):
        pesticides = copy.deepcopy(PESTICIDES)
        pesticides[0]["targets"] = ["不存在的虫"]
        problems = validate_knowledge(pesticides=pesticides)
        self.assertTrue(any("未知类别" in p for p in problems))

    def test_suggestion_exposes_knowledge_fields(self):
        for name in PEST_CLASSES:
            s = build_suggestion(name, 0.9)
            self.assertTrue(s["host_parts"], name)
            self.assertTrue(s["non_chemical"], name)
            self.assertTrue(s["differential"]["confusable"], name)
            self.assertTrue(s["differential"]["distinguishing"], name)
            for other in s["differential"]["confusable"]:
                self.assertIn(other, PESTS)
                self.assertNotEqual(other, name)

        healthy = build_suggestion("健康果实", 0.95)
        self.assertEqual(healthy["host_parts"], [])
        self.assertEqual(healthy["non_chemical"], [])
        self.assertEqual(healthy["differential"], {"confusable": [], "distinguishing": []})

    def test_action_uses_knowledge_base_measures(self):
        disease = build_suggestion("荔枝炭疽病", 0.9)
        self.assertIn("剪除病枝病叶并集中销毁", disease["action_reason"])
        self.assertIn("病源基数", disease["action_reason"])
        self.assertNotIn("虫口", disease["action_reason"])

        insect = build_suggestion("荔枝蝽", 0.9)
        self.assertIn("清晨低温时人工捕杀成虫", insect["action_reason"])
        self.assertIn("虫口基数", insect["action_reason"])

    def test_alias_normalization(self):
        cases = {
            "荔蝽": "荔枝蝽",
            "litchi fruit borer": "荔枝蒂蛀虫",
            "healthy fruit": "健康果实",
            "healthy": "健康叶片",
            "unknown": "无法判断",
            "正常叶片": "健康叶片",
            "霜疫霉": "荔枝霜疫霉病",
        }
        for raw, expected in cases.items():
            self.assertEqual(_normalize_class(raw), expected, raw)


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
        self.assertEqual(post.call_count, 1)

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


class ConfirmVerificationTest(unittest.TestCase):
    """二次确认：病虫害结论要经得起「换个问法再问一次」。"""

    def test_confirm_true(self):
        content = ('{"observed":"果面有针尖状蛀孔，孔口带褐色虫粪",'
                   '"present":true,"reason":"见蛀孔与虫粪"}')
        with mock.patch("httpx.post", return_value=_vision_response(content)) as post:
            pest_class, confidence, verification = _verify_prediction(
                b"\xff\xd8jpeg", "荔枝蒂蛀虫", 0.91, "glm-x", True)

        self.assertEqual(pest_class, "荔枝蒂蛀虫")
        self.assertAlmostEqual(confidence, 0.91)
        self.assertEqual(verification["status"], "confirmed")
        self.assertEqual(post.call_count, 1)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "glm-x")
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["messages"][0]["content"], CONFIRM_SYSTEM_PROMPT)
        question = payload["messages"][1]["content"][1]["text"]
        self.assertIn("针尖状蛀孔", question)
        self.assertIn("荔枝炭疽病", question)

    def test_confirm_false_downgrades(self):
        content = '{"observed":"果皮均匀，未见病斑","present":false,"reason":"未见典型症状"}'
        with mock.patch("httpx.post", return_value=_vision_response(content)):
            pest_class, confidence, verification = _verify_prediction(
                b"\xff\xd8jpeg", "荔枝炭疽病", 0.903, "glm-x", True)

        self.assertEqual(pest_class, "无法判断")
        self.assertAlmostEqual(confidence, 0.3)
        self.assertEqual(verification["status"], "rejected")

    def test_confirm_failure_keeps_first_result(self):
        with mock.patch("httpx.post", side_effect=RuntimeError("boom")):
            pest_class, confidence, verification = _verify_prediction(
                b"\xff\xd8jpeg", "荔枝炭疽病", 0.9, "glm-x", True)

        self.assertEqual(pest_class, "荔枝炭疽病")
        self.assertAlmostEqual(confidence, 0.9)
        self.assertEqual(verification["status"], "unavailable")
        self.assertTrue(verification["reason"].startswith("error:"))

    def test_confirm_malformed_keeps_first_result(self):
        with mock.patch("httpx.post", return_value=_vision_response("我觉得是炭疽病")):
            pest_class, _, verification = _verify_prediction(
                b"\xff\xd8jpeg", "荔枝炭疽病", 0.9, "glm-x", True)

        self.assertEqual(pest_class, "荔枝炭疽病")
        self.assertEqual(verification["status"], "unavailable")
        self.assertEqual(verification["reason"], "malformed")

    def test_confirm_skipped_for_healthy(self):
        with mock.patch("httpx.post") as post:
            pest_class, _, verification = _verify_prediction(
                b"\xff\xd8jpeg", "健康果实", 0.95, "glm-x", True)

        post.assert_not_called()  # 健康照片必须保持一次调用
        self.assertEqual(pest_class, "健康果实")
        self.assertEqual(verification["reason"], "not_pest")

    def test_confirm_skipped_when_disabled(self):
        with mock.patch("httpx.post") as post:
            _, _, verification = _verify_prediction(
                b"\xff\xd8jpeg", "荔枝炭疽病", 0.9, "glm-x", False)

        post.assert_not_called()
        self.assertEqual(verification["reason"], "disabled")

    def test_confirm_no_retry_on_rate_limit(self):
        fake = mock.Mock()
        fake.status_code = 429
        fake.raise_for_status.side_effect = RuntimeError("429")
        with mock.patch("httpx.post", return_value=fake) as post:
            pest_class, _, verification = _verify_prediction(
                b"\xff\xd8jpeg", "荔枝炭疽病", 0.9, "glm-x", True)

        self.assertEqual(post.call_count, 1)  # 限流时不重试、不翻倍
        self.assertEqual(pest_class, "荔枝炭疽病")
        self.assertEqual(verification["status"], "unavailable")

    def test_recognize_rejected_suffix_and_result(self):
        from backend import ai_service

        with mock.patch.object(ai_service, "current_provider", return_value="api"), \
                mock.patch.object(ai_service, "_remote_recognize",
                                  return_value=("荔枝蒂蛀虫", 0.91, "glm-x")), \
                mock.patch.object(ai_service, "_confirm_presence",
                                  return_value=(False, "未见蛀孔")):
            result = ai_service.recognize(b"\xff\xd8jpeg")

        self.assertEqual(result["pest_class"], "无法判断")
        self.assertAlmostEqual(result["confidence"], 0.3)
        self.assertTrue(result["source"].endswith("#confirm_false"))
        self.assertFalse(result["is_mock"])
        self.assertEqual(result["suggestion"]["verification"]["status"], "rejected")
        self.assertTrue(any("二次确认" in w for w in result["suggestion"]["warnings"]))

    def test_mock_provider_skips_confirm(self):
        from backend import ai_service

        result = ai_service.recognize(b"mock-image-bytes")
        self.assertEqual(result["verification"]["status"], "skipped")
        self.assertEqual(result["verification"]["reason"], "mock")


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

    def test_location_override(self):
        risk = evaluate_risk([{
            "date": "2026-11-06", "precip_mm": 12, "precip_prob": 85, "humidity": 92,
        }], location="广东广州")
        self.assertEqual(risk["location"], "广东广州")
        self.assertIn("广东广州", risk["detail"])


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

    def test_demo_persists_verification(self):
        """演示结果也要带复核状态，历史回看才解释得清「为什么没有结论」。"""
        rec = self.client.post("/api/recognitions/demo", json={"pest_class": "荔枝炭疽病"}).json()
        self.assertEqual(rec["verification"]["status"], "skipped")

        rows = self.client.get("/api/recognitions?limit=300").json()
        mine = next(r for r in rows if r["id"] == rec["id"])
        saved = json.loads(mine["suggestion_json"])
        self.assertEqual(saved["verification"]["reason"], "demo")

    def test_pests_exposes_knowledge_fields(self):
        rows = {p["name"]: p for p in self.client.get("/api/pests").json()}
        anthracnose = rows["荔枝炭疽病"]
        self.assertIn("果实", anthracnose["host_parts"])
        self.assertEqual(anthracnose["differential"]["confusable"], ["荔枝霜疫霉病"])
        self.assertTrue(anthracnose["non_chemical"])
        self.assertEqual(rows["健康果实"]["non_chemical"], [])

    def test_todos_without_weather(self):
        items = self.client.get("/api/todos").json()
        self.assertTrue(all(i.get("type") != "weather" for i in items))


class WeatherRegionApiTest(unittest.TestCase):
    """天气地区：界面保存 → SQLite → 待办/风险接口立即生效。"""

    _GZ = {"name": "广州", "admin1": "广东", "lat": 23.11667, "lon": 113.25}
    _DRY = [{"date": "2026-11-06", "precip_mm": 0, "precip_prob": 5, "humidity": 60}]

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from backend.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self._clear_region()

    def tearDown(self):
        self._clear_region()

    @staticmethod
    def _clear_region():
        from backend.db import get_conn

        with get_conn() as conn:
            conn.execute("DELETE FROM settings WHERE key='weather_region'")
        with weather._LOCK:
            weather._CACHE.update(key=None, expires=0.0, risk=None, loaded=False)

    def test_region_default_from_env(self):
        from backend import config

        body = self.client.get("/api/weather/region").json()
        self.assertFalse(body["enabled"])  # 测试环境 WEATHER_ENABLED=0
        region = body["region"]
        self.assertEqual(region["source"], "env")
        self.assertEqual(region["lat"], config.WEATHER_LAT)
        self.assertEqual(region["lon"], config.WEATHER_LON)
        self.assertEqual(region["label"], config.WEATHER_LOCATION)

    def test_save_region_persists(self):
        with mock.patch.object(weather, "geocode", return_value=dict(self._GZ)):
            res = self.client.put("/api/weather/region", json={"name": " 广州 "})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["region"]["source"], "db")
        self.assertEqual(body["region"]["label"], "广东广州")
        self.assertEqual(body["matched"]["name"], "广州")

        again = self.client.get("/api/weather/region").json()["region"]
        self.assertEqual(again["source"], "db")
        self.assertEqual(again["name"], "广州")
        self.assertAlmostEqual(again["lat"], 23.11667)

        from backend.db import get_conn

        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='weather_region'").fetchone()
        self.assertIn("广州", row["value"])

    def test_save_region_not_found(self):
        with mock.patch.object(weather, "geocode", return_value=None):
            res = self.client.put("/api/weather/region", json={"name": "从化"})
        self.assertEqual(res.status_code, 404)
        self.assertIn("未找到", res.json()["detail"])

    def test_save_region_upstream_error(self):
        with mock.patch.object(weather, "geocode", side_effect=RuntimeError("down")):
            res = self.client.put("/api/weather/region", json={"name": "广州"})
        self.assertEqual(res.status_code, 502)

    def test_save_region_blank_name(self):
        res = self.client.put("/api/weather/region", json={"name": "   "})
        self.assertEqual(res.status_code, 400)

    def test_geocode_parses_first_result(self):
        fake = mock.Mock()
        fake.status_code = 200
        fake.json.return_value = {"results": [{
            "name": "广州市", "latitude": 23.13, "longitude": 113.26,
            "admin1": "广东省", "country": "中国",
        }]}
        with mock.patch("httpx.get", return_value=fake) as get:
            out = weather.geocode("广州")

        self.assertEqual(out["name"], "广州市")
        self.assertEqual(out["admin1"], "广东省")
        self.assertAlmostEqual(out["lat"], 23.13)
        self.assertEqual(get.call_args.kwargs["params"]["language"], "zh")

    def test_geocode_no_results(self):
        fake = mock.Mock()
        fake.status_code = 200
        fake.json.return_value = {"results": []}
        with mock.patch("httpx.get", return_value=fake):
            self.assertIsNone(weather.geocode("不存在的地方"))

    def test_region_change_invalidates_cache(self):
        with mock.patch.object(weather.config, "WEATHER_ENABLED", True), \
                mock.patch.object(weather, "_fetch_days", return_value=self._DRY) as fetch:
            weather.save_region("广州", "广东", 23.11667, 113.25)
            self.assertIsNone(weather.get_pest_risk())
            self.assertIsNone(weather.get_pest_risk())  # 同地区命中缓存
            self.assertEqual(fetch.call_count, 1)

            weather.save_region("茂名", "广东", 21.66625, 110.91364)
            self.assertIsNone(weather.get_pest_risk())
            self.assertEqual(fetch.call_count, 2)  # 换地区不复用旧缓存

    def test_pest_risk_reports_saved_region(self):
        weather.save_region("广州", "广东", 23.11667, 113.25)
        body = self.client.get("/api/weather/pest-risk").json()
        self.assertFalse(body["enabled"])
        self.assertIsNone(body["risk"])
        self.assertEqual(body["location"], "广东广州")
        self.assertEqual(body["region"]["name"], "广州")


if __name__ == "__main__":
    unittest.main(verbosity=2)
