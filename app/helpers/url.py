"""URL 辅助查询，移植自原 app/helpers/url.py。"""
from __future__ import annotations

from ..database import conn_db


async def get_url_by_task_id(task_id: str) -> list[str]:
    return await conn_db('url').distinct("url", {"task_id": task_id})
