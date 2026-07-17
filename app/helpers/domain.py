"""任务相关 IP/域名查询，移植自原 app/helpers/domain.py。"""
from __future__ import annotations

from ..database import conn_db


async def find_private_domain_by_task_id(task_id: str) -> list[str]:
    """查询任务中 PRIVATE 类型的关联域名。"""
    cursor = conn_db('ip').find({"task_id": task_id, "ip_type": "PRIVATE"})
    domains: list[str] = []
    async for item in cursor:
        if not item.get("domain"):
            continue
        domains.extend(item["domain"])
    return list(set(domains))


async def find_public_ip_by_task_id(task_id: str) -> list[str]:
    return await conn_db('ip').distinct("ip", {"task_id": task_id, "ip_type": "PUBLIC"})


async def find_domain_by_task_id(task_id: str) -> list[str]:
    return await conn_db('domain').distinct("domain", {"task_id": task_id})
