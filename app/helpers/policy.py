"""策略（policy）辅助，移植自原 app/helpers/policy.py。

从 policy 集合加载扫描选项（domain_config/ip_config/site_config/scope_config）。
"""
from __future__ import annotations

from bson import ObjectId

from ..database import conn_db
from ..modules import TaskTag


async def get_options_by_policy_id(policy_id: str, task_tag: str) -> dict | None:
    data = await conn_db("policy").find_one({"_id": ObjectId(policy_id)})
    if not data:
        return None
    policy = data["policy"]
    options: dict = {"policy_name": data["name"]}
    domain_config = policy.pop("domain_config")
    ip_config = policy.pop("ip_config")
    site_config = policy.pop("site_config")
    if "scope_config" in policy:
        scope_config = policy.pop("scope_config")
        options["related_scope_id"] = scope_config["scope_id"]
    # 仅资产发现任务需要 domain/ip 配置
    if task_tag == TaskTag.TASK:
        options.update(domain_config)
        options.update(ip_config)
    options.update(site_config)
    options.update(policy)
    return options
