"""dirsearch 路由：任务提交 / 列表 / 停止 / 删除 / 结果查询 / 导出。

提交任务后立即返回 task_id，扫描在 asyncio 后台执行（参考 task_runner 的做法）。
任务状态写入 dirsearch_task 集合，结果写入 dirsearch_result 集合。
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
from ..services.dirsearch import PARAM_META
from ..tasks.dirsearch_task import run_dirsearch_task
from ..utils import curr_date
from .base import build_data, export_collection, parse_query_params

logger = get_logger()
router = APIRouter(prefix="/dirsearch", tags=["dirsearch"], dependencies=[Depends(require_auth)])

# 运行中的 dirsearch 任务：run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}
# task_id -> run_id（便于按 task_id 取消）
_task_to_run: dict[str, str] = {}


# ----------------------------- 数据模型 -----------------------------
class AddDirSearchBody(BaseModel):
    name: str = Field(..., description="任务名")
    targets: list[str] = Field(..., description="目标 URL 列表")
    options: dict[str, Any] = Field(default_factory=dict, description="dirsearch 参数")


class DeleteBody(BaseModel):
    task_ids: list[str]


# ----------------------------- 任务列表 / 提交 -----------------------------
@router.get("/task/")
async def list_task(request: Request):
    """dirsearch 任务列表（分页 + 过滤）。"""
    return await build_data(parse_query_params(request), "dirsearch_task")


@router.post("/task/")
async def add_task(body: AddDirSearchBody):
    """提交 dirsearch 扫描任务，立即返回 task_id。"""
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
    await conn_db("dirsearch_task").insert_one(doc)

    # 后台执行
    coro = _run_with_cancel_guard(task_id, run_id)
    t = asyncio.create_task(coro, name=f"dirsearch-{run_id}")
    _running[run_id] = t
    _task_to_run[task_id] = run_id
    t.add_done_callback(lambda _: _cleanup_run(run_id, task_id))

    return {"code": 200, "message": "success", "data": {"task_id": task_id, "run_id": run_id}}


async def _run_with_cancel_guard(task_id: str, run_id: str) -> None:
    try:
        await run_dirsearch_task(task_id)
    except asyncio.CancelledError:
        logger.info(f"dirsearch task cancelled: {task_id}")
        raise
    except Exception as e:
        logger.exception(e)


def _cleanup_run(run_id: str, task_id: str) -> None:
    _running.pop(run_id, None)
    _task_to_run.pop(task_id, None)


# ----------------------------- 停止 / 删除 -----------------------------
@router.get("/task/stop/{task_id}")
async def stop_task(task_id: str):
    """停止运行中的 dirsearch 任务。"""
    run_id = _task_to_run.get(task_id)
    if not run_id:
        return build_ret(error_map["Error"], {"error": "任务不在运行中或已结束"})
    t = _running.get(run_id)
    if t and not t.done():
        t.cancel()
    # 状态由任务协程捕获 CancelledError 时置 stop；这里兜底
    await conn_db("dirsearch_task").update_one(
        {"_id": ObjectId(task_id), "status": {"$in": ["waiting", "running"]}},
        {"$set": {"status": "stop", "update_date": curr_date()}},
    )
    return {"code": 200, "message": "success"}


@router.post("/task/delete/")
async def delete_task(body: DeleteBody):
    """删除 dirsearch 任务及其结果。"""
    deleted: list[str] = []
    for task_id in body.task_ids:
        # 先尝试停止（如果在跑）
        run_id = _task_to_run.get(task_id)
        if run_id:
            t = _running.get(run_id)
            if t and not t.done():
                t.cancel()
        await conn_db("dirsearch_task").delete_one({"_id": ObjectId(task_id)})
        await conn_db("dirsearch_result").delete_many({"task_id": task_id})
        deleted.append(task_id)
    return {"code": 200, "message": "success", "data": {"deleted": deleted}}


# ----------------------------- 结果查询 / 导出 -----------------------------
@router.get("/result/")
async def list_result(request: Request):
    """dirsearch 结果分页查询。"""
    return await build_data(parse_query_params(request), "dirsearch_result")


@router.get("/result/export/")
async def export_result(request: Request):
    """导出结果为 .txt（按 URL 去重）。"""
    return await export_collection(parse_query_params(request), "dirsearch_result")


# ----------------------------- 辅助：站点选择 / 文件上传 / 参数元数据 -----------------------------
@router.get("/param_meta/")
async def param_meta():
    """返回 dirsearch 参数元数据，供前端动态渲染表单。"""
    return {"code": 200, "message": "success", "data": PARAM_META}


@router.post("/site_list/")
async def site_list(body: dict | None = None):
    """从 site 集合查询站点 URL，供前端「从站点选择」。

    body 可传 {"task_id": "...", "search": "..."} 过滤。
    """
    body = body or {}
    query: dict[str, Any] = {}
    if body.get("task_id"):
        query["task_id"] = body["task_id"]
    if body.get("search"):
        query["site"] = {"$regex": body["search"], "$options": "i"}

    limit = max(1, min(int(body.get("size", 200)), 1000))
    cursor = conn_db("site").find(query, {"site": 1, "_id": 0}).limit(limit)
    sites = [item["site"] for item in await cursor.to_list(length=limit) if item.get("site")]
    return {"code": 200, "message": "success", "data": sites}


@router.post("/upload_urls/")
async def upload_urls(file: UploadFile = File(...)):
    """上传 URL 列表 .txt，返回解析后的 URL 数组（不入库，仅解析回填表单）。"""
    raw = await file.read()
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception as e:
        return build_ret(error_map["Error"], {"error": f"文件解码失败: {e}"})
    urls = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return {"code": 200, "message": "success", "data": urls}
