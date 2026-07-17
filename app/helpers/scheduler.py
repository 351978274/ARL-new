"""监控任务查重辅助，移植自原 app/helpers/scheduler.py。"""
from __future__ import annotations

from ..database import conn_db


async def have_same_site_update_monitor(scope_id: str) -> bool:
    result = await conn_db('scheduler').find_one(
        {"scope_id": scope_id, "scope_type": "site_update_monitor"})
    return result is not None


async def have_same_wih_update_monitor(scope_id: str) -> bool:
    result = await conn_db('scheduler').find_one(
        {"scope_id": scope_id, "scope_type": "wih_update_monitor"})
    return result is not None
