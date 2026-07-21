"""sqlmap 任务编排：从 MongoDB 读取任务记录 -> 执行 -> 写结果 -> 更新状态。

对应 app/tasks/dirsearch_task.py / hydra_task.py 的姊妹模块，状态机一致：
    waiting -> running -> done/error/stop

任务记录由 app/routes/sqlmap.py 在提交时写入 sqlmap_task 集合。
"""
from __future__ import annotations

import asyncio

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..services.sqlmap import run_sqlmap
from ..utils import curr_date

logger = get_logger()

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_STOP = "stop"


async def _update_task(task_id: str, **fields) -> None:
    """更新 sqlmap_task 文档字段。"""
    fields["update_date"] = curr_date()
    await conn_db("sqlmap_task").update_one(
        {"_id": ObjectId(task_id)}, {"$set": fields}
    )


async def run_sqlmap_task(task_id: str) -> None:
    """执行一次 sqlmap 扫描任务。

    1. 读取任务记录（targets / options）
    2. 标记 running
    3. 调 run_sqlmap 拿结果
    4. 写入 sqlmap_result（带 task_id、save_date）
    5. 标记 done（或 error）
    """
    doc = await conn_db("sqlmap_task").find_one({"_id": ObjectId(task_id)})
    if not doc:
        logger.warning(f"sqlmap task not found: {task_id}")
        return

    targets: list[str] = list(doc.get("targets", []))
    options: dict = dict(doc.get("options", {}))

    await _update_task(task_id, status=STATUS_RUNNING)

    try:
        results = await run_sqlmap(targets=targets, options=options)
    except asyncio.CancelledError:
        await _update_task(task_id, status=STATUS_STOP)
        raise
    except Exception as e:
        logger.exception(e)
        await _update_task(task_id, status=STATUS_ERROR, error=str(e))
        return

    # 写入结果集
    now = curr_date()
    if results:
        docs = []
        seen: set[str] = set()
        for item in results:
            target = item.get("target", "")
            # 同一任务内按 target 去重
            if target in seen:
                continue
            seen.add(target)
            item["task_id"] = task_id
            item["save_date"] = now
            docs.append(item)
        if docs:
            await conn_db("sqlmap_result").insert_many(docs)

    await _update_task(
        task_id, status=STATUS_DONE, result_count=len(results),
        finish_date=now,
    )
    logger.info(f"sqlmap task {task_id} done, results: {len(results)}")
