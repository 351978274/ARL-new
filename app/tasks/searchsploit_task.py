"""searchsploit 任务编排：从 MongoDB 读取任务记录 -> 执行 -> 写结果 -> 更新状态。

对应 app/tasks/dirsearch_task.py / hydra_task.py / sqlmap_task.py / aircrack_task.py 的姊妹模块，
状态机一致：waiting -> running -> done/error/stop

任务记录由 app/routes/searchsploit.py 在提交时写入 searchsploit_task 集合。
"""
from __future__ import annotations

import asyncio

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..services.searchsploit import run_searchsploit
from ..utils import curr_date

logger = get_logger()

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_STOP = "stop"


async def _update_task(task_id: str, **fields) -> None:
    """更新 searchsploit_task 文档字段。"""
    fields["update_date"] = curr_date()
    await conn_db("searchsploit_task").update_one(
        {"_id": ObjectId(task_id)}, {"$set": fields}
    )


async def run_searchsploit_task(task_id: str) -> None:
    """执行一次 searchsploit 搜索任务。

    1. 读取任务记录（terms / options）
    2. 标记 running
    3. 调 run_searchsploit 拿结果
    4. 写入 searchsploit_result（带 task_id、save_date）
    5. 标记 done（或 error）
    """
    doc = await conn_db("searchsploit_task").find_one({"_id": ObjectId(task_id)})
    if not doc:
        logger.warning(f"searchsploit task not found: {task_id}")
        return

    terms: list[str] = list(doc.get("terms", []))
    options: dict = dict(doc.get("options", {}))

    await _update_task(task_id, status=STATUS_RUNNING)

    try:
        results = await run_searchsploit(terms=terms, options=options)
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
            edb_id = item.get("edb_id", "")
            # 同一任务内按 (source, edb_id) 去重；edb_id 为空时按 title+path
            key = (item.get("source", ""), edb_id or item.get("title", "") + item.get("path", ""))
            if key in seen:
                continue
            seen.add(key)
            item["task_id"] = task_id
            item["save_date"] = now
            docs.append(item)
        if docs:
            await conn_db("searchsploit_result").insert_many(docs)

    await _update_task(
        task_id, status=STATUS_DONE, result_count=len(results),
        finish_date=now,
    )
    logger.info(f"searchsploit task {task_id} done, results: {len(results)}")
