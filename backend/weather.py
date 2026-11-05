"""天气联动：Open-Meteo 免 Key 预报 → 霜疫霉病风险。

只做一件事：把未来 3 天的降雨/湿度翻译成一条「雨前预防」提示，
供 /api/todos 使用。任何网络或解析异常都静默返回 None，绝不影响主流程。

注意：Open-Meteo 的日级变量里没有相对湿度，湿度要用 hourly 拉取后按天聚合。
"""
from __future__ import annotations

import threading
import time
from typing import Any

from . import config

_RISK_TTL = 30 * 60      # 成功结果缓存 30 分钟
_FAIL_TTL = 5 * 60       # 失败结果缓存 5 分钟，断网时避免每次请求都等超时
_CACHE: dict[str, Any] = {"expires": 0.0, "risk": None, "loaded": False}
_LOCK = threading.Lock()


def _pick(seq: Any, index: int):
    try:
        return seq[index]
    except (TypeError, IndexError, KeyError):
        return None


def _fetch_days() -> list[dict]:
    """拉未来 3 天预报，返回按天聚合的列表；失败抛异常由调用方兜底。"""
    import httpx

    resp = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config.WEATHER_LAT,
            "longitude": config.WEATHER_LON,
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


def evaluate_risk(days: list[dict] | None) -> dict | None:
    """纯函数：按未来 3 天降雨/湿度判断霜疫霉病风险，便于单测。"""
    if not days:
        return None

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
        f"未来 3 天{config.WEATHER_LOCATION}{'，'.join(bits)}。"
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
        "location": config.WEATHER_LOCATION,
        "source": "Open-Meteo",
    }


def get_pest_risk(force: bool = False) -> dict | None:
    """带缓存的入口；关闭开关或任何异常都返回 None。"""
    if not config.WEATHER_ENABLED:
        return None

    now = time.time()
    with _LOCK:
        if not force and _CACHE["loaded"] and now < _CACHE["expires"]:
            return _CACHE["risk"]

    try:
        risk = evaluate_risk(_fetch_days())
        ttl = _RISK_TTL
    except Exception:
        risk = None
        ttl = _FAIL_TTL

    with _LOCK:
        _CACHE.update(loaded=True, expires=time.time() + ttl, risk=risk)
    return risk
