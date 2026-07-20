"""任务路由，移植自原 app/routes/task.py。

提供任务查询/提交/停止/删除/同步/重启/按策略提交。
"""
from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..database import conn_db
from ..deps import require_auth
from ..helpers import get_options_by_policy_id, submit_task_task, submit_risk_cruising
from ..helpers.task import restart_task
from ..logger import get_logger
from ..modules import (TaskAction, TaskStatus, TaskSyncStatus, TaskTag, TaskType,
                       build_ret, error_map)
from .base import build_data, parse_query_params

logger = get_logger()
router = APIRouter(prefix="/task", tags=["任务"], dependencies=[Depends(require_auth)])


# 默认任务选项
DEFAULT_OPTIONS = {
    "domain_brute": False, "domain_brute_type": "test", "port_scan_type": "test",
    "port_scan": False, "service_detection": False, "service_brute": False,
    "os_detection": False, "site_identify": False, "site_capture": False,
    "file_leak": False, "search_engines": False, "site_spider": False,
    "arl_search": False, "alt_dns": False, "ssl_cert": False,
    "dns_query_plugin": False, "skip_scan_cdn_ip": False,
    "nuclei_scan": False, "findvhost": False, "web_info_hunter": False,
}


class AddTaskBody(BaseModel):
    name: str = Field(..., description="任务名")
    target: str = Field(..., description="目标")
    # 以下选项均可选
    domain_brute: bool | None = None
    domain_brute_type: str | None = None
    port_scan_type: str | None = None
    port_scan: bool | None = None
    service_detection: bool | None = None
    service_brute: bool | None = None
    os_detection: bool | None = None
    site_identify: bool | None = None
    site_capture: bool | None = None
    file_leak: bool | None = None
    search_engines: bool | None = None
    site_spider: bool | None = None
    arl_search: bool | None = None
    alt_dns: bool | None = None
    ssl_cert: bool | None = None
    dns_query_plugin: bool | None = None
    skip_scan_cdn_ip: bool | None = None
    nuclei_scan: bool | None = None
    findvhost: bool | None = None
    web_info_hunter: bool | None = None


def _merge_options(body: AddTaskBody) -> dict:
    options = DEFAULT_OPTIONS.copy()
    for k in DEFAULT_OPTIONS:
        v = getattr(body, k, None)
        if v is not None:
            options[k] = v
    return options


@router.get("/")
async def list_task(request: Request):
    """任务信息查询（分页 + 过滤）。"""
    args = parse_query_params(request)
    return await build_data(args, "task")


@router.post("/")
async def add_task(body: AddTaskBody):
    """任务提交：拆分 IP/域名目标后分别下发。"""
    options = _merge_options(body)
    try:
        task_data_list = await submit_task_task(target=body.target, name=body.name, options=options)
    except Exception as e:
        logger.exception(e)
        return build_ret(error_map["Error"], {"error": str(e)})
    if not task_data_list:
        return build_ret(error_map["TaskTargetIsEmpty"], {"target": body.target})
    return {"code": 200, "message": "success", "data": task_data_list}


@router.post("/batch_stop/")
async def batch_stop(task_ids: list[str]):
    """批量停止任务。"""
    from ..core.task_runner import cancel_task_by_task_id
    ret = []
    for task_id in task_ids:
        item = await conn_db('task').find_one({"_id": ObjectId(task_id)}, {"status": 1, "celery_id": 1})
        if not item:
            ret.append(build_ret(error_map["NotFoundTask"], {"task_id": task_id}))
            continue
        if item.get("status") in (TaskStatus.DONE, TaskStatus.STOP, TaskStatus.ERROR):
            ret.append(build_ret(error_map["TaskIsDone"], {"task_id": task_id}))
            continue
        await cancel_task_by_task_id(task_id)
        await conn_db('task').update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": TaskStatus.STOP, "end_time": None}})
        ret.append(build_ret(error_map["Success"], {"task_id": task_id}))
    return ret


@router.get("/stop/{task_id}")
async def stop_task(task_id: str):
    """停止单个任务。"""
    from ..core.task_runner import cancel_task_by_task_id
    item = await conn_db('task').find_one({"_id": ObjectId(task_id)}, {"status": 1})
    if not item:
        return build_ret(error_map["NotFoundTask"], {"task_id": task_id})
    if item["status"] == TaskStatus.DONE:
        return build_ret(error_map["TaskIsDone"], {"task_id": task_id})
    await cancel_task_by_task_id(task_id)
    await conn_db('task').update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": TaskStatus.STOP, "end_time": None}})
    return build_ret(error_map["Success"], {"task_id": task_id})


@router.post("/delete/")
async def delete_task(items: list[dict]):
    """删除任务。item 含 task_id 与可选 del_task_data。"""
    del_collections = ["cert", "domain", "fileleak", "ip", "service", "site", "url",
                       "vuln", "cip", "npoc_service", "wih", "nuclei_result", "stat_finger"]
    for item in items:
        task_id = item.get("task_id")
        if not task_id:
            continue
        del_data = item.get("del_task_data", False)
        await conn_db('task').delete_one({"_id": ObjectId(task_id)})
        if del_data:
            for col in del_collections:
                await conn_db(col).delete_many({"task_id": task_id})
    return build_ret(error_map["Success"])


@router.post("/sync/")
async def sync_task(body: dict):
    """将域名任务结果同步到资产组。"""
    from ..core.task_runner import submit_task_action
    task_id = body.get("task_id")
    scope_id = body.get("scope_id")
    if not task_id or not scope_id:
        return build_ret(error_map["Error"], {"message": "task_id/scope_id 必填"})
    item = await conn_db('task').find_one({"_id": ObjectId(task_id)})
    if not item:
        return build_ret(error_map["NotFoundTask"], {"task_id": task_id})
    if item.get("type") != TaskType.DOMAIN:
        return build_ret(error_map["TaskTypeIsNotDomain"], {"task_id": task_id})
    if item.get("status") != TaskStatus.DONE:
        return build_ret(error_map["TaskIsDone"], {"task_id": task_id})
    sync_status = item.get("sync_status", TaskSyncStatus.DEFAULT)
    if sync_status == TaskSyncStatus.RUNNING:
        return build_ret(error_map["TaskSyncDealing"], {"task_id": task_id})
    options = {"celery_action": TaskAction.DOMAIN_TASK_SYNC_TASK,
               "data": {"task_id": task_id, "scope_id": scope_id}}
    run_id = await submit_task_action(options)
    return build_ret(error_map["Success"], {"task_id": task_id, "run_id": run_id})


@router.post("/policy/")
async def add_task_by_policy(body: dict):
    """按策略 ID 提交任务。"""
    policy_id = body.get("policy_id")
    target = body.get("target")
    name = body.get("name")
    task_tag = body.get("task_tag", TaskTag.TASK)
    if not (policy_id and target and name):
        return build_ret(error_map["Error"], {"message": "policy_id/target/name 必填"})
    options = await get_options_by_policy_id(policy_id, task_tag=task_tag)
    if options is None:
        return build_ret(error_map["PolicyIDNotFound"], {"policy_id": policy_id})
    try:
        if task_tag == TaskTag.RISK_CRUISING:
            options["result_set_id"] = body.get("result_set_id")
            options["result_set_len"] = body.get("result_set_len", 0)
            task_data_list = await submit_risk_cruising(target=target, name=name, options=options)
        else:
            task_data_list = await submit_task_task(target=target, name=name, options=options)
    except Exception as e:
        logger.exception(e)
        return build_ret(error_map["Error"], {"error": str(e)})
    return {"code": 200, "message": "success", "data": task_data_list}


@router.post("/restart/")
async def restart(body: dict):
    """重新运行已完成的任务。"""
    task_id = body.get("task_id")
    try:
        task_data = await restart_task(task_id)
        return {"code": 200, "message": "success", "data": task_data}
    except Exception as e:
        logger.exception(e)
        return build_ret(error_map["Error"], {"error": str(e)})
