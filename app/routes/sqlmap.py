"""sqlmap 路由：任务提交 / 列表 / 停止 / 删除 / 结果查询 / 导出。

提交任务后立即返回 task_id，扫描在 asyncio 后台执行（与 dirsearch/hydra 一致）。
任务状态写入 sqlmap_task 集合，注入检测结果写入 sqlmap_result 集合。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field

from ..database import conn_db
from ..deps import require_auth
from ..logger import get_logger
from ..modules import build_ret, error_map
from ..services.sqlmap import PARAM_META
from ..tasks.sqlmap_task import run_sqlmap_task
from ..utils import curr_date
from .base import build_data, export_collection, parse_query_params

logger = get_logger()
router = APIRouter(prefix="/sqlmap", tags=["sqlmap"], dependencies=[Depends(require_auth)])

# 运行中的 sqlmap 任务：run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}
# task_id -> run_id（便于按 task_id 取消）
_task_to_run: dict[str, str] = {}


# ----------------------------- 数据模型 -----------------------------
class AddSqlmapBody(BaseModel):
    name: str = Field(..., description="任务名")
    targets: list[str] = Field(..., description="目标 URL 列表")
    options: dict[str, Any] = Field(default_factory=dict, description="sqlmap 参数")


class DeleteBody(BaseModel):
    task_ids: list[str]


# ----------------------------- 任务列表 / 提交 -----------------------------
@router.get("/task/")
async def list_task(request: Request):
    """sqlmap 任务列表（分页 + 过滤）。"""
    return await build_data(parse_query_params(request), "sqlmap_task")


@router.post("/task/")
async def add_task(body: AddSqlmapBody):
    """提交 sqlmap 扫描任务，立即返回 task_id。"""
    targets = [t.strip() for t in body.targets if t and t.strip()]
    if not targets:
        return build_ret(error_map["Error"], {"error": "targets 为空"})

    now = curr_date()
    task_id = str(ObjectId())
    run_id = uuid.uuid4().hex
    doc = {
        "_id": ObjectId(task_id),
        "name": body.name,
        "targets": targets,
        "options": body.options,
        "status": "waiting",
        "run_id": run_id,
        "result_count": 0,
        "save_date": now,
        "update_date": now,
    }
    await conn_db("sqlmap_task").insert_one(doc)

    # 后台执行
    coro = _run_with_cancel_guard(task_id, run_id)
    t = asyncio.create_task(coro, name=f"sqlmap-{run_id}")
    _running[run_id] = t
    _task_to_run[task_id] = run_id
    t.add_done_callback(lambda _: _cleanup_run(run_id, task_id))

    return {"code": 200, "message": "success", "data": {"task_id": task_id, "run_id": run_id}}


async def _run_with_cancel_guard(task_id: str, run_id: str) -> None:
    try:
        await run_sqlmap_task(task_id)
    except asyncio.CancelledError:
        logger.info(f"sqlmap task cancelled: {task_id}")
        raise
    except Exception as e:
        logger.exception(e)


def _cleanup_run(run_id: str, task_id: str) -> None:
    _running.pop(run_id, None)
    _task_to_run.pop(task_id, None)


# ----------------------------- 停止 / 删除 -----------------------------
@router.get("/task/stop/{task_id}")
async def stop_task(task_id: str):
    """停止运行中的 sqlmap 任务。"""
    run_id = _task_to_run.get(task_id)
    if not run_id:
        return build_ret(error_map["Error"], {"error": "任务不在运行中或已结束"})
    t = _running.get(run_id)
    if t and not t.done():
        t.cancel()
    await conn_db("sqlmap_task").update_one(
        {"_id": ObjectId(task_id), "status": {"$in": ["waiting", "running"]}},
        {"$set": {"status": "stop", "update_date": curr_date()}},
    )
    return {"code": 200, "message": "success"}


@router.post("/task/delete/")
async def delete_task(body: DeleteBody):
    """删除 sqlmap 任务及其结果。"""
    deleted: list[str] = []
    for task_id in body.task_ids:
        run_id = _task_to_run.get(task_id)
        if run_id:
            t = _running.get(run_id)
            if t and not t.done():
                t.cancel()
        await conn_db("sqlmap_task").delete_one({"_id": ObjectId(task_id)})
        await conn_db("sqlmap_result").delete_many({"task_id": task_id})
        deleted.append(task_id)
    return {"code": 200, "message": "success", "data": {"deleted": deleted}}


# ----------------------------- 结果查询 / 导出 -----------------------------
@router.get("/result/")
async def list_result(request: Request):
    """sqlmap 结果分页查询。"""
    return await build_data(parse_query_params(request), "sqlmap_result")


@router.get("/result/export/")
async def export_result(request: Request):
    """导出结果为 .txt（按 target 列表）。"""
    return await export_collection(parse_query_params(request), "sqlmap_result")


# ----------------------------- 辅助：参数元数据 / 上传 -----------------------------
@router.get("/param_meta/")
async def param_meta():
    """返回 sqlmap 参数元数据，供前端动态渲染表单。"""
    return {"code": 200, "message": "success", "data": PARAM_META}


@router.post("/upload_urls/")
async def upload_urls(file: UploadFile = File(...)):
    """上传目标 URL 列表 .txt，返回解析后的 URL 数组（不入库，仅解析回填表单）。"""
    raw = await file.read()
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception as e:
        return build_ret(error_map["Error"], {"error": f"文件解码失败: {e}"})
    urls = [line.strip() for line in text.splitlines()
            if line.strip() and not line.startswith("#")]
    return {"code": 200, "message": "success", "data": urls}
