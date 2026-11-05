识别→处置闭环 实现计划
Context（为什么做）
当前病虫害识别是「断头路」：拍照返回识别结果后，识别记录落库但没有状态、没有处置动作、待办无法销项。 /api/todos 里「近 7 天识别 N 次」这条告警是实时聚合的，识别记录再多也不会消失，同一个告警会天天刷屏， 且评委问「识别完然后呢？」时没有答案。

目标：给识别记录加处置闭环——识别后能「按建议用药 / 人工清除 / 误判 / 忽略」，处置后待办自动消项； 选「用药」时自动写入用药台账并复用现有 CAS 校验 + 安全间隔期逻辑，形成 识别→告警→处置→销项 的闭环。

已确认：做到 H5 + 小程序 + 看板 全界面；用药处置自动写台账并回链识别。

一、后端
1. backend/db.py — 给 recognitions 加状态列
CREATE TABLE recognitions（第 68-80 行）新增列：

status            TEXT NOT NULL DEFAULT 'pending',  -- pending | handled | ignored | false_positive
handled_at        TEXT,
handle_method     TEXT,                              -- pesticide | operation | ignore | false_positive
handle_note       TEXT,
pesticide_record_id INTEGER,                        -- 用药处置时回链 pesticide_records.id
operation_id      INTEGER                            -- 农事处置时回链 farm_operations.id
在 _migrate(conn)（第 138-142 行）追加对 recognitions 的迁移块（沿用现有 PRAGMA table_info 守卫模式）：

rec_cols = {row["name"] for row in conn.execute("PRAGMA table_info(recognitions)")}
if "status" not in rec_cols:
    conn.execute("ALTER TABLE recognitions ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
    conn.execute("ALTER TABLE recognitions ADD COLUMN handled_at TEXT")
    conn.execute("ALTER TABLE recognitions ADD COLUMN handle_method TEXT")
    conn.execute("ALTER TABLE recognitions ADD COLUMN handle_note TEXT")
    conn.execute("ALTER TABLE recognitions ADD COLUMN pesticide_record_id INTEGER")
    conn.execute("ALTER TABLE recognitions ADD COLUMN operation_id INTEGER")
status NOT NULL DEFAULT 'pending'：SQLite 加列时对旧行自动回填 'pending'，旧库无需重建。 两个识别 INSERT（main.py 第 302、319 行）不写 status，自动取默认值 'pending'。

2. backend/main.py — 处置接口 + 待办过滤
(a) 新增 Pydantic 模型（放在 DemoRecognitionIn 之后）：

class RecognitionHandleIn(BaseModel):
    method: str  # pesticide | operation | ignore | false_positive
    # 用药处置（method=pesticide）
    pesticide_name: str | None = None
    cas_no: str | None = None
    dosage: str = ""
    dilution: str = ""
    application_method: str = "叶面喷雾"
    operator: str = "果农"
    apply_time: str | None = None
    days_to_harvest: int | None = None
    # 农事处置（method=operation）
    operation_type: str | None = None
    operation_date: str | None = None
    detail: dict = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    # 忽略/误判/通用备注
    note: str = ""
(b) 抽取用药写入助手：把 create_pesticide_record（第 240-273 行）里的「查登记库 + CAS 校验 + INSERT」抽成 _write_pesticide(conn, *, plot_id, pesticide_name, cas_no, dosage, dilution, application_method, operator, apply_time, days_to_harvest) -> int， 返回新记录 id；原接口与新处置接口共用，避免 CAS 校验逻辑双份维护。

(c) 新增接口：

@app.post("/api/recognitions/{rid}/handle")
def handle_recognition(rid: int, payload: RecognitionHandleIn):
    # 1. 校验 method 合法
    # 2. SELECT * FROM recognitions WHERE id=?（无则 404）
    # 3. method=pesticide：要求 rec["plot_id"] 非空 → _write_pesticide(...) 得 pesticide_record_id
    #    method=operation：要求 plot_id 非空 → INSERT farm_operations 得 operation_id
    #    method=ignore / false_positive：不写台账
    # 4. status = "handled"（pesticide/operation）| "ignored" | "false_positive"
    #    UPDATE recognitions SET status, handled_at, handle_method, handle_note, pesticide_record_id, operation_id
    # 5. 返回 {id, status, handle_method, handled_at, pesticide_record_id, operation_id}
(d) 两个识别创建接口（第 302、319 行）在返回前补 result["status"] = "pending"、result["plot_id"] = plot_id， 让前端渲染初始状态时能拿到 id/status/plot_id。

(e) /api/todos 识别告警过滤（第 517-528 行）：聚合查询加 AND status='pending'， 并把 title/detail 改成「未处置」口径，加 type: "recognition" 便于前端给按钮：

recent = conn.execute(
    "SELECT detected_class, COUNT(*) AS c FROM recognitions "
    "WHERE created_at >= ? AND detected_class != '健康叶片' AND status='pending' "
    "GROUP BY detected_class ORDER BY c DESC LIMIT 2", (...)).fetchall()
# title: f"近 7 天「{detected_class}」未处置识别 {c} 次"
# detail: "病虫害有集中发生趋势，请前往识别记录处置"
# 加 "type": "recognition", "action": "去处置"
(f) /api/dashboard/summary（第 538-569 行）新增两个字段：recognition_handled_7d、recognition_disposal_rate （近 7 天 status != 'pending' 的识别数 / 近 7 天识别总数，总数为 0 时 rate=0）。list_recognitions 用 SELECT r.* 会自动带出新列，无需改。

二、H5 frontend/mobile.html
showRecognition(r, el)（第 162-178 行）：在结果卡底部加「处置」按钮区。
存 window.__rid = r.id；s.pesticides 有值时给「按建议用药」按钮（取 s.pesticides[0] 的 name + cas_no）；
按钮：按建议用药 / 人工清除(农事) / 误判 / 忽略。
新函数 handleRecognition(method)：拼 body 后 api.post('/api/recognitions/'+window.__rid+'/handle', body)， 成功后重渲染为「已处理」badge 并禁用按钮。
loadTodos()（第 60-71 行）：渲染 i.action；当 i.type==='recognition' 时加「去处置」按钮 → switchTab('scan')。
三、小程序
miniprogram/pages/scan/scan.wxml（第 47-65 行结果卡）：加「处置」按钮组（bindtap="handleRecognition" data-method）+ 已处理 badge。
miniprogram/pages/scan/scan.js：新增 handleRecognition(e)，用 wx.showActionSheet 选处置方式， api.request('/api/recognitions/'+this.data.result.id+'/handle','POST',body)；用药时取 result.suggestion.pesticides[0]； 成功后 setData 更新 result 状态并 toast。
miniprogram/pages/todo/todo.wxml（第 28-31 行）：渲染 item.action，type==='recognition' 时加「去处置」按钮跳 scan 页； todo.js 加对应导航方法（复用现有 wx.navigateTo）。
四、看板 frontend/dashboard.html
loadSummary()（第 52-58 行）在 tiles 里加一块「识别处置率」： ${(s.recognition_disposal_rate*100).toFixed(0)}%（近 7 天已处置 / 识别总数）。

五、测试 tests/test_core.py
新增（沿用现有 ApiTest 风格）：

test_handle_recognition_writes_pesticide：先 POST /api/recognitions/demo（plot_id=1、荔枝蒂蛀虫）， 再 POST /api/recognitions/{id}/handle method=pesticide + 合法药剂名，断言返回 status=='handled'、pesticide_record_id 非空， 并 SELECT 到对应 pesticide_records 行。
test_handle_ignore_and_false_positive：method=ignore / false_positive 分别置 ignored / false_positive。
test_todos_exclude_handled：处置后 GET /api/todos 不含该「未处置识别」条目（或该害虫计数不再出现）。
六、文档
README.md：在「四个通关点对应实现」的识别行补充「识别→处置闭环」，并在「关键设计决策」加一条 「识别只给类别、处置写台账回链、待办可销项」。

验证方式
python -m unittest discover -s tests -v（现有 15 条 + 新增 3 条全绿）。
重启 python run.py，首次启动自动执行 _migrate 给旧库补列。
H5 走查：/ 拍照/演示识别 → 结果卡点「按建议用药」→ 用药台账新增一条且回链识别；待办里该害虫「未处置」计数消失；/dashboard 处置率上涨。
小程序走查：识别页 → 处置按钮 → 选「按建议用药」→ toast 成功、结果卡变「已处理」；待办页「去处置」跳识别页。
篡改演示不受影响：python tools/hash_chain_demo.py tamper LZ-P03-20260702-0001 → 溯源页红字，restore 恢复。
关键复用点
用药校验/插入：抽自 backend/main.py:create_pesticide_record（第 240-273 行），规则库 PESTICIDE_BY_NAME/PESTICIDE_BY_CAS 来自 backend/rules.py:53-54。
迁移模式：backend/db.py:_migrate（第 138-142 行）。
前端请求封装：H5 api.post（mobile.html 第 44 行）、小程序 api.request（miniprogram/utils/api.js）。