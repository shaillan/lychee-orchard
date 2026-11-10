"""巡园报告：把同一次「进园巡拍」的识别结果聚合成一句可读结论。

纯函数，便于单测；建议文案复用知识库的 monitoring 字段，不新增数据。
"""
from __future__ import annotations

from datetime import date, datetime

from .rules import HEALTHY_CLASSES, PESTS

_CLASS_ORDER = {"高": 0, "中高": 1, "中": 2, "未知": 3, "无": 4}


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def _risk_of(name: str) -> str:
    return (PESTS.get(name) or {}).get("risk", "未知")


def build_patrol_report(
    items: list[dict],
    plot_names: dict[int, str] | None = None,
    patrol_id: str | None = None,
    today: date | datetime | None = None,
) -> dict:
    """items 为 recognitions 行（需含 detected_class、plot_id）。"""
    plot_names = plot_names or {}
    day = _as_date(today)

    counts: dict[str, int] = {}
    by_plot: dict[int, dict] = {}
    total = 0

    for item in items:
        name = item.get("detected_class") or "无法判断"
        if name in HEALTHY_CLASSES:
            continue
        total += 1
        counts[name] = counts.get(name, 0) + 1

        plot_id = item.get("plot_id")
        if plot_id is None:
            continue
        bucket = by_plot.setdefault(int(plot_id), {
            "plot_id": int(plot_id),
            "plot_name": plot_names.get(int(plot_id)) or f"地块 {plot_id}",
            "count": 0,
            "classes": {},
        })
        bucket["count"] += 1
        bucket["classes"][name] = bucket["classes"].get(name, 0) + 1

    by_class = [
        {"class": name, "count": count, "risk": _risk_of(name)}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], _CLASS_ORDER.get(_risk_of(kv[0]), 9)))
    ]

    plots = []
    for bucket in by_plot.values():
        bucket["classes"] = [
            {"class": name, "count": count}
            for name, count in sorted(bucket["classes"].items(), key=lambda kv: -kv[1])
        ]
        plots.append(bucket)
    plots.sort(key=lambda p: (-p["count"], p["plot_id"]))

    focus_plot = plots[0] if plots else None
    summary = _summary_sentence(by_class, focus_plot, total)

    advice = []
    for entry in by_class[:3]:
        info = PESTS.get(entry["class"]) or {}
        monitoring = info.get("monitoring")
        if monitoring:
            advice.append({"class": entry["class"], "monitoring": monitoring})

    return {
        "patrol_id": patrol_id,
        "date": day.isoformat(),
        "total": total,
        "by_plot": plots,
        "by_class": by_class,
        "focus_plot": focus_plot,
        "summary": summary,
        "advice": advice,
    }


def _summary_sentence(by_class: list[dict], focus_plot: dict | None, total: int) -> str:
    if not total:
        return "今日巡园未发现异常，果面与叶片状态良好"
    parts = [f"{entry['class']} {entry['count']} 处" for entry in by_class[:3]]
    text = f"今日巡园 {total} 处：" + "、".join(parts)
    if focus_plot and focus_plot["count"] >= 2:
        text += f"，建议重点巡查 {focus_plot['plot_name']}"
    return text


def recognized_ok(item: dict) -> bool:
    """判定是否算「一处问题」，供路由层快速过滤。"""
    name = item.get("detected_class") or ""
    return bool(name) and name not in HEALTHY_CLASSES
