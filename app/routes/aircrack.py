"""aircrack-ng 路由：握手包上传 / 任务提交 / 列表 / 停止 / 删除 / 结果查询 / 导出。

提交任务后立即返回 task_id，破解在 asyncio 后台执行（与 dirsearch/hydra/sqlmap 一致）。
任务状态写入 aircrack_task 集合，破解结果写入 aircrack_result 集合。

与其它工具不同，aircrack-ng 的输入是抓包文件而非网络目标，因此提供：
    POST /aircrack/upload_capture/  上传 .cap/.pcap/.ivs/.hccapx，返回 capture_id 与路径
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field

from ..config import Config
from ..database import conn_db
from ..deps import require_auth
from ..logger import get_logger
from ..modules import build_ret, error_map
from ..services.aircrack import PARAM_META
from ..tasks.aircrack_task import run_aircrack_task
from ..utils import curr_date
from .base import build_data, export_collection, parse_query_params

logger = get_logger()
router = APIRouter(prefix="/aircrack", tags=["aircrack"], dependencies=[Depends(require_auth)])

# 抓包文件持久化目录（首次上传时创建）
CAPTURE_DIR = os.path.join(Config.TMP_PATH, "aircrack_captures")
os.makedirs(CAPTURE_DIR, exist_ok=True)

# 允许的抓包文件扩展名
_ALLOWED_EXT = {".cap", ".pcap", ".pcapng", ".ivs", ".hccapx", ".hccap", ".dump"}

# 运行中的 aircrack-ng 任务：run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}
# task_id -> run_id（便于按 task_id 取消）
_task_to_run: dict[str, str] = {}


# ----------------------------- 数据模型 -----------------------------
class AddAircrackBody(BaseModel):
    name: str = Field(..., description="任务名")
    capture_file: str = Field(..., description="抓包文件路径（由 upload_capture 返回）")
    options: dict[str, Any] = Field(default_factory=dict, description="aircrack-ng 参数")


class DeleteBody(BaseModel):
    task_ids: list[str]


# ----------------------------- 抓包文件上传 -----------------------------
@router.post("/upload_capture/")
async def upload_capture(file: UploadFile = File(...)):
    """上传抓包文件（.cap/.pcap/.ivs/.hccapx），返回文件路径供提交任务使用。

    文件持久化到 tmp/aircrack_captures/，元数据写入 aircrack_capture 集合，
    以便在任务列表中追溯。
    """
    filename = file.filename or "capture.cap"
    _, ext = os.path.splitext(filename)
    if ext.lower() not in _ALLOWED_EXT:
        return build_ret(error_map["Error"],
                         {"error": f"不支持的文件类型: {ext}，允许: {sorted(_ALLOWED_EXT)}"})

    capture_id = uuid.uuid4().hex[:12]
    stored_name = f"{capture_id}_{filename}"
    stored_path = os.path.join(CAPTURE_DIR, stored_name)
    raw = await file.read()
    try:
        with open(stored_path, "wb") as f:
            f.write(raw)
    except OSError as e:
        return build_ret(error_map["Error"], {"error": f"文件保存失败: {e}"})

    now = curr_date()
    doc = {
        "capture_id": capture_id,
        "filename": filename,
        "stored_path": stored_path,
        "size": len(raw),
        "save_date": now,
    }
    await conn_db("aircrack_capture").insert_one(doc)
    return {
        "code": 200, "message": "success",
        "data": {"capture_id": capture_id, "capture_file": stored_path,
                 "filename": filename, "size": len(raw)},
    }


@router.get("/captures/")
async def list_captures(request: Request):
    """已上传抓包文件列表（供前端选择）。"""
    return await build_data(parse_query_params(request), "aircrack_capture")


# ----------------------------- 任务列表 / 提交 -----------------------------
@router.get("/task/")
async def list_task(request: Request):
    """aircrack-ng 任务列表（分页 + 过滤）。"""
    return await build_data(parse_query_params(request), "aircrack_task")


@router.post("/task/")
async def add_task(body: AddAircrackBody):
    """提交 aircrack-ng 破解任务，立即返回 task_id。"""
    if not body.capture_file:
        return build_ret(error_map["Error"], {"error": "capture_file 为空"})
    if not os.path.exists(body.capture_file):
        return build_ret(error_map["Error"], {"error": "抓包文件不存在，请重新上传"})

    now = curr_date()
    task_id = str(ObjectId())
    run_id = uuid.uuid4().hex
    doc = {
        "_id": ObjectId(task_id),
        "name": body.name,
        "capture_file": body.capture_file,
        "options": body.options,
        "status": "waiting",
        "run_id": run_id,
        "result_count": 0,
        "save_date": now,
        "update_date": now,
    }
    await conn_db("aircrack_task").insert_one(doc)

    # 后台执行
    coro = _run_with_cancel_guard(task_id, run_id)
    t = asyncio.create_task(coro, name=f"aircrack-{run_id}")
    _running[run_id] = t
    _task_to_run[task_id] = run_id
    t.add_done_callback(lambda _: _cleanup_run(run_id, task_id))

    return {"code": 200, "message": "success", "data": {"task_id": task_id, "run_id": run_id}}


async def _run_with_cancel_guard(task_id: str, run_id: str) -> None:
    try:
        await run_aircrack_task(task_id)
    except asyncio.CancelledError:
        logger.info(f"aircrack-ng task cancelled: {task_id}")
        raise
    except Exception as e:
        logger.exception(e)


def _cleanup_run(run_id: str, task_id: str) -> None:
    _running.pop(run_id, None)
    _task_to_run.pop(task_id, None)


# ----------------------------- 停止 / 删除 -----------------------------
@router.get("/task/stop/{task_id}")
async def stop_task(task_id: str):
    """停止运行中的 aircrack-ng 任务。"""
    run_id = _task_to_run.get(task_id)
    if not run_id:
        return build_ret(error_map["Error"], {"error": "任务不在运行中或已结束"})
    t = _running.get(run_id)
    if t and not t.done():
        t.cancel()
    await conn_db("aircrack_task").update_one(
        {"_id": ObjectId(task_id), "status": {"$in": ["waiting", "running"]}},
        {"$set": {"status": "stop", "update_date": curr_date()}},
    )
    return {"code": 200, "message": "success"}


@router.post("/task/delete/")
async def delete_task(body: DeleteBody):
    """删除 aircrack-ng 任务及其结果。"""
    deleted: list[str] = []
    for task_id in body.task_ids:
        run_id = _task_to_run.get(task_id)
        if run_id:
            t = _running.get(run_id)
            if t and not t.done():
                t.cancel()
        await conn_db("aircrack_task").delete_one({"_id": ObjectId(task_id)})
        await conn_db("aircrack_result").delete_many({"task_id": task_id})
        deleted.append(task_id)
    return {"code": 200, "message": "success", "data": {"deleted": deleted}}


# ----------------------------- 结果查询 / 导出 -----------------------------
@router.get("/result/")
async def list_result(request: Request):
    """aircrack-ng 结果分页查询。"""
    return await build_data(parse_query_params(request), "aircrack_result")


@router.get("/result/export/")
async def export_result(request: Request):
    """导出结果为 .txt（按破解成功的密钥列表）。"""
    return await export_collection(parse_query_params(request), "aircrack_result")


# ----------------------------- 辅助：参数元数据 -----------------------------
@router.get("/param_meta/")
async def param_meta():
    """返回 aircrack-ng 参数元数据，供前端动态渲染表单。"""
    return {"code": 200, "message": "success", "data": PARAM_META}
