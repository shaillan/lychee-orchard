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

# 别名统一放在知识库里维护；这里展开成查表结构，长别名优先匹配
_KB_ALIASES: dict[str, str] = {
    alias.strip().lower(): name
    for name, info in PESTS.items()
    for alias in (info.get("aliases") or [])
    if alias.strip()
}
_KB_ALIASES_BY_LENGTH = sorted(_KB_ALIASES, key=len, reverse=True)

# 先要证据、再要结论：模型必须先描述看到的可疑部位，才允许给出病虫害类别。
# 这样即使小模型想「凑一个答案」，也会因为写不出病征而在后处理里被降级为无法判断。
SYSTEM_PROMPT = (
    "你是荔枝病虫害识别专家，只描述你在图片里真实看到的东西，不要臆测。"
    "必须只输出一个 JSON 对象，不要输出 markdown、解释或多余文字。\n"
    f"可选类别：{'、'.join(VLM_CLASSES)}。\n"
    "字段（按顺序逐项填写，不能跳过、不能合并）：\n"
    "1. shape：叶片/果实形态是否正常？卷曲、皱缩、畸形、隆起、穿孔，逐项写明有/无。\n"
    "2. color：颜色是否异常？斑点、褐变、黑变、黄化、褪绿、非新叶自然红的异常发红，逐项写明有/无。\n"
    "3. surface：表面有无霉层、白粉、霜状物、煤污、蜡粉、虫粪、附着物？逐项写明有/无。\n"
    "4. insects：画面任何位置（枝干、花穗、叶面、叶背）有无昆虫或其幼虫、卵、蛹？写明有/无与位置。\n"
    "以上 1-4 项写「有」时必须写出具体表现（例如「卷曲」「褐色斑点」「白色霉层」"
    "「叶背有黄色小虫」），只写一个「有」字不合格；每项不超过 12 字，不要复述题目。\n"
    "5. class：从可选类别中选一个。只要 1-4 里任何一项写了「有」，"
    "就不能填「健康叶片」或「健康果实」。\n"
    "6. confidence：0 到 1 的小数，必须与前四项的确凿程度一致。\n"
    "常见混淆先按要点排除（这是评测里错得最多的几组）：\n"
    "· 蓟马 vs 木虱：有白色蜡丝、蜜露、若虫群集才算木虱；只有银白锉伤条斑、果面锈斑时选蓟马。\n"
    "· 藻斑病 vs 煤烟病：病斑灰绿至红褐、绒状、带辐射状纹理选藻斑病；黑色煤粉能擦掉、叶肉不坏死选煤烟病。\n"
    "· 煤烟病 vs 炭疽病：只是表面附着物、无凹陷病斑选煤烟病；褐色凹陷病斑带晕圈、后期小黑点选炭疽病。\n"
    "· 叶瘿蚊 vs 瘿螨：水疱状虫瘿、叶面凸起选叶瘿蚊；叶背黄褐色毛毡状绒毛选瘿螨。\n"
    "· 酸腐病 vs 霜疫霉病：软化流汁、有酸臭味选酸腐病；水渍状病斑、白色霜状霉层、扩展快选霜疫霉病。\n"
    "特别注意：果面水珠、反光、果皮天然龟裂纹路、未转色的青黄斑块、叶片自然色差不是病斑。\n"
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


def _vision_chat(
    image_bytes: bytes,
    system_prompt: str,
    user_text: str,
    *,
    temperature: float = 0.1,
    models: list[str] | None = None,
    retry: bool = True,
    timeout: float | None = None,
) -> tuple[str, str]:
    """OpenAI 兼容的视觉调用，返回 (content, 实际命中的模型名)。"""
    import time

    import httpx

    payload = {
        "model": config.VISION_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_url(image_bytes)}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        "temperature": temperature,
        # 智谱多模态接口带 max_tokens 会报 1210，这里不能设；输出长度靠提示词约束。
    }

    delays = _RETRY_DELAYS if retry else ()
    last_error = ""
    for model in (models or _models_to_try()):
        payload["model"] = model
        resp = None
        for attempt in range(len(delays) + 1):
            try:
                resp = httpx.post(
                    config.VISION_BASE_URL,
                    headers={
                        "Authorization": f"Bearer {config.VISION_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout or config.VISION_TIMEOUT,
                )
            except Exception as exc:  # 超时/连接失败：换下一个模型，别直接放弃
                last_error = f"{model}: {type(exc).__name__}: {exc}"
                resp = None
                break
            if resp.status_code not in _RETRY_STATUS or attempt == len(delays):
                break
            time.sleep(delays[attempt])

        if resp is None:
            continue
        try:
            resp.raise_for_status()
        except Exception as exc:  # 记下响应体，方便定位 1210/1211 之类的参数或模型错误
            last_error = f"{model}: {exc} | {str(getattr(resp, 'text', ''))[:200]}"
            continue

        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
        except Exception as exc:  # 网关返回非 JSON 时也换模型，而不是整张图降级成 mock
            last_error = f"{model}: 响应解析失败: {exc} | {str(getattr(resp, 'text', ''))[:200]}"
            continue
        if isinstance(content, list):  # 部分兼容实现返回分段内容
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content), model

    raise RuntimeError(last_error or "所有视觉模型均调用失败")


def _remote_recognize(image_bytes: bytes) -> tuple[str, float, str, str]:
    """首轮识别，返回 (类别, 置信度, 实际命中的模型名, 首轮观察到的证据)。"""
    # 限流/截断时模型可能只回一个 class 就断了（实测出现过「class=荔枝龟背天牛、
    # confidence 缺失、1-4 项全无」，被下游误判成 0% 的无法判断）。逐项观察为空
    # 说明这一轮没说完，不是「图中无异常」，重问一次再下结论。
    for attempt in range(2):
        content, model = _vision_chat(
            image_bytes, SYSTEM_PROMPT, "请识别这张荔枝病虫害照片。", temperature=0.1
        )
        pest_class, confidence, evidence = _parse_vlm_content(content)
        if evidence:
            break
        logger.warning(
            "首轮输出不完整（class=%s, confidence=%s），第 %d 次重试",
            pest_class, confidence, attempt + 1,
        )
    pest_class, confidence = _apply_evidence_check(pest_class, confidence, evidence)
    return pest_class, confidence, model, evidence


def _load_json_object(content: str) -> dict:
    """取模型输出里的第一个完整 JSON 对象，容忍代码块包裹和尾部多余内容。

    模型偶尔会输出两个对象（或在 JSON 后面再跟一段解释）。用贪婪正则
    `\\{.*\\}` 会把它们拼在一起，json.loads 报 "Extra data: line 6 column 1"，
    整张图被迫降级成 mock。这里改用 raw_decode，只解析第一个对象。
    """
    text = (content or "").strip()
    if not text:
        raise ValueError("模型返回空内容")
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for candidate in (text, _repair_broken_fields(text)):
        for match in re.finditer(r"\{", candidate):
            try:
                obj, _ = decoder.raw_decode(candidate, match.start())
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj:
                return obj
    raise ValueError(f"模型未返回 JSON：{text[:120]}")


# 模型偶尔把手填的字段写成 `"1": "shape": "有 卷曲"`（序号和字段名都当键），
# 这不是合法 JSON，但语义是清楚的，值得救回来而不是整张图判失败。
_BROKEN_FIELD = re.compile(
    r'"\d+"\s*:\s*"(shape|color|surface|insects|class|confidence|evidence|symptoms)"'
    r'\s*:\s*"([^"]*)"'
)


def _repair_broken_fields(text: str) -> str:
    """把 `"1": "shape": "有 卷曲"` 还原成 `"shape": "有 卷曲"`。"""
    return _BROKEN_FIELD.sub(lambda m: f'"{m.group(1)}": "{m.group(2)}"', text)


# 提示词让模型逐项填 shape/color/surface/insects，比让它自由写一句 evidence 更能
# 逼它真的去看：实测同一张卷叶图，自由描述会写「未见异常」，逐项填就会写出卷曲。
# 提示词给了字段名，但模型经常改用 "1"~"6" 当键，两种都要认。
_CHECK_FIELD_LABELS = (
    (("shape", "1"), "形态"), (("color", "2"), "颜色"),
    (("surface", "3"), "表面"), (("insects", "4"), "虫体"),
)
_CLASS_KEYS = ("class", "5")
_CONFIDENCE_KEYS = ("confidence", "6")
_NEGATIVE_VALUE_PREFIXES = ("无", "没有", "未见", "未发现", "否", "正常")


def _first_value(obj: dict, keys) -> str:
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _evidence_from_checks(obj: dict) -> str:
    """把逐项检查结果拼成证据文本；四项全为「无」时补上「未见异常」。"""
    parts: list[str] = []
    all_clear = True
    for keys, label in _CHECK_FIELD_LABELS:
        value = _first_value(obj, keys)
        if not value:
            continue
        if not value.startswith(_NEGATIVE_VALUE_PREFIXES):
            all_clear = False
        parts.append(f"{label}{value}")
    if all_clear and parts:
        parts.append("未见异常")
    return "；".join(parts)


def _parse_vlm_content(content: str) -> tuple[str, float, str]:
    """从模型输出中提取 JSON，容忍 markdown 代码块等包裹，返回 (类别, 置信度, 证据)。"""
    obj = _load_json_object(content)
    pest_class = _normalize_class(_first_value(obj, _CLASS_KEYS))
    confidence = _normalize_confidence(_first_value(obj, _CONFIDENCE_KEYS) or None)
    evidence = str(obj.get("evidence") or obj.get("symptoms") or "").strip()
    if not evidence:
        evidence = _evidence_from_checks(obj)
    return pest_class, confidence, evidence


# 正向证据：病害看病征，虫害看虫体或为害状。用错一套关键词会把正确结论误杀：
# 「甲虫，无病斑」是虫害照片的常见描述，不能因为「无病斑」就否定虫害。
_DISEASE_KEYWORDS = (
    "病斑", "斑点", "斑块", "褐", "黑", "灰", "霉", "霜状", "白粉", "粉层",
    "煤污", "腐", "水渍", "凹陷", "开裂", "流胶", "绒毛", "锈",
    "褪绿", "黄化", "枯", "萎", "畸形", "卷曲", "斑",
)
_INSECT_KEYWORDS = (
    "虫", "幼虫", "成虫", "若虫", "蛹", "卵", "虫粪", "蛀孔", "蛀",
    "啃食", "缺刻", "孔洞", "虫体", "介壳", "蚧", "蜡粉", "蜜露", "虫瘿",
    # 瘿螨、蓟马、蚜虫这类微小害虫通常只拍得到为害状，拍不到虫体；
    # 只认「虫」字会把它们正确的识别全部误杀。
    "畸形", "卷曲", "皱缩", "毛毡", "锈色", "银白", "褪绿", "聚集",
)


# 健康结论的「正向证据」反过来：必须明确写出没有异常，
# 否则模型很容易把介壳虫、煤烟层当成叶面纹理，直接回一句「健康叶片」。
_HEALTHY_ABSENT = (
    "无病斑", "未见病斑", "无异常", "未见异常", "没有异常", "无虫", "未见虫",
    "没有虫", "无蛀孔", "未见蛀孔", "无霉", "未见霉", "无腐烂", "未见腐烂",
    "无缺刻", "未见缺刻", "无虫孔", "健康", "正常", "完整",
    "无明显", "未见明显",
)


_NEGATIVE_MARKERS = ("无", "未", "没有", "没", "未见", "未发现", "排除")


def _mentions(text: str, keywords) -> bool:
    """关键词是否被以肯定语气提到，排除「无病斑」「未见明显虫体」这类否定表达。

    按分句判断否定作用域：「无明显病斑、霉层」里的「霉层」同样是否定，
    而「叶片有甲虫，无病斑」前半句的「甲虫」仍然算肯定证据。
    """
    for clause in re.split(r"[，。；,;！!？?\n但]", text):
        stripped = clause.strip()
        # 逐项检查的写法是「标签+结论」（如「虫体无」「卷曲:有」），
        # 否定词在关键词后面，不能只看前缀。
        suffix_negative = stripped.endswith(tuple(_NEGATIVE_MARKERS))
        neg_positions = [clause.find(m) for m in _NEGATIVE_MARKERS if m in clause]
        neg_idx = min(neg_positions) if neg_positions else -1
        for kw in keywords:
            idx = clause.find(kw)
            if idx == -1:
                continue
            if suffix_negative:
                continue
            if neg_idx == -1 or idx < neg_idx:
                return True
    return False


def _negative_clause_count(text: str) -> int:
    """统计「明确写了没有异常」的短句数（如「形态无卷曲」「无皱缩」「虫体无」）。

    逐项检查的写法是四段阴性描述（「形态无卷曲…；颜色无斑点…；表面无…；虫体无」），
    里面没有「无病斑/未见异常」这类现成短语，只靠 `_HEALTHY_ABSENT` 会被误杀。
    """
    count = 0
    for clause in re.split(r"[，。；,;\n]", text or ""):
        clause = clause.strip()
        if not clause:
            continue
        if any(m in clause for m in _NEGATIVE_MARKERS) and not _mentions(
            clause, _DISEASE_KEYWORDS + _INSECT_KEYWORDS
        ):
            count += 1
    return count


def _apply_evidence_check(pest_class: str, confidence: float, evidence: str) -> tuple[str, float]:
    """结论必须有可见证据支撑，否则降级为「无法判断」。

    这是防误报的硬闸门：模型被逼着在闭集里选一个类别时，
    常把水珠、果皮纹理当成病斑并给出很高的置信度。
    判定用「正向证据」而不是长度，且按类别分开：
    - 病害：evidence 必须写出病征（病斑/霉层/腐烂…）；
    - 虫害：evidence 必须写出虫体或为害状（幼虫/蛀孔/虫粪/缺刻…）；
    - 健康：evidence 必须写出「无病斑/未见虫/无异常」之类的阴性证据，
      且不能同时肯定地描述出病征或虫体（否则说明画面里其实有东西）。
    """
    kind = PESTS.get(pest_class, {}).get("kind")
    if kind not in ("虫害", "病害", "无异常"):
        return pest_class, confidence
    text = (evidence or "").strip()
    if kind == "无异常":
        disease_reported = _mentions(text, _DISEASE_KEYWORDS)
        insect_reported = _mentions(text, _INSECT_KEYWORDS)
        says_absent = any(m in text for m in _HEALTHY_ABSENT)
        # 「形态无卷曲…；颜色无斑点…；表面无…；虫体无」这类逐项阴性描述同样算
        # 明确写了没有异常；只有一两句或含糊时才要求出现现成的阴性短语。
        if not says_absent and _negative_clause_count(text) >= 2:
            says_absent = True
        if disease_reported or insect_reported or not says_absent:
            logger.warning(
                "模型给出 %s（健康），但 evidence 不支持（%r），已降级为无法判断",
                pest_class, text[:60],
            )
            return "无法判断", min(confidence, 0.3)
        return pest_class, confidence
    keywords = _INSECT_KEYWORDS if kind == "虫害" else _DISEASE_KEYWORDS
    # 只看「肯定语气」提到的证据：evidence 里写「无病斑」不算病征，
    # 但「有虫体，无病斑」这种混写不能因为后半句就把虫害结论否掉。
    has_evidence = _mentions(text, keywords)
    if not has_evidence:
        logger.warning(
            "模型给出 %s（%s），但 evidence 不足（%r），已降级为无法判断",
            pest_class, kind, text[:60],
        )
        return "无法判断", min(confidence, 0.3)
    return pest_class, confidence


# ---------------------------------------------------------------------------
# 二次确认：病虫害结论必须经得起「换个问法再问一次」。
# 注意：复核不是「教科书的每一条症状都要对上」。实测同一张炭疽病叶片，按「褐色凹陷病斑、
# 边缘晕圈、中央小黑点」逐项严卡时，4 次里会拒 1~2 次，导致正确结果被降级成无法判断；
# 改成「看到任意一项典型症状，且没有更合理的非病害解释」后，同一张图 3/3 通过，
# 而健康叶片 / 健康果实仍然 2/2 拒绝。病程早期本来就不会把全部症状长齐。
CONFIRM_SYSTEM_PROMPT = (
    "你是荔枝病虫害复核员。只根据图片核实第一轮记录的异常是否真实存在，不要臆测，"
    "也不要因为类别名称就脑补出画面里没有的东西。"
    "不要要求所有典型症状同时出现：症状随病程阶段不同只表现一部分是正常的。"
    "必须只输出一个 JSON 对象，不要 markdown、解释或多余文字。\n"
    "字段：\n"
    "1. observed：逐项核实结果，写明每一项看到的实际情况，30-60 字。\n"
    "2. present：true 或 false。\n"
    "3. reason：一句话说明依据，必须引用看到或未看到的关键特征。\n"
    "看不清、图片与荔枝无关、或逐项核实后确实没有任何异常时，present 填 false。"
)


def _confirm_user_text(pest_class: str, info: dict, evidence: str = "") -> str:
    diff = info.get("differential") or {}
    kind = info.get("kind", "")
    lines = [
        f"第一轮识别为「{pest_class}」（{kind}）。",
        f"第一轮记录到的异常：{evidence.strip() or '未记录'}",
        f"该类别典型症状：{info.get('symptoms', '')}",
        f"主要为害部位：{'、'.join(info.get('host_parts') or []) or '未注明'}",
        f"易混淆类别：{'、'.join(diff.get('confusable') or []) or '无'}",
        f"区分要点：{'；'.join(diff.get('distinguishing') or []) or '无'}",
        "请按下面四项逐项核实，并写明看到的实际情况：",
        "1) 叶片/果实形态是否卷曲、皱缩、畸形、隆起或穿孔？",
        "2) 颜色是否有斑点、褐变、黑变、黄化、褪绿或异常发红？",
        "3) 表面有无霉层、白粉、霜状物、煤污、蜡粉或虫粪？",
        "4) 画面任何位置（枝干、花穗、叶面、叶背）有无昆虫或其幼虫、卵、蛹？",
    ]
    # 不再要求「全部典型症状」：叶片/果实的病程阶段不同，只会表现其中一部分。
    # 只要有一项能对上、且不能被水珠/反光/天然纹理等解释，就应当保留首轮结论。
    lines.append(
        "判定规则：只要看到上述典型症状中的任意一项（不必全部出现），且这些异常不能被水珠、"
        "反光、果皮天然纹理、机械伤、自然老化等非病害原因解释，present 填 true。"
        "症状随病程阶段不同只表现一部分是正常的，不要因为缺少某一项典型症状就填 false。"
        "只有画面确实没有异常、或异常明显更符合另一个类别时，才填 false。"
    )
    if kind == "虫害":
        # 虫害照片经常只拍虫体不拍为害状，只按「症状」卡会把正确的虫体识别误杀。
        lines.append(
            "虫害补充：第 4 项确实看到该害虫的虫体时直接填 true，即使没有明显为害状。"
        )
    lines.append('严格输出 JSON：{"observed":"...","present":true,"reason":"..."}')
    return "\n".join(lines)


def _parse_confirm_content(content: str) -> tuple[bool | None, str]:
    """解析复核结果；present 缺失或不是布尔语义时返回 None（fail-open）。"""
    obj = _load_json_object(content)
    present = obj.get("present")
    if isinstance(present, str):
        lowered = present.strip().lower()
        if lowered in ("true", "yes", "1", "是", "有", "存在"):
            present = True
        elif lowered in ("false", "no", "0", "否", "无", "不存在"):
            present = False
        else:
            present = None
    elif not isinstance(present, bool):
        present = None
    reason = str(obj.get("reason") or obj.get("observed") or "").strip()[:200]
    return present, reason


def _confirm_presence(
    image_bytes: bytes, pest_class: str, model_used: str, evidence: str = ""
) -> tuple[bool | None, str]:
    """单模型、不重试、短超时；返回 (present, reason)，None 表示复核不可用。"""
    info = PESTS.get(pest_class) or {}
    try:
        content, _ = _vision_chat(
            image_bytes,
            CONFIRM_SYSTEM_PROMPT,
            _confirm_user_text(pest_class, info, evidence),
            temperature=0.0,
            models=[model_used],
            retry=False,
            timeout=config.VISION_CONFIRM_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("二次确认调用失败（%s），保留首轮结果：%s", pest_class, exc)
        return None, f"error:{type(exc).__name__}"
    try:
        return _parse_confirm_content(content)
    except Exception as exc:
        logger.warning("二次确认输出无法解析（%s）：%s", pest_class, exc)
        return None, "malformed"


def _verify_prediction(
    image_bytes: bytes, pest_class: str, confidence: float,
    model_used: str, enabled: bool, evidence: str = "",
) -> tuple[str, float, dict]:
    """对首轮病虫害结论做二次复核，返回 (类别, 置信度, 复核信息)。"""
    info = PESTS.get(pest_class) or {}
    if info.get("kind") not in ("虫害", "病害"):
        return pest_class, confidence, {"status": "skipped", "reason": "not_pest", "model": None}
    if not enabled:
        return pest_class, confidence, {"status": "skipped", "reason": "disabled", "model": None}

    present, reason = _confirm_presence(image_bytes, pest_class, model_used, evidence)
    if present is False:
        logger.warning("二次确认未通过（%s）：%s，降级为无法判断", pest_class, reason[:80])
        return "无法判断", min(confidence, 0.3), {
            "status": "rejected", "reason": reason, "model": model_used,
        }
    if present is None:
        return pest_class, confidence, {
            "status": "unavailable", "reason": reason, "model": model_used,
        }
    return pest_class, confidence, {
        "status": "confirmed", "reason": reason, "model": model_used,
    }


def _normalize_class(raw: str) -> str:
    raw = raw.strip()
    if raw in PESTS:
        return raw
    for name in PESTS:
        if name in raw or raw in name:
            return name

    lowered = raw.lower()
    if lowered in _KB_ALIASES:  # 精确命中优先，避免 healthy fruit 落到 healthy
        return _KB_ALIASES[lowered]
    for alias in _KB_ALIASES_BY_LENGTH:  # 长别名优先，再做子串
        if alias in lowered:
            return _KB_ALIASES[alias]
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
            pest_class, confidence, model_used, evidence = _remote_recognize(image_bytes)
            pest_class, confidence, verification = _verify_prediction(
                image_bytes, pest_class, confidence, model_used, config.VISION_CONFIRM,
                evidence,
            )
            source = f"{_provider_label()}:{model_used}"
            if verification["status"] == "rejected":
                source += "#confirm_false"
            elif verification["status"] == "unavailable":
                source += "#confirm_error"
        except Exception as exc:  # 云端不可用时要老实说不知道，不能随机猜一个病虫害
            logger.warning("云端识别失败（%s），返回无法判断：%s", ", ".join(_models_to_try()), exc)
            pest_class, confidence = "无法判断", 0.0
            source = f"cloud_failed({type(exc).__name__})"
            verification = {"status": "skipped", "reason": "cloud_failed", "model": None}
    elif provider == "custom":
        try:
            pest_class, confidence, bbox = _custom_api_recognize(image_bytes, plot_id)
            source = "custom_api"
            verification = {"status": "skipped", "reason": "custom_provider", "model": None}
        except Exception as exc:
            pest_class, confidence = _mock_class(seed), _mock_confidence(seed)
            source = f"mock_fallback({type(exc).__name__})"
            verification = {"status": "skipped", "reason": "custom_failed", "model": None}
    else:
        pest_class, confidence = _mock_class(seed), _mock_confidence(seed)
        source = "mock"
        verification = {"status": "skipped", "reason": "mock", "model": None}

    # 「无法判断」不是结论，不能带着 90%、100% 的置信度出门：
    # 报告里会自相矛盾，下游也可能把它当成可自动处置的结果。
    if pest_class == "无法判断":
        confidence = min(confidence, 0.3)

    suggestion = build_suggestion(pest_class, confidence, days_to_harvest)
    if verification["status"] == "rejected":
        suggestion["warnings"].append(
            "二次确认未通过：图中未见知识库描述的典型症状，结果已降级为无法判断，请人工复核。"
        )
    if source.startswith("cloud_failed"):
        suggestion["warnings"].append(
            "云端识别服务暂时不可用，本次没有给出结论，请检查网络后重新拍照识别。"
        )
    elif pest_class == "无法判断" and confidence == 0.0:
        # 两轮都只拿到半截输出（限流时常见），别把「模型没说完」说成「图里没病」。
        suggestion["warnings"].append(
            "本次云端返回不完整，可能是调用被限流，请稍后重新识别。"
        )
    suggestion["verification"] = verification
    return {
        "pest_class": pest_class,
        "confidence": confidence,
        "bbox": bbox or _mock_bbox(seed),
        "source": source,
        "is_mock": source.startswith("mock"),
        "verification": verification,
        "suggestion": suggestion,
    }


def recognize_known(pest_class: str, confidence: float = 0.92,
                    days_to_harvest: int | None = None) -> dict:
    """演示用：直接指定类别（不依赖图片内容）。"""
    if pest_class not in PESTS:
        pest_class = MOCK_CLASS_POOL[0]
    suggestion = build_suggestion(pest_class, confidence, days_to_harvest)
    verification = {"status": "skipped", "reason": "demo", "model": None}
    suggestion["verification"] = verification
    return {
        "pest_class": pest_class,
        "confidence": confidence,
        "bbox": [120, 150, 220, 220],
        "source": "demo",
        "is_mock": True,
        "verification": verification,
        "suggestion": suggestion,
    }
