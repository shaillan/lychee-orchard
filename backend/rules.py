"""静态规则库：荔枝常用农药、主要病虫害与防治建议生成。

数据来源：整理自公开农药登记信息（中国农药信息网）与荔枝栽培农技资料，
v1 仅内置常见药剂用于演示；正式上线应替换为可维护的药品字典表。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 农药知识库（静态表）
# cas_no 用于录入时校验，防止录错药名；safe_interval_days 为推荐安全间隔期
# ---------------------------------------------------------------------------
PESTICIDES: list[dict] = [
    {"name": "高效氯氟氰菊酯", "cas_no": "91465-08-6", "category": "杀虫剂",
     "targets": ["荔枝蒂蛀虫", "荔枝蝽"], "safe_interval_days": 14, "dosage_hint": "2.5%乳油 2000-3000倍液"},
    {"name": "氯虫苯甲酰胺", "cas_no": "500008-45-7", "category": "杀虫剂",
     "targets": ["荔枝蒂蛀虫"], "safe_interval_days": 14, "dosage_hint": "20%悬浮剂 3000-4000倍液"},
    {"name": "甲氨基阿维菌素苯甲酸盐", "cas_no": "155569-91-8", "category": "杀虫剂",
     "targets": ["荔枝蒂蛀虫", "荔枝尺蠖"], "safe_interval_days": 7, "dosage_hint": "5%微乳剂 1500-2000倍液"},
    {"name": "吡虫啉", "cas_no": "138261-41-3", "category": "杀虫剂",
     "targets": ["荔枝尺蠖"], "safe_interval_days": 7, "dosage_hint": "10%可湿性粉剂 2000倍液"},
    {"name": "啶虫脒", "cas_no": "135410-20-7", "category": "杀虫剂",
     "targets": ["荔枝尺蠖"], "safe_interval_days": 7, "dosage_hint": "20%可溶粉剂 4000倍液"},
    {"name": "敌百虫", "cas_no": "52-68-6", "category": "杀虫剂",
     "targets": ["荔枝蝽"], "safe_interval_days": 14, "dosage_hint": "90%晶体 800-1000倍液"},
    {"name": "溴氰菊酯", "cas_no": "52918-63-5", "category": "杀虫剂",
     "targets": ["荔枝蝽", "荔枝蒂蛀虫"], "safe_interval_days": 14, "dosage_hint": "2.5%乳油 2500倍液"},
    {"name": "阿维菌素", "cas_no": "71751-41-2", "category": "杀虫剂",
     "targets": ["荔枝瘿螨"], "safe_interval_days": 7, "dosage_hint": "1.8%乳油 3000倍液"},
    {"name": "哒螨灵", "cas_no": "96489-71-3", "category": "杀虫剂",
     "targets": ["荔枝瘿螨"], "safe_interval_days": 14, "dosage_hint": "15%乳油 2000倍液"},
    {"name": "代森锰锌", "cas_no": "8018-01-7", "category": "杀菌剂",
     "targets": ["荔枝霜疫霉病", "荔枝炭疽病"], "safe_interval_days": 10, "dosage_hint": "80%可湿性粉剂 600-800倍液"},
    {"name": "甲霜灵", "cas_no": "57837-19-1", "category": "杀菌剂",
     "targets": ["荔枝霜疫霉病"], "safe_interval_days": 14, "dosage_hint": "25%可湿性粉剂 500-800倍液"},
    {"name": "烯酰吗啉", "cas_no": "110488-70-5", "category": "杀菌剂",
     "targets": ["荔枝霜疫霉病"], "safe_interval_days": 14, "dosage_hint": "50%可湿性粉剂 1500-2000倍液"},
    {"name": "嘧菌酯", "cas_no": "131860-33-8", "category": "杀菌剂",
     "targets": ["荔枝炭疽病"], "safe_interval_days": 14, "dosage_hint": "25%悬浮剂 1500-2000倍液"},
    {"name": "苯醚甲环唑", "cas_no": "119446-68-3", "category": "杀菌剂",
     "targets": ["荔枝炭疽病"], "safe_interval_days": 14, "dosage_hint": "10%水分散粒剂 2000-3000倍液"},
    {"name": "咪鲜胺", "cas_no": "67747-09-5", "category": "杀菌剂",
     "targets": ["荔枝炭疽病"], "safe_interval_days": 10, "dosage_hint": "25%乳油 1000-1500倍液"},
    {"name": "多菌灵", "cas_no": "10605-21-7", "category": "杀菌剂",
     "targets": ["荔枝炭疽病"], "safe_interval_days": 14, "dosage_hint": "50%可湿性粉剂 800倍液"},
    {"name": "波尔多液", "cas_no": "8011-63-0", "category": "杀菌剂",
     "targets": ["荔枝霜疫霉病"], "safe_interval_days": 15, "dosage_hint": "0.5%等量式"},
    {"name": "草甘膦", "cas_no": "1071-83-6", "category": "除草剂",
     "targets": ["杂草"], "safe_interval_days": 30, "dosage_hint": "41%水剂 150-200倍液（行间定向喷雾）"},
    {"name": "乙氧氟草醚", "cas_no": "42874-03-3", "category": "除草剂",
     "targets": ["杂草"], "safe_interval_days": 30, "dosage_hint": "24%乳油 100-150倍液（行间定向喷雾）"},
]

PESTICIDE_BY_NAME = {p["name"]: p for p in PESTICIDES}
PESTICIDE_BY_CAS = {p["cas_no"]: p for p in PESTICIDES}


# ---------------------------------------------------------------------------
# 主要病虫害知识库
# ---------------------------------------------------------------------------
PESTS: dict[str, dict] = {
    "荔枝蒂蛀虫": {
        "latin": "Conopomorpha sinensis",
        "kind": "虫害",
        "risk": "高",
        "symptoms": "果实表面可见针尖状蛀孔，孔口有褐色虫粪，果核被蛀空导致落果。",
        "timing": "果实膨大期至转色期（5-6月）为防治关键期，重点保护果穗。",
        "notes": "成虫昼伏夜出，傍晚施药效果较好；注意轮换用药，避免抗性。",
    },
    "荔枝蝽": {
        "latin": "Tessaratoma papillosa",
        "kind": "虫害",
        "risk": "中高",
        "symptoms": "若虫、成虫刺吸嫩梢与花穗汁液，造成落花落果，分泌物污染果面。",
        "timing": "越冬成虫恢复活动期（3-4月）与若虫孵化盛期是防治窗口。",
        "notes": "可在清晨低温时人工捕杀成虫；保护平腹小蜂等天敌。",
    },
    "荔枝霜疫霉病": {
        "latin": "Peronophythora litchii",
        "kind": "病害",
        "risk": "高",
        "symptoms": "果皮出现褐色水渍状病斑，潮湿时表面生白色霜状霉层，果实迅速腐烂。",
        "timing": "花穗期、幼果期及连续阴雨高湿天气需提前预防。",
        "notes": "以预防为主，雨前施药；及时清除病果病枝，改善通风透光。",
    },
    "荔枝炭疽病": {
        "latin": "Colletotrichum gloeosporioides",
        "kind": "病害",
        "risk": "中高",
        "symptoms": "叶片与果实上出现褐色凹陷病斑，边缘有晕圈，后期病斑中央生小黑点。",
        "timing": "高温高湿季节（5-8月）高发，采前果实期为重点。",
        "notes": "加强树体管理，避免偏施氮肥；采后及时清园。",
    },
    "荔枝瘿螨": {
        "latin": "Aceria litchii",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "嫩叶背面出现黄褐色毛毡状绒毛，叶片卷曲畸形，影响新梢生长。",
        "timing": "新梢抽发期是防治关键，重点喷施叶背。",
        "notes": "瘿螨体型极小，需用杀螨剂并保证叶背着药；剪除严重受害枝梢。",
    },
    "荔枝尺蠖": {
        "latin": "Ascotis selenaria",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "幼虫啃食嫩叶，造成叶片缺刻甚至仅剩叶脉，暴发时可将整株叶片吃光。",
        "timing": "新梢期与幼虫三龄前为最佳防治期。",
        "notes": "低龄幼虫耐药性弱，宜早施药；可结合灯光诱杀成虫。",
    },
    "健康叶片": {
        "latin": "-",
        "kind": "无异常",
        "risk": "无",
        "symptoms": "叶色正常、无病斑与虫孔，未见明显受害症状。",
        "timing": "建议保持常规巡检频次。",
        "notes": "继续做好水肥管理与定期巡检，发现异常及时拍照记录。",
    },
    "无法判断": {
        "latin": "-",
        "kind": "未知",
        "risk": "未知",
        "symptoms": "图片未能匹配到已知荔枝病虫害特征。",
        "timing": "建议在自然光下重新拍摄叶片或果实特写，或联系农技人员现场诊断。",
        "notes": "结果不可靠，请勿据此用药。",
    },
}

# 可用于模拟/演示的病虫害类别（排除健康与兜底）
PEST_CLASSES = [k for k in PESTS if k not in ("健康叶片", "无法判断")]

# 用于模拟识别的常见类别权重（演示用，越靠前越常见）
MOCK_CLASS_POOL = [
    "荔枝蒂蛀虫", "荔枝霜疫霉病", "荔枝炭疽病", "荔枝蝽",
    "荔枝蒂蛀虫", "荔枝霜疫霉病", "荔枝瘿螨", "荔枝尺蠖",
    "荔枝炭疽病", "健康叶片",
]


def lookup_pesticide(name: str | None = None, cas_no: str | None = None) -> dict | None:
    if cas_no and cas_no in PESTICIDE_BY_CAS:
        return PESTICIDE_BY_CAS[cas_no]
    if name and name in PESTICIDE_BY_NAME:
        return PESTICIDE_BY_NAME[name]
    return None


def recommended_pesticides(pest_class: str) -> list[dict]:
    """按病虫害类别返回可用药剂，按安全间隔期由短到长排序（越短越灵活）。"""
    if pest_class not in PESTS or PESTS[pest_class]["kind"] in ("无异常", "未知"):
        return []
    items = [p for p in PESTICIDES if pest_class in p["targets"]]
    return sorted(items, key=lambda p: p["safe_interval_days"])


def build_suggestion(pest_class: str, confidence: float, days_to_harvest: int | None = None) -> dict:
    """把识别结果转换为结构化防治建议。

    这是「规则引擎兜底」：大模型/识别 API 只负责给出类别，
    用药建议一律由本地规则库生成并做安全间隔期校验。
    """
    info = PESTS.get(pest_class)
    if info is None:
        return {
            "pest_class": pest_class,
            "kind": "未知",
            "risk": "未知",
            "confidence": confidence,
            "summary": "未能匹配到本地病虫害知识库，建议人工复核或送检。",
            "pesticides": [],
            "warnings": ["识别结果不在知识库范围内，请勿直接按建议用药。"],
            "text": "",
        }

    pesticide_opts = recommended_pesticides(pest_class)
    warnings: list[str] = []

    if info["kind"] == "无异常":
        text = (
            f"识别结果：{pest_class}（置信度 {confidence:.0%}）。\n"
            f"{info['symptoms']}\n建议：{info['notes']}"
        )
        return {
            "pest_class": pest_class, "kind": info["kind"], "risk": info["risk"],
            "latin": info["latin"], "confidence": confidence,
            "summary": info["symptoms"], "timing": info["timing"], "notes": info["notes"],
            "pesticides": [], "warnings": [], "text": text,
        }

    if info["kind"] == "未知":
        text = (
            f"识别结果：{pest_class}（置信度 {confidence:.0%}）。\n"
            f"{info['symptoms']}\n建议：{info['timing']}"
        )
        return {
            "pest_class": pest_class, "kind": info["kind"], "risk": info["risk"],
            "latin": info["latin"], "confidence": confidence,
            "summary": info["symptoms"], "timing": info["timing"], "notes": info["notes"],
            "pesticides": [],
            "warnings": ["结果不在已知病虫害知识库内，请勿据此用药。"],
            "text": text,
        }

    # 安全间隔期与采收期冲突检查
    safe_opts = []
    for p in pesticide_opts:
        if days_to_harvest is not None and days_to_harvest < p["safe_interval_days"]:
            continue
        safe_opts.append(p)
    if days_to_harvest is not None and len(safe_opts) < len(pesticide_opts):
        warnings.append(
            f"距离预计采收仅 {days_to_harvest} 天，已过滤安全间隔期更长的药剂；"
            f"临近采收期建议优先采用农业/物理防治。"
        )
    if days_to_harvest is not None and not safe_opts:
        warnings.append("当前距采收期过近，无可用化学药剂，请改用人工捕杀、清园等非化学措施。")

    lines = [
        f"识别结果：{pest_class}（置信度 {confidence:.0%}，风险等级：{info['risk']}）",
        f"典型症状：{info['symptoms']}",
        f"防治时机：{info['timing']}",
        f"田间管理：{info['notes']}",
    ]
    if safe_opts:
        picks = "、".join(f"{p['name']}（安全间隔期 {p['safe_interval_days']} 天）" for p in safe_opts[:3])
        lines.append(f"可选药剂：{picks}")
        lines.append("施药前请核对农药标签登记作物与剂量，严格执行安全间隔期。")
    lines.extend(warnings)

    return {
        "pest_class": pest_class,
        "latin": info["latin"],
        "kind": info["kind"],
        "risk": info["risk"],
        "confidence": confidence,
        "summary": info["symptoms"],
        "timing": info["timing"],
        "notes": info["notes"],
        # 只要调用了方给了采收倒计时，就严格只返回已过滤的安全药剂（可能为空）
        "pesticides": safe_opts,
        "warnings": warnings,
        "text": "\n".join(lines),
    }
