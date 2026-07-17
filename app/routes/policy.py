"""策略路由，移植自原 app/routes/policy.py。

策略 CRUD（policy 集合，含 domain_config/ip_config/site_config/scope_config）。
"""
from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..database import conn_db
from ..deps import require_auth
from ..modules import build_ret, error_map
from .base import build_data, parse_query_params

router = APIRouter(prefix="/policy", tags=["策略"], dependencies=[Depends(require_auth)])


class PolicyBody(BaseModel):
    name: str
    policy: dict


@router.get("/")
async def list_policy(request: Request):
    return await build_data(parse_query_params(request), "policy")


@router.post("/")
async def add_policy(body: PolicyBody):
    if not body.policy:
        return build_ret(error_map["PolicyDataIsEmpty"])
    await conn_db('policy').insert_one({"name": body.name, "policy": body.policy})
    return build_ret(error_map["Success"], {"name": body.name})


@router.post("/delete/")
async def delete_policy(items: list[dict]):
    for item in items:
        pid = item.get("policy_id") or item.get("_id")
        if pid:
            await conn_db('policy').delete_one({"_id": ObjectId(pid)})
    return build_ret(error_map["Success"])


@router.post("/save/")
async def save_policy(body: dict):
    """更新策略。"""
    policy_id = body.pop("policy_id", None)
    if not policy_id:
        return build_ret(error_map["PolicyIDNotFound"])
    await conn_db('policy').update_one({"_id": ObjectId(policy_id)}, {"$set": body})
    return build_ret(error_map["Success"], {"policy_id": policy_id})
