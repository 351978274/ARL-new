"""aircrack-ng 任务编排：从 MongoDB 读取任务记录 -> 执行 -> 写结果 -> 更新状态。

对应 app/tasks/dirsearch_task.py / hydra_task.py / sqlmap_task.py 的姊妹模块，
状态机一致：waiting -> running -> done/error/stop

任务记录由 app/routes/aircrack.py 在提交时写入 aircrack_task 集合。
"""
from __future__ import annotations

import asyncio

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..services.aircrack import run_aircrack
from ..utils import curr_date

logger = get_logger()

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_STOP = "stop"


async def _update_task(task_id: str, **fields) -> None:
    """更新 aircrack_task 文档字段。"""
    fields["update_date"] = curr_date()
    await conn_db("aircrack_task").update_one(
        {"_id": ObjectId(task_id)}, {"$set": fields}
    )


async def run_aircrack_task(task_id: str) -> None:
    """执行一次 aircrack-ng 离线破解任务。

    1. 读取任务记录（capture_file / options）
    2. 标记 running
    3. 调 run_aircrack 拿结果
    4. 写入 aircrack_result（带 task_id、save_date）
    5. 标记 done（或 error）
    """
    doc = await conn_db("aircrack_task").find_one({"_id": ObjectId(task_id)})
    if not doc:
        logger.warning(f"aircrack-ng task not found: {task_id}")
        return

    capture_file: str = doc.get("capture_file", "")
    options: dict = dict(doc.get("options", {}))

    await _update_task(task_id, status=STATUS_RUNNING)

    try:
        result = await run_aircrack(capture_file=capture_file, options=options)
    except asyncio.CancelledError:
        await _update_task(task_id, status=STATUS_STOP)
        raise
    except Exception as e:
        logger.exception(e)
        await _update_task(task_id, status=STATUS_ERROR, error=str(e))
        return

    # 写入结果集（单任务单结果文档）
    now = curr_date()
    result["task_id"] = task_id
    result["save_date"] = now
    await conn_db("aircrack_result").insert_one(result)

    await _update_task(
        task_id, status=STATUS_DONE,
        result_count=1 if result.get("cracked") else 0,
        finish_date=now,
    )
    logger.info(f"aircrack-ng task {task_id} done, cracked: {result.get('cracked')}")
