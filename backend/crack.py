"""荔枝裂果风险：久旱后骤雨 + 品种敏感性 + 物候期。

纯规则函数，输入是 weather 取回的「过去 7 天 + 未来 3 天」按天数据，
便于单测；不直接发网络请求。
"""
from __future__ import annotations

from datetime import date, datetime

from . import maturity

# 品种对裂果的敏感度：糯米糍皮薄最易裂，妃子笑相对抗裂
VARIETY_SENSITIVITY = {"糯米糍": "high", "桂味": "medium", "妃子笑": "low"}
DEFAULT_SENSITIVITY = "medium"

# 触发预警的未来单日降雨量阈值（mm），敏感品种来得更早
RAIN_THRESHOLD_MM = {"high": 8.0, "medium": 12.0, "low": 20.0}

DRY_TOTAL_MM = 5.0        # 过去 7 天累计降雨不超过 5mm 视为「久旱」
DRY_STREAK_DAYS = 3       # 且至少连续 3 天无雨
PAST_WINDOW = 7
FUTURE_WINDOW = 3
MIN_PAST_DAYS = 5         # 历史数据不足时不贸然预警


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _rain(day: dict) -> float:
    try:
        return float(day.get("precip_mm") or 0)
    except (TypeError, ValueError):
        return 0.0


def _longest_dry_streak(days: list[dict]) -> int:
    best = current = 0
    for day in days:
        if _rain(day) < 0.5:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def evaluate_crack_risk(
    days: list[dict] | None,
    variety: str,
    today: date | datetime | None = None,
    phenology: str | None = None,
    location: str | None = None,
) -> dict | None:
    """命中返回风险字典，否则 None。

    days 需同时包含历史与未来日期；只有未来数据或历史不足 5 天时返回 None。
    """
    if not days:
        return None

    day = today.date() if isinstance(today, datetime) else (today or date.today())
    parsed = [(d, _as_date(d.get("date"))) for d in days]
    parsed = [(d, dt) for d, dt in parsed if dt is not None]
    if not parsed:
        return None

    past = [d for d, dt in parsed if dt < day][-PAST_WINDOW:]
    future = [d for d, dt in parsed if dt >= day][:FUTURE_WINDOW]
    if len(past) < MIN_PAST_DAYS or not future:
        return None

    stage = phenology or maturity.phenology(variety, day)
    if not maturity.is_sensitive_stage(stage):
        return None

    total_past = sum(_rain(d) for d in past)
    if total_past > DRY_TOTAL_MM:
        return None
    streak = _longest_dry_streak(past)
    if streak < DRY_STREAK_DAYS:
        return None

    sensitivity = VARIETY_SENSITIVITY.get(variety, DEFAULT_SENSITIVITY)
    threshold = RAIN_THRESHOLD_MM[sensitivity]
    hit = next((d for d in future if _rain(d) >= threshold), None)
    if hit is None:
        return None

    rain = _rain(hit)
    level = "high" if sensitivity == "high" else "medium"
    name = variety or "荔枝"
    detail = (
        f"过去 {len(past)} 天累计降雨仅 {total_past:.0f}mm（连续 {streak} 天无雨），"
        f"预计 {hit['date']} 降雨 {rain:.0f}mm。{name}正处于{stage}，久旱转雨容易裂果，"
        "建议提前采收、控制灌溉或叶面补钙。"
    )

    return {
        "type": "crack",
        "level": level,
        "variety": variety,
        "sensitivity": sensitivity,
        "date": hit["date"],
        "rain_mm": round(rain, 1),
        "dry_days": streak,
        "past_rain_mm": round(total_past, 1),
        "phenology": stage,
        "detail": detail,
        "location": location,
        "source": "Open-Meteo",
    }
