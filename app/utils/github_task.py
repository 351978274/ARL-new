"""GitHub 监控任务调度，移植自原 app/utils/github_task.py。

原版用 crontab.CronTab，改用 croniter。任务派发改为 task_runner。
"""
from __future__ import annotations

import time
from datetime import datetime

from bson import ObjectId
from croniter import croniter

from ..database import conn_db
from ..logger import get_logger
from ..modules import SchedulerStatus, TaskAction, TaskStatus
from ..utils import curr_date, time2date

logger = get_logger()


async def submit_github_task(task_data: dict, action: str, delay_flag: bool = True):
    """派发 GitHub 任务。"""
    if action not in (TaskAction.GITHUB_TASK_TASK, TaskAction.GITHUB_TASK_MONITOR):
        return "Not in action_map"
    from ..core.task_runner import submit_task_action
    task_options = {"celery_action": action, "data": task_data}
    keyword = task_data["keyword"]
    task_data["celery_id"] = ""
    await conn_db("github_task").insert_one(task_data)
    task_id = str(task_data.pop("_id"))
    task_data["task_id"] = task_id
    try:
        run_id = await submit_task_action(task_options)
        logger.info(f"target:{keyword} task_id:{task_id} run_id:{run_id}")
        task_data["celery_id"] = run_id
        await conn_db("github_task").update_one({"_id": ObjectId(task_id)}, {"$set": {"celery_id": run_id}})
    except Exception as e:
        await conn_db("github_task").delete_one({"_id": ObjectId(task_id)})
        logger.info(f"Github 任务下发失败 {keyword}")
        return str(e)
    return task_data


async def github_cron_run(item: dict):
    task_data = {
        "name": "GitHub监控-" + item["name"], "keyword": item["keyword"],
        "start_time": "-", "end_time": "-",
        "github_scheduler_id": str(item["_id"]), "status": TaskStatus.WAITING,
    }
    await submit_github_task(task_data=task_data, action=TaskAction.GITHUB_TASK_MONITOR)
    item["run_number"] = item.get("run_number", 0) + 1
    item["last_run_date"] = curr_date()
    item["last_run_time"] = int(time.time())
    now = datetime.now() + __import__('datetime').timedelta(seconds=61)
    nxt = croniter(item["cron"], now).get_next(datetime)
    item["next_run_date"] = time2date(nxt.timestamp() - 60)
    await conn_db('github_scheduler').find_one_and_replace({"_id": item["_id"]}, item)


async def github_task_scheduler():
    """扫描 github_scheduler 集合，到期则派发监控任务。"""
    items = await conn_db('github_scheduler').find({}).to_list(length=None)
    for item in items:
        try:
            if item.get("status") != SchedulerStatus.RUNNING:
                continue
            nxt = croniter(item["cron"], datetime.now()).get_next(datetime)
            next_sec = (nxt - datetime.now()).total_seconds()
            if next_sec < 60 and abs(time.time() - item.get("last_run_time", 0)) > 60 * 3:
                logger.info(f"github_cron_run {item['keyword']} {item['_id']}")
                await github_cron_run(item)
        except Exception as e:
            logger.exception(e)


async def find_github_scheduler(_id: str) -> dict | None:
    return await conn_db('github_scheduler').find_one({"_id": ObjectId(_id)})


async def delete_github_scheduler(_id: str):
    if len(_id) != 24:
        return
    await conn_db('github_scheduler').delete_one({"_id": ObjectId(_id)})
    q = {"github_scheduler_id": _id}
    await conn_db('github_hash').delete_many(q)
    await conn_db('github_monitor_result').delete_many(q)


async def recover_task(_id: str):
    if len(_id) != 24:
        return
    item = await find_github_scheduler(_id)
    if not item:
        return
    item["status"] = SchedulerStatus.RUNNING
    nxt = croniter(item["cron"], datetime.now()).get_next(datetime)
    item["next_run_date"] = time2date(nxt.timestamp())
    await conn_db('github_scheduler').find_one_and_replace({"_id": ObjectId(_id)}, item)


async def stop_task(_id: str):
    if len(_id) != 24:
        return
    item = await find_github_scheduler(_id)
    if not item:
        return
    item["status"] = SchedulerStatus.STOP
    item["next_run_date"] = "-"
    await conn_db('github_scheduler').find_one_and_replace({"_id": ObjectId(_id)}, item)
