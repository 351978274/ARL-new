"""资产 WIH（WebInfoHunter）监控，移植自原 app/services/asset_wih_monitor.py。

对 scope 中站点周期性调用 WIH，返回新发现的记录。
"""
from __future__ import annotations

from ..database import conn_db
from ..logger import get_logger
from .info_hunter import run_wih

logger = get_logger()


async def asset_wih_monitor(scope_id: str):
    """对 scope 下所有站点运行 WIH，返回 WihRecord 列表。"""
    sites = [item["site"] async for item in conn_db('asset_site').find({"scope_id": scope_id}, {"site": 1})]
    if not sites:
        return []
    records = await run_wih(sites)
    # 只保留 scope_domain 范围内的记录（domain 类型）
    return records
