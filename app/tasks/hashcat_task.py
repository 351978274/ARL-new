"""hashcat 任务编排：从 MongoDB 读取任务记录 -> 执行 -> 写结果 -> 更新状态。

状态机与 dirsearch/hydra/sqlmap/aircrack/searchsploit 一致：
    waiting -> running -> done/error/stop
"""
from __future__ import annotations

import asyncio

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..services.hashcat import run_hashcat
from ..utils import curr_date

logger = get_logger()

STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_STOP = "stop"


async def _update_task(task_id: str, **fields) -> None:
    """更新 hashcat_task 文档字段。"""
    fields["update_date"] = curr_date()
    await conn_db("hashcat_task").update_one(
        {"_id": ObjectId(task_id)}, {"$set": fields}
    )


async def run_hashcat_task(task_id: str) -> None:
    """执行一次 hashcat 哈希恢复任务。"""
    doc = await conn_db("hashcat_task").find_one({"_id": ObjectId(task_id)})
    if not doc:
        logger.warning(f"hashcat task not found: {task_id}")
        return

    hash_file: str = doc.get("hash_file", "")
    wordlist: str = doc.get("wordlist", "")
    options: dict = dict(doc.get("options", {}))

    await _update_task(task_id, status=STATUS_RUNNING)

    try:
        results = await run_hashcat(hash_file=hash_file, wordlist=wordlist, options=options)
    except asyncio.CancelledError:
        await _update_task(task_id, status=STATUS_STOP)
        raise
    except Exception as e:
        logger.exception(e)
        await _update_task(task_id, status=STATUS_ERROR, error=str(e))
        return

    # 写入结果集
    now = curr_date()
    cracked_count = 0
    if results:
        docs = []
        seen: set[str] = set()
        for item in results:
            h = item.get("hash", "")
            if h in seen:
                continue
            seen.add(h)
            item["task_id"] = task_id
            item["save_date"] = now
            docs.append(item)
            if item.get("cracked"):
                cracked_count += 1
        if docs:
            await conn_db("hashcat_result").insert_many(docs)

    await _update_task(
        task_id, status=STATUS_DONE, result_count=cracked_count,
        finish_date=now,
    )
    logger.info(f"hashcat task {task_id} done, cracked: {cracked_count}")
