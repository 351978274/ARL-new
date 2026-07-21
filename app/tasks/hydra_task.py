"""hydra 任务编排：从 MongoDB 读取任务记录 -> 执行 -> 写结果 -> 更新状态。

对应 app/tasks/dirsearch_task.py 的姊妹模块，保持相同的状态机：
    waiting -> running -> done/error/stop

任务记录由 app/routes/hydra.py 在提交时写入 hydra_task 集合。
"""
from __future__ import annotations

import asyncio

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..services.hydra import run_hydra
from ..utils import curr_date

logger = get_logger()

# hydra 任务状态（与 dirsearch 保持一致，便于前端复用）
STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_STOP = "stop"


async def _update_task(task_id: str, **fields) -> None:
    """更新 hydra_task 文档字段。"""
    fields["update_date"] = curr_date()
    await conn_db("hydra_task").update_one(
        {"_id": ObjectId(task_id)}, {"$set": fields}
    )


async def run_hydra_task(task_id: str) -> None:
    """执行一次 hydra 爆破任务。

    1. 读取任务记录（targets / options）
    2. 标记 running
    3. 调 run_hydra 拿结果
    4. 写入 hydra_result（带 task_id、save_date）
    5. 标记 done（或 error）
    """
    doc = await conn_db("hydra_task").find_one({"_id": ObjectId(task_id)})
    if not doc:
        logger.warning(f"hydra task not found: {task_id}")
        return

    targets: list[str] = list(doc.get("targets", []))
    options: dict = dict(doc.get("options", {}))

    await _update_task(task_id, status=STATUS_RUNNING)

    try:
        results = await run_hydra(targets=targets, options=options)
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
        seen: set[tuple] = set()
        for item in results:
            host = item.get("host", "")
            login = item.get("login", "")
            password = item.get("password", "")
            # 同一任务内按 (host, login, password) 去重
            key = (host, login, password)
            if key in seen:
                continue
            seen.add(key)
            item.setdefault("service", "")
            item["task_id"] = task_id
            item["save_date"] = now
            docs.append(item)
        if docs:
            await conn_db("hydra_result").insert_many(docs)

    await _update_task(
        task_id, status=STATUS_DONE, result_count=len(results),
        finish_date=now,
    )
    logger.info(f"hydra task {task_id} done, cracked: {len(results)}")
