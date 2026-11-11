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
    _apply_evidence_check,
    _image_url,
    _normalize_class,
    _normalize_confidence,
    _parse_confirm_content,
    _parse_vlm_content,
    _remote_recognize,
    _verify_prediction,
    _vision_chat,
)
from backend.rules import (  # noqa: E402
    PEST_CLASSES,
    PESTICIDES,
    PESTS,
    build_suggestion,
    validate_knowledge,
)
from backend.traceability import make_batch_no  # noqa: E402
from backend import crack, maturity, patrol, weather  # noqa: E402
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
            self.assertTrue(s["peak_months"], name)
            self.assertTrue(s["monitoring"], name)
            self.assertTrue(s["biological"], name)
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

    def test_new_entries_registered(self):
        # 2026-11 扩充：6 个广东常见病虫，合计 18 个病虫害类别
        names = ["荔枝酸腐病", "荔枝龟背天牛", "荔枝吸果夜蛾", "荔枝蚜虫", "荔枝蓟马", "荔枝金龟子"]
        for name in names:
            self.assertIn(name, PESTS)
            self.assertIn(name, PEST_CLASSES)
        kinds = {name: PESTS[name]["kind"] for name in names}
        self.assertEqual(kinds["荔枝酸腐病"], "病害")
        self.assertEqual({kinds[n] for n in names if n != "荔枝酸腐病"}, {"虫害"})
        self.assertEqual(len(PEST_CLASSES), 18)

    def test_new_entries_have_drugs_or_explicit_no_drug(self):
        # 蚜虫/蓟马/金龟子有可轮换药剂；天牛/吸果夜蛾/酸腐病以非化学措施为主
        for name in ("荔枝蚜虫", "荔枝蓟马", "荔枝金龟子"):
            s = build_suggestion(name, 0.9)
            self.assertTrue(s["pesticides"], name)
            for p in s["pesticides"]:
                self.assertGreater(p["safe_interval_days"], 0)

        for name in ("荔枝龟背天牛", "荔枝酸腐病"):
            s = build_suggestion(name, 0.9)
            self.assertEqual(s["pesticides"], [], name)
            self.assertEqual(s["recommended_action"], "operation", name)
            self.assertIn("物理/农业防治", s["action_reason"], name)

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
            pest_class, confidence, model_used, _ = _remote_recognize(b"\xff\xd8jpeg")

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
                pest_class, confidence, _, _ = _remote_recognize(b"\xff\xd8jpeg")
            self.assertEqual(pest_class, "无法判断", content)
            self.assertLessEqual(confidence, 0.3)

    def test_insect_evidence_accepts_body_without_disease_spots(self):
        """虫害照片写「无病斑」是正常的，不能因此误杀正确的虫体识别。"""
        pest_class, confidence = _apply_evidence_check(
            "荔枝龟背天牛", 0.9, "叶片上有橙黑相间带斑纹的甲虫，无病斑、霉层等异常")
        self.assertEqual(pest_class, "荔枝龟背天牛")
        self.assertAlmostEqual(confidence, 0.9)

    def test_insect_evidence_rejects_absent_body(self):
        pest_class, confidence = _apply_evidence_check(
            "荔枝龟背天牛", 0.9, "枝干表面未见虫体，也无蛀孔")
        self.assertEqual(pest_class, "无法判断")
        self.assertLessEqual(confidence, 0.3)

    def test_sooty_mold_evidence_is_accepted(self):
        """煤烟病的证据是「黑色煤污层」，旧关键词只认「黑点/病斑」，会误杀。"""
        pest_class, confidence = _apply_evidence_check(
            "荔枝煤烟病", 0.85, "叶片表面覆盖一层黑色煤污状霉层，多分布在叶背")
        self.assertEqual(pest_class, "荔枝煤烟病")
        self.assertAlmostEqual(confidence, 0.85)

    def test_mite_damage_evidence_is_accepted(self):
        """瘿螨只拍得到为害状（畸形/卷曲），不能因为没有虫体就否掉。"""
        pest_class, confidence = _apply_evidence_check(
            "荔枝瘿螨", 0.8, "叶背出现毛毡状隆起，叶片皱缩卷曲")
        self.assertEqual(pest_class, "荔枝瘿螨")

    def test_healthy_rejects_when_insects_described(self):
        """模型一边说「健康叶片」一边描述介壳虫，是自相矛盾的结论。"""
        pest_class, confidence = _apply_evidence_check(
            "健康叶片", 1.0, "叶背附着少量白色介壳虫，叶面整体平整")
        self.assertEqual(pest_class, "无法判断")
        self.assertLessEqual(confidence, 0.3)

    def test_checklist_fields_build_evidence(self):
        """逐项检查全为「无」时，应补出「未见异常」，否则健康结论会被闸门误杀。"""
        content = json.dumps({
            "shape": "无", "color": "无", "surface": "无", "insects": "无",
            "class": "健康叶片", "confidence": 1,
        }, ensure_ascii=False)
        pest_class, confidence, evidence = _parse_vlm_content(content)
        self.assertEqual(pest_class, "健康叶片")
        self.assertIn("未见异常", evidence)
        self.assertEqual(_apply_evidence_check(pest_class, confidence, evidence)[0], "健康叶片")

    def test_numeric_key_schema_is_accepted(self):
        """模型有时改用 "1"~"6" 当键，不能因此把整张图判成无法判断。"""
        content = json.dumps({
            "1": "有卷曲", "2": "有褐色斑点、褪绿",
            "3": "无霉层、无白粉", "4": "无",
            "5": "荔枝瘿螨", "6": 0.8,
        }, ensure_ascii=False)
        pest_class, confidence, evidence = _parse_vlm_content(content)
        self.assertEqual(pest_class, "荔枝瘿螨")
        self.assertAlmostEqual(confidence, 0.8)
        self.assertIn("卷曲", evidence)

    def test_checklist_insect_found_blocks_healthy(self):
        """检查项里写了「有虫」，模型却仍填健康叶片，必须降级。"""
        content = json.dumps({
            "shape": "无", "color": "无", "surface": "无", "insects": "有,花簇处",
            "class": "健康叶片", "confidence": 1,
        }, ensure_ascii=False)
        pest_class, confidence, evidence = _parse_vlm_content(content)
        self.assertEqual(_apply_evidence_check(pest_class, confidence, evidence)[0], "无法判断")

    def test_checklist_mite_damage_passes_insect_gate(self):
        content = json.dumps({
            "shape": "卷曲:有,畸形:有", "color": "异常发红:有", "surface": "无",
            "insects": "无", "class": "荔枝瘿螨", "confidence": 0.8,
        }, ensure_ascii=False)
        pest_class, confidence, evidence = _parse_vlm_content(content)
        self.assertEqual(_apply_evidence_check(pest_class, confidence, evidence)[0], "荔枝瘿螨")

    def test_negation_scope_covers_enumerations(self):
        """「无明显病斑、霉层」这一串都是否定，不能因为「霉层」离「无」远就当成病征。"""
        pest_class, confidence = _apply_evidence_check(
            "健康果实", 0.9, "果皮着色均匀，无明显病斑、霉层")
        self.assertEqual(pest_class, "健康果实")
        self.assertAlmostEqual(confidence, 0.9)

    def test_healthy_requires_negative_evidence(self):
        pest_class, _ = _apply_evidence_check("健康叶片", 0.9, "叶片平整，光照充足")
        self.assertEqual(pest_class, "无法判断")
        pest_class, confidence = _apply_evidence_check(
            "健康叶片", 0.9, "叶片翠绿平整，无病斑、未见虫体")
        self.assertEqual(pest_class, "健康叶片")
        self.assertAlmostEqual(confidence, 0.9)


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

    def test_confirm_prompt_carries_first_pass_evidence(self):
        """复核要把首轮看到的异常带上，否则模型会重新瞎扫一遍、把正确结论否掉。"""
        content = '{"observed":"叶背有毛毡状绒毛","present":true,"reason":"见绒毛"}'
        with mock.patch("httpx.post", return_value=_vision_response(content)) as post:
            _verify_prediction(b"\xff\xd8jpeg", "荔枝瘿螨", 0.8, "glm-x", True,
                               "形态卷曲:有；虫体无")
        question = post.call_args.kwargs["json"]["messages"][1]["content"][1]["text"]
        self.assertIn("第一轮记录到的异常", question)
        self.assertIn("形态卷曲", question)

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
                                  return_value=("荔枝蒂蛀虫", 0.91, "glm-x", "果面有蛀孔")), \
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


class VisionJsonParsingTest(unittest.TestCase):
    """模型偶尔会输出两个 JSON 对象，贪婪正则会把它们拼在一起导致整张图降级。"""

    def test_trailing_second_object_is_ignored(self):
        content = (
            '{"class":"荔枝蝽","confidence":0.9,"evidence":"叶片上有虫孔"}\n'
            '{"class":"健康叶片","confidence":0.8,"evidence":"无异常"}'
        )
        pest_class, confidence, evidence = _parse_vlm_content(content)
        self.assertEqual(pest_class, "荔枝蝽")
        self.assertAlmostEqual(confidence, 0.9)
        self.assertEqual(evidence, "叶片上有虫孔")

    def test_markdown_fence(self):
        content = '```json\n{"class":"荔枝炭疽病","confidence":"85%","evidence":"果面褐色病斑"}\n```'
        pest_class, confidence, _ = _parse_vlm_content(content)
        self.assertEqual(pest_class, "荔枝炭疽病")
        self.assertAlmostEqual(confidence, 0.85)

    def test_leading_explanation_with_braces(self):
        content = '说明 {不是JSON} 正式结果：{"class":"健康果实","confidence":0.95}'
        pest_class, confidence, _ = _parse_vlm_content(content)
        self.assertEqual(pest_class, "健康果实")
        self.assertAlmostEqual(confidence, 0.95)

    def test_broken_index_and_field_keys_are_repaired(self):
        """实测输出 `"1": "shape": "有 卷曲"` 不是合法 JSON，但不能整张图作废。"""
        content = (
            '{\n  "1": "shape": "有 卷曲",\n  "2": "color": "有 褐色斑点",\n'
            '  "3": "surface": "无",\n  "4": "insects": "无",\n'
            '  "5": "荔枝瘿螨",\n  "6": 0.8\n}'
        )
        pest_class, confidence, evidence = _parse_vlm_content(content)
        self.assertEqual(pest_class, "荔枝瘿螨")
        self.assertAlmostEqual(confidence, 0.8)
        self.assertIn("形态有 卷曲", evidence)
        self.assertIn("颜色有 褐色斑点", evidence)

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            _parse_vlm_content("我觉得是炭疽病")
        with self.assertRaises(ValueError):
            _parse_vlm_content("")

    def test_confirm_trailing_object(self):
        content = ('{"observed":"见蛀孔","present":true,"reason":"有虫粪"}\n'
                   '{"observed":"duplicate","present":false,"reason":"x"}')
        present, reason = _parse_confirm_content(content)
        self.assertIs(present, True)
        self.assertEqual(reason, "有虫粪")

    def test_timeout_falls_back_to_next_model(self):
        """主模型超时不能直接判整张图失败，要换备选模型再试。"""
        from unittest import mock

        import httpx

        fake = mock.Mock()
        fake.status_code = 200
        fake.json.return_value = {"choices": [{"message": {
            "content": '{"class":"健康叶片","confidence":0.9}'}}]}
        with mock.patch("httpx.post",
                        side_effect=[httpx.ReadTimeout("timeout"), fake]):
            content, model = _vision_chat(
                b"\xff\xd8jpeg", "sys", "user", models=["slow-model", "backup-model"])

        self.assertEqual(model, "backup-model")
        self.assertIn("健康叶片", content)

    def test_non_json_gateway_response_falls_back(self):
        from unittest import mock

        bad = mock.Mock()
        bad.status_code = 200
        bad.json.side_effect = ValueError("not json")
        bad.text = "<html>gateway error</html>"
        good = mock.Mock()
        good.status_code = 200
        good.json.return_value = {"choices": [{"message": {
            "content": '{"class":"健康果实","confidence":0.8}'}}]}
        with mock.patch("httpx.post", side_effect=[bad, good]):
            content, model = _vision_chat(
                b"\xff\xd8jpeg", "sys", "user", models=["m1", "m2"])

        self.assertEqual(model, "m2")
        self.assertIn("健康果实", content)


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
        # 采后段：冷链节点与农残快检（种子演示数据补齐）
        self.assertIn("cold_chain", body["sales"])
        self.assertIn("residue_tests", body["sales"])
        self.assertTrue(body["sales"]["residue_tests"])
        self.assertEqual(body["sales"]["residue_conclusion"], "合格")
        self.assertIn(body["sales"]["cold_chain"]["status"],
                      {"cooling", "transit", "arrived"})

    def test_dashboard_summary_new_fields(self):
        body = self.client.get("/api/dashboard/summary").json()
        for key in ("coldchain_overdue", "residue_unqualified", "harvest_ready"):
            self.assertIn(key, body)
        self.assertIsInstance(body["harvest_ready"], list)

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

    def test_expired_cache_served_without_blocking(self):
        """缓存过期时先返回旧结论，外部请求交给后台线程：接口不再被天气拖慢 1~3 秒。"""
        stale = {"pest": "荔枝霜疫霉病", "level": "high", "date": "2026-11-06",
                 "precip_mm": 12.0, "precip_prob": 90, "humidity": 92,
                 "detail": "旧结论", "location": "广东广州", "source": "Open-Meteo"}
        with mock.patch.object(weather.config, "WEATHER_ENABLED", True), \
                mock.patch.object(weather, "_fetch_days", return_value=self._DRY) as fetch, \
                mock.patch.object(weather, "_refresh_in_background") as bg:
            weather.save_region("广州", "广东", 23.11667, 113.25)
            with weather._LOCK:
                weather._CACHE.update(key=(23.117, 113.25), loaded=True,
                                      expires=0.0, risk=stale)
            self.assertEqual(weather.get_pest_risk(), stale)
            self.assertEqual(fetch.call_count, 0)   # 没有同步等外部接口
            bg.assert_called_once()                 # 改成后台刷新

    def test_pest_risk_reports_saved_region(self):
        weather.save_region("广州", "广东", 23.11667, 113.25)
        body = self.client.get("/api/weather/pest-risk").json()
        self.assertFalse(body["enabled"])
        self.assertIsNone(body["risk"])
        self.assertEqual(body["location"], "广东广州")
        self.assertEqual(body["region"]["name"], "广州")


class MaturityTest(unittest.TestCase):
    """采收窗口是纯日历规则：边界、未知品种、物候期。"""

    def test_unknown_variety_falls_back_to_default(self):
        info = maturity.window_for("白糖罂", date(2026, 6, 16))
        self.assertEqual(info["window_start"], "2026-06-15")
        self.assertEqual(info["window_end"], "2026-07-15")
        self.assertEqual(info["status"], "最佳")

    def test_status_boundaries(self):
        near = maturity.window_for("妃子笑", date(2026, 6, 1))       # 距 6/5 还有 4 天
        self.assertEqual(near["status"], "临近")
        self.assertEqual(near["days_to_start"], 4)

        far = maturity.window_for("妃子笑", date(2026, 5, 1))
        self.assertEqual(far["status"], "未到")

        best = maturity.window_for("妃子笑", date(2026, 6, 5))      # 窗口首日
        self.assertEqual(best["status"], "最佳")
        self.assertEqual(best["days_remaining"], 20)

        over = maturity.window_for("妃子笑", date(2026, 7, 1))      # 6/25 之后 6 天
        self.assertEqual(over["status"], "已过")
        self.assertEqual(over["days_overdue"], 6)

    def test_phenology_mapping(self):
        self.assertEqual(maturity.phenology("桂味", date(2026, 4, 1)), "花穗期")
        self.assertEqual(maturity.phenology("桂味", date(2026, 5, 10)), "幼果期")
        self.assertEqual(maturity.phenology("桂味", date(2026, 6, 10)), "果实膨大期")
        self.assertEqual(maturity.phenology("桂味", date(2026, 6, 25)), "转色成熟期")
        self.assertEqual(maturity.phenology("桂味", date(2026, 8, 1)), "采后")


class CrackRiskTest(unittest.TestCase):
    """久旱转雨 + 品种敏感度 + 物候期，任一不满足都不预警。"""

    TODAY = date(2026, 7, 5)

    @classmethod
    def _days(cls, past, future):
        days = [{
            "date": (cls.TODAY - timedelta(days=len(past) - i)).isoformat(),
            "precip_mm": mm,
        } for i, mm in enumerate(past)]
        days += [{
            "date": (cls.TODAY + timedelta(days=i)).isoformat(),
            "precip_mm": mm,
        } for i, mm in enumerate(future)]
        return days

    def test_high_sensitivity_hits(self):
        risk = crack.evaluate_crack_risk(
            self._days([0] * 7, [15, 0, 0]), "糯米糍", today=self.TODAY)
        self.assertIsNotNone(risk)
        self.assertEqual(risk["level"], "high")
        self.assertEqual(risk["phenology"], "转色成熟期")
        self.assertEqual(risk["rain_mm"], 15.0)

    def test_medium_sensitivity_needs_more_rain(self):
        days = self._days([0] * 7, [10, 0, 0])   # 10mm：糯米糍触发，桂味（12mm）不触发
        self.assertIsNotNone(crack.evaluate_crack_risk(days, "糯米糍", today=self.TODAY))
        self.assertIsNone(crack.evaluate_crack_risk(days, "桂味", today=self.TODAY))

    def test_non_sensitive_phenology_skipped(self):
        # 妃子笑 6/25 后已过窗口，物候期为采后
        self.assertIsNone(crack.evaluate_crack_risk(
            self._days([0] * 7, [30, 0, 0]), "妃子笑", today=self.TODAY))

    def test_wet_past_skipped(self):
        self.assertIsNone(crack.evaluate_crack_risk(
            self._days([30] + [0] * 6, [30, 0, 0]), "糯米糍", today=self.TODAY))

    def test_short_dry_streak_skipped(self):
        wet = [0, 2, 0, 2, 0, 2, 0]   # 累计 6mm 但最长连续无雨只有 1 天
        self.assertIsNone(crack.evaluate_crack_risk(
            self._days(wet, [30, 0, 0]), "糯米糍", today=self.TODAY))

    def test_missing_history_skipped(self):
        self.assertIsNone(crack.evaluate_crack_risk(
            self._days([0] * 3, [30, 0, 0]), "糯米糍", today=self.TODAY))
        self.assertIsNone(crack.evaluate_crack_risk([], "糯米糍", today=self.TODAY))


class ColdChainTest(unittest.TestCase):
    def setUp(self):
        from backend import main as backend_main

        self.main = backend_main
        self.now = datetime(2026, 7, 3, 12, 0, 0)

    def test_overdue_without_precool(self):
        chain = self.main._cold_chain_for(
            {"harvest_at": "2026-07-02 06:00:00"}, now=self.now)
        self.assertEqual(chain["status"], "overdue")
        self.assertEqual(chain["hours_since_harvest"], 30.0)

    def test_stage_progression(self):
        batch = {"harvest_at": "2026-07-02 06:00:00", "precooled_at": "2026-07-02 08:00:00"}
        self.assertEqual(self.main._cold_chain_for(batch, now=self.now)["status"], "cooling")
        batch["shipped_at"] = "2026-07-02 14:00:00"
        self.assertEqual(self.main._cold_chain_for(batch, now=self.now)["status"], "transit")
        batch["arrived_at"] = "2026-07-03 07:00:00"
        self.assertEqual(self.main._cold_chain_for(batch, now=self.now)["status"], "arrived")

    def test_missing_harvest_at_estimated(self):
        chain = self.main._cold_chain_for(
            {"harvest_date": "2026-07-02"}, now=self.now)
        self.assertTrue(chain["harvest_at_estimated"])
        self.assertEqual(chain["harvest_at"], "2026-07-02 06:00:00")

    def test_old_estimated_batch_is_legacy(self):
        chain = self.main._cold_chain_for(
            {"harvest_date": "2026-06-01"}, now=self.now)
        self.assertEqual(chain["status"], "legacy")


class _ApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from backend.main import app

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)


class ColdChainApiTest(_ApiBase):
    def _new_batch(self, seq):
        today = date.today().isoformat()
        res = self.client.post("/api/batches", json={
            "plot_id": 2, "harvest_date": today, "packaging_seq": seq,
            "harvest_at": f"{today} 06:00:00",
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "released")
        return res.json()["batch_no"]

    def test_events_in_order_and_trace(self):
        batch_no = self._new_batch(90)
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        out_of_order = self.client.post(
            f"/api/batches/{batch_no}/cold-chain", json={"event": "ship"})
        self.assertEqual(out_of_order.status_code, 400)

        first = self.client.post(f"/api/batches/{batch_no}/cold-chain",
                                 json={"event": "precool", "at": f"{today} 08:00:00"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["cold_chain"]["status"], "cooling")

        dup = self.client.post(f"/api/batches/{batch_no}/cold-chain",
                               json={"event": "precool", "at": f"{today} 09:00:00"})
        self.assertEqual(dup.status_code, 409)

        for event, at in (("ship", f"{today} 14:00:00"), ("arrive", f"{tomorrow} 06:00:00")):
            res = self.client.post(f"/api/batches/{batch_no}/cold-chain",
                                   json={"event": event, "at": at})
            self.assertEqual(res.status_code, 200, res.text)

        trace = self.client.get(f"/api/trace/{batch_no}").json()
        chain = trace["sales"]["cold_chain"]
        self.assertEqual(chain["status"], "arrived")
        self.assertFalse(chain["harvest_at_estimated"])
        self.assertTrue(trace["chain_verify"]["valid"])

    def test_blocked_batch_rejected(self):
        res = self.client.post("/api/batches/LZ-P01-20260708-0002/cold-chain",
                               json={"event": "precool"})
        self.assertEqual(res.status_code, 400)

    def test_todos_report_coldchain_and_residue(self):
        harvest_at = datetime.now() - timedelta(hours=30)
        res = self.client.post("/api/batches", json={
            "plot_id": 2, "harvest_date": date.today().isoformat(), "packaging_seq": 96,
            "harvest_at": harvest_at.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "released")
        batch_no = res.json()["batch_no"]

        items = self.client.get("/api/todos").json()
        cold = [i for i in items if i.get("type") == "coldchain" and i.get("batch_no") == batch_no]
        residue = [i for i in items if i.get("type") == "residue" and i.get("batch_no") == batch_no]
        self.assertTrue(cold, "30 小时未预冷应产生 coldchain 待办")
        self.assertEqual(cold[0]["level"], "critical")
        self.assertTrue(residue, "24 小时~7 天无检测应产生 residue 待办")


class TodoExtrasTest(_ApiBase):
    """裂果 / 采收窗口待办：用替身绕过真实日历与网络。"""

    def test_harvest_todo(self):
        from backend import main as backend_main

        fake = {
            "variety": "桂味", "status": "最佳",
            "window_start": "2026-11-01", "window_end": "2026-11-30",
            "days_to_start": 0, "days_remaining": 20, "days_overdue": 0,
            "suggested_date": "2026-11-09", "label": "桂味最佳采收期 11/1–11/30",
        }
        with mock.patch.object(backend_main.maturity, "window_for", return_value=fake):
            items = self.client.get("/api/todos").json()
        harvest = [i for i in items if i.get("type") == "harvest"]
        self.assertTrue(harvest)
        self.assertEqual(harvest[0]["level"], "warning")

    def test_crack_todo(self):
        from backend import main as backend_main

        fake = {
            "type": "crack", "level": "high", "variety": "糯米糍", "sensitivity": "high",
            "date": "2026-11-10", "rain_mm": 15.0, "dry_days": 5, "past_rain_mm": 0.0,
            "phenology": "转色成熟期", "detail": "久旱转雨，容易裂果",
            "location": None, "source": "Open-Meteo",
        }
        with mock.patch.object(backend_main.weather, "get_extended_days",
                               return_value=[{"date": "2026-11-08", "precip_mm": 0}]):
            with mock.patch.object(backend_main.crack, "evaluate_crack_risk",
                                   return_value=fake):
                items = self.client.get("/api/todos").json()
        crack_items = [i for i in items if i.get("type") == "crack"]
        self.assertTrue(crack_items)
        self.assertEqual(crack_items[0]["level"], "serious")
        self.assertLessEqual(len(crack_items), 2)   # 最多两条，避免刷屏


class ResidueApiTest(_ApiBase):
    def _new_batch(self, seq):
        res = self.client.post("/api/batches", json={
            "plot_id": 2, "harvest_date": date.today().isoformat(), "packaging_seq": seq,
        })
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["batch_no"]

    def test_new_batch_waits_for_detection(self):
        res = self.client.post("/api/batches", json={
            "plot_id": 2, "harvest_date": date.today().isoformat(), "packaging_seq": 95,
        })
        trace = self.client.get(f"/api/trace/{res.json()['batch_no']}").json()
        self.assertEqual(trace["sales"]["residue_conclusion"], "待检测")
        self.assertEqual(trace["sales"]["detection_report"], "待检测")

    def test_qualified_record(self):
        batch_no = self._new_batch(91)
        res = self.client.post(f"/api/batches/{batch_no}/residue-tests", json={
            "tested_at": date.today().isoformat(),
            "lab": "测试检测站",
            "conclusion": "合格",
            "items": [{"name": "毒死蜱", "value": "0.008", "unit": "mg/kg",
                       "limit": "0.01", "passed": True}],
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()["blocked"])
        self.assertIn("合格", res.json()["detection_report"])

        rows = self.client.get(f"/api/batches/{batch_no}/residue-tests").json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["items"][0]["name"], "毒死蜱")

    def test_unqualified_blocks_released_batch(self):
        batch_no = self._new_batch(92)
        res = self.client.post(f"/api/batches/{batch_no}/residue-tests", json={
            "conclusion": "不合格", "lab": "测试检测站",
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["blocked"])
        self.assertEqual(res.json()["status"], "blocked")

        trace = self.client.get(f"/api/trace/{batch_no}").json()
        self.assertEqual(trace["status"], "blocked")
        self.assertIn("农残", trace["block_reason"])

    def test_pending_retest_does_not_block(self):
        batch_no = self._new_batch(93)
        res = self.client.post(f"/api/batches/{batch_no}/residue-tests", json={
            "conclusion": "待复检",
        })
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["blocked"])
        self.assertEqual(res.json()["status"], "released")

    def test_invalid_conclusion(self):
        batch_no = self._new_batch(94)
        res = self.client.post(f"/api/batches/{batch_no}/residue-tests", json={
            "conclusion": "勉强合格",
        })
        self.assertEqual(res.status_code, 400)


class UploadApiTest(_ApiBase):
    def test_returns_static_url(self):
        from backend import main as backend_main

        with mock.patch.object(backend_main.ai_service, "save_image",
                               return_value=("/static/uploads/x.jpg", "/tmp/x.jpg")):
            res = self.client.post("/api/uploads", files={
                "file": ("report.jpg", b"fake-bytes", "image/jpeg")})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["url"], "/static/uploads/x.jpg")

    def test_rejects_bad_suffix(self):
        res = self.client.post("/api/uploads", files={
            "file": ("report.txt", b"text", "text/plain")})
        self.assertEqual(res.status_code, 400)

    def test_rejects_empty_file(self):
        res = self.client.post("/api/uploads", files={
            "file": ("photo.jpg", b"", "image/jpeg")})
        self.assertEqual(res.status_code, 400)


class MaturityApiTest(_ApiBase):
    def test_plots_include_maturity(self):
        plots = self.client.get("/api/plots").json()
        for plot in plots:
            self.assertIn("maturity", plot)
            self.assertIn(plot["maturity"]["status"], {"未到", "临近", "最佳", "已过"})
            self.assertIn("phenology", plot["maturity"])

    def test_maturity_check_written_to_operations(self):
        res = self.client.post("/api/plots/1/maturity-check", json={
            "ripeness": 86, "note": "果肩转红约七成"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["check"]["ripeness"], 86)

        plot = self.client.get("/api/plots/1").json()
        checks = [o for o in plot["operations"] if o["operation_type"] == "成熟度观察"]
        self.assertTrue(checks)
        self.assertIn("果肩转红", checks[0]["detail"])


class PatrolTest(_ApiBase):
    PID = "patrol-demo-01"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for pest, plot_id in (("荔枝蒂蛀虫", 2), ("荔枝蒂蛀虫", 2),
                              ("荔枝霜疫霉病", 3), ("健康叶片", 1)):
            cls.client.post("/api/recognitions/demo", json={
                "pest_class": pest, "plot_id": plot_id, "patrol_id": cls.PID})

    def test_report_aggregation(self):
        body = self.client.get(f"/api/patrols/{self.PID}").json()
        self.assertEqual(body["total"], 3)          # 健康叶片不计入
        self.assertEqual(body["by_class"][0]["class"], "荔枝蒂蛀虫")
        self.assertEqual(body["by_class"][0]["count"], 2)
        self.assertEqual(body["focus_plot"]["plot_id"], 2)
        self.assertEqual(body["focus_plot"]["count"], 2)
        self.assertIn("荔枝蒂蛀虫", body["summary"])
        self.assertTrue(body["advice"])

    def test_unknown_and_invalid_ids(self):
        self.assertEqual(self.client.get("/api/patrols/patrol-none-99").status_code, 404)
        self.assertEqual(self.client.get("/api/patrols/bad id!").status_code, 400)


class CorrectionApiTest(_ApiBase):
    """识别纠错回流：人工判定真实类别后，样本可导出用于评测/微调。"""

    def _recognize(self, pest="荔枝蒂蛀虫", plot_id=2):
        res = self.client.post("/api/recognitions/demo",
                               json={"pest_class": pest, "plot_id": plot_id})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["id"]

    def test_actual_class_saved_and_exported(self):
        rid = self._recognize()
        res = self.client.post(f"/api/recognitions/{rid}/handle",
                               json={"method": "false_positive", "actual_class": "荔枝蝽"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["actual_class"], "荔枝蝽")
        self.assertEqual(res.json()["detected_class"], "荔枝蒂蛀虫")

        row = next(r for r in self.client.get("/api/recognitions?limit=300").json()
                   if r["id"] == rid)
        self.assertEqual(row["actual_class"], "荔枝蝽")

        corrections = self.client.get("/api/recognitions/corrections?limit=2000").json()
        self.assertIn(rid, {r["id"] for r in corrections["rows"]})

        summary = self.client.get("/api/dashboard/summary").json()
        self.assertGreaterEqual(summary["recognition_corrected"], 1)
        self.assertIn("recognition_correction_rate", summary)

    def test_unknown_actual_class_rejected(self):
        rid = self._recognize()
        res = self.client.post(f"/api/recognitions/{rid}/handle",
                               json={"method": "false_positive", "actual_class": "隔壁老王"})
        self.assertEqual(res.status_code, 400)
        row = next(r for r in self.client.get("/api/recognitions?limit=300").json()
                   if r["id"] == rid)
        self.assertEqual(row["status"], "pending")

    def test_false_positive_without_actual_class(self):
        rid = self._recognize()
        res = self.client.post(f"/api/recognitions/{rid}/handle",
                               json={"method": "false_positive"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNone(res.json()["actual_class"])


class VoidRecordApiTest(_ApiBase):
    """台账留痕：记录只能作废、不能改删，作废后退出安全间隔期与合规统计。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        res = cls.client.post("/api/plots", json={
            "code": "T-VOID", "name": "留痕测试区", "variety": "桂味",
            "area_mu": 1.0, "tree_count": 10, "planting_year": 2018,
        })
        cls.plot_id = res.json()["id"]

    def test_pesticide_void_excluded_from_safety(self):
        today = date.today().isoformat()
        rec = self.client.post("/api/pesticide-records", json={
            "plot_id": self.plot_id, "pesticide_name": "高效氯氟氰菊酯",
            "apply_time": today, "operator": "测试",
        }).json()
        self.assertFalse(
            self.client.get(f"/api/plots/{self.plot_id}/safety-status").json()["safe"])

        res = self.client.post(f"/api/pesticide-records/{rec['id']}/void",
                               json={"reason": "录入错误", "operator": "测试"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["void_reason"], "录入错误")
        self.assertEqual(res.json()["voided_by"], "测试")

        # 作废后不再影响采收放行
        self.assertTrue(
            self.client.get(f"/api/plots/{self.plot_id}/safety-status").json()["safe"])
        # 重复作废被拒绝
        again = self.client.post(f"/api/pesticide-records/{rec['id']}/void", json={})
        self.assertEqual(again.status_code, 409)
        # 合规明细不再包含该记录
        rows = self.client.get("/api/dashboard/compliance?limit=500").json()["rows"]
        self.assertNotIn(rec["id"], {r["id"] for r in rows})
        # 但原记录仍可查，且带作废信息
        plot = self.client.get(f"/api/plots/{self.plot_id}").json()
        row = next(r for r in plot["pesticides"] if r["id"] == rec["id"])
        self.assertTrue(row["voided_at"])

        # 溯源同样排除作废记录
        batch = self.client.post("/api/batches", json={
            "plot_id": self.plot_id, "harvest_date": today, "packaging_seq": 1,
        }).json()
        self.assertEqual(batch["status"], "released")
        trace = self.client.get(f"/api/trace/{batch['trace_code']}").json()
        self.assertEqual(trace["care"]["pesticide_count"], 0)
        self.assertEqual(trace["care"]["pesticides"], [])

    def test_operation_void_keeps_history(self):
        op = self.client.post("/api/operations", json={
            "plot_id": self.plot_id, "operation_type": "施肥", "operator": "测试",
        }).json()
        res = self.client.post(f"/api/operations/{op['id']}/void", json={})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["void_reason"], "未填写原因")

        rows = self.client.get("/api/operations?limit=500").json()
        row = next(r for r in rows if r["id"] == op["id"])
        self.assertTrue(row["voided_at"])
        self.assertEqual(row["voided_by"], "果农")

        self.assertEqual(
            self.client.post("/api/operations/999999/void", json={}).status_code, 404)


class EvalToolTest(unittest.TestCase):
    """评测脚本的纯函数：标签归一化与统计口径不能悄悄错。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import eval_vision

        cls.ev = eval_vision

    @staticmethod
    def _item(label, pred, conf):
        correct = (pred == "无法判断") if label == "非目标" else (pred == label)
        return {
            "file": f"{label}-{pred}.jpg", "label": label, "pred": pred,
            "confidence": conf, "source": "test",
            "correct": correct, "abstained": pred == "无法判断",
            "low_confidence": conf < 0.65, "elapsed_s": 1.0, "error": "",
        }

    def test_canonical_label(self):
        self.assertEqual(self.ev._canonical_label("蒂蛀虫"), "荔枝蒂蛀虫")
        self.assertEqual(self.ev._canonical_label("非目标"), "非目标")
        self.assertIsNone(self.ev._canonical_label("随便写的"))

    def test_summary_counts(self):
        items = [
            self._item("荔枝蒂蛀虫", "荔枝蒂蛀虫", 0.9),
            self._item("荔枝蒂蛀虫", "荔枝霜疫霉病", 0.8),
            self._item("非目标", "无法判断", 0.2),
            self._item("非目标", "荔枝炭疽病", 0.9),
        ]
        summary = self.ev.summarize(items, 0.65)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["correct"], 2)
        self.assertEqual(summary["accuracy"], 0.5)
        self.assertEqual(summary["abstained"], 1)
        self.assertEqual(summary["non_target_false_alarms"], 1)

    def test_summary_counts_mock_fallbacks(self):
        items = [
            self._item("荔枝蒂蛀虫", "荔枝蒂蛀虫", 0.9),
            {**self._item("荔枝蒂蛀虫", "健康叶片", 0.95),
             "source": "mock_fallback(RuntimeError)"},
        ]
        summary = self.ev.summarize(items, 0.65)
        self.assertEqual(summary["mock_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
