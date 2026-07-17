"""资产站点辅助，移植自原 app/helpers/asset_site.py。"""
from __future__ import annotations

from ..database import conn_db


def build_show_filed_map(fields: list[str]) -> dict:
    """mongo projection {field: 1}。"""
    return {f: 1 for f in fields}


async def find_site_info_by_scope_id(scope_id: str) -> list[dict]:
    show_map = build_show_filed_map(["site", "title", "status"])
    cursor = conn_db('asset_site').find({"scope_id": scope_id}, show_map)
    return await cursor.to_list(length=None)


async def find_site_by_scope_id(scope_id: str) -> list[str]:
    return await conn_db('asset_site').distinct("site", {"scope_id": scope_id})


def check_asset_site_in_scope(site: str, scope_array: list) -> bool:
    """简单判断站点是否在范围内（子串匹配）。"""
    return any(scope in site for scope in scope_array)


async def find_asset_site_not_in_scope(sites: list, scope_id: str) -> list:
    from .scope import get_scope_by_scope_id
    scopes = await get_scope_by_scope_id(scope_id)
    scope_array = (scopes or {}).get("scope_array", [])
    return [site for site in sites if not check_asset_site_in_scope(site, scope_array)]
