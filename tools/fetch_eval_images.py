#!/usr/bin/env python
"""评测集图片抓取：按知识库类别从 iNaturalist / Bing / 360 抓图，生成 manifest 与核对页。

图片只落在本地 `data/eval/images/`（已 gitignore），用于自建小样本评测集；
图搜来源的版权不明，禁止提交仓库、禁止放进 PPT / 答辩素材。

用法：
    E:/python.exe tools/fetch_eval_images.py --dry-run          # 只看查询计划
    E:/python.exe tools/fetch_eval_images.py                    # 全部类别，每类 5 张，非目标 15 张
    E:/python.exe tools/fetch_eval_images.py --class 荔枝蝽 --per-class 6
    E:/python.exe tools/fetch_eval_images.py --source inat --class 荔枝蝽
    E:/python.exe tools/fetch_eval_images.py --prune-missing    # 删图后清理 manifest / labels

流程：抓取 → 打开 data/eval/contact-sheet.html 人工剔除错图 → --prune-missing
      → tools/prelabel.py 预标注 → 修正 label → tools/eval_vision.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

# 本机 E:\python.exe 装在盘符根目录，sys.prefix 是 "E:"（少了反斜杠），
# site-packages 因此成了盘符相对路径，会跟着 E: 盘的当前目录漂移：
# 从 E:\Temp 之类的目录启动时就 import 不到第三方包。这里按 exe 位置显式补回。
_site_packages = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                              "Lib", "site-packages")
if os.path.isdir(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)

import requests
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.rules import PEST_CLASSES, PESTS  # noqa: E402

NON_TARGET = "非目标"
ABSTAIN = "无法判断"

DEFAULT_DIR = BASE_DIR / "data" / "eval" / "images"
DEFAULT_MANIFEST = BASE_DIR / "data" / "eval" / "manifest.csv"
DEFAULT_LABELS = BASE_DIR / "data" / "eval" / "labels.csv"
SHEET_NAME = "contact-sheet.html"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
INAT_UA = "LycheeOrchardEval/1.0 (local evaluation; contact: local user)"
TIMEOUT = (10, 30)
MAX_BYTES = 12 * 1024 * 1024
MIN_SIDE = 300
MIN_AREA = 120_000
MAX_SIDE = 1400
JPEG_QUALITY = 88
AHASH_DISTANCE = 5
SEARCH_DELAY = 0.7
INAT_LICENSES = {"cc0", "cc-by", "cc-by-sa"}

BING_URL = "https://cn.bing.com/images/async"
BING_PAGE = "https://cn.bing.com/images/search"
SO_URL = "https://image.so.com/j"
SO_PAGE = "https://image.so.com/i"
SO_WEB_URL = "https://www.so.com/s"
INAT_URL = "https://api.inaturalist.org/v1/observations"

MANIFEST_FIELDS = [
    "file", "label", "query", "title", "source", "source_url", "page_url",
    "license", "attribution", "fetched_at", "width", "height", "sha256", "status",
]
LABEL_FIELDS = ["file", "label", "model_guess", "model_confidence", "model_source"]

Image.MAX_IMAGE_PIXELS = 60_000_000
RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
RESAMPLE_BILINEAR = Image.Resampling.BILINEAR


# ---------------------------------------------------------------------------
# 查询计划：类别、slug、iNat 映射、搜索词
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClassPlan:
    label: str
    slug: str
    inat_taxon: str | None
    inat_order: str | None   # first | last | None
    queries: tuple[str, ...]
    inat_params: tuple[tuple[str, str], ...] = ()  # 额外 iNat 过滤（如 life stage）


CLASS_PLANS: tuple[ClassPlan, ...] = (
    ClassPlan("荔枝蒂蛀虫", "tichengchong", None, None,
              ("荔枝蒂蛀虫", "荔枝蛀蒂虫", "荔枝果蛀虫", "荔枝蒂蛀虫 危害状",
               "荔枝蛀果虫", "Conopomorpha sinensis")),
    ClassPlan("荔枝蝽", "lichun", "Tessaratoma papillosa", "first",
              ("荔枝蝽", "荔枝椿象", "荔蝽", "荔枝蝽 若虫", "荔枝蝽 卵",
               "Tessaratoma papillosa")),
    ClassPlan("荔枝霜疫霉病", "shuangyimeibing", None, None,
              ("荔枝霜疫霉病", "荔枝霜霉病", "荔枝霜疫病", "荔枝霜疫霉病 果实",
               "荔枝霜疫霉病 叶片", "litchi downy blight")),
    ClassPlan("荔枝炭疽病", "tanjubing", "Colletotrichum gloeosporioides", "last",
              ("荔枝炭疽病", "荔枝炭疽病 叶片", "荔枝炭疽病 果实", "荔枝炭疽 病斑",
               "荔枝炭疽病 症状", "litchi anthracnose")),
    ClassPlan("荔枝瘿螨", "yingman", "Aceria litchii", "first",
              ("荔枝瘿螨", "荔枝毛毡病", "荔枝叶瘿螨", "荔枝瘿螨 叶背",
               "荔枝毛毡病 症状", "litchi erinose mite")),
    ClassPlan("荔枝尺蠖", "chihuo", "Geometridae", "first",
              ("荔枝尺蠖", "荔枝造桥虫", "尺蠖 荔枝", "荔枝尺蠖 幼虫",
               "荔枝尺蠖 危害", "litchi looper"),
              (("term_id", "1"), ("term_value_id", "4"))),  # 只看幼虫
    ClassPlan("荔枝煤烟病", "meiyanbing", "Capnodium", "first",
              ("荔枝煤烟病", "荔枝煤污病", "煤烟病 荔枝", "荔枝煤烟病 叶片",
               "荔枝煤烟病 果实", "litchi sooty mold")),
    ClassPlan("荔枝藻斑病", "zaobanbing", "Cephaleuros", "first",
              ("荔枝藻斑病", "藻斑病 荔枝", "荔枝绿藻病", "藻斑病 叶片",
               "荔枝藻斑病 症状", "litchi algal leaf spot")),
    ClassPlan("荔枝叶瘿蚊", "yeyingwen", None, None,
              ("荔枝叶瘿蚊", "荔枝瘿蚊", "荔枝叶瘿蚊 虫瘿", "荔枝叶瘿蚊 嫩叶",
               "荔枝叶瘿蚊 危害", "litchi leaf gall midge")),
    ClassPlan("荔枝木虱", "mushi", "Psyllidae", "first",
              ("荔枝木虱", "荔枝木虱 若虫", "木虱 荔枝", "荔枝木虱 危害",
               "荔枝木虱 嫩梢", "litchi psyllid")),
    ClassPlan("荔枝介壳虫", "jiekechong", "Coccus hesperidum", "last",
              ("荔枝介壳虫", "荔枝蚧壳虫", "介壳虫 荔枝", "荔枝介壳虫 枝干",
               "荔枝介壳虫 果实", "litchi scale insect")),
    ClassPlan("荔枝小灰蝶", "xiaohuidie", "Deudorix epijarbas", "first",
              ("荔枝小灰蝶", "小灰蝶 荔枝", "荔枝小灰蝶 幼虫", "荔枝小灰蝶 蛀果",
               "荔枝小灰蝶 危害", "Deudorix epijarbas")),
    ClassPlan("荔枝酸腐病", "suanfubing", None, None,
              ("荔枝酸腐病", "荔枝酸腐", "荔枝酸腐病 果实", "酸腐病 荔枝",
               "荔枝酸腐病 症状", "litchi sour rot")),
    ClassPlan("荔枝龟背天牛", "guibeitianniu", "Aristobia testudo", "first",
              ("荔枝龟背天牛", "荔枝天牛", "龟背天牛", "天牛 荔枝",
               "荔枝龟背天牛 危害", "Aristobia testudo")),
    ClassPlan("荔枝吸果夜蛾", "xiguoyee", "Eudocima phalonia", "first",
              ("荔枝吸果夜蛾", "吸果夜蛾", "嘴壶夜蛾", "荔枝吸果夜蛾 危害",
               "吸果夜蛾 果实", "Eudocima phalonia")),
    ClassPlan("荔枝蚜虫", "yachong", "Aphis aurantii", "first",
              ("荔枝蚜虫", "蚜虫 荔枝", "荔枝蚜虫 嫩梢", "荔枝蚜虫 蜜露",
               "荔枝蚜虫 危害", "litchi aphid")),
    ClassPlan("荔枝蓟马", "jimaa", "Scirtothrips dorsalis", "first",
              ("荔枝蓟马", "蓟马 荔枝", "荔枝蓟马 花穗", "荔枝蓟马 危害",
               "荔枝蓟马 幼果", "litchi thrips")),
    ClassPlan("荔枝金龟子", "jinguizi", None, None,
              ("荔枝金龟子", "金龟子 荔枝", "铜绿金龟子", "金龟子 成虫",
               "金龟子 危害 荔枝", "litchi scarab")),
    ClassPlan("健康叶片", "jiankangyepian", "Litchi chinensis", "last",
              ("荔枝 健康叶片", "荔枝 正常叶片", "荔枝叶 绿色 特写", "荔枝 叶片 近景",
               "healthy litchi leaf", "Litchi chinensis leaf")),
    ClassPlan("健康果实", "jiankangguoshi", "Litchi chinensis", "last",
              ("荔枝 健康果实", "荔枝 正常果实", "新鲜荔枝 果实 特写", "荔枝 果皮 近景",
               "healthy litchi fruit", "Litchi chinensis fruit")),
    ClassPlan(NON_TARGET, "non_target", None, None,
              ("办公桌 桌面", "人的手 特写", "天空 云朵", "白色墙面", "模糊照片",
               "过暗照片", "其他植物 叶片", "草地 近景", "室内 盆栽", "马路 路面",
               "手机 屏幕", "水果拼盘", "树叶 阴影", "塑料瓶", "纸张 桌面")),
)

PLAN_BY_LABEL = {plan.label: plan for plan in CLASS_PLANS}
EXPECTED_LABELS = set(PEST_CLASSES) | {"健康叶片", "健康果实"}


def _build_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for label, meta in PESTS.items():
        if label == ABSTAIN:
            continue
        for alias in meta.get("aliases") or []:
            aliases[str(alias).strip().lower()] = label
    for label in PESTS:
        if label != ABSTAIN:
            aliases[label.lower()] = label
    aliases[NON_TARGET] = NON_TARGET
    return aliases


ALIASES = _build_aliases()


def validate_plan() -> None:
    labels = {plan.label for plan in CLASS_PLANS}
    missing = EXPECTED_LABELS - labels
    if missing:
        raise AssertionError(f"查询计划缺少类别：{sorted(missing)}")
    slugs = [plan.slug for plan in CLASS_PLANS]
    if len(slugs) != len(set(slugs)):
        raise AssertionError("查询计划存在重复 slug")
    for plan in CLASS_PLANS:
        if not re.fullmatch(r"[a-z0-9_]+", plan.slug):
            raise AssertionError(f"slug 不是 ASCII：{plan.slug}")
        if plan.inat_order not in (None, "first", "last"):
            raise AssertionError(f"iNat 顺序非法：{plan.inat_order}")


validate_plan()


def resolve_label(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    raise KeyError(f"未知类别：{raw}（运行 --dry-run 可查看全部类别）")


def target_for(plan: ClassPlan, args: argparse.Namespace) -> int:
    if plan.label == NON_TARGET:
        if args.non_target is not None:
            return args.non_target
        return args.per_class if args.classes else 15
    return args.per_class


HOST_WORDS = {"荔枝", "litchi", "lychee"}


def plan_keywords(plan: ClassPlan) -> tuple[str, ...]:
    """标题必须命中具体的病虫害词；只出现「荔枝」不算相关（会混进新闻和商品图）。"""
    if plan.label == NON_TARGET:
        return ()
    if plan.label == "健康叶片":
        return ("荔枝叶", "叶片", "叶子", "leaf", "foliage")
    if plan.label == "健康果实":
        return ("荔枝", "litchi", "lychee", "果实", "fruit")
    meta = PESTS.get(plan.label, {})
    words = [plan.label, *(meta.get("aliases") or [])]
    cleaned = {str(word).strip().lower() for word in words if len(str(word).strip()) >= 2}
    cleaned -= HOST_WORDS
    if not cleaned:  # 理论上不会发生，保底避免整类被过滤空
        cleaned = {plan.label.lower()}
    return tuple(sorted(cleaned))


def tiers_for(plan: ClassPlan, source: str) -> tuple[str, ...]:
    if source in ("bing", "so", "so_web", "inat"):
        return (source,)
    order: list[str] = []
    if plan.inat_taxon and plan.inat_order == "first":
        order.append("inat")
    order.extend(("bing", "so_web", "so"))
    if plan.inat_taxon and plan.inat_order == "last":
        order.append("inat")
    return tuple(order)


# ---------------------------------------------------------------------------
# 搜索结果解析（纯函数，测试不联网）
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    url: str
    query: str
    source: str
    page_url: str = ""
    license: str = "unknown"
    attribution: str = ""
    title: str = ""
    width: int | None = None
    height: int | None = None
    fallbacks: tuple[str, ...] = ()


def _clean_url(raw) -> str:
    if not raw:
        return ""
    url = html.unescape(str(raw)).replace("\\/", "/").replace("\\u0026", "&").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _matches_keywords(keywords: tuple[str, ...], *values: str) -> bool:
    if not keywords:
        return True
    haystack = " ".join(value for value in values if value).lower()
    return any(word in haystack for word in keywords)


def parse_bing_html(text: str, query: str, page_url: str,
                    keywords: tuple[str, ...] = ()) -> list[Candidate]:
    if not text:
        return []
    blocks = re.findall(r'm="(\{&quot;.*?\})"', text)
    if not blocks:
        blocks = re.findall(r"""m='(\{"murl".*?\})'""", text)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for block in blocks:
        try:
            data = json.loads(html.unescape(block))
        except (TypeError, ValueError):
            continue
        url = _clean_url(data.get("murl"))
        if not url or url in seen:
            continue
        title = str(data.get("t") or "").strip()
        purl = _clean_url(data.get("purl"))
        if not _matches_keywords(keywords, title, purl, url):
            continue
        thumbnail = _clean_url(data.get("turl"))
        fallbacks = (thumbnail,) if thumbnail and thumbnail != url else ()
        seen.add(url)
        candidates.append(Candidate(
            url=url, query=query, source="bing", page_url=purl or page_url,
            license="search-only", title=title, fallbacks=fallbacks,
        ))
    if candidates:
        return candidates

    # 兜底：页面结构变化时退回只抓 murl；没有标题就无法判断相关性，宁可不用
    if keywords:
        return []
    decoded = html.unescape(text).replace("\\/", "/").replace("\\u0026", "&")
    urls = [_clean_url(url) for url in re.findall(r'"murl"\s*:\s*"([^"]+)"', decoded)]
    return [Candidate(url=url, query=query, source="bing", page_url=page_url,
                      license="search-only")
            for url in _dedupe_urls(urls)]


def parse_so_web_html(text: str, query: str) -> list[Candidate]:
    """360 网页搜索顶部的图片包：<a data-original="原图" data-url="缩略图">。

    图片包条目没有标题，只有原图地址；相关性由具体查询词保证，仍需人工核对。
    """
    if not text:
        return []
    out: list[Candidate] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a\b[^>]*\bdata-original="([^"]+)"[^>]*>', text):
        tag = match.group(0)
        url = _clean_url(match.group(1))
        if not url or url in seen:
            continue
        seen.add(url)
        href = re.search(r'\bhref="([^"]+)"', tag)
        page_url = _clean_url(html.unescape(href.group(1))) if href else ""
        thumb = re.search(r'\bdata-url="([^"]+)"', tag)
        thumb_url = _clean_url(thumb.group(1)) if thumb else ""
        out.append(Candidate(
            url=url, query=query, source="360-web", page_url=page_url,
            license="search-only", attribution=urlparse(url).netloc,
            title=query,
            fallbacks=(thumb_url,) if thumb_url and thumb_url != url else (),
        ))
    return out


def parse_so_payload(payload: dict, query: str,
                     keywords: tuple[str, ...] = ()) -> list[Candidate]:
    out: list[Candidate] = []
    for item in (payload or {}).get("list") or []:
        urls = []
        for key in ("downurl_true", "downurl", "img", "thumb"):
            url = _clean_url(item.get(key))
            if url and url not in urls:
                urls.append(url)
        if not urls:
            continue
        raw_src = str(item.get("src") or "").strip()
        src_url = _clean_url(raw_src)
        title = str(item.get("title") or item.get("litetitle") or "").strip()
        if not _matches_keywords(keywords, title, raw_src, urls[0]):
            continue
        page_url = _clean_url(item.get("link")) or src_url
        if not page_url:
            page_url = f"{SO_PAGE}?q={quote(query)}"
        attribution = str(item.get("copyright_owner") or "").strip()
        if not attribution:
            attribution = urlparse(src_url).netloc if src_url else raw_src
        width = item.get("width")
        height = item.get("height")
        out.append(Candidate(
            url=urls[0], query=query, source="360", page_url=page_url,
            license="search-only", attribution=attribution, title=title,
            width=int(width) if str(width or "").isdigit() else None,
            height=int(height) if str(height or "").isdigit() else None,
            fallbacks=tuple(urls[1:]),
        ))
    return out


def _inat_size_url(url: str, size: str) -> str:
    pattern = r"/(?:square|thumb|small|medium|large|original)\.(jpe?g|png)$"
    if re.search(pattern, url, re.IGNORECASE):
        return re.sub(pattern, f"/{size}.\\1", url, flags=re.IGNORECASE)
    return url


def parse_inat_payload(payload: dict, taxon_name: str) -> list[Candidate]:
    out: list[Candidate] = []
    for obs in (payload or {}).get("results") or []:
        obs_id = obs.get("id")
        if not obs_id:
            continue
        page_url = f"https://www.inaturalist.org/observations/{obs_id}"
        login = ((obs.get("user") or {}).get("login") or "").strip()
        for photo in obs.get("photos") or []:
            license_code = (photo.get("license_code") or "").lower()
            if license_code not in INAT_LICENSES:
                continue
            url = _clean_url(photo.get("url"))
            if not url:
                continue
            large = _inat_size_url(url, "large")
            original = _inat_size_url(url, "original")
            fallbacks = (original,) if original != large else ()
            attribution = re.sub(r"<[^>]+>", "", str(photo.get("attribution") or "")).strip()
            if not attribution:
                attribution = f"iNaturalist @{login}" if login else "iNaturalist"
            dims = photo.get("original_dimensions") or {}
            width = dims.get("width")
            height = dims.get("height")
            out.append(Candidate(
                url=large, query=taxon_name, source="inat", page_url=page_url,
                license=license_code, attribution=attribution, title=taxon_name,
                width=int(width) if width else None,
                height=int(height) if height else None,
                fallbacks=fallbacks,
            ))
    return out


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    })
    return session


def polite_sleep(base: float) -> None:
    if base > 0:
        time.sleep(base + random.uniform(0, base * 0.4))


def fetch_text(session: requests.Session, url: str, params: dict) -> str | None:
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        resp.encoding = "utf-8"
        return resp.text
    except requests.RequestException:
        return None


def fetch_json(session: requests.Session, url: str, params: dict,
               headers: dict | None = None) -> dict | None:
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT, headers=headers or {})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (requests.RequestException, ValueError):
        return None


def bing_group(session: requests.Session, query: str, keywords: tuple[str, ...] = ()):
    page_url = f"{BING_PAGE}?q={quote(query)}"
    for first in (1, 36, 71):
        polite_sleep(SEARCH_DELAY)
        text = fetch_text(session, BING_URL, {
            "q": query, "first": first, "count": 35, "mkt": "zh-CN",
            "qft": "+filterui:imagesize-large+filterui:photo-photo", "adlt": "strict",
        })
        if not text:
            return
        yield from parse_bing_html(text, query, page_url, keywords)


def so_group(session: requests.Session, query: str, keywords: tuple[str, ...] = ()):
    page_url = f"{SO_PAGE}?q={quote(query)}"
    for sn in (0, 30, 60):
        polite_sleep(SEARCH_DELAY)
        payload = fetch_json(session, SO_URL, {
            "q": query, "src": "srp", "sn": sn, "pn": 30,
        })
        if not payload:
            return
        yield from parse_so_payload(payload, query, keywords)


def so_web_group(session: requests.Session, queries: tuple[str, ...]):
    """360 网页搜索的图片包；按查询词串行请求，避免一次并发太多被验证码拦截。"""
    for query in queries:
        for page in (1, 2):
            candidates: list[Candidate] = []
            for attempt in range(2):
                polite_sleep(SEARCH_DELAY)
                text = fetch_text(session, SO_WEB_URL, {"q": query, "pn": page})
                if text and ("验证" in text or "访问异常" in text):
                    if attempt == 0:
                        time.sleep(30)
                        continue
                    return  # 触发验证码，整轮停止，避免继续加重封禁
                candidates = parse_so_web_html(text, query) if text else []
                break
            if not candidates:
                break
            yield from candidates


def inat_group(session: requests.Session, taxon_name: str,
               extra: tuple[tuple[str, str], ...] = ()):
    params = {
        "taxon_name": taxon_name,
        "photos": "true",
        "photo_license": "cc0,cc-by,cc-by-sa",
        "per_page": 50,
        "order_by": "votes",
    }
    params.update(dict(extra))
    payload = fetch_json(session, INAT_URL, params, headers={"User-Agent": INAT_UA})
    if not payload:
        return
    yield from parse_inat_payload(payload, taxon_name)


def build_groups(session: requests.Session, plan: ClassPlan, tier: str):
    if tier == "inat":
        if not plan.inat_taxon:
            return []
        return [inat_group(session, plan.inat_taxon, plan.inat_params)]
    keywords = plan_keywords(plan)
    if tier == "bing":
        return [bing_group(session, query, keywords) for query in plan.queries]
    if tier == "so":
        return [so_group(session, query, keywords) for query in plan.queries]
    if tier == "so_web":
        return [so_web_group(session, plan.queries)]
    return []


def interleave(groups):
    iterators = [iter(group) for group in groups]
    while iterators:
        alive = []
        for iterator in iterators:
            try:
                yield next(iterator)
                alive.append(iterator)
            except StopIteration:
                pass
        iterators = alive


# ---------------------------------------------------------------------------
# 下载、校验、去重
# ---------------------------------------------------------------------------
@dataclass
class PreparedImage:
    jpeg: bytes
    width: int
    height: int
    sha256: str
    ahash: int


def average_hash(image: Image.Image) -> int:
    small = image.convert("L").resize((8, 8), RESAMPLE_BILINEAR)
    pixels = list(small.tobytes())
    average = sum(pixels) / len(pixels)
    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | (1 if pixel > average else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _safe_referer(referer: str) -> str:
    """Referer 里可能带中文（Bing 的 purl），HTTP 头只能放 latin-1。"""
    if not referer:
        return ""
    try:
        referer.encode("latin-1")
        return referer
    except UnicodeEncodeError:
        return requests.utils.requote_uri(referer)


def download_bytes(session: requests.Session, url: str, referer: str = "") -> bytes | None:
    referer = _safe_referer(referer)
    for attempt in range(3):
        headers = {"Referer": referer} if referer else {}
        try:
            resp = session.get(url, timeout=TIMEOUT, stream=True, headers=headers)
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        with resp:
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < 2:
                    retry_after = resp.headers.get("Retry-After", "")
                    wait = float(retry_after) if retry_after.isdigit() else 2.0 * (attempt + 1)
                    time.sleep(min(wait, 10))
                    continue
                return None
            if resp.status_code in (401, 403) and attempt == 0 and referer:
                # Referer 可能正是被拦截的原因，第二次不带 Referer 再试
                referer = ""
                continue
            if resp.status_code != 200:
                return None

            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type and not (
                content_type.startswith("image/")
                or content_type in ("application/octet-stream", "binary/octet-stream")
            ):
                return None
            length = resp.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_BYTES:
                return None

            buffer = bytearray()
            for chunk in resp.iter_content(64 * 1024):
                buffer.extend(chunk)
                if len(buffer) > MAX_BYTES:
                    return None
            return bytes(buffer) if buffer else None
    return None


def prepare_image(data: bytes) -> PreparedImage | None:
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            else:
                image = image.convert("RGB")

            width, height = image.size
            if min(width, height) < MIN_SIDE or width * height < MIN_AREA:
                return None
            if max(width, height) > MAX_SIDE:
                image.thumbnail((MAX_SIDE, MAX_SIDE), RESAMPLE_LANCZOS)

            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            jpeg = buffer.getvalue()
            return PreparedImage(
                jpeg=jpeg, width=image.width, height=image.height,
                sha256=hashlib.sha256(jpeg).hexdigest(), ahash=average_hash(image),
            )
    except Exception:
        return None


def fetch_prepared(session: requests.Session, candidate: Candidate
                   ) -> tuple[PreparedImage, str] | None:
    for url in (candidate.url,) + tuple(candidate.fallbacks):
        data = download_bytes(session, url, referer=candidate.page_url)
        if not data:
            continue
        prepared = prepare_image(data)
        if prepared:
            return prepared, url
    return None


class DedupeState:
    def __init__(self) -> None:
        self.urls: set[str] = set()
        self.shas: set[str] = set()
        self.hashes: list[int] = []

    def seen_url(self, url: str) -> bool:
        return url in self.urls

    def seen_image(self, prepared: PreparedImage) -> bool:
        if prepared.sha256 in self.shas:
            return True
        return any(hamming(prepared.ahash, other) <= AHASH_DISTANCE for other in self.hashes)

    def add(self, url: str, prepared: PreparedImage) -> None:
        self.urls.add(url)
        self.shas.add(prepared.sha256)
        self.hashes.append(prepared.ahash)

    def seed(self, rows: dict[str, dict], image_dir: Path) -> None:
        for filename, row in rows.items():
            path = image_dir / filename
            if not path.exists():
                continue
            sha = (row.get("sha256") or "").strip()
            if sha:
                self.shas.add(sha)
            try:
                with Image.open(path) as image:
                    self.hashes.append(average_hash(image.convert("RGB")))
            except Exception:
                continue


def natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name)]


def next_filename(image_dir: Path, slug: str, taken: set[str]) -> str:
    existing = {path.name for path in image_dir.glob(f"{slug}_*.jpg")} | set(taken)
    index = 1
    while f"{slug}_{index:02d}.jpg" in existing:
        index += 1
    return f"{slug}_{index:02d}.jpg"


def atomic_write_jpeg(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.part")
    temp.write_bytes(data)
    os.replace(temp, path)


# ---------------------------------------------------------------------------
# manifest / labels / 核对页
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            filename = (row.get("file") or "").strip()
            if filename:
                row["file"] = filename
                rows[filename] = row
    return rows


def save_manifest(path: Path, rows: dict[str, dict]) -> None:
    order = {plan.label: index for index, plan in enumerate(CLASS_PLANS)}
    ordered = sorted(rows.values(),
                     key=lambda row: (order.get(row.get("label"), len(order)),
                                      natural_key(row.get("file", ""))))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in ordered:
            writer.writerow({key: row.get(key, "") for key in MANIFEST_FIELDS})


def prune_manifest(rows: dict[str, dict], image_dir: Path) -> tuple[dict[str, dict], list[str]]:
    kept: dict[str, dict] = {}
    removed: list[str] = []
    for filename, row in rows.items():
        if (image_dir / filename).exists():
            kept[filename] = row
        else:
            removed.append(filename)
    return kept, removed


def load_label_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if (row.get("file") or "").strip()]


def save_label_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in LABEL_FIELDS})


def prune_labels_missing(path: Path, image_dir: Path) -> list[str]:
    rows = load_label_rows(path)
    if not rows:
        return []
    kept, removed = [], []
    for row in rows:
        filename = (row.get("file") or "").strip()
        if (image_dir / filename).exists():
            kept.append(row)
        else:
            removed.append(filename)
    if removed:
        save_label_rows(path, kept)
    return removed


def prefill_labels(path: Path, rows: dict[str, dict], image_dir: Path) -> int:
    existing = load_label_rows(path)
    by_file = {(row.get("file") or "").strip(): row for row in existing}
    changed = 0
    for filename, row in rows.items():
        if not (image_dir / filename).exists():
            continue
        current = by_file.get(filename)
        if current is None:
            current = {"file": filename, "label": "", "model_guess": "",
                       "model_confidence": "", "model_source": ""}
            by_file[filename] = current
            existing.append(current)
        if not (current.get("label") or "").strip():
            current["label"] = row.get("label", "")
            changed += 1
    if changed:
        save_label_rows(path, existing)
    return changed


def _escape(value) -> str:
    return html.escape(str(value or ""))


def render_contact_sheet(rows: dict[str, dict], image_dir: Path, out_path: Path) -> None:
    groups: dict[str, list[dict]] = {}
    for row in rows.values():
        if (image_dir / row.get("file", "")).exists():
            groups.setdefault(row.get("label", ""), []).append(row)
    order = {plan.label: index for index, plan in enumerate(CLASS_PLANS)}

    def sort_key(label: str):
        return (order.get(label, len(order)), label)

    total = sum(len(items) for items in groups.values())
    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        "<title>评测集核对</title>",
        "<style>",
        "body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:24px;background:#f7f7f8;color:#222}",
        "h1{font-size:20px;margin:0 0 6px}h2{font-size:15px;margin:28px 0 10px}",
        ".muted{color:#777;font-weight:400;font-size:12px}",
        ".notice{background:#fff7e0;border:1px solid #f0d48a;padding:10px 14px;border-radius:8px;font-size:13px}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}",
        ".card{margin:0;background:#fff;border:1px solid #e3e3e6;border-radius:8px;overflow:hidden}",
        ".card img{display:block;width:100%;height:150px;object-fit:cover;background:#eee}",
        ".card figcaption{padding:8px 10px;font-size:12px;line-height:1.5;word-break:break-all}",
        "code{background:#eee;padding:1px 4px;border-radius:3px}",
        "</style></head><body>",
        "<h1>评测集核对</h1>",
        f'<p class="muted">共 {total} 张。逐张确认类别；删掉不符、重复、带水印的图片，'
        "然后运行 <code>--prune-missing</code>，再执行 <code>tools/prelabel.py</code>。</p>",
        '<p class="notice">图搜来源的图片版权不明，仅用于本地评测，不要提交仓库或放进 PPT。</p>',
    ]
    for label in sorted(groups, key=sort_key):
        items = sorted(groups[label], key=lambda row: natural_key(row.get("file", "")))
        parts.append(f"<h2>{_escape(label)} <span class='muted'>({len(items)} 张)</span></h2>")
        parts.append("<div class='grid'>")
        for row in items:
            filename = _escape(row.get("file", ""))
            query = _escape(row.get("query", ""))
            title = _escape(row.get("title", ""))
            source = _escape(row.get("source", ""))
            license_code = _escape(row.get("license", ""))
            attribution = _escape(row.get("attribution", ""))
            parts.append(
                "<figure class='card'>"
                f"<img loading='lazy' src='images/{filename}' alt='{filename}'>"
                f"<figcaption><b>{filename}</b><br><span>{query}</span>"
                + (f"<br><span>{title}</span>" if title else "")
                + f"<br><span class='muted'>{source} · {license_code}</span>"
                + (f"<br><span class='muted'>{attribution}</span>" if attribution else "")
                + "</figcaption></figure>"
            )
        parts.append("</div>")
    parts.append("</body></html>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def select_plans(raw_classes: list[str] | None) -> list[ClassPlan]:
    if not raw_classes:
        return list(CLASS_PLANS)
    selected: list[ClassPlan] = []
    for raw in raw_classes:
        plan = PLAN_BY_LABEL[resolve_label(raw)]
        if plan not in selected:
            selected.append(plan)
    return selected


def run_fetch(session: requests.Session, plans: list[ClassPlan], rows: dict[str, dict],
              image_dir: Path, manifest_path: Path,
              args: argparse.Namespace) -> dict[str, int]:
    dedupe = DedupeState()
    dedupe.seed(rows, image_dir)
    totals = {"added": 0, "duplicate": 0, "failed": 0}

    for plan in plans:
        target = target_for(plan, args)
        if target <= 0:
            continue

        existing = [row for row in rows.values()
                    if row.get("label") == plan.label
                    and (image_dir / row.get("file", "")).exists()]

        if args.overwrite:
            for filename, row in list(rows.items()):
                if row.get("label") != plan.label:
                    continue
                try:
                    (image_dir / filename).unlink()
                except OSError:
                    pass
                rows.pop(filename, None)
            existing = []
            dedupe = DedupeState()
            dedupe.seed(rows, image_dir)

        need = target - len(existing)
        if need <= 0:
            print(f"[{plan.label}] 已有 {len(existing)} 张，跳过")
            continue
        print(f"[{plan.label}] 目标 {target} 张，已有 {len(existing)}，需补 {need} 张", flush=True)

        added = 0
        for tier in tiers_for(plan, args.source):
            if added >= need:
                break
            groups = build_groups(session, plan, tier)
            if not groups:
                if args.source == "inat":
                    print(f"  ! {plan.label} 没有 iNaturalist 映射，跳过")
                continue
            print(f"  · 来源 {tier}", flush=True)
            for candidate in interleave(groups):
                if added >= need:
                    break
                if dedupe.seen_url(candidate.url):
                    continue
                polite_sleep(args.delay)
                fetched = fetch_prepared(session, candidate)
                if not fetched:
                    totals["failed"] += 1
                    continue
                prepared, used_url = fetched
                if dedupe.seen_image(prepared):
                    totals["duplicate"] += 1
                    continue

                filename = next_filename(image_dir, plan.slug, set(rows))
                atomic_write_jpeg(image_dir / filename, prepared.jpeg)
                rows[filename] = {
                    "file": filename,
                    "label": plan.label,
                    "query": candidate.query,
                    "title": candidate.title,
                    "source": candidate.source,
                    "source_url": used_url,
                    "page_url": candidate.page_url,
                    "license": candidate.license,
                    "attribution": candidate.attribution,
                    "fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "width": prepared.width,
                    "height": prepared.height,
                    "sha256": prepared.sha256,
                    "status": "ok",
                }
                dedupe.add(used_url, prepared)
                added += 1
                totals["added"] += 1
                print(f"    [{added}/{need}] {filename} ← {candidate.source} · "
                      f"{candidate.query} ({prepared.width}×{prepared.height})", flush=True)
        save_manifest(manifest_path, rows)
        if added < need:
            print(f"  ! {plan.label} 只补到 {added}/{need} 张，可重跑或换查询词", flush=True)
    return totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="抓取识别评测集图片（iNaturalist / Bing / 360），仅本地使用")
    parser.add_argument("--class", dest="classes", action="append", metavar="类别",
                        help="只抓指定类别，可重复；支持别名")
    parser.add_argument("--per-class", type=int, default=5, help="每个类别抓几张（默认 5）")
    parser.add_argument("--non-target", type=int, default=None,
                        help="非目标图数量（默认 15；指定 --class 时随 per-class）")
    parser.add_argument("--source", choices=("auto", "bing", "so", "so_web", "inat"),
                        default="auto")
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--overwrite", action="store_true", help="重抓选中类别（删除已有图片）")
    parser.add_argument("--prune-missing", action="store_true",
                        help="清理图片已删除的 manifest / labels 行；单独使用时清理后退出")
    parser.add_argument("--prefill-labels", action=argparse.BooleanOptionalAction, default=True,
                        help="把类别预填进 labels.csv（默认开）")
    parser.add_argument("--sheet", action=argparse.BooleanOptionalAction, default=True,
                        help="生成 contact-sheet.html（默认开）")
    parser.add_argument("--dry-run", action="store_true", help="只打印查询计划，不写文件")
    parser.add_argument("--delay", type=float, default=1.0, help="每张图片下载前的间隔秒数")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plans = select_plans(args.classes)
    except KeyError as exc:
        print(exc.args[0])
        return 2

    image_dir = Path(args.dir)
    manifest_path = Path(args.manifest)
    labels_path = Path(args.labels)

    if args.dry_run:
        for plan in plans:
            print(f"[{plan.label}] slug={plan.slug} 目标={target_for(plan, args)} "
                  f"来源={'→'.join(tiers_for(plan, args.source))} "
                  f"iNat={plan.inat_taxon or '—'} 查询={len(plan.queries)}")
            for query in plan.queries:
                print(f"    - {query}")
        return 0

    rows = load_manifest(manifest_path)

    if args.prune_missing:
        rows, removed = prune_manifest(rows, image_dir)
        if removed:
            save_manifest(manifest_path, rows)
            print(f"manifest 清理 {len(removed)} 条：{', '.join(removed[:5])}"
                  + (" ..." if len(removed) > 5 else ""))
        removed_labels = prune_labels_missing(labels_path, image_dir)
        if removed_labels:
            print(f"labels.csv 清理 {len(removed_labels)} 条")
        if not args.classes and not args.overwrite:
            if args.prefill_labels:
                prefill_labels(labels_path, rows, image_dir)
            if args.sheet:
                sheet = image_dir.parent / SHEET_NAME
                render_contact_sheet(rows, image_dir, sheet)
                print(f"核对页：{sheet}")
            return 0

    image_dir.mkdir(parents=True, exist_ok=True)
    session = new_session()
    totals = run_fetch(session, plans, rows, image_dir, manifest_path, args)
    save_manifest(manifest_path, rows)

    if args.prefill_labels:
        changed = prefill_labels(labels_path, rows, image_dir)
        if changed:
            print(f"labels.csv 预填 {changed} 条（仍需视觉核对）")
    if args.sheet:
        sheet = image_dir.parent / SHEET_NAME
        render_contact_sheet(rows, image_dir, sheet)
        print(f"核对页：{sheet}")

    print(f"完成：新增 {totals['added']} 张，判重 {totals['duplicate']} 张，"
          f"下载失败 {totals['failed']} 张")
    print("下一步：打开核对页删掉不符图片 → --prune-missing → prelabel.py → eval_vision.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
