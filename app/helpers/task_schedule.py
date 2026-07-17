"""计划任务调度，移植自原 app/helpers/task_schedule.py。

支持周期任务（cron）与一次性定时任务（future_scan）。
原版用 crontab.CronTab，改用 croniter（croniter 的 next() 返回秒数，语义一致）。
"""
from __future__ import annotations

import time
from datetime import datetime

from croniter import croniter

from ..database import conn_db
from ..logger import get_logger
from ..modules import TaskScheduleStatus, TaskTag
from ..utils import curr_date, time2date

logger = get_logger()


async def task_scheduler():
    """扫描 task_schedule 集合并按计划触发。"""
    items = await conn_db('task_schedule').find({}).to_list(length=None)
    for item in items:
        try:
            if item["status"] != TaskScheduleStatus.SCHEDULED:
                continue
            task_tag = item["task_tag"]
            if task_tag not in [TaskTag.TASK, TaskTag.RISK_CRUISING]:
                logger.warning(f"非资产发现任务或风险巡航任务, {item['task_tag']} {item['_id']}")
                continue
            if item["schedule_type"] == "recurrent_scan":
                cron = item["cron"]
                # 计算距离下一次触发秒数
                now = datetime.now()
                nxt = croniter(cron, now).get_next(datetime)
                next_sec = (nxt - now).total_seconds()
                if next_sec < 60 and abs(time.time() - item.get("last_run_time", 0)) > 60 * 3:
                    logger.info(f"run_recurrent_scan {item['target']} {item['_id']}")
                    await run_recurrent_scan(item)
            elif item["schedule_type"] == "future_scan":
                start_time = item["start_time"]
                if 0 < start_time <= time.time():
                    logger.info(f"run_future_scan {item['target']} {item['_id']}")
                    await run_future_scan(item)
        except Exception as e:
            logger.exception(e)


async def submit_task_schedule(item: dict):
    from .task import submit_risk_cruising, submit_task_task
    from .policy import get_options_by_policy_id
    target = item["target"]
    task_tag = item["task_tag"]
    name = item["name"]
    policy_id = item["policy_id"]
    options = await get_options_by_policy_id(policy_id, task_tag=task_tag)
    if task_tag == TaskTag.TASK:
        await submit_task_task(target=target, name=name, options=options)
    elif task_tag == TaskTag.RISK_CRUISING:
        await submit_risk_cruising(target=target, name=name, options=options)


def get_next_run_date(cron: str) -> str:
    """根据 cron 生成下一次运行时间。"""
    now = datetime.now()
    nxt = croniter(cron, now + __import__('datetime').timedelta(seconds=61)).get_next(datetime)
    return time2date(nxt.timestamp() - 60)


async def run_recurrent_scan(item: dict):
    item["next_run_date"] = get_next_run_date(item["cron"])
    item["run_number"] = item.get("run_number", 0) + 1
    item["last_run_time"] = int(time.time())
    item["last_run_date"] = curr_date()
    await conn_db('task_schedule').find_one_and_replace({"_id": item["_id"]}, item)
    await submit_task_schedule(item)


async def run_future_scan(item: dict):
    item["run_number"] = item.get("run_number", 0) + 1
    item["status"] = TaskScheduleStatus.DONE
    await conn_db('task_schedule').find_one_and_replace({"_id": item["_id"]}, item)
    await submit_task_schedule(item)


async def find_task_schedule(_id: str) -> dict | None:
    from bson import ObjectId
    return await conn_db('task_schedule').find_one({"_id": ObjectId(_id)})


async def remove_task_schedule(_id: str) -> int:
    from bson import ObjectId
    result = await conn_db('task_schedule').delete_one({"_id": ObjectId(_id)})
    return result.deleted_count


async def change_task_schedule_status(_id: str, status: str):
    from bson import ObjectId
    item = await find_task_schedule(_id)
    if not item:
        return None
    old_status = item["status"]
    if old_status == TaskScheduleStatus.ERROR:
        return f"{item['name']} 不可改变状态"
    if old_status == status:
        return f"{item['name']} 已经处于 {status}"
    item["status"] = status
    done_status_list = [TaskScheduleStatus.DONE, TaskScheduleStatus.ERROR, TaskScheduleStatus.STOP]
    if status in done_status_list:
        item["next_run_date"] = "-"
    elif status == TaskScheduleStatus.SCHEDULED:
        if item["schedule_type"] == "recurrent_scan":
            item["next_run_date"] = get_next_run_date(item["cron"])
        else:
            item["next_run_date"] = item.get("start_date", "-")
    await conn_db('task_schedule').find_one_and_replace({"_id": ObjectId(_id)}, item)
    return item
