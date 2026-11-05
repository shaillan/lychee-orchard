"""病虫害识别服务。

识别链路（配置决定，业务后端无感知）：
1. OpenAI 兼容的云端视觉 API —— 智谱 GLM-4V、通义千问 Qwen-VL、豆包、硅基流动等，
   配好 VISION_API_KEY / VISION_BASE_URL / VISION_MODEL 即启用；
2. 自定义视觉 API（VISION_CUSTOM_URL + VISION_CUSTOM_KEY）；
3. 本地模拟识别 —— 无网络 / 无 Key 时保证演示不中断。

设计原则：识别链路只回答「这是什么病虫害 + 置信度」，
防治用药建议一律交给 rules.build_suggestion() 规则库生成并做安全间隔期校验。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import re
import uuid
from pathlib import Path

from . import config
from .rules import MOCK_CLASS_POOL, PESTS, build_suggestion

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# 可选类别：知识库中的病虫害 + 健康叶片/果实 + 兜底
VLM_CLASSES = [k for k in PESTS.keys()]

# 先要证据、再要结论：模型必须先描述看到的可疑部位，才允许给出病虫害类别。
# 这样即使小模型想「凑一个答案」，也会因为写不出病征而在后处理里被降级为无法判断。
SYSTEM_PROMPT = (
    "你是荔枝病虫害识别专家，只描述你在图片里真实看到的东西，不要臆测。"
    "必须只输出一个 JSON 对象，不要输出 markdown、解释或多余文字。\n"
    f"可选类别：{'、'.join(VLM_CLASSES)}。\n"
    "字段（按此顺序输出）：\n"
    "1. evidence：先客观描述图中可疑部位的形态、颜色、位置，20-40 字；"
    "没有可疑部位时写「未见异常」。\n"
    "2. class：必须是上述类别之一。只有 evidence 里确实写出了病斑、蛀孔、霉层、"
    "虫体等可辨识特征，才允许填对应的病虫害；否则填「健康叶片」或「健康果实」。\n"
    "3. confidence：0 到 1 的小数，必须与 evidence 的确凿程度一致。\n"
    "特别注意：果面水珠、反光、果皮天然龟裂纹路、未转色的青黄斑块、叶片自然色差"
    "都不是病斑，不能作为病虫害依据。\n"
    "如果图片与荔枝无关或看不清，class 填「无法判断」。"
)


# 云端 OpenAI 兼容接口的渠道别名（dashscope 为历史写法，保留兼容）
_REMOTE_PROVIDERS = ("auto", "api", "dashscope")


def _provider_label() -> str:
    """从端点推断渠道名，用于前端展示「云端 AI · zhipu:glm-4.6v-flash」。"""
    url = config.VISION_BASE_URL.lower()
    for key, label in (
        ("bigmodel", "zhipu"),
        ("dashscope", "dashscope"),
        ("volces", "doubao"),
        ("siliconflow", "siliconflow"),
        ("moonshot", "kimi"),
        ("localhost", "local"),
        ("127.0.0.1", "local"),
    ):
        if key in url:
            return label
    return "vision_api"


def is_real_api_enabled() -> bool:
    return bool(
        (config.VISION_PROVIDER in _REMOTE_PROVIDERS and config.VISION_API_KEY)
        or (config.VISION_PROVIDER in ("auto", "custom")
            and config.VISION_CUSTOM_URL and config.VISION_CUSTOM_KEY)
    )


def current_provider() -> str:
    if config.VISION_PROVIDER in _REMOTE_PROVIDERS and config.VISION_API_KEY:
        return "api"
    if config.VISION_PROVIDER in ("auto", "custom") and config.VISION_CUSTOM_URL and config.VISION_CUSTOM_KEY:
        return "custom"
    return "mock"


def save_image(data: bytes, suffix: str = ".jpg") -> tuple[str, str]:
    """保存上传图片，返回 (相对URL, 绝对路径)。"""
    name = f"{uuid.uuid4().hex}{suffix}"
    path = UPLOAD_DIR / name
    path.write_bytes(data)
    return f"/static/uploads/{name}", str(path)


# ---------------------------------------------------------------------------
# 云识别：OpenAI 兼容的视觉接口（智谱 GLM / 通义千问 / 豆包 / 硅基流动 / 本地 Ollama）
# ---------------------------------------------------------------------------
def _image_url(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    if config.VISION_IMAGE_FORMAT == "raw":
        return b64
    return f"data:image/jpeg;base64,{b64}"


# 免费档模型限流频繁（智谱 1305 / 429），退避重试能扛过大部分间歇性拥堵
_RETRY_STATUS = (429, 503)
_RETRY_DELAYS = (1.5, 3.0)


def _models_to_try() -> list[str]:
    """主模型 + 可选备选模型，去重。"""
    models = [config.VISION_MODEL]
    fallback = config.VISION_FALLBACK_MODEL
    if fallback and fallback not in models:
        models.append(fallback)
    return models


def _remote_recognize(image_bytes: bytes) -> tuple[str, float, str]:
    """返回 (类别, 置信度, 实际命中的模型名)。"""
    import time

    import httpx

    payload = {
        "model": config.VISION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_url(image_bytes)}},
                    {"type": "text", "text": "请识别这张荔枝病虫害照片。"},
                ],
            },
        ],
        "temperature": 0.1,
    }

    last_error = ""
    for model in _models_to_try():
        payload["model"] = model
        resp = None
        for attempt in range(len(_RETRY_DELAYS) + 1):
            resp = httpx.post(
                config.VISION_BASE_URL,
                headers={
                    "Authorization": f"Bearer {config.VISION_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.VISION_TIMEOUT,
            )
            if resp.status_code not in _RETRY_STATUS or attempt == len(_RETRY_DELAYS):
                break
            time.sleep(_RETRY_DELAYS[attempt])

        try:
            resp.raise_for_status()
        except Exception as exc:  # 记下响应体，方便定位 1210/1211 之类的参数或模型错误
            last_error = f"{model}: {exc} | {str(getattr(resp, 'text', ''))[:200]}"
            continue

        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):  # 部分兼容实现返回分段内容
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        pest_class, confidence, evidence = _parse_vlm_content(str(content))
        pest_class, confidence = _apply_evidence_check(pest_class, confidence, evidence)
        return pest_class, confidence, model

    raise RuntimeError(last_error or "所有视觉模型均调用失败")


def _parse_vlm_content(content: str) -> tuple[str, float, str]:
    """从模型输出中提取 JSON，容忍 markdown 代码块等包裹，返回 (类别, 置信度, 证据)。"""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError(f"模型未返回 JSON：{content[:120]}")
    obj = json.loads(match.group(0))
    pest_class = _normalize_class(str(obj.get("class", "")))
    confidence = _normalize_confidence(obj.get("confidence"))
    evidence = str(obj.get("evidence") or obj.get("symptoms") or "").strip()
    return pest_class, confidence, evidence


# 这些词说明模型自己也没看到病征
_NO_LESION_MARKERS = (
    "未见异常", "无异常", "没有异常", "未见明显", "无明显", "未见病斑",
    "无病斑", "未见虫孔", "无虫孔", "未见虫体", "未发现", "健康", "正常",
)

# 病征关键词：evidence 里至少得出现一个，病虫害结论才成立
_LESION_KEYWORDS = (
    "病斑", "褐", "黑点", "霉", "蛀", "孔", "虫", "卷曲", "畸形", "斑",
    "腐烂", "绒毛", "缺刻", "虫粪", "萎", "水渍",
)


def _apply_evidence_check(pest_class: str, confidence: float, evidence: str) -> tuple[str, float]:
    """病虫害结论必须有可见证据支撑，否则降级为「无法判断」。

    这是防误报的硬闸门：模型被逼着在闭集里选一个类别时，
    常把水珠、果皮纹理当成病斑并给出很高的置信度。
    判定用「正向证据」而不是长度：evidence 必须写出至少一个病征关键词。
    """
    if PESTS.get(pest_class, {}).get("kind") not in ("虫害", "病害"):
        return pest_class, confidence
    text = (evidence or "").strip()
    has_lesion = any(k in text for k in _LESION_KEYWORDS)
    says_healthy = any(m in text for m in _NO_LESION_MARKERS)
    if not has_lesion or says_healthy:
        logger.warning(
            "模型给出 %s，但 evidence 不足（%r），已降级为无法判断", pest_class, text[:60]
        )
        return "无法判断", min(confidence, 0.3)
    return pest_class, confidence


def _normalize_class(raw: str) -> str:
    raw = raw.strip()
    if raw in PESTS:
        return raw
    for name in PESTS:
        if name in raw or raw in name:
            return name
    # 常见英文/别名兜底
    aliases = {
        "蒂蛀虫": "荔枝蒂蛀虫", "蝽": "荔枝蝽", "霜疫霉": "荔枝霜疫霉病",
        "炭疽": "荔枝炭疽病", "瘿螨": "荔枝瘿螨", "尺蠖": "荔枝尺蠖",
        "healthy fruit": "健康果实", "healthy leaf": "健康叶片",
        "healthy": "健康叶片", "unknown": "无法判断",
    }
    lowered = raw.lower()
    for key, value in aliases.items():
        if key.lower() in lowered:
            return value
    return "无法判断"


def _normalize_confidence(value) -> float:
    try:
        if isinstance(value, str):
            value = value.strip()
            if value.endswith("%"):
                return max(0.0, min(1.0, float(value[:-1]) / 100))
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    if conf > 1.0:
        conf = conf / 100.0
    return max(0.0, min(1.0, round(conf, 4)))


# ---------------------------------------------------------------------------
# 云识别：自定义 API（保留通用接入点）
# ---------------------------------------------------------------------------
def _custom_api_recognize(image_bytes: bytes, plot_id: int | None) -> tuple[str, float, list | None]:
    import httpx

    resp = httpx.post(
        config.VISION_CUSTOM_URL,
        headers={"Authorization": f"Bearer {config.VISION_CUSTOM_KEY}"},
        json={"image_base64": base64.b64encode(image_bytes).decode(), "plot_id": plot_id},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    return (
        _normalize_class(str(body.get("class", ""))),
        _normalize_confidence(body.get("confidence", 0.0)),
        body.get("bbox"),
    )


# ---------------------------------------------------------------------------
# 本地模拟
# ---------------------------------------------------------------------------
def _mock_class(seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(MOCK_CLASS_POOL)
    return MOCK_CLASS_POOL[idx]


def _mock_confidence(seed: str) -> float:
    rng = random.Random(seed)
    return round(rng.uniform(0.78, 0.97), 4)


def _mock_bbox(seed: str) -> list[int]:
    rng = random.Random("bbox-" + seed)
    x = rng.randint(40, 360)
    y = rng.randint(40, 360)
    w = rng.randint(120, 260)
    h = rng.randint(120, 260)
    return [x, y, w, h]


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def recognize(image_bytes: bytes, plot_id: int | None = None,
              days_to_harvest: int | None = None) -> dict:
    """识别入口：真实 API 优先，失败或无配置时降级本地模拟。"""
    seed = hashlib.md5(image_bytes).hexdigest() if image_bytes else uuid.uuid4().hex
    provider = current_provider()
    bbox: list | None = None

    if provider == "api":
        try:
            pest_class, confidence, model_used = _remote_recognize(image_bytes)
            source = f"{_provider_label()}:{model_used}"
        except Exception as exc:  # 云端失败降级，演示不中断
            logger.warning("云端识别失败（%s），已降级本地模拟：%s", ", ".join(_models_to_try()), exc)
            pest_class, confidence = _mock_class(seed), _mock_confidence(seed)
            source = f"mock_fallback({type(exc).__name__})"
    elif provider == "custom":
        try:
            pest_class, confidence, bbox = _custom_api_recognize(image_bytes, plot_id)
            source = "custom_api"
        except Exception as exc:
            pest_class, confidence = _mock_class(seed), _mock_confidence(seed)
            source = f"mock_fallback({type(exc).__name__})"
    else:
        pest_class, confidence = _mock_class(seed), _mock_confidence(seed)
        source = "mock"

    suggestion = build_suggestion(pest_class, confidence, days_to_harvest)
    return {
        "pest_class": pest_class,
        "confidence": confidence,
        "bbox": bbox or _mock_bbox(seed),
        "source": source,
        "is_mock": source.startswith("mock"),
        "suggestion": suggestion,
    }


def recognize_known(pest_class: str, confidence: float = 0.92,
                    days_to_harvest: int | None = None) -> dict:
    """演示用：直接指定类别（不依赖图片内容）。"""
    if pest_class not in PESTS:
        pest_class = MOCK_CLASS_POOL[0]
    suggestion = build_suggestion(pest_class, confidence, days_to_harvest)
    return {
        "pest_class": pest_class,
        "confidence": confidence,
        "bbox": [120, 150, 220, 220],
        "source": "demo",
        "is_mock": True,
        "suggestion": suggestion,
    }
