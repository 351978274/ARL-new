"""APScheduler 调度：资产监控/GitHub 监控/计划任务调度。

移植自原 app/scheduler.py（自研 run_forever 循环）+ github_task_scheduler。
本版使用 APScheduler AsyncIOScheduler 定时轮询 scheduler 集合并派发任务。
"""
from __future__ import annotations

import time

from bson import ObjectId

from ..database import conn_db as conn
from ..helpers import asset_site_monitor as asset_site_monitor_helper
from ..helpers import asset_wih_monitor as asset_wih_monitor_helper
from ..helpers.task_schedule import task_scheduler
from ..logger import get_logger
from ..modules import AssetScopeType, SchedulerStatus
from ..utils import curr_date, time2date

logger = get_logger()

# 监控任务默认选项（与原 app/scheduler.py 一致）
domain_monitor_options = {
    'domain_brute': True, 'domain_brute_type': 'big', 'alt_dns': False,
    'arl_search': True, 'port_scan_type': 'test', 'port_scan': True,
    'dns_query_plugin': True, 'site_identify': False,
}
ip_monitor_options = {'port_scan_type': 'test', 'port_scan': True, 'site_identify': False}


# ---- job CRUD ----

async def add_job(domain, scope_id, options=None, interval: int = 3600, name: str = "",
                  scope_type: str = AssetScopeType.DOMAIN) -> str:
    logger.info(f"add {scope_type} job {interval} {domain} {scope_id}")
    if options is None:
        options = domain_monitor_options.copy() if scope_type == AssetScopeType.DOMAIN else ip_monitor_options.copy()
    disable_options = {"domain_brute": False, "alt_dns": False, "dns_query_plugin": False, "arl_search": False}
    if scope_type == AssetScopeType.IP:
        options.update(disable_options)
    current_time = int(time.time()) + 30
    item = {
        "domain": domain, "scope_id": scope_id, "interval": interval,
        "next_run_time": current_time, "next_run_date": time2date(current_time),
        "last_run_time": 0, "last_run_date": "-", "run_number": 0,
        "status": SchedulerStatus.RUNNING, "monitor_options": options,
        "name": name, "scope_type": scope_type,
    }
    await conn('scheduler').insert_one(item)
    return str(item["_id"])


async def add_asset_site_monitor_job(scope_id: str, name: str, interval: int = 3600) -> str:
    current_time = int(time.time()) + 30
    item = {
        "domain": "资产站点更新", "scope_id": scope_id, "interval": interval,
        "next_run_time": current_time, "next_run_date": time2date(current_time),
        "last_run_time": 0, "last_run_date": "-", "run_number": 0,
        "status": SchedulerStatus.RUNNING, "monitor_options": {},
        "name": name, "scope_type": "site_update_monitor",
    }
    await conn('scheduler').insert_one(item)
    return str(item["_id"])


async def add_asset_wih_monitor_job(scope_id: str, name: str, interval: int = 3600) -> str:
    current_time = int(time.time()) + 30
    item = {
        "domain": "资产分组 WIH 更新", "scope_id": scope_id, "interval": interval,
        "next_run_time": current_time, "next_run_date": time2date(current_time),
        "last_run_time": 0, "last_run_date": "-", "run_number": 0,
        "status": SchedulerStatus.RUNNING, "monitor_options": {},
        "name": name, "scope_type": "wih_update_monitor",
    }
    await conn('scheduler').insert_one(item)
    return str(item["_id"])


async def delete_job(job_id: str):
    return await conn("scheduler").delete_one({"_id": ObjectId(job_id)})


async def stop_job(job_id: str):
    item = await find_job(job_id)
    if not item:
        return None
    item["next_run_date"] = "-"
    item["next_run_time"] = 2**63 - 1  # sys.maxsize 等价
    item["status"] = SchedulerStatus.STOP
    return await conn('scheduler').find_one_and_replace({"_id": ObjectId(job_id)}, item)


async def recover_job(job_id: str):
    current_time = int(time.time()) + 30
    item = await find_job(job_id)
    if not item:
        return None
    next_run_time = current_time + item["interval"]
    item["next_run_date"] = time2date(next_run_time)
    item["next_run_time"] = next_run_time
    item["status"] = SchedulerStatus.RUNNING
    return await conn('scheduler').find_one_and_replace({"_id": ObjectId(job_id)}, item)


async def find_job(job_id: str) -> dict | None:
    return await conn('scheduler').find_one({"_id": ObjectId(job_id)})


async def all_job() -> list[dict]:
    return await conn('scheduler').find({}).to_list(length=None)


async def update_job_run(job_id: str) -> None:
    """记录 job 运行时间并更新下次运行时间。"""
    curr_time = int(time.time())
    item = await find_job(job_id)
    if not item:
        return
    item["next_run_time"] = curr_time + item["interval"]
    item["next_run_date"] = time2date(item["next_run_time"])
    item["last_run_time"] = curr_time
    item["last_run_date"] = time2date(curr_time)
    item["run_number"] += 1
    await conn('scheduler').find_one_and_replace({"_id": item["_id"]}, item)


async def submit_job(domain: str, job_id: str, scope_id: str, options=None,
                     name: str = "", scope_type: str = AssetScopeType.DOMAIN):
    """派发监控任务到 task_runner。"""
    from ..core.task_runner import submit_task_action
    from ..modules import TaskAction

    monitor_options = (domain_monitor_options.copy() if scope_type == AssetScopeType.DOMAIN
                       else ip_monitor_options.copy())
    if options:
        monitor_options.update(options)
    task_data = {
        "domain": domain, "scope_id": scope_id, "job_id": job_id,
        "type": scope_type, "monitor_options": monitor_options, "name": name,
    }
    action = (TaskAction.DOMAIN_EXEC_TASK if scope_type == AssetScopeType.DOMAIN
              else TaskAction.IP_EXEC_TASK)
    task_options = {"celery_action": action, "data": task_data}
    run_id = await submit_task_action(task_options)
    logger.info(f"submit {scope_type} job {run_id} {domain} {scope_id}")


# ---- 主调度循环 ----

async def asset_monitor_scheduler():
    """扫描 scheduler 集合，到期则派发任务。"""
    curr_time = int(time.time())
    items = await all_job()
    for item in items:
        try:
            if item.get("status") == SchedulerStatus.STOP:
                continue
            if item["next_run_time"] > curr_time:
                continue
            domain = item["domain"]
            scope_id = item["scope_id"]
            options = item.get("monitor_options")
            name = item.get("name", "")
            scope_type = item.get("scope_type") or AssetScopeType.DOMAIN

            if scope_type == "site_update_monitor":
                await asset_site_monitor_helper.submit_asset_site_monitor_job(
                    scope_id=scope_id, name=name, scheduler_id=str(item["_id"]))
            elif scope_type == "wih_update_monitor":
                await asset_wih_monitor_helper.submit_asset_wih_monitor_job(
                    scope_id=scope_id, name=name, scheduler_id=str(item["_id"]))
            else:
                await submit_job(domain=domain, job_id=str(item["_id"]),
                                 scope_id=scope_id, options=options, name=name, scope_type=scope_type)
            item["next_run_time"] = curr_time + item["interval"]
            item["next_run_date"] = time2date(item["next_run_time"])
            await conn('scheduler').find_one_and_replace({"_id": item["_id"]}, item)
        except Exception as e:
            logger.exception(e)


async def github_task_scheduler():
    """GitHub 监控任务调度。"""
    from ..utils.github_task import github_task_scheduler as _gts
    await _gts()


async def run_scheduler_tick():
    """单次调度轮询：资产监控 + GitHub 监控 + 计划任务。"""
    await asset_monitor_scheduler()
    await github_task_scheduler()
    await task_scheduler()
