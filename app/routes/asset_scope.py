"""资产组（scope）路由，移植自原 app/routes/assetScope.py。"""
from __future__ import annotations

import re

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..database import conn_db
from ..deps import require_auth
from ..modules import AssetScopeType, build_ret, error_map
from ..utils import is_valid_domain, transfer_ip_scope
from .base import build_data, parse_query_params

router = APIRouter(prefix="/asset_scope", tags=["资产组"], dependencies=[Depends(require_auth)])


class AddScopeBody(BaseModel):
    name: str
    scope: str
    black_scope: str | None = ""
    scope_type: str = "domain"


@router.get("/")
async def list_scope(request: Request):
    return await build_data(parse_query_params(request), "asset_scope")


@router.post("/")
async def add_scope(body: AddScopeBody):
    scope_type = body.scope_type if body.scope_type in (AssetScopeType.IP, AssetScopeType.DOMAIN) else AssetScopeType.DOMAIN
    black_scope_array = []
    if body.black_scope:
        black_scope_array = [x for x in re.split(r",|\s", body.black_scope) if x]
    scope_array = [x for x in re.split(r",|\s", body.scope) if x]
    new_scope_array = []
    for x in scope_array:
        if scope_type == AssetScopeType.DOMAIN:
            if not is_valid_domain(x):
                return build_ret(error_map["DomainInvalid"], {"scope": x})
            new_scope_array.append(x)
        else:
            transfer = transfer_ip_scope(x)
            if transfer is None:
                return build_ret(error_map["ScopeTypeIsNotIP"], {"scope": x})
            new_scope_array.append(transfer)
    if not new_scope_array:
        return build_ret(error_map["DomainInvalid"], {"scope": ""})
    scope_data = {
        "name": body.name, "scope_type": scope_type, "scope": ",".join(new_scope_array),
        "scope_array": new_scope_array, "black_scope": body.black_scope or "",
        "black_scope_array": black_scope_array,
    }
    await conn_db('asset_scope').insert_one(scope_data)
    scope_id = str(scope_data.pop("_id"))
    scope_data["scope_id"] = scope_id
    return build_ret(error_map["Success"], scope_data)


@router.post("/delete/")
async def delete_scope(items: list[dict]):
    for item in items:
        scope_id = item.get("scope_id")
        if not scope_id:
            continue
        await conn_db('asset_scope').delete_one({"_id": ObjectId(scope_id)})
        # 删除关联监控任务
        await conn_db('scheduler').delete_many({"scope_id": scope_id})
    return build_ret(error_map["Success"])
