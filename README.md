# 智慧果园管家 · 从田间到餐桌

面向赛道一「智慧果园管家」的可运行原型：**微信小程序（果农端）+ Web 管理看板 + 品质溯源**。

- 后端：Python FastAPI + SQLite（零配置，无需 MySQL/Redis）
- 果农端：微信小程序（原生 WXML，`miniprogram/`）
- 管理端：原生 HTML/CSS/JS + ECharts 看板（`frontend/`）
- AI 识别：任意 OpenAI 兼容的视觉大模型（默认智谱 GLM-4.6V-Flash，免费；也可换千问 / 豆包 / 硅基流动），未配置 Key 时自动降级本地模拟，演示不中断
- 防治建议：本地农药/安全间隔期规则库生成，AI 不直出用药建议

## 四个通关点对应实现

| 赛道要求 | 实现 |
|---|---|
| 果园电子档案 | 地块分区 / 农事记录 / 用药台账 / 产量趋势（小程序「我的果园」+ 地块详情） |
| 病虫害拍照识别 | 拍照压缩上传 → 视觉大模型识别 → 规则库生成防治建议 + 安全间隔期校验；识别后可「按建议用药 / 人工清除 / 误判 / 忽略」→ 自动写台账并销项（处置闭环）；识别记录页可回看并补处置 |
| 品质溯源 | 一物一码（批次码 + 二维码），扫码展示「种植—管护—销售」三段式 + 哈希存证链；可打印批次质量合格证 |
| 农事数据看板 | 产量趋势 / 用药堆叠 / 虫害周趋势 / 虫害热力图 + 安全间隔期拦截警示 + 用药合规明细表（可导出 CSV） |

## 快速启动（后端）

```bash
cd lychee-orchard
pip install -r requirements.txt
python run.py
```

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000 | 果农端 H5（今日待办 / 我的果园 / 拍照识别 / 快速填报） |
| http://127.0.0.1:8000/dashboard | 农事数据看板（产量 / 用药 / 虫害） |
| http://127.0.0.1:8000/trace | 品质溯源（扫码或输码，含批次二维码） |
| http://127.0.0.1:8000/docs | FastAPI 接口文档 |

首次启动自动建库并写入演示种子数据（3 个地块、5 年产量、农事/用药/识别记录、4 个批次）。

## 启动微信小程序

1. 打开**微信开发者工具** → 导入项目 → 目录选择 `lychee-orchard/miniprogram`；
2. AppID 可先用「测试号 / 游客模式」；
3. 在「详情 → 本地设置」勾选 **不校验合法域名、web-view、TLS 及 HTTPS 证书**（本地 HTTP 调试必需）；
4. 保持后端已启动，编译即可。

真机预览时：

```bash
# Windows Git Bash
HOST=0.0.0.0 python run.py
```

把 `miniprogram/utils/config.js` 里的 `BASE_URL` 改成电脑的局域网 IP（如 `http://192.168.1.10:8000`），手机与电脑连同一 Wi-Fi。

## 接入真实 AI 识别

后端调用的是 **OpenAI 兼容的 `chat/completions` 接口**，任何同类服务都能直接换，不用改代码。

**默认推荐：智谱 `glm-4.1v-thinking-flash`（免费）**

1. 在[智谱开放平台](https://open.bigmodel.cn/)手机号注册 → 「API Keys」创建密钥；
2. 复制 `.env.example` 为 `.env`，填写：

```bash
VISION_API_KEY=你的智谱Key
VISION_BASE_URL=https://open.bigmodel.cn/api/paas/v4/chat/completions
VISION_MODEL=glm-4.1v-thinking-flash
VISION_FALLBACK_MODEL=glm-4.6v-flash
VISION_PROVIDER=auto
```

> - `glm-4v-flash`（旧版）**不支持 base64 传图**，不能用；
> - `glm-4.6v-flash` 实测长期返回 `1305 该模型当前访问量过大`，所以默认用 `glm-4.1v-thinking-flash`，并把它配成备选；
> - 遇到 429/1305 会自动退避重试（1.5s、3s），仍失败才切换备选模型，最后才降级本地模拟。

3. 重启后端。识别结果会标注来源「云端 AI · zhipu:glm-4.6v-flash」；
   调用失败或未配置 Key 时自动降级为本地模拟，并在结果中标注「本地模拟」。

**换其它服务商**只改 `VISION_BASE_URL` / `VISION_MODEL`：

| 服务商 | `VISION_BASE_URL` | `VISION_MODEL` |
|---|---|---|
| 智谱（免费） | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `glm-4.1v-thinking-flash` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` | `qwen-vl-plus` |
| 火山豆包 | `https://ark.cn-beijing.volces.com/api/v3/chat/completions` | 你创建的推理接入点 ID |
| 硅基流动 | `https://api.siliconflow.cn/v1/chat/completions` | `Qwen/Qwen2.5-VL-7B-Instruct` |
| 本地 Ollama | `http://127.0.0.1:11434/v1/chat/completions` | `qwen2.5vl:7b` |

个别网关要求纯 base64（不带 `data:image/jpeg;base64,` 前缀）时，设 `VISION_IMAGE_FORMAT=raw`。

> 旧变量名 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` 仍然兼容，但推荐统一用 `VISION_*`。

> 识别输出被提示词约束在知识库的 8 个类别内（荔枝蒂蛀虫、荔枝蝽、霜疫霉病、炭疽病、瘿螨、尺蠖、健康叶片、健康果实），
> 无法判断时返回「无法判断」并禁止给出用药建议。**用药建议始终由 `backend/rules.py` 规则库生成**。
>
> 三道防误报闸门：① 模型必须先写 `evidence`（看到的病斑形态）再给类别，没写出可辨识病征的病虫害结论
> 会被后端降级为「无法判断」；② 水珠、反光、果皮天然龟裂、未转色斑块明确不算病斑；
> ③ 置信度低于 65% 时只展示结果、不给自动处置建议，提示人工复核。

## 一物一码

批次编码规则（参考 GS1 结构，自建规则）：

```
LZ / P03 / 20260702 / 0001
品种  地块   采收日期    包装序号
```

- 每个批次的二维码：`GET /api/batches/{batch_no}/qrcode`（PNG）；
- 小程序「批次二维码」页可直接展示、长按保存；溯源页也会展示批次二维码；
- 默认二维码内容为溯源码本身（小程序内「扫一扫」解析）；
  配置 `.env` 的 `QR_BASE_URL=https://your-domain` 后，二维码内容变为
  `{QR_BASE_URL}/trace?code=xxx`，消费者用微信扫码可直接打开 H5 溯源页。

### 哈希链校验（防篡改）

每次写入存证时，原文一并存入 `trace_hash_log.payload_json`：

- `record_hash = SHA-256(原文 + 上一条哈希)`，逐条首尾相连；
- 校验时按原文重算，任何一条被改动都会断链，并定位到具体记录 ID。

| 接口 | 说明 |
|---|---|
| `GET /api/trace/{code}` | 返回 `chain_verify`：`valid`、`total`、`tampered`、`broken`、`legacy` |
| `GET /api/trace-verify` | 全链校验结果 |

溯源页与小程序会在「哈希存证链」旁显示徽章：`✅ 链校验通过 · N 条` 或 `❌ 链校验失败 · 第 N 条`。

**现场演示**（工具会自动备份原值）：

```bash
python tools/hash_chain_demo.py tamper LZ-P03-20260702-0001
# 刷新 /trace?code=LZ-P03-20260702-0001 → 徽章变红并指出第几条
python tools/hash_chain_demo.py restore
# 刷新 → 恢复「链校验通过」
```

注意：单机哈希链只能证明「存证写入后未被修改」，不能证明录入时数据本身为真；更强证明需把链头对外锚定（印在合格证或第三方存证）。另外，当前链覆盖的是写入时的存证快照，直接改农事/用药业务表不会让链断——若要覆盖到业务明细，需要把明细一并写入存证并按批次对账。

### 批次质量合格证

溯源页（`/trace?code=...`）查询成功后，底部有「打印合格证 / 保存为 PDF」：

- 合格证独立于页面展示，打印时只输出这一页（A4 纵向），带批次二维码、产地、采收日期、农残检测、用药记录与安全间隔期状态、哈希链校验结果、签字栏；
- 被拦截的批次会印上红色「已拦截 · 不得销售」并附拦截原因，可直接打印给收购商看复核结果。

## 加分项

### 天气联动预警（免 Key）

`backend/weather.py` 调用 [Open-Meteo](https://open-meteo.com/) 未来 3 天预报（降雨量 / 降雨概率 / 逐小时湿度），
判断是否利于「荔枝霜疫霉病」发生；有风险时在 `/api/todos` 里追加一条预警待办，并附「雨前预防」建议。

- 结果缓存 30 分钟、超时 3 秒、任何异常静默跳过——断网时只是少一条待办，不会拖慢接口；
- `.env` 中 `WEATHER_ENABLED=0` 可整体关闭（测试默认关闭）；`WEATHER_LAT` / `WEATHER_LON` / `WEATHER_LOCATION` 可换果园位置；
- 单独查看：`GET /api/weather/pest-risk`。

### 用药合规明细 + CSV

`/dashboard` 新增「用药合规明细（安全间隔期）」表：每行给出最早可采日、剩余天数与状态；
右上角「导出 CSV」下载全量明细（UTF-8 BOM，Excel 打开不乱码），可直接交给收购商或监管抽查。

- 接口：`GET /api/dashboard/compliance`、`GET /api/dashboard/compliance.csv`。

### 识别记录页

小程序「拍照识别」页与 H5 拍照页底部都有「识别记录」，按未处置优先排列：

- 待办里的「去处置」会直接跳到识别记录区，点开未处置记录即可按建议处置；
- 处置成功后列表状态同步刷新，不再出现「点了去处置却找不到记录」的断点。

### 适老化大字模式

- H5 果农端顶栏「大字」按钮，切换后写入 `localStorage`，刷新保持；页面同时允许双指缩放；
- 小程序「今日待办」顶部有一个「大字模式」开关，存本地存储，所有页面进入时读取并整体放大字号。

## 30 秒演示脚本

1. **电子档案** — 小程序「我的果园」：果树分区示意图 + 地块档案；进入地块看农事记录、用药台账、产量趋势。
2. **病虫害识别 + 处置闭环** — 「拍照识别」拍一张叶片（或演示模式选类别）→ 返回类别、置信度、防治建议；
   输入「距采收 5 天」会看到安全间隔期过滤药剂的告警；系统会高亮建议处置并说明理由
   （如「距采收 5 天，药剂来不及过间隔期 → 建议人工清除」）；点「按建议用药」自动写用药台账并回链本次识别，
   待办里的「未处置识别」随之销项；也可选「人工清除 / 误判 / 忽略」。
3. **品质溯源** — 「批次二维码」生成/展示二维码 → 扫码或输入 `LZ-P03-20260702-0001`（已放行）
   与 `LZ-P01-20260708-0002`（已拦截），对比三段式溯源与哈希存证链；存证链旁显示「链校验通过 · N 条」。
   可选加分演示：改一条存证原文 → 刷新页面 → 徽章变红并指出第几条被篡改。
   再点「打印合格证」→ 打印预览里只有一页合格证；拦截批次带红色「已拦截 · 不得销售」。
4. **数据看板** — 打开 `/dashboard`：产量趋势、用药堆叠、虫害趋势、虫害热力图与拦截警示卡片；
   下方「用药合规明细」表逐条列出最早可采日，点「导出 CSV」可下载给收购商。
5. **加分演示** — 待办里的「去处置」直达未处置识别记录（识别→处置→销项闭环完整）；
   联网时待办会出现「天气预警：未来利于霜疫霉病发生」；点顶栏「大字」切换适老化字号。

## 目录结构

```
lychee-orchard/
├── run.py                  # 一键启动（HOST/PORT 可配）
├── requirements.txt
├── .env.example            # AI Key / 二维码地址配置模板
├── backend/
│   ├── main.py             # FastAPI 路由（档案/识别/溯源/二维码/看板）
│   ├── config.py           # .env + 环境变量
│   ├── db.py               # SQLite 建表与连接
│   ├── rules.py            # 农药库 + 病虫害知识库 + 防治建议规则引擎
│   ├── ai_service.py       # Qwen-VL / 自定义 API / 本地模拟三级识别
│   ├── traceability.py     # 批次编码 + 哈希链存证
│   ├── weather.py          # Open-Meteo 天气 → 霜疫霉病风险（缓存 + 静默降级）
│   └── seed.py             # 演示种子数据
├── miniprogram/            # 微信小程序（果农端）
│   ├── pages/todo|plots|plot|scan|form|trace|batches/
│   └── utils/config.js     # 后端地址（真机预览改这里）
│       utils/font.js       # 大字模式偏好（本地存储）
├── frontend/
│   ├── mobile.html         # H5 果农端（与小程序功能对齐，备用演示）
│   ├── dashboard.html      # 数据看板（ECharts）
│   ├── trace.html          # 品质溯源页（含二维码）
│   └── css/app.css
├── static/                 # echarts.min.js + 上传图片
└── data/                   # SQLite 数据库文件（自动生成）
```

## 关键设计决策

1. **识别只给类别，用药走规则库**：AI 结果不直接变成用药建议，避免超范围用药；临近采收自动过滤长间隔期药剂。
   识别后必须落处置（用药 / 人工清除 / 误判 / 忽略），用药处置复用台账校验并回链识别，待办销项——形成「识别→处置→销项」闭环。
   系统还会按「风险等级 + 距采收天数 + 合规药剂」给出**建议处置及理由**并高亮对应按钮，果农确认或改选，避免让用户自己判断。
2. **安全间隔期自动驱动放行**：批次创建时校验该地块全部用药记录，未过间隔期的批次状态为 `blocked`，不生成销售溯源码。
3. **哈希链存证**：批次关键节点（种植/管护/销售）写入追加式哈希日志，每条携带上一条哈希；原文一并入库，校验时逐条重算，改任一条即断链并可定位到记录 ID。
4. **能砍则砍**：不引入时序库、消息队列、区块链；单库 + 单进程即可完整演示。

## 常见问题

- **小程序请求失败**：确认后端已启动、`utils/config.js` 地址正确，并在开发者工具关闭域名校验。
- **识别显示「本地模拟」**：未配置 `VISION_API_KEY` 或云端调用失败，检查 `.env` 后重启；后端日志里会有降级原因（如 `mock_fallback(HTTPStatusError)`）。
- **云端返回 400 / 1210**：优先检查模型是否支持 base64 传图（`glm-4v-flash` 不支持，用 `glm-4.6v-flash`），以及 `VISION_BASE_URL` 是否为 OpenAI 兼容端点。
- **二维码在手机上打不开 H5**：默认二维码内容是溯源码本身；需要 H5 链接时配置 `QR_BASE_URL`，且该域名需公网可访问。
