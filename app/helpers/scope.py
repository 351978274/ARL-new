"""资产范围（scope）辅助，移植自原 app/helpers/scope.py。"""
from __future__ import annotations

from bson import ObjectId

from ..database import conn_db
from ..utils import ip_in_scope
from ..utils.domain_util import is_in_scopes


async def check_target_in_scope(target: str, scope_list: list[str]):
    from .task import get_ip_domain_list
    ip_list, domain_list = await get_ip_domain_list(target)
    for ip in ip_list:
        if not ip_in_scope(ip, scope_list):
            raise Exception(f"{ip}不在范围{','.join(scope_list)}中")
    for domain in domain_list:
        if not is_in_scopes(domain, scope_list):
            raise Exception(f"{domain}不在范围{','.join(scope_list)}中")
    return ip_list, domain_list


async def get_scope_by_scope_id(scope_id: str) -> dict | None:
    return await conn_db("asset_scope").find_one({"_id": ObjectId(scope_id)})
