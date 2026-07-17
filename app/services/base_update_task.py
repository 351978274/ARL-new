"""任务状态更新基类，移植自原 app/services/baseUpdateTask.py（异步）。"""
from __future__ import annotations

from bson import ObjectId

from ..database import conn_db


class BaseUpdateTask:
    """更新 task 文档的 status / service 字段。"""

    def __init__(self, task_id: str):
        self.task_id = task_id

    async def update_services(self, service_name: str, elapsed: float) -> None:
        elapsed_str = f"{elapsed:.2f}"
        await self.update_task_field("status", service_name)
        query = {"_id": ObjectId(self.task_id)}
        update = {"$push": {"service": {"name": service_name, "elapsed": float(elapsed_str)}}}
        await conn_db('task').update_one(query, update)

    async def update_task_field(self, field=None, value=None) -> None:
        query = {"_id": ObjectId(self.task_id)}
        update = {"$set": {field: value}}
        await conn_db('task').update_one(query, update)
