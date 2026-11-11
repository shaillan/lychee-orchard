#!/usr/bin/env python
"""识别准确率评测：按 labels.csv 跑一遍完整识别链路，输出可写进答辩材料的数字。

用法：
    E:/python.exe tools/eval_vision.py
    E:/python.exe tools/eval_vision.py --conf 0.65 --out docs/eval-report.md

输出：
    docs/eval-report.md   Markdown 报告（准确率 / 分类召回 / 混淆 / 拒答 / 耗时）
    data/eval/report.json 逐张明细，便于二次分析

评测口径：
    1. 直接调用 ai_service.recognize()，与 /api/recognitions 完全同一条链路
       （含证据闸门、二次确认、云端失败降级），不额外清洗结果；
    2. label 必须与知识库类别名一致（允许别名，如「蒂蛀虫」），
       非目标物（桌面、手、天空、模糊照）统一标成「非目标」，
       只有判为「无法判断」才算拒答正确；
    3. 置信度 < --conf 的结果按系统约定不自动给处置建议，单独统计。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# 本机 E:\python.exe 的 sys.prefix 是 "E:"，site-packages 会随 E: 盘的当前
# 目录漂移：从 E:\Temp 之类的目录启动时就 import 不到依赖。按 exe 位置补回。
_site_packages = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                              "Lib", "site-packages")
if os.path.isdir(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend import ai_service, config  # noqa: E402
from backend.rules import PEST_CLASSES, PESTS  # noqa: E402

ABSTAIN = "无法判断"
NON_TARGET = "非目标"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name)]


def _pct(part: int, total: int) -> str:
    return f"{part / total * 100:.1f}%" if total else "—"


def _canonical_label(raw: str) -> str | None:
    """把人工填写的 label 归一化到知识库类别；无法识别时返回 None。"""
    text = (raw or "").strip()
    if not text:
        return None
    if text in PESTS or text in (ABSTAIN, NON_TARGET):
        return text
    normalized = ai_service._normalize_class(text)
    return normalized if normalized != ABSTAIN else None


def load_cases(label_path: Path, image_dir: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    cases: list[tuple[Path, str]] = []
    problems: list[str] = []
    with label_path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("file") or "").strip()
            if not name:
                continue
            label = _canonical_label(row.get("label") or "")
            if not label:
                problems.append(f"{name}：label「{row.get('label') or ''}」不在知识库中，且无法通过别名匹配")
                continue
            path = image_dir / name
            if not path.exists():
                problems.append(f"{name}：图片不存在（{path}）")
                continue
            cases.append((path, label))
    cases.sort(key=lambda case: _natural_key(case[0].name))
    return cases, problems


def evaluate(cases, conf_threshold: float, on_progress=None):
    """逐张评测；on_progress(items) 每 5 张回调一次，长任务中断也不丢已跑结果。"""
    items = []
    for index, (path, label) in enumerate(cases, 1):
        start = time.perf_counter()
        try:
            result = ai_service.recognize(path.read_bytes())
            error = ""
        except Exception as exc:  # 单张失败不中断，但要计入分母
            result = {"pest_class": ABSTAIN, "confidence": 0.0, "source": f"error:{type(exc).__name__}"}
            error = str(exc)[:200]
        elapsed = time.perf_counter() - start
        pred = result["pest_class"]
        confidence = float(result["confidence"])
        # 非目标图（桌面/手/天空/模糊照）只有判为「无法判断」才算拒答正确
        correct = (pred == ABSTAIN) if label == NON_TARGET else (pred == label)
        items.append({
            "file": path.name,
            "label": label,
            "pred": pred,
            "confidence": round(confidence, 4),
            "source": result["source"],
            "correct": correct,
            "abstained": pred == ABSTAIN,
            "low_confidence": confidence < conf_threshold,
            "elapsed_s": round(elapsed, 2),
            "error": error,
        })
        mark = "✓" if correct else "✗"
        mock_tag = " [mock]" if str(result["source"]).startswith("mock") else ""
        print(f"[{index}/{len(cases)}] {mark} {path.name}: {label} → {pred} "
              f"({confidence:.0%}, {elapsed:.1f}s){mock_tag}", flush=True)
        if on_progress and (index % 5 == 0 or index == len(cases)):
            on_progress(items)
    return items


def summarize(items, conf_threshold: float) -> dict:
    total = len(items)
    correct = sum(1 for i in items if i["correct"])
    abstained = sum(1 for i in items if i["abstained"])
    low_conf = sum(1 for i in items if i["low_confidence"])

    non_target = [i for i in items if i["label"] == NON_TARGET]
    non_target_correct = sum(1 for i in non_target if i["correct"])
    false_alarms = [i for i in non_target if i["pred"] in PEST_CLASSES]

    per_label: dict[str, dict] = {}
    for item in items:
        bucket = per_label.setdefault(item["label"], {"support": 0, "correct": 0})
        bucket["support"] += 1
        bucket["correct"] += int(item["correct"])

    confusion = Counter(
        (item["label"], item["pred"]) for item in items if not item["correct"]
    )

    latencies = [i["elapsed_s"] for i in items]
    conf_correct = [i["confidence"] for i in items if i["correct"]]
    conf_wrong = [i["confidence"] for i in items if not i["correct"]]

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "abstained": abstained,
        "abstain_rate": round(abstained / total, 4) if total else 0.0,
        "low_confidence": low_conf,
        "low_confidence_rate": round(low_conf / total, 4) if total else 0.0,
        "actionable": total - low_conf,
        "non_target_total": len(non_target),
        "non_target_correct": non_target_correct,
        "non_target_false_alarms": len(false_alarms),
        "false_alarm_files": [i["file"] for i in false_alarms],
        "per_label": per_label,
        "confusion": [[label, pred, count] for (label, pred), count in confusion.most_common()],
        "latency_avg": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "latency_median": round(statistics.median(latencies), 2) if latencies else 0.0,
        "latency_max": round(max(latencies), 2) if latencies else 0.0,
        "confidence_avg_correct": round(statistics.mean(conf_correct), 3) if conf_correct else 0.0,
        "confidence_avg_wrong": round(statistics.mean(conf_wrong), 3) if conf_wrong else 0.0,
        "sources": dict(Counter(i["source"] for i in items)),
        "mock_count": sum(1 for i in items if str(i["source"]).startswith("mock")),
        "conf_threshold": conf_threshold,
    }


def render_report(summary: dict, items: list[dict], provider: str, label_path: Path,
                  image_dir: Path) -> str:
    total = summary["total"]
    lines = [
        "# 识别评测报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 评测集：`{image_dir}`（{total} 张）",
        f"- 标注文件：`{label_path}`",
        f"- 识别渠道：`{provider}`",
        f"- 二次确认：{'开启' if config.VISION_CONFIRM else '关闭'}",
        f"- 低置信度阈值：{summary['conf_threshold']:.0%}",
        "",
    ]

    mock_count = summary.get("mock_count", 0)
    if mock_count and mock_count == total:
        lines += [
            "> ⚠️ **本次全部走本地模拟（mock），数字不能用于答辩或对外说明。**",
            "> 请在 `.env` 配置 `VISION_API_KEY` / `VISION_BASE_URL` 后重跑。",
            "",
        ]
    elif mock_count:
        lines += [
            f"> ⚠️ **有 {mock_count}/{total} 张云端调用失败、走了本地模拟降级；"
            "这些数字不代表真实模型能力，请检查网络/额度后重跑。**",
            "",
        ]

    lines += [
        "## 一、总体",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| Top-1 准确率 | **{summary['accuracy'] * 100:.1f}%**（{summary['correct']}/{total}） |",
        f"| 拒答率（判为「{ABSTAIN}」） | {summary['abstain_rate'] * 100:.1f}%（{summary['abstained']}/{total}） |",
        f"| 低置信度占比（<{summary['conf_threshold']:.0%}） | {summary['low_confidence_rate'] * 100:.1f}%（{summary['low_confidence']}/{total}） |",
        f"| 可自动处置（置信度 ≥{summary['conf_threshold']:.0%}） | {summary['actionable']}/{total} |",
        f"| 非目标图拒答 | {summary['non_target_correct']}/{summary['non_target_total']} |",
        f"| 非目标图误报为病虫害 | **{summary['non_target_false_alarms']}** 张 |",
        f"| 平均耗时 | {summary['latency_avg']}s（中位数 {summary['latency_median']}s，最长 {summary['latency_max']}s） |",
        f"| 平均置信度 | 正确 {summary['confidence_avg_correct']:.2f} / 错误 {summary['confidence_avg_wrong']:.2f} |",
        "",
        "> 口径：准确率 = 判对张数 / 总张数；「非目标」图只有判为「无法判断」才算对。",
        "",
        "## 二、分类别召回",
        "",
        "| 类别 | 样本 | 正确 | 召回 |",
        "|---|---:|---:|---:|",
    ]
    for label, bucket in sorted(summary["per_label"].items(),
                                key=lambda kv: (-kv[1]["support"], kv[0])):
        lines.append(
            f"| {label} | {bucket['support']} | {bucket['correct']} | "
            f"{_pct(bucket['correct'], bucket['support'])} |"
        )

    lines += ["", "## 三、主要混淆", ""]
    if summary["confusion"]:
        lines += ["| 人工标注 | 模型判为 | 次数 |", "|---|---|---:|"]
        for label, pred, count in summary["confusion"][:15]:
            lines.append(f"| {label} | {pred} | {count} |")
    else:
        lines.append("没有误判样本。")

    wrong_low = [i for i in items if not i["correct"] and i["low_confidence"]]
    wrong_high = [i for i in items if not i["correct"] and not i["low_confidence"]]
    lines += ["", "## 四、误判明细", ""]
    if wrong_high:
        lines += [
            f"### 高置信度误判（{len(wrong_high)} 张，最需要关注）",
            "",
            "| 文件 | 标注 | 判为 | 置信度 |",
            "|---|---|---|---:|",
        ]
        for item in wrong_high[:20]:
            lines.append(
                f"| {item['file']} | {item['label']} | {item['pred']} | {item['confidence']:.0%} |"
            )
    if wrong_low:
        lines += [
            "",
            f"### 低置信度误判（{len(wrong_low)} 张，已被系统拦截，不会自动给用药建议）",
            "",
            "| 文件 | 标注 | 判为 | 置信度 |",
            "|---|---|---|---:|",
        ]
        for item in wrong_low[:20]:
            lines.append(
                f"| {item['file']} | {item['label']} | {item['pred']} | {item['confidence']:.0%} |"
            )
    if not wrong_low and not wrong_high:
        lines.append("没有误判样本。")

    errors = [i for i in items if i.get("error")]
    if errors:
        lines += ["", "## 五、调用失败", "", "| 文件 | 错误 |", "|---|---|"]
        for item in errors[:10]:
            lines.append(f"| {item['file']} | {item['error'].replace('|', '/')} |")

    lines += [
        "",
        "## 使用说明",
        "",
        "- 这是**自建小样本评测集**，数字用于说明「防误报设计是否有效」，不等同于公开基准；",
        "- 答辩时建议同时给出样本量、类别分布与置信度口径，避免被追问时口径不一致；",
        "- 类别覆盖不足时先补样本再改提示词，不要只看总体准确率。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="识别准确率评测")
    parser.add_argument("--dir", default=str(BASE_DIR / "data" / "eval" / "images"))
    parser.add_argument("--labels", default=str(BASE_DIR / "data" / "eval" / "labels.csv"))
    parser.add_argument("--out", default=str(BASE_DIR / "docs" / "eval-report.md"))
    parser.add_argument("--json", default=str(BASE_DIR / "data" / "eval" / "report.json"))
    parser.add_argument("--conf", type=float, default=0.65, help="低置信度阈值（默认 0.65）")
    parser.add_argument("--limit", type=int, default=0, help="最多评测多少张（0 = 全部）")
    parser.add_argument("--retry-failed", action="store_true",
                        help="只重跑上次因限流/断网失败或降级的样本，其余结果保留")
    parser.add_argument("--class", dest="classes", action="append", default=[],
                        help="只评测指定类别（可重复，支持别名）")
    parser.add_argument("--merge", action="store_true",
                        help="与上次 report.json 里未重跑的样本合并，报告覆盖全部样本")
    args = parser.parse_args()

    image_dir = Path(args.dir)
    label_path = Path(args.labels)
    if not label_path.exists():
        print(f"标注文件不存在：{label_path}")
        print("先执行 E:/python.exe tools/prelabel.py 生成草稿。")
        return 2

    cases, problems = load_cases(label_path, image_dir)
    if problems:
        print("标注文件有问题，请先修正：")
        for problem in problems:
            print("  -", problem)
        return 2
    if not cases:
        print("没有可评测的样本：labels.csv 里没有有效图片。")
        return 2
    if args.limit:
        cases = cases[: args.limit]

    if args.classes:
        wanted = {_canonical_label(name) or name for name in args.classes}
        cases = [case for case in cases if case[1] in wanted]
        if not cases:
            print(f"没有匹配的样本：{'、'.join(args.classes)}")
            return 2

    provider = ai_service.current_provider()
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    previous_items: list[dict] = []
    if args.retry_failed or args.merge:
        if not json_path.exists():
            if args.retry_failed:
                print(f"找不到上次结果：{json_path}（先跑一次全量评测）")
                return 2
        else:
            previous_items = json.loads(json_path.read_text(encoding="utf-8")).get("items") or []

    if args.retry_failed:
        failed = {
            i["file"] for i in previous_items
            if str(i.get("source", "")).startswith(("mock", "cloud_failed")) or i.get("error")
        }
        if not failed:
            print("上次没有失败或降级的样本，无需重跑。")
            return 0
        cases = [case for case in cases if case[0].name in failed]
        if not cases:
            print("失败样本已不在当前评测集里，跳过。")
            return 0
        print(f"只重跑上次失败/降级的 {len(cases)} 张，其余结果保留原样。")

    def merge_with_previous(done_items):
        if not previous_items:
            return done_items
        by_file = {i["file"]: i for i in previous_items}
        by_file.update({i["file"]: i for i in done_items})
        order = {i["file"]: n for n, i in enumerate(previous_items)}
        return sorted(by_file.values(), key=lambda i: order.get(i["file"], 10 ** 9))

    def checkpoint(done_items):
        """中途落盘：全量评测要跑几十分钟，断网/限流中断时不能把已跑的结果全丢掉。"""
        json_path.write_text(json.dumps({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "provider": provider,
            "partial": True,
            "items": merge_with_previous(done_items),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"待评测 {len(cases)} 张，识别渠道 {provider}，低置信度阈值 {args.conf:.0%}\n")
    items = merge_with_previous(evaluate(cases, args.conf, on_progress=checkpoint))
    summary = summarize(items, args.conf)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_report(summary, items, provider, label_path, image_dir),
                        encoding="utf-8")

    json_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "summary": summary,
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 结果 =====")
    print(f"Top-1 准确率：{summary['accuracy'] * 100:.1f}%（{summary['correct']}/{summary['total']}）")
    print(f"拒答率：{summary['abstain_rate'] * 100:.1f}%  低置信度：{summary['low_confidence_rate'] * 100:.1f}%")
    print(f"非目标误报：{summary['non_target_false_alarms']}/{summary['non_target_total']}")
    print(f"平均耗时：{summary['latency_avg']}s")
    if summary.get("mock_count"):
        print(f"\n⚠️ 有 {summary['mock_count']}/{summary['total']} 张走了本地模拟降级，"
              "这些结果不代表真实模型能力，建议检查网络/额度后重跑。")
    print(f"\n报告已写入：{out_path}")
    print(f"明细已写入：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
