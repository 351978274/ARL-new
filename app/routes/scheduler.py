"""资产监控任务路由（scheduler），移植自原 app/routes/scheduler.py。

add/stop/recover/delete 监控任务 + 查询列表。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..deps import require_auth
from ..modules import AssetScopeType, build_ret, error_map
from ..scheduler.jobs import (add_asset_site_monitor_job, add_asset_wih_monitor_job, add_job,
                               delete_job, find_job, recover_job, stop_job)
from .base import build_data, parse_query_params

router = APIRouter(prefix="/scheduler", tags=["资产监控任务"], dependencies=[Depends(require_auth)])


class AddMonitorBody(BaseModel):
    scope_id: str
    interval: int = 3600
    name: str = ""
    scope_type: str = AssetScopeType.DOMAIN


@router.get("/")
async def list_scheduler(request: Request):
    return await build_data(parse_query_params(request), "scheduler")


@router.post("/add/")
async def add_monitor(body: AddMonitorBody):
    try:
        job_id = await add_job(body.scope_id, body.scope_id, interval=body.interval,
                               name=body.name, scope_type=body.scope_type)
        return build_ret(error_map["Success"], {"job_id": job_id})
    except Exception as e:
        return build_ret(error_map["Error"], {"error": str(e)})


@router.post("/add_site_monitor/")
async def add_site_monitor(body: AddMonitorBody):
    job_id = await add_asset_site_monitor_job(body.scope_id, body.name, body.interval)
    return build_ret(error_map["Success"], {"job_id": job_id})


@router.post("/add_wih_monitor/")
async def add_wih_monitor(body: AddMonitorBody):
    job_id = await add_asset_wih_monitor_job(body.scope_id, body.name, body.interval)
    return build_ret(error_map["Success"], {"job_id": job_id})


@router.post("/stop/")
async def stop(body: dict):
    job_id = body.get("job_id")
    item = await find_job(job_id)
    if not item:
        return build_ret(error_map["JobNotFound"], {"job_id": job_id})
    await stop_job(job_id)
    return build_ret(error_map["Success"], {"job_id": job_id})


@router.post("/recover/")
async def recover(body: dict):
    job_id = body.get("job_id")
    item = await find_job(job_id)
    if not item:
        return build_ret(error_map["JobNotFound"], {"job_id": job_id})
    await recover_job(job_id)
    return build_ret(error_map["Success"], {"job_id": job_id})


@router.post("/delete/")
async def delete(items: list[dict]):
    for item in items:
        job_id = item.get("job_id")
        if job_id:
            await delete_job(job_id)
    return build_ret(error_map["Success"])
