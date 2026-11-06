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
        "aliases": ["蒂蛀虫", "荔枝蛀蒂虫", "荔枝果蛀虫", "litchi fruit borer"],
        "host_parts": ["果实", "果蒂", "果核", "嫩梢"],
        "differential": {
            "confusable": ["荔枝炭疽病", "荔枝蝽"],
            "distinguishing": [
                "蛀孔针尖状，孔口常附褐色虫粪",
                "剖果可见果核被蛀空、果肉有隧道",
                "炭疽病为褐色凹陷病斑、边缘晕圈、后期小黑点，无蛀孔虫粪",
                "蝽害为刺吸斑与臭液污染，无蛀孔虫粪",
            ],
        },
        "non_chemical": [
            "及时捡拾落果并深埋或销毁",
            "冬季清园，剪除被害枝梢",
            "果穗套袋保护",
            "成虫期悬挂诱虫灯或性诱剂监测",
        ],
    },
    "荔枝蝽": {
        "latin": "Tessaratoma papillosa",
        "kind": "虫害",
        "risk": "中高",
        "symptoms": "若虫、成虫刺吸嫩梢与花穗汁液，造成落花落果，分泌物污染果面。",
        "timing": "越冬成虫恢复活动期（3-4月）与若虫孵化盛期是防治窗口。",
        "notes": "可在清晨低温时人工捕杀成虫；保护平腹小蜂等天敌。",
        "aliases": ["蝽", "荔枝椿象", "荔蝽", "litchi stink bug"],
        "host_parts": ["嫩梢", "花穗", "幼果"],
        "differential": {
            "confusable": ["荔枝蒂蛀虫"],
            "distinguishing": [
                "刺吸口针痕、果面有臭液污染斑，受惊时喷臭液",
                "无蛀孔、无虫粪，可与蒂蛀虫区分",
                "卵块多产于叶背，若虫聚集嫩梢",
            ],
        },
        "non_chemical": [
            "清晨低温时人工捕杀成虫",
            "摘除叶背卵块、剪除若虫聚集枝梢",
            "保护平腹小蜂等天敌",
        ],
    },
    "荔枝霜疫霉病": {
        "latin": "Peronophythora litchii",
        "kind": "病害",
        "risk": "高",
        "symptoms": "果皮出现褐色水渍状病斑，潮湿时表面生白色霜状霉层，果实迅速腐烂。",
        "timing": "花穗期、幼果期及连续阴雨高湿天气需提前预防。",
        "notes": "以预防为主，雨前施药；及时清除病果病枝，改善通风透光。",
        "aliases": ["霜疫霉病", "霜疫霉", "荔枝霜霉病", "downy blight"],
        "host_parts": ["果实", "花穗", "嫩叶", "果柄"],
        "differential": {
            "confusable": ["荔枝炭疽病"],
            "distinguishing": [
                "病斑褐色水渍状、扩展快，潮湿时表面生白色霜状霉层",
                "果实迅速腐烂，常伴酸腐味",
                "炭疽病为凹陷病斑、边缘晕圈、中央小黑点，霉层不呈霜状",
            ],
        },
        "non_chemical": [
            "雨前抢晴保护、雨后及时排水降湿",
            "清除病果病枝与地面落果，集中销毁",
            "修剪郁闭枝梢，改善通风透光",
        ],
    },
    "荔枝炭疽病": {
        "latin": "Colletotrichum gloeosporioides",
        "kind": "病害",
        "risk": "中高",
        "symptoms": "叶片与果实上出现褐色凹陷病斑，边缘有晕圈，后期病斑中央生小黑点。",
        "timing": "高温高湿季节（5-8月）高发，采前果实期为重点。",
        "notes": "加强树体管理，避免偏施氮肥；采后及时清园。",
        "aliases": ["炭疽病", "炭疽", "anthracnose"],
        "host_parts": ["叶片", "果实", "枝梢", "果柄"],
        "differential": {
            "confusable": ["荔枝霜疫霉病"],
            "distinguishing": [
                "褐色凹陷病斑，边缘有晕圈",
                "后期病斑中央生小黑点（分生孢子盘），干燥时病部干枯",
                "霜疫霉病为水渍状斑、白色霜状霉层、腐烂更快",
            ],
        },
        "non_chemical": [
            "剪除病枝病叶并集中销毁",
            "采后清园，清除落果落叶",
            "改善通风透光，避免偏施氮肥",
        ],
    },
    "荔枝瘿螨": {
        "latin": "Aceria litchii",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "嫩叶背面出现黄褐色毛毡状绒毛，叶片卷曲畸形，影响新梢生长。",
        "timing": "新梢抽发期是防治关键，重点喷施叶背。",
        "notes": "瘿螨体型极小，需用杀螨剂并保证叶背着药；剪除严重受害枝梢。",
        "aliases": ["瘿螨", "荔枝毛毡病", "荔枝叶瘿螨", "litchi erinose mite"],
        "host_parts": ["嫩叶", "叶背", "新梢", "花穗"],
        "differential": {
            "confusable": ["荔枝尺蠖", "荔枝炭疽病"],
            "distinguishing": [
                "叶背出现黄褐色毛毡状绒毛（虫瘿），叶片卷曲畸形",
                "无咬食缺刻，可与尺蠖区分",
                "炭疽病为褐色病斑伴小黑点，无毛毡状绒毛",
            ],
        },
        "non_chemical": [
            "剪除严重受害枝梢并集中销毁",
            "重点检查叶背，及时摘除虫瘿叶",
            "保护捕食螨等天敌",
        ],
    },
    "荔枝尺蠖": {
        "latin": "Ascotis selenaria",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "幼虫啃食嫩叶，造成叶片缺刻甚至仅剩叶脉，暴发时可将整株叶片吃光。",
        "timing": "新梢期与幼虫三龄前为最佳防治期。",
        "notes": "低龄幼虫耐药性弱，宜早施药；可结合灯光诱杀成虫。",
        "aliases": ["尺蠖", "荔枝造桥虫", "litchi looper"],
        "host_parts": ["嫩叶", "叶片", "新梢"],
        "differential": {
            "confusable": ["荔枝瘿螨"],
            "distinguishing": [
                "幼虫啃食造成叶片缺刻、孔洞，暴发时仅剩叶脉",
                "可见幼虫以腹足拱行，拟态枝条",
                "瘿螨为叶背毛毡状绒毛与卷曲，无咬食缺刻",
            ],
        },
        "non_chemical": [
            "人工捕捉幼虫，注意其拟态枝条",
            "灯光诱杀成虫",
            "剪除卵块和低龄幼虫聚集叶",
        ],
    },
    "健康叶片": {
        "latin": "-",
        "kind": "无异常",
        "risk": "无",
        "symptoms": "叶色正常、无病斑与虫孔，未见明显受害症状。",
        "timing": "建议保持常规巡检频次。",
        "notes": "继续做好水肥管理与定期巡检，发现异常及时拍照记录。",
        "aliases": ["healthy leaf", "healthy", "正常叶片", "健康叶"],
        "host_parts": [],
        "differential": {"confusable": [], "distinguishing": []},
        "non_chemical": [],
    },
    "健康果实": {
        "latin": "-",
        "kind": "无异常",
        "risk": "无",
        "symptoms": "果皮着色均匀、有光泽，无褐色凹陷病斑、蛀孔与霉层，未见明显受害症状。",
        "timing": "建议保持常规巡检频次，采收前重点检查果蒂与果面。",
        "notes": "继续做好水肥管理与定期巡检；果面水珠、自然龟裂与未转色斑块属正常现象。",
        "aliases": ["healthy fruit", "正常果实", "健康果"],
        "host_parts": [],
        "differential": {"confusable": [], "distinguishing": []},
        "non_chemical": [],
    },
    "无法判断": {
        "latin": "-",
        "kind": "未知",
        "risk": "未知",
        "symptoms": "图片未能匹配到已知荔枝病虫害特征。",
        "timing": "建议在自然光下重新拍摄叶片或果实特写，或联系农技人员现场诊断。",
        "notes": "结果不可靠，请勿据此用药。",
        "aliases": ["unknown", "未知", "无法识别", "看不清"],
        "host_parts": [],
        "differential": {"confusable": [], "distinguishing": []},
        "non_chemical": [],
    },
}

# 表示「未见异常」的类别，统计与待办里需要与病虫害分开
HEALTHY_CLASSES = ("健康叶片", "健康果实")

# 可用于模拟/演示的病虫害类别（排除健康与兜底）
PEST_CLASSES = [k for k in PESTS if k not in HEALTHY_CLASSES + ("无法判断",)]

# 用于模拟识别的常见类别权重（演示用，越靠前越常见）
MOCK_CLASS_POOL = [
    "荔枝蒂蛀虫", "荔枝霜疫霉病", "荔枝炭疽病", "荔枝蝽",
    "荔枝蒂蛀虫", "荔枝霜疫霉病", "荔枝瘿螨", "荔枝尺蠖",
    "荔枝炭疽病", "健康叶片", "健康果实",
]

# 低于该置信度的病虫害结论不做自动处置建议，提示人工复核
LOW_CONFIDENCE = 0.65


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


def _measure_text(non_chemical: list[str] | None, kind: str) -> str:
    """取知识库里的前两条非化学措施，缺失时回退到通用措辞。"""
    measures = [m for m in (non_chemical or []) if m][:2]
    if measures:
        return "、".join(measures)
    return "剪除病枝病果、清除病残体" if kind == "病害" else "人工捕杀、剪除虫枝虫果"


def _pick_action(
    risk: str, safe_opts: list[dict], all_opts: list[dict], days_to_harvest: int | None,
    kind: str = "虫害", non_chemical: list[str] | None = None,
) -> tuple[str, str]:
    """根据风险等级与可用药剂，给出建议处置方式及理由（纯规则、可解释）。

    优先保证「不打来不及过间隔期的药」：
      - 高风险且仍有合规药剂 → 用药；
      - 高风险但临近采收/无药剂 → 人工清除；
      - 中高风险 → 人工清除等物理防治；
      - 中风险 → 观察（忽略），病情/虫口上升再处置。

    kind 只影响措辞：虫害说「虫口基数」，病害说「病源基数」。
    non_chemical 来自知识库，用于把措施说具体。
    """
    if risk == "高":
        if safe_opts:
            if days_to_harvest is not None:
                return "pesticide", (
                    f"风险高；距采收 {days_to_harvest} 天仍有 {len(safe_opts)} 种合规药剂，"
                    f"建议按安全间隔期用药。"
                )
            return "pesticide", "风险高；有登记药剂可用，施药前请确认距采收时间满足安全间隔期。"
        if all_opts and days_to_harvest is not None:
            return "operation", (
                f"风险高，但距采收仅 {days_to_harvest} 天，推荐药剂均来不及过安全间隔期，"
                f"建议优先{_measure_text(non_chemical, kind)}等非化学措施。"
            )
        return "operation", (
            f"该病虫害暂无可用登记药剂，建议优先{_measure_text(non_chemical, kind)}等物理/农业防治。"
        )
    if risk == "中高":
        target = "病源基数" if kind == "病害" else "虫口基数"
        return "operation", (
            f"风险中高，建议优先{_measure_text(non_chemical, kind)}等物理/农业防治，"
            f"压低{target}后再评估是否用药。"
        )
    trend = "病情" if kind == "病害" else "虫口"
    return "ignore", f"风险中等，暂未达防治阈值，建议持续观察并加强巡园；{trend}上升时再处置。"


def _knowledge_fields(info: dict | None) -> dict:
    """把知识库的结构化字段复制一份给 suggestion，避免调用方改到全局数据。"""
    info = info or {}
    diff = info.get("differential") or {}
    return {
        "host_parts": list(info.get("host_parts") or []),
        "differential": {
            "confusable": list(diff.get("confusable") or []),
            "distinguishing": list(diff.get("distinguishing") or []),
        },
        "non_chemical": list(info.get("non_chemical") or []),
    }


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
            "recommended_action": "none",
            "action_reason": "识别结果不在知识库内，建议重新拍照或联系农技人员现场诊断。",
            "text": "",
            **_knowledge_fields(None),
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
            "pesticides": [], "warnings": [],
            "recommended_action": "none",
            "action_reason": "未发现明显病虫害，保持常规巡检与水肥管理即可，无需处置。",
            "text": text,
            **_knowledge_fields(info),
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
            "recommended_action": "none",
            "action_reason": "结果不可靠，建议重新拍摄或请农技人员复核，暂勿处置。",
            "text": text,
            **_knowledge_fields(info),
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

    low_confidence = confidence < LOW_CONFIDENCE
    if low_confidence:
        warnings.append(
            f"识别置信度仅 {confidence:.0%}，低于 {LOW_CONFIDENCE:.0%} 的自动处置阈值，"
            "建议先人工复核或重新拍照，确认后再处置。"
        )

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

    if low_confidence:
        # 低置信度结论只展示症状与风险，不给自动处置，避免误报被当成确诊
        action, action_reason = "none", "识别置信度偏低，暂不建议按该结果处置，请人工复核。"
    else:
        action, action_reason = _pick_action(
            info["risk"], safe_opts, pesticide_opts, days_to_harvest, info["kind"],
            info.get("non_chemical"),
        )

    return {
        "pest_class": pest_class,
        "latin": info["latin"],
        "kind": info["kind"],
        "risk": info["risk"],
        "confidence": confidence,
        "low_confidence": low_confidence,
        "summary": info["symptoms"],
        "timing": info["timing"],
        "notes": info["notes"],
        # 只要调用了方给了采收倒计时，就严格只返回已过滤的安全药剂（可能为空）
        "pesticides": safe_opts,
        "warnings": warnings,
        "recommended_action": action,
        "action_reason": action_reason,
        "text": "\n".join(lines),
        **_knowledge_fields(info),
    }


# ---------------------------------------------------------------------------
# 知识库自检：数据改动后由测试和启动日志兜底
# ---------------------------------------------------------------------------
_KNOWN_KINDS = ("虫害", "病害", "无异常", "未知")
_KNOWN_RISKS = ("高", "中高", "中", "无", "未知")
_REQUIRED_PEST_KEYS = (
    "latin", "kind", "risk", "symptoms", "timing", "notes",
    "aliases", "host_parts", "differential", "non_chemical",
)


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def validate_knowledge(
    pests: dict[str, dict] | None = None,
    pesticides: list[dict] | None = None,
) -> list[str]:
    """校验知识库数据，返回人类可读的问题列表；空列表表示通过。

    参数可注入，方便测试构造坏数据，不影响全局字典。
    """
    pests = PESTS if pests is None else pests
    pesticides = PESTICIDES if pesticides is None else pesticides
    problems: list[str] = []

    aliases_seen: dict[str, str] = {}
    for name, info in pests.items():
        for key in _REQUIRED_PEST_KEYS:
            if key not in info:
                problems.append(f"{name}：缺少字段 {key}")
        if info.get("kind") not in _KNOWN_KINDS:
            problems.append(f"{name}：kind 取值非法 {info.get('kind')!r}")
        if info.get("risk") not in _KNOWN_RISKS:
            problems.append(f"{name}：risk 取值非法 {info.get('risk')!r}")

        aliases = info.get("aliases") or []
        if not _is_str_list(aliases):
            problems.append(f"{name}：aliases 必须是非空字符串列表")
        else:
            for alias in aliases:
                key = alias.strip().lower()
                if key in aliases_seen and aliases_seen[key] != name:
                    problems.append(f"{name}：别名「{alias}」与 {aliases_seen[key]} 重复")
                aliases_seen[key] = name
                if alias in pests and alias != name:
                    problems.append(f"{name}：别名「{alias}」与类别名冲突")

        for key in ("host_parts", "non_chemical"):
            value = info.get(key) or []
            if not _is_str_list(value):
                problems.append(f"{name}：{key} 必须是非空字符串列表")
            elif len(set(value)) != len(value):
                problems.append(f"{name}：{key} 存在重复项")

        diff = info.get("differential") or {}
        if not isinstance(diff, dict):
            problems.append(f"{name}：differential 必须是对象")
            diff = {}
        for key in ("confusable", "distinguishing"):
            value = diff.get(key) or []
            if not _is_str_list(value):
                problems.append(f"{name}：differential.{key} 必须是非空字符串列表")
            elif len(set(value)) != len(value):
                problems.append(f"{name}：differential.{key} 存在重复项")
        for other in diff.get("confusable") or []:
            if other == name:
                problems.append(f"{name}：differential.confusable 不能是自己")
            elif other not in pests:
                problems.append(f"{name}：differential.confusable 引用了未知类别「{other}」")

        if info.get("kind") in ("虫害", "病害"):
            if not str(info.get("symptoms") or "").strip():
                problems.append(f"{name}：symptoms 不能为空")
            if not str(info.get("timing") or "").strip():
                problems.append(f"{name}：timing 不能为空")
            if not (info.get("host_parts") or []):
                problems.append(f"{name}：病虫害必须填写 host_parts")
            if not (info.get("non_chemical") or []):
                problems.append(f"{name}：病虫害必须填写 non_chemical")
            if not (diff.get("distinguishing") or []):
                problems.append(f"{name}：病虫害必须填写 differential.distinguishing")

    seen_names: set[str] = set()
    seen_cas: set[str] = set()
    for p in pesticides:
        name = p.get("name") or "<未命名>"
        if name in seen_names:
            problems.append(f"农药 {name}：名称重复")
        seen_names.add(name)
        cas_no = str(p.get("cas_no") or "").strip()
        if not cas_no:
            problems.append(f"农药 {name}：cas_no 不能为空")
        elif cas_no in seen_cas:
            problems.append(f"农药 {name}：CAS 号 {cas_no} 重复")
        seen_cas.add(cas_no)
        try:
            if int(p.get("safe_interval_days", 0)) <= 0:
                problems.append(f"农药 {name}：safe_interval_days 必须为正整数")
        except (TypeError, ValueError):
            problems.append(f"农药 {name}：safe_interval_days 必须是数字")
        for target in p.get("targets") or []:
            if target in pests:
                if pests[target].get("kind") not in ("虫害", "病害"):
                    problems.append(f"农药 {name}：targets 指向非病虫害类别「{target}」")
            elif p.get("category") != "除草剂":
                # 除草剂针对「杂草」这类防治对象，本就不在病虫害知识库里
                problems.append(f"农药 {name}：targets 引用了未知类别「{target}」")

    if pests is PESTS and pesticides is PESTICIDES:
        if not PEST_CLASSES:
            problems.append("PEST_CLASSES 不能为空")
        for name in MOCK_CLASS_POOL:
            if name not in PESTS:
                problems.append(f"MOCK_CLASS_POOL 引用了未知类别「{name}」")
        for name in HEALTHY_CLASSES:
            if PESTS.get(name, {}).get("kind") != "无异常":
                problems.append(f"HEALTHY_CLASSES 中的「{name}」kind 必须是「无异常」")
        if PESTS.get("无法判断", {}).get("kind") != "未知":
            problems.append("必须存在 kind 为「未知」的「无法判断」类别")

    return problems
