"""hashcat 路由：哈希文件上传 / 任务提交 / 列表 / 停止 / 删除 / 结果查询 / 导出。

提交任务后立即返回 task_id，恢复在 asyncio 后台执行。
任务状态写入 hashcat_task 集合，破解结果写入 hashcat_result 集合。

hashcat 的输入是哈希文件（每行一个哈希），与 aircrack 的抓包文件类似，
提供上传端点持久化到 tmp/hashcat_hashes/。
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
from ..services.hashcat import PARAM_META
from ..tasks.hashcat_task import run_hashcat_task
from ..utils import curr_date
from .base import build_data, export_collection, parse_query_params

logger = get_logger()
router = APIRouter(prefix="/hashcat", tags=["hashcat"], dependencies=[Depends(require_auth)])

# 哈希文件持久化目录
HASH_DIR = os.path.join(Config.TMP_PATH, "hashcat_hashes")
os.makedirs(HASH_DIR, exist_ok=True)

# 允许的哈希文件扩展名（宽松，哈希文件常无扩展名或 .hash/.txt）
_ALLOWED_EXT = {".txt", ".hash", ".hashes", ".lst", ".list", ".hccapx", ".hccap", ""}

# 运行中的 hashcat 任务：run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}
_task_to_run: dict[str, str] = {}


# ----------------------------- 数据模型 -----------------------------
class AddHashcatBody(BaseModel):
    name: str = Field(..., description="任务名")
    hash_file: str = Field(..., description="哈希文件路径（由 upload_hash 返回）")
    wordlist: str = Field("", description="字典/掩码路径")
    options: dict[str, Any] = Field(default_factory=dict, description="hashcat 参数")


class DeleteBody(BaseModel):
    task_ids: list[str]


# ----------------------------- 哈希文件上传 -----------------------------
@router.post("/upload_hash/")
async def upload_hash(file: UploadFile = File(...)):
    """上传哈希文件，返回文件路径供提交任务使用。"""
    filename = file.filename or "hashes.txt"
    _, ext = os.path.splitext(filename)
    if ext.lower() not in _ALLOWED_EXT:
        # 不强制拦截扩展名，哈希文件常无标准扩展，宽松放行
        pass

    hash_id = uuid.uuid4().hex[:12]
    stored_name = f"{hash_id}_{filename}"
    stored_path = os.path.join(HASH_DIR, stored_name)
    raw = await file.read()
    try:
        with open(stored_path, "wb") as f:
            f.write(raw)
    except OSError as e:
        return build_ret(error_map["Error"], {"error": f"文件保存失败: {e}"})

    now = curr_date()
    line_count = sum(1 for line in raw.splitlines() if line.strip())
    doc = {
        "hash_id": hash_id,
        "filename": filename,
        "stored_path": stored_path,
        "size": len(raw),
        "line_count": line_count,
        "save_date": now,
    }
    await conn_db("hashcat_hash").insert_one(doc)
    return {
        "code": 200, "message": "success",
        "data": {"hash_id": hash_id, "hash_file": stored_path,
                 "filename": filename, "size": len(raw), "line_count": line_count},
    }


@router.get("/hashes/")
async def list_hashes(request: Request):
    """已上传哈希文件列表（供前端选择）。"""
    return await build_data(parse_query_params(request), "hashcat_hash")


# ----------------------------- 任务列表 / 提交 -----------------------------
@router.get("/task/")
async def list_task(request: Request):
    """hashcat 任务列表（分页 + 过滤）。"""
    return await build_data(parse_query_params(request), "hashcat_task")


@router.post("/task/")
async def add_task(body: AddHashcatBody):
    """提交 hashcat 恢复任务，立即返回 task_id。"""
    if not body.hash_file:
        return build_ret(error_map["Error"], {"error": "hash_file 为空"})
    if not os.path.exists(body.hash_file):
        return build_ret(error_map["Error"], {"error": "哈希文件不存在，请重新上传"})

    now = curr_date()
    task_id = str(ObjectId())
    run_id = uuid.uuid4().hex
    doc = {
        "_id": ObjectId(task_id),
        "name": body.name,
        "hash_file": body.hash_file,
        "wordlist": body.wordlist,
        "options": body.options,
        "status": "waiting",
        "run_id": run_id,
        "result_count": 0,
        "save_date": now,
        "update_date": now,
    }
    await conn_db("hashcat_task").insert_one(doc)

    # 后台执行
    coro = _run_with_cancel_guard(task_id, run_id)
    t = asyncio.create_task(coro, name=f"hashcat-{run_id}")
    _running[run_id] = t
    _task_to_run[task_id] = run_id
    t.add_done_callback(lambda _: _cleanup_run(run_id, task_id))

    return {"code": 200, "message": "success", "data": {"task_id": task_id, "run_id": run_id}}


async def _run_with_cancel_guard(task_id: str, run_id: str) -> None:
    try:
        await run_hashcat_task(task_id)
    except asyncio.CancelledError:
        logger.info(f"hashcat task cancelled: {task_id}")
        raise
    except Exception as e:
        logger.exception(e)


def _cleanup_run(run_id: str, task_id: str) -> None:
    _running.pop(run_id, None)
    _task_to_run.pop(task_id, None)


# ----------------------------- 停止 / 删除 -----------------------------
@router.get("/task/stop/{task_id}")
async def stop_task(task_id: str):
    """停止运行中的 hashcat 任务。"""
    run_id = _task_to_run.get(task_id)
    if not run_id:
        return build_ret(error_map["Error"], {"error": "任务不在运行中或已结束"})
    t = _running.get(run_id)
    if t and not t.done():
        t.cancel()
    await conn_db("hashcat_task").update_one(
        {"_id": ObjectId(task_id), "status": {"$in": ["waiting", "running"]}},
        {"$set": {"status": "stop", "update_date": curr_date()}},
    )
    return {"code": 200, "message": "success"}


@router.post("/task/delete/")
async def delete_task(body: DeleteBody):
    """删除 hashcat 任务及其结果。"""
    deleted: list[str] = []
    for task_id in body.task_ids:
        run_id = _task_to_run.get(task_id)
        if run_id:
            t = _running.get(run_id)
            if t and not t.done():
                t.cancel()
        await conn_db("hashcat_task").delete_one({"_id": ObjectId(task_id)})
        await conn_db("hashcat_result").delete_many({"task_id": task_id})
        deleted.append(task_id)
    return {"code": 200, "message": "success", "data": {"deleted": deleted}}


# ----------------------------- 结果查询 / 导出 -----------------------------
@router.get("/result/")
async def list_result(request: Request):
    """hashcat 结果分页查询。"""
    return await build_data(parse_query_params(request), "hashcat_result")


@router.get("/result/export/")
async def export_result(request: Request):
    """导出结果为 .txt（按 hash 列表）。"""
    return await export_collection(parse_query_params(request), "hashcat_result")


# ----------------------------- 辅助：参数元数据 -----------------------------
@router.get("/param_meta/")
async def param_meta():
    """返回 hashcat 参数元数据，供前端动态渲染表单。"""
    return {"code": 200, "message": "success", "data": PARAM_META}
