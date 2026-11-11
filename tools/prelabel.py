#!/usr/bin/env python
"""批量预标注：用当前识别链路给 data/eval/images 里的图片打标，生成 labels.csv 草稿。

模型只负责「先给一个猜测」，人工只需检查并改正错的那几条，避免从零开始标注。

用法：
    E:/python.exe tools/prelabel.py              # 只给新图片补标，已有 label 不覆盖
    E:/python.exe tools/prelabel.py --force      # 全部重新预标（覆盖模型列，不动人工 label）
    E:/python.exe tools/prelabel.py --allow-mock # 本地模拟模式下也生成（仅用于跑通脚本）

labels.csv 列：file,label,model_guess,model_confidence,model_source
    - file：图片文件名
    - label：人工确认后的正确类别（空 = 还没标）
    - 其余三列只是预标注参考值，评测时会被忽略
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

# 本机 E:\python.exe 的 sys.prefix 是 "E:"，site-packages 会随 E: 盘的当前
# 目录漂移：从 E:\Temp 之类的目录启动时就 import 不到依赖。按 exe 位置补回。
_site_packages = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                              "Lib", "site-packages")
if os.path.isdir(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend import ai_service  # noqa: E402
from backend.rules import PESTS  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
FIELDS = ["file", "label", "model_guess", "model_confidence", "model_source"]


def _natural_key(name: str):
    """按数字自然排序：img2 排在 img10 前面。"""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name)]


def load_labels(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return {row["file"]: row for row in csv.DictReader(fh) if row.get("file")}


def save_labels(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDS})


def main() -> int:
    parser = argparse.ArgumentParser(description="批量预标注评测图片")
    parser.add_argument("--dir", default=str(BASE_DIR / "data" / "eval" / "images"))
    parser.add_argument("--labels", default=str(BASE_DIR / "data" / "eval" / "labels.csv"))
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少张（0 = 全部）")
    parser.add_argument("--force", action="store_true", help="重新预标已有 model_guess 的图片")
    parser.add_argument("--allow-mock", action="store_true", help="允许本地模拟模式（结果无意义）")
    args = parser.parse_args()

    image_dir = Path(args.dir)
    label_path = Path(args.labels)
    if not image_dir.is_dir():
        print(f"图片目录不存在：{image_dir}")
        return 2

    provider = ai_service.current_provider()
    if provider == "mock" and not args.allow_mock:
        print("当前识别链路是本地模拟（mock），预标注没有意义。")
        print("请在 .env 配置 VISION_API_KEY / VISION_BASE_URL 后重试；")
        print("如只想跑通脚本，可加 --allow-mock。")
        return 2

    images = sorted(
        (p for p in image_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda p: _natural_key(p.name),
    )
    if not images:
        print(f"{image_dir} 里没有图片（支持 {' '.join(sorted(IMAGE_SUFFIXES))}）")
        return 2

    existing = load_labels(label_path)
    rows: list[dict] = []
    todo: list[Path] = []
    for image in images:
        row = existing.pop(image.name, {"file": image.name, "label": ""})
        row["file"] = image.name
        rows.append(row)
        if args.force or not row.get("model_guess"):
            todo.append(image)
    # 图片已被删除的旧标注保留，避免误删人工工作
    rows.extend(existing.values())

    if args.limit:
        todo = todo[: args.limit]

    print(f"图片 {len(images)} 张，待预标注 {len(todo)} 张，识别渠道 {provider}")
    changed = 0
    for index, image in enumerate(todo, 1):
        try:
            result = ai_service.recognize(image.read_bytes())
        except Exception as exc:  # 单张失败不中断
            print(f"  [{index}/{len(todo)}] {image.name} 识别失败：{exc}")
            continue
        row = next(r for r in rows if r["file"] == image.name)
        row["model_guess"] = result["pest_class"]
        row["model_confidence"] = f"{float(result['confidence']):.3f}"
        row["model_source"] = result["source"]
        changed += 1
        print(f"  [{index}/{len(todo)}] {image.name} → {result['pest_class']} "
              f"({float(result['confidence']):.0%})")
        if index % 5 == 0:  # 定期落盘，长任务中断也不丢
            save_labels(label_path, rows)

    save_labels(label_path, rows)

    unlabelled = [r["file"] for r in rows if not (r.get("label") or "").strip()]
    print(f"\n已写入 {label_path}（本次更新 {changed} 条）")
    if unlabelled:
        print(f"还有 {len(unlabelled)} 条没有人工 label，直接采用模型结果的话把 model_guess 抄到 label 即可：")
        for name in unlabelled[:10]:
            print("  -", name)
        if len(unlabelled) > 10:
            print(f"  ...另有 {len(unlabelled) - 10} 条")
    print("\n下一步：检查并改正 label 列 → E:/python.exe tools/eval_vision.py")
    print(f"知识库共 {len(PESTS)} 个可选类别，label 必须与其中之一完全一致（或写「非目标」）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
