"""searchsploit 路由：任务提交 / 列表 / 停止 / 删除 / 结果查询 / 导出 / Nmap XML 上传。

提交任务后立即返回 task_id，搜索在 asyncio 后台执行（与 dirsearch/hydra/sqlmap/aircrack 一致）。
任务状态写入 searchsploit_task 集合，搜索结果写入 searchsploit_result 集合。

searchsploit 的 --nmap 模式需要 Nmap XML 文件，提供上传端点。
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
from ..services.searchsploit import PARAM_META
from ..tasks.searchsploit_task import run_searchsploit_task
from ..utils import curr_date
from .base import build_data, export_collection, parse_query_params

logger = get_logger()
router = APIRouter(prefix="/searchsploit", tags=["searchsploit"],
                   dependencies=[Depends(require_auth)])

# Nmap XML 文件持久化目录（--nmap 模式使用）
NMAP_DIR = os.path.join(Config.TMP_PATH, "searchsploit_nmap")
os.makedirs(NMAP_DIR, exist_ok=True)

# 运行中的 searchsploit 任务：run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}
# task_id -> run_id（便于按 task_id 取消）
_task_to_run: dict[str, str] = {}


# ----------------------------- 数据模型 -----------------------------
class AddSearchsploitBody(BaseModel):
    name: str = Field(..., description="任务名")
    terms: list[str] = Field(..., description="搜索关键词列表")
    options: dict[str, Any] = Field(default_factory=dict, description="searchsploit 参数")


class DeleteBody(BaseModel):
    task_ids: list[str]


# ----------------------------- 任务列表 / 提交 -----------------------------
@router.get("/task/")
async def list_task(request: Request):
    """searchsploit 任务列表（分页 + 过滤）。"""
    return await build_data(parse_query_params(request), "searchsploit_task")


@router.post("/task/")
async def add_task(body: AddSearchsploitBody):
    """提交 searchsploit 搜索任务，立即返回 task_id。"""
    terms = [t.strip() for t in body.terms if t and t.strip()]
    options = dict(body.options)

    # 非搜索模式（-p/-m/-x/--nmap）允许 terms 为空
    non_search = any(options.get(k) for k in ("path", "mirror", "examine", "nmap"))
    if not terms and not non_search:
        return build_ret(error_map["Error"], {"error": "搜索关键词为空"})

    now = curr_date()
    task_id = str(ObjectId())
    run_id = uuid.uuid4().hex
    doc = {
        "_id": ObjectId(task_id),
        "name": body.name,
        "terms": terms,
        "options": options,
        "status": "waiting",
        "run_id": run_id,
        "result_count": 0,
        "save_date": now,
        "update_date": now,
    }
    await conn_db("searchsploit_task").insert_one(doc)

    # 后台执行
    coro = _run_with_cancel_guard(task_id, run_id)
    t = asyncio.create_task(coro, name=f"searchsploit-{run_id}")
    _running[run_id] = t
    _task_to_run[task_id] = run_id
    t.add_done_callback(lambda _: _cleanup_run(run_id, task_id))

    return {"code": 200, "message": "success", "data": {"task_id": task_id, "run_id": run_id}}


async def _run_with_cancel_guard(task_id: str, run_id: str) -> None:
    try:
        await run_searchsploit_task(task_id)
    except asyncio.CancelledError:
        logger.info(f"searchsploit task cancelled: {task_id}")
        raise
    except Exception as e:
        logger.exception(e)


def _cleanup_run(run_id: str, task_id: str) -> None:
    _running.pop(run_id, None)
    _task_to_run.pop(task_id, None)


# ----------------------------- 停止 / 删除 -----------------------------
@router.get("/task/stop/{task_id}")
async def stop_task(task_id: str):
    """停止运行中的 searchsploit 任务。"""
    run_id = _task_to_run.get(task_id)
    if not run_id:
        return build_ret(error_map["Error"], {"error": "任务不在运行中或已结束"})
    t = _running.get(run_id)
    if t and not t.done():
        t.cancel()
    await conn_db("searchsploit_task").update_one(
        {"_id": ObjectId(task_id), "status": {"$in": ["waiting", "running"]}},
        {"$set": {"status": "stop", "update_date": curr_date()}},
    )
    return {"code": 200, "message": "success"}


@router.post("/task/delete/")
async def delete_task(body: DeleteBody):
    """删除 searchsploit 任务及其结果。"""
    deleted: list[str] = []
    for task_id in body.task_ids:
        run_id = _task_to_run.get(task_id)
        if run_id:
            t = _running.get(run_id)
            if t and not t.done():
                t.cancel()
        await conn_db("searchsploit_task").delete_one({"_id": ObjectId(task_id)})
        await conn_db("searchsploit_result").delete_many({"task_id": task_id})
        deleted.append(task_id)
    return {"code": 200, "message": "success", "data": {"deleted": deleted}}


# ----------------------------- 结果查询 / 导出 -----------------------------
@router.get("/result/")
async def list_result(request: Request):
    """searchsploit 结果分页查询。"""
    return await build_data(parse_query_params(request), "searchsploit_result")


@router.get("/result/export/")
async def export_result(request: Request):
    """导出结果为 .txt（按 EDB-ID 或标题列表）。"""
    return await export_collection(parse_query_params(request), "searchsploit_result")


# ----------------------------- 辅助：参数元数据 / Nmap 上传 -----------------------------
@router.get("/param_meta/")
async def param_meta():
    """返回 searchsploit 参数元数据，供前端动态渲染表单。"""
    return {"code": 200, "message": "success", "data": PARAM_META}


@router.post("/upload_nmap/")
async def upload_nmap(file: UploadFile = File(...)):
    """上传 Nmap XML 文件（用于 --nmap 模式），返回文件路径供提交任务时填入 options.nmap。

    文件持久化到 tmp/searchsploit_nmap/，便于在任务中引用。
    """
    filename = file.filename or "nmap.xml"
    if not filename.lower().endswith((".xml", ".nmap")):
        return build_ret(error_map["Error"], {"error": "仅支持 .xml 或 .nmap 文件"})
    stored_name = f"{uuid.uuid4().hex[:12]}_{filename}"
    stored_path = os.path.join(NMAP_DIR, stored_name)
    raw = await file.read()
    try:
        with open(stored_path, "wb") as f:
            f.write(raw)
    except OSError as e:
        return build_ret(error_map["Error"], {"error": f"文件保存失败: {e}"})
    return {
        "code": 200, "message": "success",
        "data": {"nmap_file": stored_path, "filename": filename, "size": len(raw)},
    }
