"""采收窗口与物候期：按品种日历规则计算，不依赖模型判定。

规则为主，照片只作为人工观察证据（记录在 farm_operations 的「成熟度观察」里），
不参与状态计算——避免识别误差把采收建议带偏。
"""
from __future__ import annotations

from datetime import date, datetime

# 品种 → 当年最佳采收窗口（月-日）。可按产区实际物候调整。
VARIETY_WINDOWS: dict[str, tuple[str, str]] = {
    "妃子笑": ("06-05", "06-25"),
    "桂味": ("06-20", "07-10"),
    "糯米糍": ("06-28", "07-18"),
}
DEFAULT_WINDOW = ("06-15", "07-15")

NEAR_DAYS = 7          # 距窗口开始 7 天内算「临近」
STALE_DAYS = 14        # 已过窗口超过 14 天不再产生待办

SENSITIVE_PHENOLOGY = ("果实膨大期", "转色成熟期")


def _as_date(value: date | datetime | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    return value


def _window_dates(variety: str, today: date) -> tuple[date, date]:
    start, end = VARIETY_WINDOWS.get(variety, DEFAULT_WINDOW)
    year = today.year
    begin = datetime.strptime(f"{year}-{start}", "%Y-%m-%d").date()
    finish = datetime.strptime(f"{year}-{end}", "%Y-%m-%d").date()
    return begin, finish


def window_for(variety: str, today: date | datetime | None = None) -> dict:
    """返回某品种在指定日期的采收窗口状态。

    status: 未到 | 临近 | 最佳 | 已过
    """
    day = _as_date(today)
    begin, finish = _window_dates(variety, day)

    if day < begin:
        days_to_start = (begin - day).days
        status = "临近" if days_to_start <= NEAR_DAYS else "未到"
        return {
            "variety": variety,
            "status": status,
            "window_start": begin.isoformat(),
            "window_end": finish.isoformat(),
            "days_to_start": days_to_start,
            "days_remaining": 0,
            "days_overdue": 0,
            "suggested_date": begin.isoformat(),
            "label": _label(variety, begin, finish),
        }

    if day <= finish:
        return {
            "variety": variety,
            "status": "最佳",
            "window_start": begin.isoformat(),
            "window_end": finish.isoformat(),
            "days_to_start": 0,
            "days_remaining": (finish - day).days,
            "days_overdue": 0,
            "suggested_date": day.isoformat(),
            "label": _label(variety, begin, finish),
        }

    return {
        "variety": variety,
        "status": "已过",
        "window_start": begin.isoformat(),
        "window_end": finish.isoformat(),
        "days_to_start": 0,
        "days_remaining": 0,
        "days_overdue": (day - finish).days,
        "suggested_date": finish.isoformat(),
        "label": _label(variety, begin, finish),
    }


def _label(variety: str, begin: date, finish: date) -> str:
    name = variety or "荔枝"
    return f"{name}最佳采收期 {begin.month}/{begin.day}–{finish.month}/{finish.day}"


def phenology(variety: str, today: date | datetime | None = None) -> str:
    """按与采收窗口的距离推断物候期：花穗期 / 幼果期 / 果实膨大期 / 转色成熟期 / 采后。"""
    day = _as_date(today)
    begin, finish = _window_dates(variety, day)
    if day > finish:
        return "采后"
    delta = (day - begin).days
    if delta < -60:
        return "花穗期"
    if delta < -30:
        return "幼果期"
    if delta < 0:
        return "果实膨大期"
    return "转色成熟期"


def is_sensitive_stage(stage: str | None) -> bool:
    return (stage or "") in SENSITIVE_PHENOLOGY
