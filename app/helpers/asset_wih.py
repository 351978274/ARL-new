"""资产 WIH 辅助，移植自原 app/helpers/asset_wih.py。"""
from __future__ import annotations

from ..database import conn_db


async def get_wih_record_fnv_hash(scope_id: str) -> list[str]:
    return await conn_db('asset_wih').distinct("fnv_hash", {"scope_id": scope_id})
