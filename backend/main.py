"""FastAPI 应用：果园电子档案 + 病虫害识别 + 品质溯源 + 数据看板。"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai_service, config, weather
from .db import get_conn, init_db, rows_to_dicts
from .rules import (
    PESTICIDES, PESTICIDE_BY_CAS, PESTICIDE_BY_NAME, PESTS, build_suggestion,
    validate_knowledge,
)
from .seed import seed_if_empty
from .traceability import append_hash, make_batch_no, verify_chain

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="智慧果园管家 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    seed_if_empty()
    problems = validate_knowledge()
    if problems:  # 只告警不阻断：数据笔误不能把演示环境拖垮
        logger.warning("知识库自检发现 %d 个问题：%s", len(problems), "；".join(problems))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PlotIn(BaseModel):
    code: str
    name: str
    variety: str
    area_mu: float
    tree_count: int
    planting_year: int
    location: str = ""


class OperationIn(BaseModel):
    plot_id: int
    operation_type: str
    operator: str = "果农"
    operation_date: str | None = None
    detail: dict = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)


class PesticideRecordIn(BaseModel):
    plot_id: int
    pesticide_name: str
    cas_no: str | None = None
    dosage: str = ""
    dilution: str = ""
    application_method: str = "叶面喷雾"
    operator: str = "果农"
    apply_time: str | None = None
    days_to_harvest: int | None = None


class BatchIn(BaseModel):
    plot_id: int
    harvest_date: str
    packaging_seq: int = 1


class DemoRecognitionIn(BaseModel):
    pest_class: str
    plot_id: int | None = None
    confidence: float = 0.92
    days_to_harvest: int | None = None


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
    # 忽略 / 误判 / 通用备注
    note: str = ""


class WeatherRegionIn(BaseModel):
    name: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _today() -> str:
    return date.today().isoformat()


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, f"日期格式应为 YYYY-MM-DD：{value}")


def _write_pesticide(
    conn, *, plot_id: int, pesticide_name: str, cas_no: str | None = None,
    dosage: str = "", dilution: str = "", application_method: str = "叶面喷雾",
    operator: str = "果农", apply_time: str | None = None, days_to_harvest: int | None = None,
) -> dict:
    """写入一条用药台账（含登记库/CAS 校验与安全间隔期计算），返回台账摘要。

    供「直接填报用药」与「识别→用药处置」两条路径共用，避免校验逻辑重复。
    """
    _plot_or_404(conn, plot_id)
    known = PESTICIDE_BY_CAS.get(cas_no or "") or PESTICIDE_BY_NAME.get(pesticide_name)
    if not known:
        raise HTTPException(
            400,
            "农药名称/CAS 编号未在登记库中找到，请核对包装信息后重试（防录错校验）",
        )
    if cas_no and known["cas_no"] != cas_no:
        raise HTTPException(400, f"CAS 编号与农药「{known['name']}」不匹配，请核对")

    apply_time = apply_time or _today()
    safe_days = known["safe_interval_days"]
    cur = conn.execute(
        "INSERT INTO pesticide_records(plot_id, pesticide_name, cas_no, dosage, dilution, "
        "application_method, operator, apply_time, safe_interval_days, target_pest, days_to_harvest, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (plot_id, known["name"], known["cas_no"], dosage or known["dosage_hint"],
         dilution, application_method, operator, apply_time,
         safe_days, "、".join(known["targets"]), days_to_harvest,
         datetime.now().isoformat(timespec="seconds")),
    )
    harvest_after = (_parse_date(apply_time) + timedelta(days=safe_days)).isoformat()
    return {
        "id": cur.lastrowid,
        "pesticide_name": known["name"],
        "cas_no": known["cas_no"],
        "safe_interval_days": safe_days,
        "earliest_harvest_date": harvest_after,
        "warning": f"安全间隔期 {safe_days} 天，{harvest_after} 之后方可采收",
    }


def check_safety(conn, plot_id: int, harvest_date: str) -> dict:
    """计算该地块在指定采收日是否满足所有用药的安全间隔期。"""
    hd = _parse_date(harvest_date)
    rows = conn.execute(
        "SELECT * FROM pesticide_records WHERE plot_id=? ORDER BY apply_time DESC", (plot_id,)
    ).fetchall()
    for r in rows:
        applied = _parse_date(r["apply_time"])
        elapsed = (hd - applied).days
        remain = r["safe_interval_days"] - elapsed
        if remain > 0:
            return {
                "safe": False,
                "remaining_days": remain,
                "last_application": dict(r),
                "message": (
                    f"{r['apply_time']} 施用「{r['pesticide_name']}」，"
                    f"安全间隔期 {r['safe_interval_days']} 天，"
                    f"距采收日仅 {elapsed} 天，还需等待 {remain} 天"
                ),
            }
    return {"safe": True, "remaining_days": 0, "last_application": dict(rows[0]) if rows else None,
            "message": "所有用药均已过安全间隔期，可采收"}


def _compliance_row(rec: dict, as_of: date | None = None) -> dict:
    """把一条用药台账换算成合规明细：最早可采日 + 剩余天数 + 状态。"""
    try:
        earliest = _parse_date(rec["apply_time"]) + timedelta(days=int(rec["safe_interval_days"] or 0))
        remaining = (earliest - (as_of or date.today())).days
    except (HTTPException, ValueError, TypeError):
        # 历史脏数据不能让整张表 500，单独标记出来
        return {
            **rec,
            "earliest_harvest_date": "",
            "days_remaining": None,
            "safe": False,
            "status": "unknown",
            "compliance_label": "日期异常",
        }
    return {
        **rec,
        "earliest_harvest_date": earliest.isoformat(),
        "days_remaining": max(remaining, 0),
        "safe": remaining <= 0,
        "status": "ok" if remaining <= 0 else "waiting",
        "compliance_label": "已过安全间隔期" if remaining <= 0 else f"还需 {remaining} 天",
    }


def _compliance_rows(conn, plot_id: int | None = None, limit: int = 200) -> list[dict]:
    sql = ("SELECT r.*, p.name AS plot_name FROM pesticide_records r "
           "JOIN plots p ON p.id=r.plot_id ")
    args: tuple = ()
    if plot_id:
        sql += "WHERE r.plot_id=? "
        args = (plot_id,)
    sql += "ORDER BY r.apply_time DESC, r.id DESC LIMIT ?"
    rows = rows_to_dicts(conn.execute(sql, (*args, limit)).fetchall())
    today = date.today()
    return [_compliance_row(r, today) for r in rows]


def _csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    """生成带 UTF-8 BOM 的 CSV（Excel 打开中文不乱码）。"""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    body = (chr(0xFEFF) + buf.getvalue()).encode("utf-8")
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _qr_payload(trace_code: str) -> str:
    """二维码内容：配置了 QR_BASE_URL 则为 H5 溯源链接，否则为溯源码本身。"""
    base = config.QR_BASE_URL.rstrip("/")
    return f"{base}/trace?code={trace_code}" if base else trace_code


def _qr_png(data: str) -> bytes:
    import qrcode

    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _plot_or_404(conn, plot_id: int) -> dict:
    row = conn.execute("SELECT * FROM plots WHERE id=?", (plot_id,)).fetchone()
    if not row:
        raise HTTPException(404, "地块不存在")
    return dict(row)


# ---------------------------------------------------------------------------
# 地块与档案
# ---------------------------------------------------------------------------
@app.get("/api/plots")
def list_plots():
    with get_conn() as conn:
        plots = rows_to_dicts(conn.execute("SELECT * FROM plots ORDER BY code").fetchall())
        for p in plots:
            p["safety"] = check_safety(conn, p["id"], _today())
        return plots


@app.get("/api/plots/{plot_id}")
def get_plot(plot_id: int):
    with get_conn() as conn:
        plot = _plot_or_404(conn, plot_id)
        plot["operations"] = rows_to_dicts(conn.execute(
            "SELECT * FROM farm_operations WHERE plot_id=? ORDER BY operation_date DESC LIMIT 30",
            (plot_id,)).fetchall())
        plot["pesticides"] = rows_to_dicts(conn.execute(
            "SELECT * FROM pesticide_records WHERE plot_id=? ORDER BY apply_time DESC LIMIT 20",
            (plot_id,)).fetchall())
        plot["yields"] = rows_to_dicts(conn.execute(
            "SELECT * FROM yield_records WHERE plot_id=? ORDER BY season", (plot_id,)).fetchall())
        plot["safety"] = check_safety(conn, plot_id, _today())
        return plot


@app.post("/api/plots")
def create_plot(payload: PlotIn):
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO plots(code, name, variety, area_mu, tree_count, planting_year, location, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (payload.code, payload.name, payload.variety, payload.area_mu, payload.tree_count,
                 payload.planting_year, payload.location, datetime.now().isoformat(timespec="seconds")),
            )
        except Exception:
            raise HTTPException(400, "地块编号已存在")
        return {"id": cur.lastrowid, **payload.model_dump()}


@app.get("/api/operations")
def list_operations(plot_id: int | None = None, limit: int = Query(50, le=500)):
    with get_conn() as conn:
        sql = ("SELECT o.*, p.name AS plot_name FROM farm_operations o "
               "JOIN plots p ON p.id=o.plot_id ")
        args: tuple = ()
        if plot_id:
            sql += "WHERE o.plot_id=? "
            args = (plot_id,)
        sql += "ORDER BY o.operation_date DESC LIMIT ?"
        return rows_to_dicts(conn.execute(sql, (*args, limit)).fetchall())


@app.post("/api/operations")
def create_operation(payload: OperationIn):
    with get_conn() as conn:
        _plot_or_404(conn, payload.plot_id)
        op_date = payload.operation_date or _today()
        cur = conn.execute(
            "INSERT INTO farm_operations(plot_id, operation_type, operator, operation_date, detail, images, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (payload.plot_id, payload.operation_type, payload.operator, op_date,
             json.dumps(payload.detail, ensure_ascii=False), json.dumps(payload.images),
             datetime.now().isoformat(timespec="seconds")),
        )
        return {"id": cur.lastrowid, "operation_date": op_date}


# ---------------------------------------------------------------------------
# 用药台账
# ---------------------------------------------------------------------------
@app.get("/api/pesticides")
def list_pesticides():
    return PESTICIDES


@app.get("/api/pesticide-records")
def list_pesticide_records(plot_id: int | None = None, limit: int = Query(100, le=500)):
    with get_conn() as conn:
        sql = ("SELECT r.*, p.name AS plot_name FROM pesticide_records r "
               "JOIN plots p ON p.id=r.plot_id ")
        args: tuple = ()
        if plot_id:
            sql += "WHERE r.plot_id=? "
            args = (plot_id,)
        sql += "ORDER BY r.apply_time DESC LIMIT ?"
        return rows_to_dicts(conn.execute(sql, (*args, limit)).fetchall())


@app.post("/api/pesticide-records")
def create_pesticide_record(payload: PesticideRecordIn):
    with get_conn() as conn:
        return _write_pesticide(
            conn,
            plot_id=payload.plot_id,
            pesticide_name=payload.pesticide_name,
            cas_no=payload.cas_no,
            dosage=payload.dosage,
            dilution=payload.dilution,
            application_method=payload.application_method,
            operator=payload.operator,
            apply_time=payload.apply_time,
            days_to_harvest=payload.days_to_harvest,
        )


@app.get("/api/plots/{plot_id}/safety-status")
def safety_status(plot_id: int, harvest_date: str | None = None):
    with get_conn() as conn:
        _plot_or_404(conn, plot_id)
        return check_safety(conn, plot_id, harvest_date or _today())


# ---------------------------------------------------------------------------
# 病虫害识别
# ---------------------------------------------------------------------------
@app.post("/api/recognitions")
async def create_recognition(
    file: UploadFile = File(...),
    plot_id: int | None = Form(None),
    days_to_harvest: int | None = Form(None),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "图片为空")
    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    if suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    url, _ = ai_service.save_image(data, suffix)
    result = ai_service.recognize(data, plot_id, days_to_harvest)

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO recognitions(plot_id, user_id, image_url, detected_class, confidence, bbox, "
            "suggestion_text, suggestion_json, is_mock, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (plot_id, "farmer_01", url, result["pest_class"], result["confidence"],
             json.dumps(result["bbox"]), result["suggestion"]["text"],
             json.dumps(result["suggestion"], ensure_ascii=False),
             int(result["is_mock"]), datetime.now().isoformat(timespec="seconds")),
        )
        result["id"] = cur.lastrowid
        result["image_url"] = url
        result["status"] = "pending"
        result["plot_id"] = plot_id
        return result


@app.post("/api/recognitions/demo")
def create_demo_recognition(payload: DemoRecognitionIn):
    result = ai_service.recognize_known(payload.pest_class, payload.confidence, payload.days_to_harvest)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO recognitions(plot_id, user_id, image_url, detected_class, confidence, bbox, "
            "suggestion_text, suggestion_json, is_mock, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (payload.plot_id, "demo", "", result["pest_class"], result["confidence"],
             json.dumps(result["bbox"]), result["suggestion"]["text"],
             json.dumps(result["suggestion"], ensure_ascii=False), 1,
             datetime.now().isoformat(timespec="seconds")),
        )
        result["id"] = cur.lastrowid
        result["status"] = "pending"
        result["plot_id"] = payload.plot_id
        return result


@app.get("/api/recognitions")
def list_recognitions(
    plot_id: int | None = None,
    status: str | None = None,
    limit: int = Query(50, le=300),
):
    allowed = {"pending", "handled", "ignored", "false_positive"}
    if status and status not in allowed:
        raise HTTPException(400, f"status 取值应为 {' / '.join(sorted(allowed))}")
    with get_conn() as conn:
        sql = ("SELECT r.*, p.name AS plot_name FROM recognitions r "
               "LEFT JOIN plots p ON p.id=r.plot_id ")
        conditions: list[str] = []
        args: list = []
        if plot_id:
            conditions.append("r.plot_id=?")
            args.append(plot_id)
        if status:
            conditions.append("r.status=?")
            args.append(status)
        if conditions:
            sql += "WHERE " + " AND ".join(conditions) + " "
        sql += "ORDER BY r.created_at DESC LIMIT ?"
        args.append(limit)
        return rows_to_dicts(conn.execute(sql, tuple(args)).fetchall())


@app.post("/api/recognitions/{rid}/handle")
def handle_recognition(rid: int, payload: RecognitionHandleIn):
    """识别→处置闭环：按建议用药 / 人工清除（农事）/ 忽略 / 误判。

    - pesticide：复用用药台账校验（登记库 + CAS + 安全间隔期），自动写台账并回链；
    - operation：写一条农事记录并回链；
    - ignore / false_positive：只改状态，不写台账。
    处置后该识别不再出现在「未处置识别」待办中。
    """
    allowed = {"pesticide", "operation", "ignore", "false_positive"}
    if payload.method not in allowed:
        raise HTTPException(400, f"不支持的处置方式：{payload.method}")

    with get_conn() as conn:
        rec = conn.execute("SELECT * FROM recognitions WHERE id=?", (rid,)).fetchone()
        if not rec:
            raise HTTPException(404, "识别记录不存在")
        if rec["status"] != "pending":
            raise HTTPException(409, "该识别已处置，无需重复操作")

        status = "handled"
        pesticide_record_id = None
        operation_id = None
        summary: dict = {}

        if payload.method in ("pesticide", "operation"):
            if not rec["plot_id"]:
                raise HTTPException(400, "该识别未关联地块，无法写入台账；请先选择地块或改用「忽略」")
            if payload.method == "pesticide":
                if not payload.pesticide_name and not payload.cas_no:
                    raise HTTPException(400, "用药处置需提供药剂名称或 CAS 编号")
                written = _write_pesticide(
                    conn,
                    plot_id=rec["plot_id"],
                    pesticide_name=payload.pesticide_name or "",
                    cas_no=payload.cas_no,
                    dosage=payload.dosage,
                    dilution=payload.dilution,
                    application_method=payload.application_method,
                    operator=payload.operator,
                    apply_time=payload.apply_time,
                    days_to_harvest=payload.days_to_harvest,
                )
                pesticide_record_id = written["id"]
                summary = written
            else:
                op_date = payload.operation_date or _today()
                detail = dict(payload.detail)
                detail.setdefault("recognition_id", rid)
                detail.setdefault("detected_class", rec["detected_class"])
                cur = conn.execute(
                    "INSERT INTO farm_operations(plot_id, operation_type, operator, operation_date, detail, images, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (rec["plot_id"], payload.operation_type or "人工清除", payload.operator, op_date,
                     json.dumps(detail, ensure_ascii=False), json.dumps(payload.images),
                     datetime.now().isoformat(timespec="seconds")),
                )
                operation_id = cur.lastrowid
                summary = {"id": operation_id, "operation_type": payload.operation_type or "人工清除",
                           "operation_date": op_date}
        elif payload.method == "ignore":
            status = "ignored"
        else:  # false_positive
            status = "false_positive"

        handled_at = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE recognitions SET status=?, handled_at=?, handle_method=?, handle_note=?, "
            "pesticide_record_id=?, operation_id=? WHERE id=?",
            (status, handled_at, payload.method, payload.note,
             pesticide_record_id, operation_id, rid),
        )
        return {
            "id": rid,
            "status": status,
            "handle_method": payload.method,
            "handled_at": handled_at,
            "pesticide_record_id": pesticide_record_id,
            "operation_id": operation_id,
            "summary": summary,
        }


@app.get("/api/pests")
def list_pests():
    return [{"name": k, **v} for k, v in PESTS.items()]


# ---------------------------------------------------------------------------
# 采收批次与溯源
# ---------------------------------------------------------------------------
@app.post("/api/batches")
def create_batch(payload: BatchIn):
    with get_conn() as conn:
        plot = _plot_or_404(conn, payload.plot_id)
        _parse_date(payload.harvest_date)
        safety = check_safety(conn, payload.plot_id, payload.harvest_date)
        batch_no = make_batch_no(plot["code"], payload.harvest_date, payload.packaging_seq)
        status = "released" if safety["safe"] else "blocked"
        block_reason = None if safety["safe"] else safety["message"]
        try:
            cur = conn.execute(
                "INSERT INTO batches(batch_no, plot_id, variety, harvest_date, trace_code, packaging_seq, "
                "status, block_reason, detection_report, packaging_info, logistics, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (batch_no, payload.plot_id, plot["variety"], payload.harvest_date, batch_no,
                 payload.packaging_seq, status, block_reason,
                 "待检测" if status == "blocked" else "农残快检合格（模板数据）",
                 "5kg 泡沫箱 · 冷链", "", datetime.now().isoformat(timespec="seconds")),
            )
        except Exception:
            raise HTTPException(400, "该地块当日该顺序号的批次已存在")
        batch_id = cur.lastrowid
        if status == "released":
            append_hash(conn, batch_id,
                        {"batch_no": batch_no, "stage": "种植", "plot": plot["code"]}, "种植档案摘要")
            append_hash(conn, batch_id,
                        {"batch_no": batch_no, "stage": "管护", "safety": safety["message"]}, "管护记录摘要")
        return {
            "id": batch_id, "batch_no": batch_no, "trace_code": batch_no,
            "status": status, "block_reason": block_reason,
            "qrcode_url": f"/api/batches/{batch_no}/qrcode",
        }


@app.get("/api/batches")
def list_batches():
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(
            "SELECT b.*, p.name AS plot_name FROM batches b JOIN plots p ON p.id=b.plot_id "
            "ORDER BY b.created_at DESC").fetchall())
        for r in rows:
            r["qrcode_url"] = f"/api/batches/{r['batch_no']}/qrcode"
        return rows


@app.get("/api/batches/{batch_no}/qrcode")
def batch_qrcode(batch_no: str):
    """返回批次二维码 PNG：内容为溯源码（或 QR_BASE_URL 配置的溯源链接）。"""
    with get_conn() as conn:
        row = conn.execute("SELECT trace_code FROM batches WHERE batch_no=?", (batch_no,)).fetchone()
        if not row:
            raise HTTPException(404, "批次不存在")
    return Response(
        content=_qr_png(_qr_payload(row["trace_code"])),
        media_type="image/png",
        headers={"Cache-Control": "max-age=3600"},
    )


@app.get("/api/trace/{code}")
def get_trace(code: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM batches WHERE trace_code=?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, "溯源码不存在")
        batch = dict(row)
        plot = _plot_or_404(conn, batch["plot_id"])
        ops = rows_to_dicts(conn.execute(
            "SELECT operation_type, operator, operation_date FROM farm_operations "
            "WHERE plot_id=? AND operation_date <= ? ORDER BY operation_date DESC LIMIT 12",
            (batch["plot_id"], batch["harvest_date"])).fetchall())
        pesticide_count = conn.execute(
            "SELECT COUNT(*) AS c FROM pesticide_records WHERE plot_id=? AND apply_time <= ?",
            (batch["plot_id"], batch["harvest_date"])).fetchone()["c"]
        last_pesticide = conn.execute(
            "SELECT * FROM pesticide_records WHERE plot_id=? AND apply_time <= ? "
            "ORDER BY apply_time DESC LIMIT 1",
            (batch["plot_id"], batch["harvest_date"])).fetchone()
        pesticides = rows_to_dicts(conn.execute(
            "SELECT pesticide_name, cas_no, operator, apply_time, safe_interval_days "
            "FROM pesticide_records WHERE plot_id=? AND apply_time <= ? "
            "ORDER BY apply_time DESC LIMIT 12",
            (batch["plot_id"], batch["harvest_date"])).fetchall())
        pesticides = [_compliance_row(p) for p in pesticides]
        hashes = rows_to_dicts(conn.execute(
            "SELECT record_hash, prev_hash, payload_summary, created_at FROM trace_hash_log "
            "WHERE batch_id=? ORDER BY id", (batch["id"],)).fetchall())

        last_p = dict(last_pesticide) if last_pesticide else None
        safety_state = "未知"
        if last_p:
            elapsed = (_parse_date(batch["harvest_date"]) - _parse_date(last_p["apply_time"])).days
            safety_state = "已过安全间隔期" if elapsed >= last_p["safe_interval_days"] else "未过安全间隔期"

        return {
            "code": code,
            "batch_no": batch["batch_no"],
            "status": batch["status"],
            "block_reason": batch["block_reason"],
            "variety": batch["variety"],
            "harvest_date": batch["harvest_date"],
            "planting": {
                "orchard": "东风荔枝果园",
                "plot_name": plot["name"],
                "location": plot["location"],
                "variety": plot["variety"],
                "planting_year": plot["planting_year"],
                "area_mu": plot["area_mu"],
            },
            "care": {
                "operations": ops,
                "pesticide_count": pesticide_count,
                "pesticides": pesticides,
                "last_pesticide": last_p,
                "safety_state": safety_state,
            },
            "sales": {
                "detection_report": batch["detection_report"],
                "packaging": batch["packaging_info"],
                "logistics": batch["logistics"],
            },
            "hash_chain": hashes,
            "chain_verify": verify_chain(conn, batch_id=batch["id"]),
        }


@app.get("/api/trace-verify")
def trace_verify():
    with get_conn() as conn:
        return verify_chain(conn)


# ---------------------------------------------------------------------------
# 今日待办
# ---------------------------------------------------------------------------
@app.get("/api/todos")
def todos():
    with get_conn() as conn:
        plots = rows_to_dicts(conn.execute("SELECT * FROM plots ORDER BY code").fetchall())
        items = []
        for p in plots:
            safety = check_safety(conn, p["id"], _today())
            if not safety["safe"]:
                items.append({
                    "level": "critical",
                    "type": "safety",
                    "plot_id": p["id"],
                    "title": f"{p['name']} 处于用药安全间隔期",
                    "detail": safety["message"],
                    "action": "查看用药台账",
                })
            last_op = conn.execute(
                "SELECT operation_date FROM farm_operations WHERE plot_id=? ORDER BY operation_date DESC LIMIT 1",
                (p["id"],)).fetchone()
            if last_op:
                gap = (date.today() - _parse_date(last_op["operation_date"])).days
                if gap >= 10:
                    items.append({
                        "level": "warning",
                        "type": "operation",
                        "plot_id": p["id"],
                        "title": f"{p['name']} 已 {gap} 天未记录农事",
                        "detail": "建议安排一次巡园并补录农事记录",
                        "action": "去填报",
                    })
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM batches WHERE plot_id=? AND status='blocked'", (p["id"],)
            ).fetchone()["c"]
            if pending:
                items.append({
                    "level": "serious",
                    "type": "batch",
                    "plot_id": p["id"],
                    "title": f"{p['name']} 有 {pending} 个批次被拦截",
                    "detail": "安全间隔期未满，暂不能生成销售溯源码",
                    "action": "查看批次",
                })

        recent = conn.execute(
            "SELECT detected_class, COUNT(*) AS c FROM recognitions "
            "WHERE created_at >= ? AND detected_class NOT IN ('健康叶片','健康果实') "
            "AND status='pending' "
            "GROUP BY detected_class ORDER BY c DESC LIMIT 2",
            ((datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"),),
        ).fetchall()
        for r in recent:
            items.append({
                "level": "serious" if r["c"] >= 5 else "warning",
                "type": "recognition",
                "pest_class": r["detected_class"],
                "count": r["c"],
                "title": f"近 7 天「{r['detected_class']}」未处置识别 {r['c']} 次",
                "detail": "病虫害有集中发生趋势，请前往识别记录处置",
                "action": "去处置",
            })

        # 天气联动：连续降雨/高湿时提示霜疫霉病风险（失败静默）
        try:
            risk = weather.get_pest_risk()
        except Exception:
            risk = None
        if risk:
            items.append({
                "level": "serious" if risk["level"] == "high" else "warning",
                "type": "weather",
                "pest_class": risk["pest"],
                "title": f"天气预警：未来利于「{risk['pest']}」发生",
                "detail": risk["detail"],
                "action": "雨前预防",
            })

        if not items:
            items.append({"level": "good", "title": "今日暂无待办", "detail": "果园状态正常", "action": ""})
        return items


# ---------------------------------------------------------------------------
# 数据看板
# ---------------------------------------------------------------------------
@app.get("/api/dashboard/summary")
def dashboard_summary():
    with get_conn() as conn:
        plots = conn.execute("SELECT COUNT(*) c, SUM(area_mu) a, SUM(tree_count) t FROM plots").fetchone()
        recent_iso = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
        applications_30d = conn.execute(
            "SELECT COUNT(*) c FROM pesticide_records WHERE apply_time >= ?",
            ((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),)).fetchone()["c"]
        recognitions_7d = conn.execute(
            "SELECT COUNT(*) c FROM recognitions WHERE created_at >= ?",
            ((datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"),)).fetchone()["c"]
        handled_7d = conn.execute(
            "SELECT COUNT(*) c FROM recognitions WHERE created_at >= ? AND status != 'pending'",
            ((datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"),)).fetchone()["c"]
        blocked = conn.execute("SELECT COUNT(*) c FROM batches WHERE status='blocked'").fetchone()["c"]
        released = conn.execute("SELECT COUNT(*) c FROM batches WHERE status='released'").fetchone()["c"]

        unsafe_plots = []
        for p in conn.execute("SELECT * FROM plots").fetchall():
            s = check_safety(conn, p["id"], _today())
            if not s["safe"]:
                unsafe_plots.append({"plot": p["name"], "message": s["message"],
                                     "remaining_days": s["remaining_days"]})

        yield_2026 = conn.execute(
            "SELECT SUM(actual_yield) y FROM yield_records WHERE season=2026").fetchone()["y"] or 0

        return {
            "plots": plots["c"], "area_mu": round(plots["a"] or 0, 1), "trees": plots["t"] or 0,
            "pesticide_applications_30d": applications_30d,
            "recognitions_7d": recognitions_7d,
            "recognition_handled_7d": handled_7d,
            "recognition_disposal_rate": round(handled_7d / recognitions_7d, 4) if recognitions_7d else 0.0,
            "blocked_batches": blocked, "released_batches": released,
            "yield_2026_kg": round(yield_2026, 0),
            "unsafe_plots": unsafe_plots,
        }


@app.get("/api/dashboard/compliance")
def dashboard_compliance(plot_id: int | None = None, limit: int = Query(200, le=500)):
    with get_conn() as conn:
        rows = _compliance_rows(conn, plot_id, limit)
        return {"as_of": _today(), "count": len(rows), "rows": rows}


@app.get("/api/dashboard/compliance.csv")
def dashboard_compliance_csv(plot_id: int | None = None, limit: int = Query(500, le=500)):
    with get_conn() as conn:
        rows = _compliance_rows(conn, plot_id, limit)
    header = [
        "地块", "农药名称", "CAS编号", "施药日期", "安全间隔期(天)", "最早采收日期",
        "剩余天数", "状态", "施药方式", "剂量", "操作人", "目标病虫害",
    ]
    body = [[
        r.get("plot_name") or "", r.get("pesticide_name") or "", r.get("cas_no") or "",
        r.get("apply_time") or "", r.get("safe_interval_days") or "",
        r.get("earliest_harvest_date") or "",
        "" if r.get("days_remaining") is None else r["days_remaining"],
        r.get("compliance_label") or "", r.get("application_method") or "",
        r.get("dosage") or "", r.get("operator") or "", r.get("target_pest") or "",
    ] for r in rows]
    return _csv_response("pesticide_compliance.csv", header, body)


@app.get("/api/weather/region")
def weather_region():
    return {"enabled": config.WEATHER_ENABLED, "region": weather.get_region()}


@app.put("/api/weather/region")
def set_weather_region(payload: WeatherRegionIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "请输入地区名")
    if len(name) > 40:
        raise HTTPException(400, "地区名过长（最多 40 字）")
    try:
        matched = weather.geocode(name)
    except Exception:
        logger.warning("地理编码失败：%s", name, exc_info=True)
        raise HTTPException(502, "地理编码服务暂不可用，请稍后再试")
    if not matched:
        raise HTTPException(404, f"未找到「{name}」，请尝试输入城市名（如 广州）")
    region = weather.save_region(
        matched["name"], matched["admin1"], matched["lat"], matched["lon"])
    return {"enabled": config.WEATHER_ENABLED, "matched": matched, "region": region}


@app.get("/api/weather/pest-risk")
def weather_pest_risk():
    region = weather.get_region()
    return {
        "enabled": config.WEATHER_ENABLED,
        "location": region["label"],
        "region": region,
        "risk": weather.get_pest_risk(region=region),
    }


@app.get("/api/dashboard/yield-trend")
def yield_trend():
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(
            "SELECT p.name, p.variety, y.season, y.actual_yield, y.estimated_yield "
            "FROM yield_records y JOIN plots p ON p.id=y.plot_id ORDER BY y.season, p.id").fetchall())
        seasons = sorted({r["season"] for r in rows})
        series_map: dict[str, dict] = {}
        for r in rows:
            key = f"{r['name']}（{r['variety']}）"
            s = series_map.setdefault(key, {"name": key, "actual": [], "estimated": []})
            s["actual"].append(r["actual_yield"])
            s["estimated"].append(r["estimated_yield"])
        return {
            "seasons": [str(s) for s in seasons],
            "series": list(series_map.values()),
            "unit": "kg",
        }


@app.get("/api/dashboard/pesticide-trend")
def pesticide_trend():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT apply_time, pesticide_name FROM pesticide_records ORDER BY apply_time").fetchall()
        months: dict[str, dict[str, int]] = {}
        for r in rows:
            month = r["apply_time"][:7]
            cat = PESTICIDE_BY_NAME.get(r["pesticide_name"], {}).get("category", "其他")
            bucket = months.setdefault(month, {})
            bucket[cat] = bucket.get(cat, 0) + 1
        keys = sorted(months)
        cats = ["杀虫剂", "杀菌剂", "除草剂"]
        return {
            "months": keys,
            "categories": cats,
            "series": [{"name": c, "data": [months[m].get(c, 0) for m in keys]} for c in cats],
        }


@app.get("/api/dashboard/pest-trend")
def pest_trend(weeks: int = 12):
    start = datetime.now() - timedelta(weeks=weeks)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT detected_class, created_at FROM recognitions WHERE created_at >= ?",
            (start.isoformat(timespec="seconds"),)).fetchall()

    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        dt = datetime.fromisoformat(r["created_at"])
        monday = dt - timedelta(days=dt.weekday())
        key = monday.strftime("%m-%d")
        buckets.setdefault(key, {})
        buckets[key][r["detected_class"]] = buckets[key].get(r["detected_class"], 0) + 1

    keys = sorted(buckets)
    totals: dict[str, int] = {}
    for b in buckets.values():
        for k, v in b.items():
            totals[k] = totals.get(k, 0) + v
    top = [k for k, _ in sorted(totals.items(), key=lambda x: -x[1])
           if k not in ("健康叶片", "健康果实")][:4]
    series = [{"name": k, "data": [buckets[m].get(k, 0) for m in keys]} for k in top]
    return {"weeks": keys, "series": series}


@app.get("/api/dashboard/pest-heatmap")
def pest_heatmap():
    start = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT p.name AS plot_name, r.detected_class, COUNT(*) AS c "
            "FROM recognitions r JOIN plots p ON p.id=r.plot_id "
            "WHERE r.created_at >= ? AND r.detected_class NOT IN ('健康叶片','健康果实') "
            "GROUP BY p.name, r.detected_class", (start,)).fetchall()
        plots = [r["name"] for r in conn.execute("SELECT name FROM plots ORDER BY id").fetchall()]

    totals: dict[str, int] = {}
    for r in rows:
        totals[r["detected_class"]] = totals.get(r["detected_class"], 0) + r["c"]
    pests = [k for k, _ in sorted(totals.items(), key=lambda x: -x[1])][:6]
    lookup = {(r["plot_name"], r["detected_class"]): r["c"] for r in rows}
    data = [[i, j, lookup.get((plot, pest), 0)] for j, pest in enumerate(pests) for i, plot in enumerate(plots)]
    return {"plots": plots, "pests": pests, "data": data}


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "mobile.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/trace")
def trace_page():
    return FileResponse(FRONTEND_DIR / "trace.html")
