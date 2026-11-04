"""病虫害识别服务。

识别链路（配置决定，业务后端无感知）：
1. 通义千问 Qwen-VL（阿里云百炼 OpenAI 兼容接口）—— 配置 DASHSCOPE_API_KEY 即启用；
2. 自定义视觉 API（VISION_API_URL + VISION_API_KEY）；
3. 本地模拟识别 —— 无网络 / 无 Key 时保证演示不中断。

设计原则：识别链路只回答「这是什么病虫害 + 置信度」，
防治用药建议一律交给 rules.build_suggestion() 规则库生成并做安全间隔期校验。
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import uuid
from pathlib import Path

from . import config
from .rules import MOCK_CLASS_POOL, PESTS, build_suggestion

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 可选类别：知识库中的病虫害 + 健康叶片 + 兜底
VLM_CLASSES = [k for k in PESTS.keys()]

SYSTEM_PROMPT = (
    "你是荔枝病虫害识别专家，只根据用户提供的图片判断，不要臆测。"
    "必须只输出一个 JSON 对象，不要输出 markdown、解释或多余文字。\n"
    f"可选类别：{'、'.join(VLM_CLASSES)}。\n"
    "字段：class（必须是上述类别之一）、confidence（0 到 1 的小数）、"
    "symptoms（对图中可见症状的一句话描述，20 字以内）。\n"
    "如果叶片/果实健康无明显病虫害，class 填「健康叶片」；"
    "如果图片与荔枝无关或无法判断，class 填「无法判断」。"
)


def is_real_api_enabled() -> bool:
    return bool(
        (config.VISION_PROVIDER in ("auto", "dashscope") and config.DASHSCOPE_API_KEY)
        or (config.VISION_PROVIDER in ("auto", "custom") and config.VISION_API_URL and config.VISION_API_KEY)
    )


def current_provider() -> str:
    if config.VISION_PROVIDER in ("auto", "dashscope") and config.DASHSCOPE_API_KEY:
        return "dashscope"
    if config.VISION_PROVIDER in ("auto", "custom") and config.VISION_API_URL and config.VISION_API_KEY:
        return "custom"
    return "mock"


def save_image(data: bytes, suffix: str = ".jpg") -> tuple[str, str]:
    """保存上传图片，返回 (相对URL, 绝对路径)。"""
    name = f"{uuid.uuid4().hex}{suffix}"
    path = UPLOAD_DIR / name
    path.write_bytes(data)
    return f"/static/uploads/{name}", str(path)


# ---------------------------------------------------------------------------
# 云识别：通义千问 Qwen-VL
# ---------------------------------------------------------------------------
def _dashscope_recognize(image_bytes: bytes) -> tuple[str, float]:
    import httpx

    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": config.VISION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "请识别这张荔枝病虫害照片。"},
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }
    resp = httpx.post(
        config.DASHSCOPE_BASE_URL,
        headers={
            "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=45,
    )
    resp.raise_for_status()
    body = resp.json()
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):  # 部分兼容实现返回分段内容
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return _parse_vlm_content(str(content))


def _parse_vlm_content(content: str) -> tuple[str, float]:
    """从模型输出中提取 JSON，容忍 markdown 代码块等包裹。"""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError(f"模型未返回 JSON：{content[:120]}")
    obj = json.loads(match.group(0))
    pest_class = _normalize_class(str(obj.get("class", "")))
    confidence = _normalize_confidence(obj.get("confidence"))
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
        config.VISION_API_URL,
        headers={"Authorization": f"Bearer {config.VISION_API_KEY}"},
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

    if provider == "dashscope":
        try:
            pest_class, confidence = _dashscope_recognize(image_bytes)
            source = f"dashscope:{config.VISION_MODEL}"
        except Exception as exc:  # 云端失败降级，演示不中断
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
