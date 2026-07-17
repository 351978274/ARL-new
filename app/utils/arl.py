"""ARL 资产聚合统计（异步），移植自原 app/utils/arl.py。

跨集合的资产查找与统计：任务→域名/IP/站点、scope→资产域名、统计计数、C段聚合、指纹统计。
"""
from __future__ import annotations

from bson import ObjectId

from ..database import conn_db
from .IPy import IP


async def get_task_ids(domain: str) -> list[str]:
    cursor = conn_db('task').find({"target": domain}, {"_id": 1})
    return [str(item["_id"]) async for item in cursor]


async def get_domain_by_id(task_id: str) -> list[str]:
    cursor = conn_db('domain').find({"task_id": task_id}, {"domain": 1})
    return [item["domain"] async for item in cursor]


async def arl_domain(domain: str) -> list[str]:
    """聚合任务历史域名 + 资产组域名（以 domain 为后缀）。"""
    from .domain_util import is_valid_domain
    domains: list[str] = []
    for task_id in await get_task_ids(domain):
        for item in await get_domain_by_id(task_id):
            if not is_valid_domain(domain):
                continue
            if item.endswith("." + domain):
                domains.append(item)

    for scope_id in await get_scope_ids(domain):
        for item in await get_asset_domain_by_id(scope_id):
            if not is_valid_domain(domain):
                continue
            if item.endswith("." + domain):
                domains.append(item)

    return list(set(domains))


async def get_asset_domain_by_id(scope_id: str) -> list[str]:
    cursor = conn_db('asset_domain').find({"scope_id": scope_id}, {"domain": 1})
    return [item["domain"] async for item in cursor]


async def get_monitor_domain_by_id(scope_id: str) -> list[str]:
    cursor = conn_db('scheduler').find({"scope_id": scope_id}, {"domain": 1})
    return [item["domain"] async for item in cursor]


async def scope_data_by_id(scope_id: str) -> dict | None:
    return await conn_db('asset_scope').find_one({"_id": ObjectId(scope_id)})


async def get_scope_ids(domain: str) -> list[str]:
    cursor = conn_db('asset_scope').find({"scope_array": domain}, {"_id": 1})
    return [str(item["_id"]) async for item in cursor]


async def task_statistic(task_id: str | None = None) -> dict:
    """统计任务各资产表数量。"""
    query: dict = {}
    if isinstance(task_id, str) and len(task_id) == 24:
        query["task_id"] = task_id

    ret: dict = {}
    table_list = ['site', 'domain', 'ip', 'cert', 'service', 'fileleak',
                  'url', 'vuln', 'npoc_service', 'cip', 'nuclei_result', 'stat_finger', 'wih']
    for table in table_list:
        cnt = await conn_db(table).count_documents(query)
        ret[f"{table}_cnt"] = cnt
    return ret


async def gen_cip_map(task_id: str | None = None) -> dict:
    """C 段（/24）IP 聚合。"""
    query: dict = {}
    if isinstance(task_id, str) and len(task_id) == 24:
        query["task_id"] = task_id

    results = await conn_db('ip').find(query, {"ip": 1, "domain": 1}).to_list(length=None)
    cip_map: dict = {}
    have_domain_flag = True

    for result in results:
        if result.get("domain") is None:
            have_domain_flag = False
        cip = IP(result["ip"] + "/24", make_net=True).strNormal(1)
        count_map = cip_map.get(cip)
        if count_map is None:
            domain_set = set(result["domain"]) if have_domain_flag else set()
            cip_map[cip] = {"domain_set": domain_set, "ip_set": {result["ip"]}}
        else:
            if have_domain_flag:
                count_map["domain_set"] |= set(result["domain"])
            count_map["ip_set"] |= {result["ip"]}
    return cip_map


async def gen_stat_finger_map(task_id: str | None = None) -> dict:
    """按指纹名聚合计数。"""
    query: dict = {}
    if isinstance(task_id, str) and len(task_id) == 24:
        query["task_id"] = task_id

    results = await conn_db('site').find(query, {"finger": 1}).to_list(length=None)
    finger_map: dict = {}
    for result in results:
        if not isinstance(result.get("finger"), list):
            continue
        for finger in result["finger"]:
            key = finger["name"].lower()
            if key not in finger_map:
                finger_map[key] = {"name": finger["name"], "cnt": 1}
            else:
                finger_map[key]["cnt"] += 1
    return finger_map
