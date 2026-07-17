"""异步任务执行器，替代原 app/celerytask.py 的 celery 调度。

- submit_task_action(options): 创建 asyncio.Task 执行 run_task(options)，返回 run_id
- run_task(options): 按 task_action（原 celery_action）分发到对应流水线
- 取消任务：通过 task_id 找到 asyncio.Task 并 cancel，同时置 status=stop

任务实际运行在事件循环的后台；任务状态/进度写入 MongoDB（task 集合）。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Awaitable, Callable

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..modules import TaskAction, TaskStatus, TaskSyncStatus
from ..utils import curr_date

logger = get_logger()

# 运行中的任务：run_id -> asyncio.Task
_running_tasks: dict[str, asyncio.Task] = {}
# task_id -> run_id（便于按 task_id 取消）
_task_id_to_run_id: dict[str, str] = {}


async def submit_task_action(options: dict) -> str:
    """派发一个任务，返回 run_id（兼容原 celery_id 字段）。

    options 结构：{"celery_action": <TaskAction.X>, "data": {...}}
    """
    run_id = uuid.uuid4().hex
    coro = _run_with_logging(run_id, options)
    task = asyncio.create_task(coro, name=f"arl-{run_id}")
    _running_tasks[run_id] = task
    task_id = options.get("data", {}).get("task_id")
    if task_id:
        _task_id_to_run_id[task_id] = run_id
    task.add_done_callback(lambda t: _on_done(run_id, t))
    return run_id


def _on_done(run_id: str, task: asyncio.Task) -> None:
    _running_tasks.pop(run_id, None)
    # 反向映射清理
    for tid, rid in list(_task_id_to_run_id.items()):
        if rid == run_id:
            _task_id_to_run_id.pop(tid, None)
            break
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error(f"task {run_id} 异常: {exc}")


async def _run_with_logging(run_id: str, options: dict) -> None:
    import time as _time
    action = options.get("celery_action")
    data = options.get("data", {})
    start = _time.time()
    logger.info(f"run_task action:{action} time:{start}")
    logger.info(f"name:{data.get('name')}, target:{data.get('target')}, task_id:{data.get('task_id')}")
    try:
        await run_task(options)
    except asyncio.CancelledError:
        # 任务被取消，置 stop
        task_id = data.get("task_id")
        if task_id:
            await _mark_task_status(task_id, TaskStatus.STOP)
        raise
    except Exception as e:
        logger.exception(e)
    logger.info(f"end {action} elapsed: {_time.time()-start:.2f}s")


async def run_task(options: dict) -> None:
    """按 task_action 分发到对应流水线。"""
    from .. import tasks as wrap_tasks

    action = options.get("celery_action")
    data = options.get("data", {})
    action_map: dict[str, Callable[[dict], Awaitable]] = {
        TaskAction.DOMAIN_TASK_SYNC_TASK: _domain_task_sync,
        TaskAction.DOMAIN_EXEC_TASK: _domain_exec,
        TaskAction.IP_EXEC_TASK: _ip_exec,
        TaskAction.DOMAIN_TASK: _domain_task,
        TaskAction.IP_TASK: _ip_task,
        TaskAction.RUN_RISK_CRUISING: _run_risk_cruising_task,
        TaskAction.FOFA_TASK: _fofa_task,
        TaskAction.GITHUB_TASK_TASK: _github_task_task,
        TaskAction.GITHUB_TASK_MONITOR: _github_task_monitor,
        TaskAction.ASSET_SITE_UPDATE: _asset_site_update,
        TaskAction.ADD_ASSET_SITE_TASK: _asset_site_add_task,
        TaskAction.ASSET_WIH_UPDATE: _asset_wih_update_task,
    }
    fun = action_map.get(action)
    if fun:
        await fun(data)
    else:
        logger.warning(f"not found {action} action")


# ---- 各 action 的薄封装，转调 tasks 包 ----

async def _domain_task_sync(data: dict):
    from ..services.sync_asset import sync_asset
    scope_id = data.get("scope_id")
    task_id = data.get("task_id")
    query = {"_id": ObjectId(task_id)}
    try:
        await conn_db('task').update_one(query, {"$set": {"sync_status": TaskSyncStatus.RUNNING}})
        await sync_asset(task_id, scope_id, update_flag=False)
        await conn_db('task').update_one(query, {"$set": {"sync_status": TaskSyncStatus.DEFAULT}})
    except Exception as e:
        await conn_db('task').update_one(query, {"$set": {"sync_status": TaskSyncStatus.ERROR}})
        logger.exception(e)


async def _domain_task(data: dict):
    from ..tasks.domain_task import domain_task
    target = data["target"]
    task_options = data["options"]
    task_id = data["task_id"]
    item = await conn_db('task').find_one({"_id": ObjectId(task_id)})
    if not item:
        logger.info(f"domain_task not found {target} {item}")
        return
    await domain_task(target, task_id, task_options)


async def _ip_task(data: dict):
    from ..tasks.ip_task import ip_task
    target = data["target"]
    task_options = data["options"]
    task_id = data["task_id"]
    await ip_task(target, task_id, task_options)


async def _run_risk_cruising_task(data: dict):
    from ..tasks.risk_cruising import run_risk_cruising_task
    task_id = data["task_id"]
    await run_risk_cruising_task(task_id)


async def _fofa_task(data: dict):
    from ..tasks.ip_task import ip_task
    task_id = data["task_id"]
    task_options = data["options"]
    target = " ".join(data["fofa_ip"])
    await ip_task(target, task_id, task_options)


async def _domain_exec(data: dict):
    from ..tasks.scheduler_exec import domain_executors
    await domain_executors(
        base_domain=data.get("domain"), job_id=data.get("job_id"),
        scope_id=data.get("scope_id"), options=data.get("monitor_options"), name=data.get("name"))


async def _ip_exec(data: dict):
    from ..tasks.scheduler_exec import ip_executor
    await ip_executor(target=data.get("domain"), scope_id=data.get("scope_id"),
                      task_name=data.get("name"), job_id=data.get("job_id"),
                      options=data.get("monitor_options"))


async def _github_task_task(data: dict):
    from ..tasks.github import github_task_task
    await github_task_task(task_id=data["task_id"], keyword=data["keyword"])


async def _github_task_monitor(data: dict):
    from ..tasks.github import github_task_monitor
    await github_task_monitor(task_id=data["task_id"], keyword=data["keyword"],
                             scheduler_id=data["github_scheduler_id"])


async def _asset_site_update(data: dict):
    from ..tasks.asset_site import asset_site_update_task
    task_options = data["options"]
    await asset_site_update_task(task_id=data["task_id"],
                                scope_id=task_options["scope_id"],
                                scheduler_id=task_options["scheduler_id"])


async def _asset_wih_update_task(data: dict):
    from ..tasks.asset_wih import asset_wih_update_task
    task_options = data["options"]
    await asset_wih_update_task(task_id=data["task_id"],
                               scope_id=task_options["scope_id"],
                               scheduler_id=task_options["scheduler_id"])


async def _asset_site_add_task(data: dict):
    from ..tasks.asset_site import run_add_asset_site_task
    await run_add_asset_site_task(data["task_id"])


# ---- 取消 ----

async def cancel_task_by_task_id(task_id: str) -> bool:
    """通过 task_id 取消运行中的任务（等价原 celery control.revoke + SIGTERM）。"""
    run_id = _task_id_to_run_id.get(task_id)
    if not run_id:
        return False
    task = _running_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _mark_task_status(task_id: str, status: str) -> None:
    try:
        await conn_db('task').update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": status, "end_time": curr_date()}})
    except Exception as e:
        logger.error(f"mark task {task_id} {status} error: {e}")


def list_running_tasks() -> dict[str, str]:
    """返回 {run_id: task_name}（调试用）。"""
    return {rid: t.get_name() for rid, t in _running_tasks.items()}
