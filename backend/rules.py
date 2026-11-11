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
     "targets": ["荔枝蒂蛀虫", "荔枝蝽", "荔枝金龟子"], "safe_interval_days": 14, "dosage_hint": "2.5%乳油 2000-3000倍液"},
    {"name": "氯虫苯甲酰胺", "cas_no": "500008-45-7", "category": "杀虫剂",
     "targets": ["荔枝蒂蛀虫"], "safe_interval_days": 14, "dosage_hint": "20%悬浮剂 3000-4000倍液"},
    {"name": "甲氨基阿维菌素苯甲酸盐", "cas_no": "155569-91-8", "category": "杀虫剂",
     "targets": ["荔枝蒂蛀虫", "荔枝尺蠖", "荔枝小灰蝶"], "safe_interval_days": 7, "dosage_hint": "5%微乳剂 1500-2000倍液"},
    {"name": "吡虫啉", "cas_no": "138261-41-3", "category": "杀虫剂",
     "targets": ["荔枝尺蠖", "荔枝木虱", "荔枝蚜虫", "荔枝蓟马"], "safe_interval_days": 7, "dosage_hint": "10%可湿性粉剂 2000倍液"},
    {"name": "啶虫脒", "cas_no": "135410-20-7", "category": "杀虫剂",
     "targets": ["荔枝尺蠖", "荔枝木虱", "荔枝蚜虫", "荔枝蓟马"], "safe_interval_days": 7, "dosage_hint": "20%可溶粉剂 4000倍液"},
    {"name": "噻虫嗪", "cas_no": "153719-23-4", "category": "杀虫剂",
     "targets": ["荔枝木虱", "荔枝介壳虫", "荔枝叶瘿蚊", "荔枝蚜虫", "荔枝蓟马"], "safe_interval_days": 14, "dosage_hint": "25%水分散粒剂 5000-8000倍液"},
    {"name": "螺虫乙酯", "cas_no": "203313-25-1", "category": "杀虫剂",
     "targets": ["荔枝介壳虫"], "safe_interval_days": 14, "dosage_hint": "22.4%悬浮剂 4000-5000倍液"},
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
     "targets": ["荔枝霜疫霉病", "荔枝藻斑病"], "safe_interval_days": 15, "dosage_hint": "0.5%等量式"},
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
        "peak_months": ["5月", "6月", "7月"],
        "monitoring": "果实膨大期至转色期每 3-5 天巡园一次，重点检查果蒂、果面是否有针尖状蛀孔和褐色虫粪；捡拾落果剖检。",
        "biological": ["保护寄生蜂、蜘蛛等天敌", "成虫期使用性诱剂诱杀"],
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
        "peak_months": ["3月", "4月", "5月"],
        "monitoring": "越冬成虫恢复活动期和若虫孵化期，清晨低温时检查叶背卵块和嫩梢若虫数量。",
        "biological": ["保护平腹小蜂等卵寄生蜂", "人工释放平腹小蜂"],
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
        "peak_months": ["4月", "5月", "6月"],
        "monitoring": "花穗期、幼果期关注天气预报，连续阴雨前检查果穗和叶片是否有水渍状病斑。",
        "biological": ["改善通风降湿，保护拮抗菌群", "发病初期可试用枯草芽孢杆菌等生防制剂"],
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
        "peak_months": ["5月", "6月", "7月", "8月"],
        "monitoring": "高温高湿季节检查叶片、果实是否有褐色凹陷病斑和中央小黑点，采前重点查果。",
        "biological": ["保护拮抗微生物，减少病源", "清除病残体并集中销毁"],
    },
    "荔枝瘿螨": {
        "latin": "Aceria litchii",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "嫩叶背面出现黄褐色毛毡状绒毛，叶片卷曲畸形，影响新梢生长。",
        "timing": "新梢抽发期是防治关键，重点喷施叶背。",
        "notes": "瘿螨体型极小，需用杀螨剂并保证叶背着药；剪除严重受害枝梢。",
        "aliases": ["瘿螨", "毛毡病", "荔枝毛毡病", "荔枝叶瘿螨", "litchi erinose mite"],
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
        "peak_months": ["3月", "4月", "5月", "8月", "9月"],
        "monitoring": "新梢抽发期检查叶背是否有黄褐色毛毡状绒毛和叶片卷曲，重点看树冠外围嫩叶。",
        "biological": ["保护捕食螨等天敌", "避免滥用广谱杀虫剂"],
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
        "peak_months": ["4月", "5月", "6月", "8月", "9月"],
        "monitoring": "新梢期检查叶片缺刻和幼虫（拟态枝条），每 3-5 天查一次，幼虫三龄前是防治窗口。",
        "biological": ["保护寄生蜂、鸟类等天敌", "灯光诱杀成虫"],
    },
    "荔枝煤烟病": {
        "latin": "Capnodium spp.",
        "kind": "病害",
        "risk": "中",
        "symptoms": "叶面、果面覆盖黑色煤粉状霉层，用手可擦掉，常伴随蚜虫、木虱、介壳虫分泌的蜜露。",
        "timing": "春夏高温高湿、虫害严重时高发，树冠郁闭处更重。",
        "notes": "煤烟病菌以蜜露为营养，治霉先治虫；修剪通风、控制刺吸类害虫是关键。",
        "aliases": ["煤烟病", "煤污病", "sooty mold"],
        "host_parts": ["叶片", "果实", "枝梢"],
        "differential": {
            "confusable": ["荔枝炭疽病", "荔枝藻斑病"],
            "distinguishing": [
                "黑色煤粉状霉层附着在表面，可擦除，叶面本身无明显坏死",
                "多伴随蜜露和蚜虫、木虱、介壳虫发生",
                "炭疽病为褐色凹陷病斑伴小黑点，擦不掉",
                "藻斑病为灰绿色至红褐色绒状斑、有辐射纹理，不是黑色煤粉",
            ],
        },
        "non_chemical": [
            "修剪郁闭枝梢，改善通风透光",
            "清除病叶病果，减少菌源",
            "防治蚜虫、木虱、介壳虫等蜜露来源",
        ],
        "peak_months": ["5月", "6月", "7月", "8月"],
        "monitoring": "巡园时观察叶面、果面是否有黑色煤粉状霉层，重点检查树冠内膛和背阴处；同时留意蚜虫、木虱、介壳虫发生。",
        "biological": [
            "保护瓢虫、草蛉等天敌，控制蜜露分泌昆虫",
            "发病初期可试用枯草芽孢杆菌等生防菌抑制霉层扩展",
        ],
    },
    "荔枝藻斑病": {
        "latin": "Cephaleuros virescens",
        "kind": "病害",
        "risk": "中",
        "symptoms": "叶面初现黄绿色小圆点，后扩大为灰绿色至红褐色绒状斑，表面有辐射状纹理，多生于树冠中下部潮湿处。",
        "timing": "3-6 月温暖潮湿、通风不良时高发，雨季扩展快。",
        "notes": "属藻类病害，以改善通风降湿为主；严重时在发病初期用药。",
        "aliases": ["藻斑病", "绿藻病", "algal leaf spot"],
        "host_parts": ["叶片", "枝梢"],
        "differential": {
            "confusable": ["荔枝煤烟病", "荔枝炭疽病"],
            "distinguishing": [
                "病斑灰绿色至红褐色、绒状，表面有辐射状纹理",
                "多从叶面发生，树冠中下部潮湿处更重",
                "煤烟病为黑色煤粉状霉层，可擦掉",
                "炭疽病为褐色凹陷病斑、边缘晕圈、中央小黑点",
            ],
        },
        "non_chemical": [
            "修剪过密枝梢，改善通风透光",
            "清除病叶并集中销毁",
            "避免树冠长时间潮湿，雨后及时排水",
        ],
        "peak_months": ["3月", "4月", "5月", "6月"],
        "monitoring": "重点检查树冠中下部老叶叶面，看是否有灰绿色绒状、带辐射纹理的圆斑；雨季前后各查一次。",
        "biological": [
            "保护叶面有益微生物群落，避免滥用广谱杀菌剂",
            "发病初期可试用木霉菌等生防制剂",
        ],
    },
    "荔枝叶瘿蚊": {
        "latin": "Dasineura sp.",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "嫩叶出现细小水疱状虫瘿，叶片扭曲皱缩，严重时新梢枯死，影响抽梢与花芽分化。",
        "timing": "新梢抽发期成虫产卵于嫩叶，幼虫孵化后蛀入叶肉形成虫瘿。",
        "notes": "以新梢期防治为主，及时摘除虫瘿叶；冬季清园压低虫源。",
        "aliases": ["叶瘿蚊", "荔枝瘿蚊", "litchi leaf gall midge"],
        "host_parts": ["嫩叶", "新梢"],
        "differential": {
            "confusable": ["荔枝瘿螨", "荔枝尺蠖"],
            "distinguishing": [
                "嫩叶出现水疱状虫瘿、叶片扭曲皱缩",
                "虫瘿多在叶面凸起，剖开可见细小幼虫",
                "瘿螨为叶背黄褐色毛毡状绒毛，不形成水疱状虫瘿",
                "尺蠖为咬食缺刻，无虫瘿",
            ],
        },
        "non_chemical": [
            "摘除虫瘿叶并集中销毁",
            "新梢抽发期覆盖防虫网或套袋保护",
            "冬季清园，剪除被害枝梢",
        ],
        "peak_months": ["3月", "4月", "8月", "9月"],
        "monitoring": "新梢抽发后逐株检查嫩叶是否出现水疱状虫瘿、卷曲畸形；每 3-5 天查一次，重点看树冠外围新梢。",
        "biological": [
            "保护寄生蜂等天敌",
            "园内种植蜜源植物，提高天敌种群数量",
        ],
    },
    "荔枝木虱": {
        "latin": "Psyllidae",
        "kind": "虫害",
        "risk": "中高",
        "symptoms": "若虫刺吸嫩梢汁液，嫩叶卷曲畸形，若虫分泌白色蜡丝和蜜露，诱发煤烟病。",
        "timing": "春梢、秋梢抽发期是若虫盛发期，也是防治关键期。",
        "notes": "重点防治新梢期，兼治煤烟病；轮换用药，避免抗性。",
        "aliases": ["木虱", "荔枝木虱", "litchi psyllid"],
        "host_parts": ["嫩梢", "嫩叶", "花穗"],
        "differential": {
            "confusable": ["荔枝蝽", "荔枝瘿螨"],
            "distinguishing": [
                "嫩梢、嫩叶背面有白色蜡丝和蜜露，叶片卷曲畸形",
                "若虫群集嫩梢，受惊时弹跳",
                "蝽为大型若虫/成虫刺吸，受惊喷臭液",
                "瘿螨为叶背毛毡状绒毛，无蜡丝和蜜露",
            ],
        },
        "non_chemical": [
            "剪除严重受害嫩梢",
            "悬挂黄色粘虫板诱杀成虫",
            "保护瓢虫、草蛉等天敌",
        ],
        "peak_months": ["2月", "3月", "4月", "9月", "10月"],
        "monitoring": "新梢抽发期检查嫩梢、嫩叶背面是否有白色蜡丝、蜜露和若虫；黄色粘虫板可辅助监测成虫数量。",
        "biological": [
            "释放或保护瓢虫、草蛉等捕食性天敌",
            "保护寄生蜂，减少广谱杀虫剂使用",
        ],
    },
    "荔枝介壳虫": {
        "latin": "Coccoidea",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "枝干、叶片、果面附着褐色或白色蜡质介壳，吸食汁液，严重时枝条枯死并诱发煤烟病。",
        "timing": "若虫孵化盛期（4-6 月、9-10 月）是防治关键，蜡质形成后药效差。",
        "notes": "介壳蜡质层厚，必须抓住若虫期用药；剪除严重受害枝。",
        "aliases": ["介壳虫", "蚧壳虫", "scale insect"],
        "host_parts": ["枝干", "叶片", "果实"],
        "differential": {
            "confusable": ["荔枝木虱", "荔枝瘿螨"],
            "distinguishing": [
                "枝干、叶面、果面有褐色或白色蜡质介壳，刮除可见虫体",
                "多固定不动，严重时枝条表面密布介壳",
                "木虱为活动性若虫，有白色蜡丝和蜜露",
                "瘿螨为叶背毛毡状绒毛，无介壳",
            ],
        },
        "non_chemical": [
            "人工刷除枝干上的介壳虫",
            "剪除严重受害枝条并销毁",
            "保护瓢虫、寄生蜂等天敌",
        ],
        "peak_months": ["4月", "5月", "6月", "9月", "10月"],
        "monitoring": "检查枝干、叶背和果面是否有褐色/白色蜡质介壳，注意枝条缝隙和树冠内膛；若虫孵化期是防治窗口。",
        "biological": [
            "保护澳洲瓢虫、寄生蜂等天敌",
            "避免滥用广谱杀虫剂杀伤天敌",
        ],
    },
    "荔枝小灰蝶": {
        "latin": "Deudorix epijarbas",
        "kind": "虫害",
        "risk": "中高",
        "symptoms": "幼虫蛀食果实，蛀孔较蒂蛀虫大，孔口有粗粒虫粪排出，常导致落果。",
        "timing": "果实膨大期（5-7 月）幼虫蛀果，是防治关键期。",
        "notes": "与蒂蛀虫区分：蛀孔较大、虫粪粗；及时捡拾落果。",
        "aliases": ["小灰蝶", "荔枝小灰蝶", "litchi butterfly"],
        "host_parts": ["果实", "果核"],
        "differential": {
            "confusable": ["荔枝蒂蛀虫", "荔枝尺蠖"],
            "distinguishing": [
                "蛀孔较蒂蛀虫大，孔口有粗粒虫粪",
                "幼虫体色偏绿，蛀入果内取食果核和果肉",
                "蒂蛀虫蛀孔针尖状、虫粪细",
                "尺蠖取食叶片造成缺刻，不蛀果",
            ],
        },
        "non_chemical": [
            "及时捡拾落果并深埋或销毁",
            "果穗套袋保护",
            "人工捕杀成虫和幼虫",
        ],
        "peak_months": ["5月", "6月", "7月"],
        "monitoring": "果实膨大期检查果面是否有较大蛀孔和粗粒虫粪，注意果蒂附近；发现落果及时剖检。",
        "biological": [
            "保护寄生蜂等天敌",
            "成虫期悬挂性诱剂辅助监测",
        ],
    },
    "荔枝酸腐病": {
        "latin": "Geotrichum candidum",
        "kind": "病害",
        "risk": "中高",
        "symptoms": "多发生于近成熟至采后果实，果皮出现褐色水渍状斑并迅速软化，表面长出白色粉状霉层，伴有明显酸臭味，病果易流汁。",
        "timing": "果实转色期至采后贮运期，高温高湿、机械伤或果蒂带菌时易发；采前 1-2 周与采后预冷是防控重点。",
        "notes": "采前用药难以根除，关键在减少机械伤、采后及时预冷与单果包装；病果应及时剔除，避免与健康果混装堆沤。",
        "aliases": ["酸腐病", "荔枝酸腐", "sour rot", "geotrichum rot"],
        "host_parts": ["果实", "果蒂"],
        "differential": {
            "confusable": ["荔枝炭疽病", "荔枝霜疫霉病"],
            "distinguishing": [
                "病部软化流汁、有酸臭味，表面白色粉状霉层",
                "炭疽病为褐色凹陷病斑、边缘晕圈、后期生小黑点，不流汁、无明显酸臭",
                "霜疫霉病多从果蒂发生、褐色水渍状并生白色霜状霉，多见于采前高湿期",
            ],
        },
        "non_chemical": [
            "采果时轻拿轻放，减少机械伤",
            "采后尽快预冷并保持 2-4℃ 冷链",
            "及时清除病果与落果，避免与健康果混装",
        ],
        "peak_months": ["6月", "7月", "8月"],
        "monitoring": "转色期至采收期检查果面是否有褐色水渍状软斑与酸味；采后贮运每 2-3 天抽样检查，发现病果立即剔除。",
        "biological": [
            "采后使用枯草芽孢杆菌等登记生防菌剂处理果面",
            "保持包装场所清洁干燥，降低病原基数",
        ],
    },
    "荔枝龟背天牛": {
        "latin": "Aristobia testudo",
        "kind": "虫害",
        "risk": "中高",
        "symptoms": "幼虫蛀食枝干皮层与木质部，枝干表面出现排粪孔和木屑状虫粪，受害枝梢枯死、遇风易折；成虫啃食嫩梢和树皮。",
        "timing": "5-7 月成虫羽化产卵期与幼虫孵化期是防治窗口，重点检查主枝和多年生枝。",
        "notes": "以人工捕杀成虫、钩杀蛀道幼虫、剪除虫枝为主；化学喷雾难以到达蛀道，不建议盲目全园喷药。",
        "aliases": ["天牛", "龟背天牛", "荔枝天牛", "litchi longhorn beetle"],
        "host_parts": ["枝干", "枝条", "嫩梢"],
        "differential": {
            "confusable": ["荔枝小灰蝶"],
            "distinguishing": [
                "蛀孔较大且位于枝干，孔口有木屑状粗虫粪",
                "小灰蝶幼虫蛀食果实，虫粪细小，不危害枝干",
                "受害枝常先出现局部枯梢，剖开蛀道可见幼虫",
            ],
        },
        "non_chemical": [
            "成虫盛发期人工捕杀",
            "用铁丝钩杀蛀道内幼虫",
            "剪除并烧毁被害枯枝",
            "树干涂白减少成虫产卵",
        ],
        "peak_months": ["5月", "6月", "7月"],
        "monitoring": "5-7 月检查枝干是否有排粪孔、木屑状虫粪与流胶，重点查看主枝分叉处和多年生枝；发现枯梢及时剖检。",
        "biological": [
            "保护寄生蜂、啄木鸟等天敌",
            "成虫期悬挂诱虫灯诱杀",
        ],
    },
    "荔枝吸果夜蛾": {
        "latin": "Eudocima spp.",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "成虫夜间刺吸近成熟果实汁液，果面留下针孔状刺吸痕与褐色晕斑，随后软化腐烂落果，常继发酸腐病。",
        "timing": "果实转色至成熟期（6-8 月）夜间为害，靠近山林、杂草多的果园发生更重。",
        "notes": "以灯光诱杀、糖醋液诱杀、果实套袋和清除周边寄主为主；化学防治效果有限，临近采收不宜喷药。",
        "aliases": ["吸果夜蛾", "嘴壶夜蛾", "eudocima", "fruit-piercing moth"],
        "host_parts": ["果实", "果面"],
        "differential": {
            "confusable": ["荔枝蒂蛀虫", "荔枝酸腐病"],
            "distinguishing": [
                "刺吸孔极小、周围有褐色晕斑，无虫粪，不同于蒂蛀虫的蛀孔与虫粪",
                "受害果随后易继发酸腐，但初期只有刺吸痕",
                "成虫夜间活动，白天难以见到虫体",
            ],
        },
        "non_chemical": [
            "果实转色期套袋保护",
            "果园悬挂诱虫灯或糖醋液诱杀成虫",
            "清除果园周边木防己等寄主植物",
        ],
        "peak_months": ["6月", "7月", "8月"],
        "monitoring": "转色期起每晚检查树冠外围果实是否有新刺吸孔与褐色斑点，清晨统计落地果数量；靠近山林地块重点监测。",
        "biological": [
            "保护蜘蛛、鸟类等自然天敌",
            "果园生草为天敌提供栖息地",
        ],
    },
    "荔枝蚜虫": {
        "latin": "Aphididae spp.",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "群集嫩梢、花穗和叶背刺吸汁液，嫩梢卷曲、生长受抑，分泌蜜露诱发起煤烟病并招致蚂蚁。",
        "timing": "春梢、花穗期（3-5 月）虫口上升快，新梢抽发期是防治关键。",
        "notes": "天敌种类多，优先保护瓢虫、草蛉；虫口低时不必用药，避免杀伤天敌导致反弹。",
        "aliases": ["蚜虫", "腻虫", "aphid", "荔枝蚜"],
        "host_parts": ["嫩梢", "花穗", "叶背"],
        "differential": {
            "confusable": ["荔枝木虱", "荔枝煤烟病"],
            "distinguishing": [
                "蚜虫虫体柔软、群集，多集中在嫩梢与花穗，蜜露黏手",
                "木虱成虫善跳、若虫多在嫩芽缝隙，蜜露较少",
                "煤烟病是蜜露诱发的黑色霉层，是蚜虫、木虱为害的结果而非虫体",
            ],
        },
        "non_chemical": [
            "保护瓢虫、草蛉等天敌",
            "剪除虫口密集的嫩梢",
            "悬挂黄色粘虫板诱杀有翅蚜",
        ],
        "peak_months": ["3月", "4月", "5月"],
        "monitoring": "新梢抽发期每 3-5 天检查嫩梢、花穗上的蚜群与蜜露；有蚜梢率达 10%-15% 时考虑挑治，不必全园普防。",
        "biological": [
            "保护瓢虫、草蛉、蚜茧蜂等天敌",
            "必要时人工释放异色瓢虫",
        ],
    },
    "荔枝蓟马": {
        "latin": "Thysanoptera spp.",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "成虫、若虫锉吸嫩梢、花器和幼果，叶片出现银白色锉伤斑，花器易脱落，幼果果面粗糙并生锈斑，严重时落果。",
        "timing": "花穗期至幼果期（3-5 月）为防治关键，花期用药需避开授粉时段。",
        "notes": "蓟马个体小、隐蔽，需在清晨或傍晚检查花穗内部；蓝色粘虫板可用于监测与诱杀。",
        "aliases": ["蓟马", "thrips", "荔枝蓟马"],
        "host_parts": ["嫩梢", "花器", "幼果", "叶背"],
        "differential": {
            "confusable": ["荔枝瘿螨", "荔枝木虱"],
            "distinguishing": [
                "蓟马锉伤呈银白色条斑，果面有锈斑，镜检可见细长虫体",
                "瘿螨为害形成毛毡状虫瘿，叶片畸形卷曲",
                "木虱若虫分泌白色蜡丝，多藏于新梢缝隙",
            ],
        },
        "non_chemical": [
            "花期悬挂蓝色粘虫板监测与诱杀",
            "保护和释放捕食螨、小花蝽等天敌",
            "清除果园杂草等寄主",
        ],
        "peak_months": ["3月", "4月", "5月"],
        "monitoring": "花穗期每 3 天检查一次花器与幼果，抖花穗于白纸上计数；蓝色粘虫板每 5-7 天查看虫量变化。",
        "biological": [
            "保护小花蝽、捕食螨等天敌",
            "使用球孢白僵菌等登记生防制剂",
        ],
    },
    "荔枝金龟子": {
        "latin": "Scarabaeidae spp.",
        "kind": "虫害",
        "risk": "中",
        "symptoms": "成虫夜间啃食嫩叶、花穗和幼果，叶片呈不规则缺刻，严重时仅剩叶脉；幼虫在土中取食根系。",
        "timing": "4-6 月成虫出土盛期，雨后傍晚活动最盛。",
        "notes": "成虫有趋光性，可灯光诱杀；树下撒施白僵菌或冬季深耕翻土可减少幼虫基数。",
        "aliases": ["金龟子", "铜绿金龟子", "scarab", "chafer"],
        "host_parts": ["嫩叶", "花穗", "幼果", "根系"],
        "differential": {
            "confusable": ["荔枝尺蠖", "荔枝小灰蝶"],
            "distinguishing": [
                "金龟子啃食造成不规则缺刻与孔洞，成虫夜间活动",
                "尺蠖幼虫蚕食叶片、常留主脉，可见幼虫与虫粪",
                "小灰蝶幼虫蛀果，不啃食叶片",
            ],
        },
        "non_chemical": [
            "傍晚人工捕杀成虫",
            "悬挂诱虫灯诱杀",
            "冬季深耕翻土，破坏幼虫越冬场所",
            "树下撒施白僵菌或绿僵菌",
        ],
        "peak_months": ["4月", "5月", "6月"],
        "monitoring": "4-6 月雨后傍晚巡视树冠，观察叶片缺刻与成虫活动；树下检查土壤中幼虫密度。",
        "biological": [
            "白僵菌、绿僵菌土壤处理",
            "保护鸟类、寄生蜂等天敌",
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
        "peak_months": [],
        "monitoring": "保持常规巡检频次，重点观察叶色、叶背和新梢是否出现新的病斑、虫孔或霉层。",
        "biological": [],
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
        "peak_months": [],
        "monitoring": "保持常规巡检频次，采收前重点检查果蒂与果面，发现异常及时拍照记录。",
        "biological": [],
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
        "peak_months": [],
        "monitoring": "重新拍摄清晰特写（自然光、叶背或果面），或请农技人员现场诊断。",
        "biological": [],
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
    "荔枝炭疽病", "荔枝木虱", "荔枝介壳虫", "荔枝小灰蝶",
    "荔枝煤烟病", "健康叶片", "健康果实",
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
        "peak_months": list(info.get("peak_months") or []),
        "monitoring": str(info.get("monitoring") or ""),
        "biological": list(info.get("biological") or []),
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
    "peak_months", "monitoring",
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

        peak = info.get("peak_months") or []
        if not _is_str_list(peak):
            problems.append(f"{name}：peak_months 必须是非空字符串列表")
        elif len(set(peak)) != len(peak):
            problems.append(f"{name}：peak_months 存在重复项")
        if not isinstance(info.get("monitoring"), str):
            problems.append(f"{name}：monitoring 必须是字符串")
        bio = info.get("biological")
        if bio is not None and not _is_str_list(bio):
            problems.append(f"{name}：biological 必须是非空字符串列表")
        elif bio and len(set(bio)) != len(bio):
            problems.append(f"{name}：biological 存在重复项")

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
            if not peak:
                problems.append(f"{name}：病虫害必须填写 peak_months")
            if not str(info.get("monitoring") or "").strip():
                problems.append(f"{name}：病虫害必须填写 monitoring")

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
