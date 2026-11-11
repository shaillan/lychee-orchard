# 识别评测集（本地使用，不进仓库）

目标：给「识别准不准」一个可复现的数字，用于答辩和回归。

## 一、自动抓取（可选）

没有自拍图时，可以先跑抓取脚本拿到一批候选图，再人工剔除不符的：

```bash
E:/python.exe tools/fetch_eval_images.py                    # 全部 18 类 + 健康叶片/果实 + 非目标
E:/python.exe tools/fetch_eval_images.py --class 荔枝蝽 --per-class 6
E:/python.exe tools/fetch_eval_images.py --dry-run          # 只看查询计划，不联网不写文件
```

- 来源：iNaturalist 开放许可照片（CC0 / CC BY / CC BY-SA，manifest 记录观察者与许可），
  昆虫与病原类别优先用它；Bing / 360 图搜兜底，其中 360 网页搜索的图片包最稳定
  （仅本地评测，`license` 记为 `search-only`）；
- 每类默认 5 张、非目标 15 张，自动校验尺寸、去重、压缩为 JPEG；
- 抓完会生成 `data/eval/contact-sheet.html` 和 `data/eval/manifest.csv`（均被 gitignore）；
- `labels.csv` 会按查询类别**预填** `label`，但这只是抓取来源的猜测，**不等于人工确认**，仍须逐张核对。

抓取后按顺序做：

1. 浏览器打开 `data/eval/contact-sheet.html`，逐张看，删掉 `data/eval/images/` 里不符的图片；
2. `E:/python.exe tools/fetch_eval_images.py --prune-missing` 清理 manifest / labels 中已删图片的行；
3. 继续下面的预标注与评测。

图搜结果里常混入海报、商品图、新闻配图；脚本已按标题中的病虫害关键词过滤，但仍需人工核对。
网络图片只用于本地评测，不要提交、不要放进 PPT 素材包。

## 二、自己放图

把图片放到 `data/eval/images/`，文件名随意（建议 `类别_序号.jpg`，如 `tichengchong_01.jpg`）。

- 最少 20~30 张，先覆盖：健康叶片、荔枝蒂蛀虫、荔枝霜疫霉病、荔枝炭疽病、荔枝瘿螨；
- 另拍 10~20 张**非目标图**：桌面、手、天空、模糊照、过暗照、其他植物。这些图用来测「会不会硬猜」；
- 自己拍的图没有版权问题；网络图片只用于本地评测，不要提交、不要放进 PPT 素材包。

## 三、预标注（模型先打标）

```bash
E:/python.exe tools/prelabel.py
```

会生成 `labels.csv`：

```
file,label,model_guess,model_confidence,model_source
tichengchong_01.jpg,荔枝蒂蛀虫,荔枝蒂蛀虫,0.92,zhipu:glm-4.1v-thinking-flash
```

- `label` 是**人工确认**的正确类别，这是唯一会被评测使用的列；
- `model_guess` 等三列只是参考，错了不用管；
- 模型猜对的直接保留，猜错的改 `label`；
- 非目标图的 `label` 统一写 `非目标`。

`label` 必须与知识库类别名一致（`GET /api/pests` 可查），也接受别名（如「蒂蛀虫」）。

## 四、跑评测

```bash
E:/python.exe tools/eval_vision.py
```

输出：

- `docs/eval-report.md`：准确率、分类别召回、混淆矩阵、误报明细、耗时
- `data/eval/report.json`：逐张明细，便于二次分析

## 五、注意

- 默认调用真实云端模型（读 `.env` 的 `VISION_*`）；没配 Key 会全部走 mock，报告会显式警告「数字不能用于答辩」。
- 每张图会调用 1~2 次模型（含二次确认），一次评测会消耗少量额度。
- 改了提示词或知识库后重跑一次，就能看出是变好还是变差——这就是最简单的回归测试。
