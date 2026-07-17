"""导出与批量导出路由，移植自原 app/routes/export.py + batchExport.py。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import require_auth
from .base import export_collection, batch_export, scope_batch_export, parse_query_params

export_router = APIRouter(prefix="/export", tags=["导出"], dependencies=[Depends(require_auth)])
batch_router = APIRouter(prefix="/batch_export", tags=["批量导出"], dependencies=[Depends(require_auth)])


@export_router.get("/{_type}/")
async def export_one(_type: str, request: Request):
    """导出单个集合：/export/site/?task_id=xxx"""
    return await export_collection(parse_query_params(request), _type)


class BatchBody:
    pass


@batch_router.post("/{_type}/")
async def batch_export_route(_type: str, body: dict):
    """批量导出：body 为 {task_id_list: [...]} 或 {scope_id_list: [...]}"""
    if "scope_id_list" in body:
        return await scope_batch_export(body["scope_id_list"], _type)
    return await batch_export(body.get("task_id_list", []), _type)
