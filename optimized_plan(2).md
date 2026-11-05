Ready for review
Select text to add comments on the plan
加分项功能 实现计划
Context（为什么做）
四个通关点已完整，但演示时仍有三类短板：

闭环有一个洞：识别后的处置按钮只存在于「刚识别完的结果卡」上。关掉页面后，待办里的「去处置」只会 switchTab 到拍照页，落地是一个空白页，找不到那条未处置记录。评审照着待办点一次就能试出来。
数据只停在页面上：用药合规、安全间隔期这些数据散落在待办和地块详情里，看板没有一张能交给收购商/监管的明细表，也没有导出；溯源页没有可打印的凭证。
场景贴合度：赛道面向果农，缺少大字模式；天气与霜疫霉病的关系没有体现，只能「事后识别」不能「事前预防」。
本轮把用户确认的 5 项一起做：看板合规明细 + CSV、批次合格证打印、天气联动预警、适老化大字模式、识别记录页。

已确认范围：全部 5 项；合格证打印仅 H5（小程序不支持 window.print）。

顺带修一个真实 bug：frontend/dashboard.html 的 loadSummary() 用了 $('#tiles')，但该文件从未定义 $。现在看板的统计卡片和警示块其实一直没渲染出来（四个图表正常，因为它们不用 $）。这次加 $ 定义，否则新增的明细表也会一起失效。

一、后端
1. 天气联动（新文件 backend/weather.py）
用 Open-Meteo（免 Key、无需注册）拉未来 3 天预报，失败静默返回 None。

# backend/weather.py
_CACHE = {"at": 0.0, "data": None}
_TTL = 30 * 60  # 30 分钟内存缓存，避免每次 /api/todos 都打外网

def _fetch_forecast() -> dict | None:
    # GET https://api.open-meteo.com/v1/forecast
    # ?latitude=..&longitude=..&daily=precipitation_sum,relative_humidity_2m_max
    #  &timezone=Asia/Shanghai&forecast_days=3
    # httpx.get(..., timeout=config.WEATHER_TIMEOUT)，任何异常返回 None

def get_forecast() -> dict | None:
    # 命中缓存直接返回；WEATHER_ENABLED 为关闭时返回 None

def rain_risk(data: dict | None) -> dict | None:
    # 未来 3 天中降雨日 >= 2（单日 >= 5mm）或最大湿度 >= 92% → 返回
    # {"wet_days": int, "total_mm": float, "max_humidity": int}
    # 否则 None
backend/config.py 末尾追加（沿用现有 os.environ.get 模式）：

WEATHER_ENABLED = os.environ.get("WEATHER_ENABLED", "1").strip().lower() not in ("0", "false", "off")
WEATHER_LAT = os.environ.get("WEATHER_LAT", "23.55").strip()
WEATHER_LON = os.environ.get("WEATHER_LON", "113.58").strip()
WEATHER_PLACE = os.environ.get("WEATHER_PLACE", "从化区").strip()
WEATHER_TIMEOUT = float(os.environ.get("WEATHER_TIMEOUT", "3"))
.env.example 增加对应注释块（默认值即从化区，用户不需要改）。

backend/main.py 的 todos()（第 609-663 行）在识别告警之后追加一条：

from .weather import get_forecast, rain_risk
risk = rain_risk(get_forecast())
if risk:
    items.append({
        "level": "warning",
        "type": "weather",
        "title": f"未来 3 天{config.WEATHER_PLACE}有降雨（{risk['wet_days']} 天约 {risk['total_mm']}mm），霜疫霉病风险升高",
        "detail": "荔枝霜疫霉病在连续阴雨高湿时易流行，建议雨前预防并加强巡园。",
        "action": "去拍照识别",
    })
前端待办已经会渲染 action 文本，无需改渲染逻辑。关键约束：/api/todos 是同步接口，天气必须「缓存 + 3 秒超时 + 全异常捕获」，断网时只是少一条待办，不能拖慢或拖垮接口。

测试隔离：tests/test_core.py 顶部环境变量里加 os.environ["WEATHER_ENABLED"] = "0"，现有 20 条测试不会碰网络。

2. 看板合规明细 + CSV（backend/main.py）
新增一个行构造助手（紧挨 check_safety 之后），复用地块/台账表：

def _compliance_rows(conn, limit: int = 100) -> list[dict]:
    # SELECT r.*, p.name AS plot_name FROM pesticide_records r
    # JOIN plots p ON p.id=r.plot_id ORDER BY r.apply_time DESC, r.id DESC LIMIT ?
    # 对每行：
    #   earliest = _parse_date(apply_time) + timedelta(days=safe_interval_days)
    #   remaining = (earliest - date.today()).days
    #   返回 {id, plot_id, plot_name, pesticide_name, cas_no, operator,
    #         apply_time, safe_interval_days, earliest_harvest_date,
    #         days_remaining: max(remaining, 0),
    #         status: "ok" if remaining <= 0 else "waiting"}
earliest_harvest_date 没有入库，_write_pesticide（第 121 行）只在返回时临时算过；这里按同一公式重算，避免加列迁移。

新增两个接口（放在 dashboard 区块，第 669 行之前或之后均可）：

@app.get("/api/dashboard/compliance")
def dashboard_compliance(limit: int = Query(50, le=200)):
    with get_conn() as conn:
        return _compliance_rows(conn, limit)

@app.get("/api/dashboard/compliance.csv")
def dashboard_compliance_csv(limit: int = Query(200, le=500)):
    # 用 csv.writer 写 io.StringIO（io 已导入，需新增 import csv）
    # 表头：地块,药剂,CAS,施药日期,操作人,安全间隔期(天),最早可采收日,剩余天数,状态
    # 正文前加 "\ufeff"（Excel 中文不乱码），UTF-8 编码
    # return Response(..., media_type="text/csv; charset=utf-8",
    #     headers={"Content-Disposition": 'attachment; filename="pesticide-compliance.csv"'})
3. 溯源接口扩展（backend/main.py 的 get_trace，第 540-597 行）
目前 care 只返回 pesticide_count 和 last_pesticide，合格证需要完整用药列表。新增查询并按同公式算最早可采日：

pesticides = rows_to_dicts(conn.execute(
    "SELECT pesticide_name, cas_no, operator, apply_time, safe_interval_days "
    "FROM pesticide_records WHERE plot_id=? AND apply_time <= ? "
    "ORDER BY apply_time DESC LIMIT 12",
    (batch["plot_id"], batch["harvest_date"])).fetchall())
for p in pesticides:
    p["earliest_harvest_date"] = (
        _parse_date(p["apply_time"]) + timedelta(days=int(p["safe_interval_days"] or 0))
    ).isoformat()
放进 care："pesticides": pesticides。其余字段保持不变，向后兼容。

二、看板 frontend/dashboard.html + frontend/css/app.css
修 bug：在第 50 行后加
const $ = s => document.querySelector(s);
HTML 在图表区之前加一张卡：
<div class="chart-card">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
    <h3>用药合规明细（安全间隔期）</h3>
    <a class="btn ghost small" href="/api/dashboard/compliance.csv">导出 CSV</a>
  </div>
  <div class="table-wrap" id="compliance"><div class="muted small">加载中…</div></div>
</div>
新增 loadCompliance()：GET /api/dashboard/compliance?limit=50，渲染 <table class="data-table">： 地块 / 药剂 / 施药日 / 间隔期 / 最早可采日 / 剩余天数 / 状态 pill（ok → good「已合规」，waiting → critical「间隔期内」）。
renderAll()（第 130 行）里加 loadCompliance()。
frontend/css/app.css 新增表格样式（目前整个仓库没有任何 table 规则）：
.table-wrap { overflow-x: auto; }
.data-table { width:100%; border-collapse: collapse; font-size: 13.5px; }
.data-table th, .data-table td { padding: 9px 10px; text-align: left;
  border-bottom: 1px solid var(--gridline); white-space: nowrap; }
.data-table th { color: var(--muted); font-weight: 600; font-size: 12.5px; }
.data-table tr:hover td { background: var(--surface-2, rgba(0,0,0,.02)); }
三、批次合格证打印 frontend/trace.html + app.css
在 #traceResult 外面加一个打印容器：
<div id="certificate" class="certificate"></div>
loadTrace() 成功后填充 #certificate（与页面展示分离，避免打印时重复）：标题「荔枝产品质量合格证」、批次码/溯源码、状态、二维码（复用 /api/batches/{batch_no}/qrcode，打印尺寸 120px）、种植信息、用药记录表（t.care.pesticides）、安全间隔期状态、农残检测/包装、哈希链徽章或 链校验失败、签字栏。
t.status !== 'released' 时在合格证顶部加红色「已拦截 · 不得销售」和 block_reason，仍然允许打印（用于演示拦截结果）。
t.care.pesticides 为空时显示「无用药记录」。
结果卡里加一个 .no-print 按钮：<button class="btn ghost small" onclick="window.print()">打印合格证</button>。
app.css 加打印规则：
@media print {
  @page { size: A4; margin: 12mm; }
  body { background:#fff; }
  .topbar, #searchBox, #traceResult, .no-print { display:none !important; }
  #certificate { display:block !important; }
  .certificate { box-shadow:none; border:1px solid #999; }
}
.certificate { display:none; }
#traceResult 里包含页面展示内容，打印时整体隐藏；合格证是独立节点，不会重复。

四、识别记录页（H5 + 小程序）
后端 GET /api/recognitions（第 377 行）已经返回 r.*（含 suggestion_json 字符串和 status），无需改接口。

H5 frontend/mobile.html
renderScan()（第 126-150 行）末尾加一张卡：
<div class="card" id="historyCard">
  <h2>识别记录 <button class="btn ghost small" onclick="loadRecognitionHistory()">刷新</button></h2>
  <div id="recognitionHistory"><span class="muted small">加载中…</span></div>
</div>
loadPests() 末尾调用 loadRecognitionHistory()。
新增：
parseSuggestion(r)：优先用 r.suggestion，否则 JSON.parse(r.suggestion_json || '{}')，异常返回 {}。
recognitionCache：id → 记录，供点击展开。
loadRecognitionHistory()：GET /api/recognitions?limit=20，未处置排前面，每行显示类别、置信度、时间、状态 pill；点击调 showHistoryRecognition(id)。
showHistoryRecognition(id)：把缓存记录补上 suggestion 后调用现有 showRecognition(r, $('#scanResult'))，并 scrollIntoView 到结果卡。复用现有处置按钮逻辑，不复制。
handleRecognition() 成功后追加 loadRecognitionHistory()，让列表状态同步。
待办的「去处置」改为 onclick="goRecognition()"：
function goRecognition(){
  window._focusHistory = true;
  switchTab('scan');
}
loadRecognitionHistory() 渲染完后若 window._focusHistory，滚动到 #historyCard 并清除标记。
小程序 pages/scan/*、pages/todo/todo.js
scan.js：
data 增加 history: []。
onShow() 里调用 this.loadHistory()。
loadHistory()：GET /api/recognitions?limit=20，解析 suggestion_json，补充 confidencePct、statusText、pending、timeText，未处置置顶。
openHistory(e)：取 history[index]；若 pending，this.setData({ result: decorate(row), handling: false }) 并 wx.pageScrollTo({ scrollTop: 0 })；已处置则 toast 提示。
处置成功后调用 this.loadHistory()。
scan.wxml 在演示卡片后加「识别记录」卡（id="historyCard"），wx:for 渲染，点击 openHistory，状态用 pill。
todo.js 的 goScan()：wx.setStorageSync('focusHistory', true) 后 wx.switchTab。scan 的 loadHistory() 完成后若读到该标记，清除并 wx.pageScrollTo({ selector: '#historyCard', duration: 200 })（包 try/catch 兜底）。
todo.wxml 第 31 行的「去处置」保持调用 goScan 即可。
五、适老化大字模式
H5 frontend/mobile.html + frontend/css/app.css
topbar 加按钮（.topbar 是 flex，第三个控件布局安全）：
<button class="pill neutral" id="fontToggle" onclick="toggleFont()">大字</button>
viewport 改回可缩放：maximum-scale=5.0, user-scalable=yes（当前是 user-scalable=no，与适老化冲突）。
新增：
function applyFont(){
  const on = localStorage.getItem('fontLarge') === '1';
  document.documentElement.classList.toggle('font-lg', on);
  const b = document.getElementById('fontToggle');
  if (b) b.textContent = on ? '标准' : '大字';
}
function toggleFont(){
  const on = document.documentElement.classList.toggle('font-lg');
  localStorage.setItem('fontLarge', on ? '1' : '0');
  applyFont();
}
applyFont();  // 初始化时调用
app.css 增加一组 html.font-lg 覆盖（只调字号，不动布局）：
html.font-lg body { font-size: 18px; }
html.font-lg .topbar h1 { font-size: 21px; }
html.font-lg .topbar .sub { font-size: 15px; }
html.font-lg .card h2 { font-size: 18px; }
html.font-lg .pill { font-size: 14px; }
html.font-lg .list-item .li-title { font-size: 17px; }
html.font-lg .li-desc { font-size: 15px; }
html.font-lg label.field { font-size: 16px; }
html.font-lg input, html.font-lg select { font-size: 17px; }
html.font-lg button.btn { font-size: 17px; }
html.font-lg .btn.small { font-size: 15px; }
html.font-lg .alert { font-size: 16px; }
html.font-lg .al-title { font-size: 17px; }
html.font-lg .al-detail { font-size: 15px; }
html.font-lg .kv { font-size: 16px; }
html.font-lg .small { font-size: 14px; }
html.font-lg .tabbar button { font-size: 14px; }
html.font-lg .tabbar button .ico { font-size: 24px; }
html.font-lg .tile .t-val { font-size: 30px; }
html.font-lg .t-label { font-size: 15px; }
html.font-lg .trace-hero .t-code { font-size: 20px; }
小程序
新文件 miniprogram/utils/font.js：
const KEY = 'fontLarge';
const isLarge = () => !!wx.getStorageSync(KEY);
const fontClass = () => (isLarge() ? 'font-lg' : '');
const setLarge = v => wx.setStorageSync(KEY, !!v);
const toggle = () => { const v = !isLarge(); setLarge(v); return v; };
module.exports = { isLarge, fontClass, setLarge, toggle };
7 个页面（todo/plots/plot/scan/form/trace/batches）：
const font = require('../../utils/font');
data 加 fontClass: ''（todo 另加 bigFont: false）；
onShow（plot/trace 用 onLoad）里 this.setData({ fontClass: font.fontClass() })；
WXML 根节点改成 <view class="wrap {{fontClass}}">。
todo 页加载后显示开关卡：
<view class="card">
  <view class="kv" style="align-items:center">
    <view>
      <view class="h2" style="margin:0">大字模式</view>
      <view class="small muted">放大字号，方便田间查看</view>
    </view>
    <switch checked="{{bigFont}}" color="#1f6f4a" bindchange="onFontToggle" />
  </view>
</view>
todo.js 的 onShow 同步 bigFont，onFontToggle(e) 调 font.setLarge(e.detail.value) 并 setData。
app.wxss 末尾加 .font-lg 覆盖（后代选择器特异性高于页面级单类选择器，能压过各页 wxss）：
.font-lg { font-size: 34rpx; }
.font-lg .h2 { font-size: 36rpx; }
.font-lg .small { font-size: 29rpx; }
.font-lg .pill { font-size: 27rpx; }
.font-lg .al-detail { font-size: 31rpx; }
.font-lg .btn { font-size: 36rpx; }
.font-lg .btn.small { font-size: 31rpx; }
.font-lg .field .label { font-size: 31rpx; }
.font-lg .field input, .font-lg .field .picker-value { font-size: 33rpx; }
.font-lg .hero-title { font-size: 45rpx; }
.font-lg .hero-sub { font-size: 29rpx; }
.font-lg .quick-item { font-size: 29rpx; }
.font-lg .quick-item .qi { font-size: 48rpx; }
.font-lg .empty { font-size: 31rpx; }
.font-lg .b-code { font-size: 36rpx; }
.font-lg .b-meta { font-size: 29rpx; }
.font-lg .t-code { font-size: 41rpx; }
.font-lg .hist-title { font-size: 32rpx; }
.font-lg .hist-meta { font-size: 26rpx; }
六、测试 tests/test_core.py
顶部环境变量加 os.environ["WEATHER_ENABLED"] = "0"。
新增：
test_compliance_endpoint：GET /api/dashboard/compliance；断言字段齐全；对每行校验 earliest_harvest_date == apply_time + safe_interval_days、days_remaining 非负、status 取值。
test_compliance_csv：GET /api/dashboard/compliance.csv；断言 200、content-type 含 text/csv、正文以 BOM 开头、表头含「地块」「安全间隔期」。
test_weather_risk_rules：直接测 rain_risk()——连续两天降雨返回风险；全是晴天返回 None；None 输入返回 None。
test_todos_without_weather：WEATHER_ENABLED=0 时 /api/todos 200，且没有 type == "weather" 的项。
test_trace_has_pesticide_list：GET /api/trace/LZ-P03-20260702-0001；断言 care.pesticides 是列表，元素含 earliest_harvest_date。
现有 20 条必须继续全绿。
七、文档
README.md：
通关点表格「农事数据看板」后补合规明细与 CSV；「品质溯源」补合格证打印；「病虫害识别」补识别记录页；
新增「天气预警（可选）」小节，说明 Open-Meteo 免 Key、WEATHER_ENABLED=0 可关闭、断网静默；
「适老化」一句话说明大字模式；
演示脚本加一句「打印合格证」和「大字模式」。
.env.example：追加 WEATHER_* 注释块。
验证方式
PYTHONIOENCODING=utf-8 E:/python.exe -m unittest discover -s tests -v → 20 + 新增全绿。
重启服务（先 TaskStop 现有后台任务，再 E:/python.exe run.py），确认 _migrate 不受影响（本轮无需迁移）。
API 冒烟（Windows 中文用 Python urllib.request，不要用 curl）：
/api/dashboard/compliance 字段与计算正确；
/api/dashboard/compliance.csv 返回 CSV 且 Excel 打开中文正常；
/api/trace/LZ-P03-20260702-0001 含 care.pesticides；
WEATHER_ENABLED=0 时 /api/todos 不含天气项；联网时手动打开开关能看到天气项。
H5 走查：
/dashboard：统计卡片恢复显示（$ 修复）、合规表出现、点「导出 CSV」能下载；
/trace?code=LZ-P03-20260702-0001：点「打印合格证」→ 打印预览里只有合格证，无 topbar/搜索框；拦截批次显示红字；
/：拍照页能看到识别记录，点未处置记录能展开处置；待办「去处置」会滚到记录区；topbar「大字」切换后刷新仍保持。
小程序：node --check 检查改动过的 JS；开发者工具里走「待办 → 去处置 → 打开未处置记录 → 处置」「大字模式开关 → 切页后仍生效」。
回归：哈希链篡改演示照旧可用（python tools/hash_chain_demo.py tamper ... → 红字 → restore）。
风险与注意
天气不能拖垮接口：/api/todos 是同步的，必须 30 分钟缓存 + 3 秒超时 + 全异常捕获；测试里 WEATHER_ENABLED=0。Open-Meteo 在部分网络下不可达属预期，静默跳过。
打印 CSS：合格证必须是 #traceResult 之外的独立节点，否则 display:none 会把合格证一起隐藏；打印前二维码 <img> 需已加载。
WXSS 特异性：.font-lg .x 高于页面级 .x，所以集中写在 app.wxss 即可；不要用 !important。
dashboard $ bug：先修再动看板，否则新增卡片也不会渲染。
识别记录：suggestion_json 是字符串，必须解析；老记录可能为空，解析失败要兜底成 {}，不能让整个列表崩。
CSV：必须带 UTF-8 BOM，否则 Excel 打开中文乱码；文件名用 ASCII，避免响应头编码问题。
不引入新依赖、不加 DB 迁移：httpx、csv、io 都是现成可用的。
Add Comment