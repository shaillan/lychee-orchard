"""天气联动：Open-Meteo 免 Key 预报 → 霜疫霉病风险。

只做一件事：把未来 3 天的降雨/湿度翻译成一条「雨前预防」提示，
供 /api/todos 使用。任何网络或解析异常都静默返回 None，绝不影响主流程。

地区可由前端设置并存入 settings 表；未设置时回退到 .env 默认值。
注意：Open-Meteo 的日级变量里没有相对湿度，湿度要用 hourly 拉取后按天聚合。
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any

from . import config
from .db import get_conn

_RISK_TTL = 30 * 60      # 成功结果缓存 30 分钟
_FAIL_TTL = 5 * 60       # 失败结果缓存 5 分钟，断网时避免每次请求都等超时
_CACHE: dict[str, Any] = {"key": None, "expires": 0.0, "risk": None, "loaded": False}
_LOCK = threading.Lock()

_REGION_KEY = "weather_region"
_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_GEOCODE_TIMEOUT = 8.0
_GEOCODE_ATTEMPTS = 2      # 本机实测 TLS 握手偶发超时，保存时自动再试一次


def _default_region() -> dict:
    """未在界面上设置地区时，沿用 .env 的默认位置。"""
    return {
        "name": config.WEATHER_LOCATION,
        "admin1": "",
        "lat": config.WEATHER_LAT,
        "lon": config.WEATHER_LON,
        "source": "env",
    }


def region_label(region: dict | None) -> str:
    """把「广东 + 广州」拼成展示用的「广东广州」；默认地区原样返回。"""
    region = region or {}
    name = str(region.get("name") or "").strip()
    admin1 = str(region.get("admin1") or "").strip()
    if admin1 and admin1 not in name:
        return admin1 + name
    return name


def _load_saved_region() -> dict | None:
    """读 settings 表；数据损坏或越界时当作没设置，回退 .env。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (_REGION_KEY,)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["value"])
        name = str(data.get("name") or "").strip()
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (TypeError, ValueError, KeyError):
        return None
    if not name or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return {
        "name": name,
        "admin1": str(data.get("admin1") or "").strip(),
        "lat": lat,
        "lon": lon,
        "source": "db",
    }


def get_region() -> dict:
    """当前生效地区：数据库优先，未设置时用 .env 默认值。"""
    region = _load_saved_region() or _default_region()
    region["label"] = region_label(region)
    return region


def save_region(name: str, admin1: str, lat: float, lon: float) -> dict:
    """保存地区并清空天气缓存，下一次 /api/todos 立即生效。"""
    payload = {
        "name": name,
        "admin1": admin1,
        "lat": float(lat),
        "lon": float(lon),
    }
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (_REGION_KEY, json.dumps(payload, ensure_ascii=False),
             datetime.now().isoformat(timespec="seconds")),
        )
    with _LOCK:
        _CACHE.update(key=None, expires=0.0, risk=None, loaded=False)
    region = dict(payload, source="db")
    region["label"] = region_label(region)
    return region


def geocode(name: str) -> dict | None:
    """地区名 → 经纬度（Open-Meteo 地理编码，免 Key）。

    无结果返回 None；网络/HTTP 异常向上抛，由接口转成 502。
    """
    import httpx

    last_error: Exception | None = None
    for _ in range(_GEOCODE_ATTEMPTS):
        try:
            resp = httpx.get(
                _GEOCODE_URL,
                params={"name": name, "count": 5, "language": "zh", "format": "json"},
                timeout=_GEOCODE_TIMEOUT,
            )
            resp.raise_for_status()
            results = (resp.json() or {}).get("results") or []
            break
        except httpx.TransportError as exc:  # 超时/连接失败时再试一次
            last_error = exc
    else:
        raise last_error or RuntimeError("地理编码请求失败")

    if not results:
        return None
    first = results[0]
    try:
        lat = float(first["latitude"])
        lon = float(first["longitude"])
    except (TypeError, KeyError, ValueError):
        return None
    return {
        "name": str(first.get("name") or name).strip(),
        "admin1": str(first.get("admin1") or "").strip(),
        "lat": lat,
        "lon": lon,
    }


def _pick(seq: Any, index: int):
    try:
        return seq[index]
    except (TypeError, IndexError, KeyError):
        return None


def _fetch_days(lat: float | None = None, lon: float | None = None) -> list[dict]:
    """拉未来 3 天预报，返回按天聚合的列表；失败抛异常由调用方兜底。

    lat/lon 不传时沿用 .env 默认坐标（兼容旧调用）。
    """
    import httpx

    resp = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config.WEATHER_LAT if lat is None else lat,
            "longitude": config.WEATHER_LON if lon is None else lon,
            "daily": (
                "precipitation_sum,precipitation_probability_max,"
                "temperature_2m_max,temperature_2m_min"
            ),
            "hourly": "relative_humidity_2m",
            "forecast_days": 3,
            "timezone": "Asia/Shanghai",
        },
        timeout=config.WEATHER_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily") or {}
    dates = daily.get("time") or []

    # hourly 时间形如 2026-11-05T13:00，按日期取当天最大湿度
    hourly = data.get("hourly") or {}
    hum_by_date: dict[str, float] = {}
    for ts, hum in zip(hourly.get("time") or [], hourly.get("relative_humidity_2m") or []):
        if hum is None:
            continue
        day = str(ts)[:10]
        hum_by_date[day] = max(hum_by_date.get(day, 0.0), float(hum))

    days: list[dict] = []
    for i, day in enumerate(dates):
        days.append({
            "date": day,
            "precip_mm": _pick(daily.get("precipitation_sum"), i) or 0.0,
            "precip_prob": _pick(daily.get("precipitation_probability_max"), i) or 0,
            "temp_max": _pick(daily.get("temperature_2m_max"), i),
            "temp_min": _pick(daily.get("temperature_2m_min"), i),
            "humidity": hum_by_date.get(day),
        })
    return days


def evaluate_risk(days: list[dict] | None, location: str | None = None) -> dict | None:
    """纯函数：按未来 3 天降雨/湿度判断霜疫霉病风险，便于单测。"""
    if not days:
        return None
    location = config.WEATHER_LOCATION if location is None else location

    high_day = None
    medium_day = None
    for day in days:
        mm = float(day.get("precip_mm") or 0)
        prob = float(day.get("precip_prob") or 0)
        hum = day.get("humidity")
        hum = float(hum) if hum is not None else 0.0
        if high_day is None and (mm >= 10 or prob >= 80 or (prob >= 50 and hum >= 85)):
            high_day = day
        if medium_day is None and (mm >= 3 or prob >= 50):
            medium_day = day

    first_two_mm = sum(float(d.get("precip_mm") or 0) for d in days[:2])
    level = "high" if (high_day or first_two_mm >= 15) else ("medium" if medium_day else None)
    if not level:
        return None

    day = high_day or medium_day or days[0]
    mm = round(float(day.get("precip_mm") or 0), 1)
    prob = int(float(day.get("precip_prob") or 0))
    hum = day.get("humidity")
    hum_pct = int(float(hum)) if hum is not None else None
    # 只写真正触发的条件：概率高但雨量小的时候，不要说「有降雨 0mm」
    bits: list[str] = []
    if mm >= 3:
        bits.append(f"预计降雨约 {mm:.0f}mm")
    if prob >= 50:
        bits.append(f"降水概率 {prob}%")
    if hum_pct is not None and hum_pct >= 80:
        bits.append(f"最高湿度 {hum_pct}%")
    if not bits:
        bits.append(f"{day['date']} 降水概率 {prob}%")
    detail = (
        f"未来 3 天{location}{'，'.join(bits)}。"
        "荔枝霜疫霉病在连续阴雨高湿时易流行，建议雨前做好保护性预防，"
        "具体用药按登记标签与安全间隔期执行。"
    )

    return {
        "pest": "荔枝霜疫霉病",
        "level": level,
        "date": day["date"],
        "precip_mm": mm,
        "precip_prob": prob,
        "humidity": int(float(hum)) if hum is not None else None,
        "detail": detail,
        "location": location,
        "source": "Open-Meteo",
    }


def get_pest_risk(force: bool = False, region: dict | None = None) -> dict | None:
    """带缓存的入口；关闭开关或任何异常都返回 None。

    缓存按地区坐标分槽：切换地区后不会复用旧地区的结论。
    """
    if not config.WEATHER_ENABLED:
        return None

    region = region or get_region()
    key = (round(float(region["lat"]), 3), round(float(region["lon"]), 3))

    now = time.time()
    with _LOCK:
        if (not force and _CACHE["loaded"] and _CACHE["key"] == key
                and now < _CACHE["expires"]):
            return _CACHE["risk"]

    try:
        risk = evaluate_risk(
            _fetch_days(region["lat"], region["lon"]),
            location=region.get("label") or region_label(region),
        )
        ttl = _RISK_TTL
    except Exception:
        risk = None
        ttl = _FAIL_TTL

    with _LOCK:
        _CACHE.update(key=key, loaded=True, expires=time.time() + ttl, risk=risk)
    return risk
