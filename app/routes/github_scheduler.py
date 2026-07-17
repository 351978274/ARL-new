"""Github 监控任务路由，移植自原 app/routes/github_scheduler.py。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..database import conn_db
from ..deps import require_auth
from ..modules import SchedulerStatus, build_ret, error_map
from ..utils import curr_date, time2date
from ..utils.cron_util import check_cron
from ..utils.github_task import delete_github_scheduler, find_github_scheduler, recover_task, stop_task
from .base import build_data, parse_query_params

router = APIRouter(prefix="/github_scheduler", tags=["Github监控任务"], dependencies=[Depends(require_auth)])


class GithubSchedulerBody(BaseModel):
    name: str
    keyword: str
    cron: str


@router.get("/")
async def list_github_scheduler(request: Request):
    return await build_data(parse_query_params(request), "github_scheduler")


@router.post("/")
async def add_github_scheduler(body: GithubSchedulerBody):
    if not check_cron(body.cron):
        return build_ret(error_map["CronError"], {"cron": body.cron})
    item = {
        "name": body.name, "keyword": body.keyword, "cron": body.cron,
        "status": SchedulerStatus.RUNNING, "run_number": 0,
        "last_run_time": 0, "last_run_date": "-",
        "next_run_time": int(time.time()) + 60,
        "next_run_date": time2date(int(time.time()) + 60),
    }
    await conn_db('github_scheduler').insert_one(item)
    return build_ret(error_map["Success"], {"_id": str(item["_id"])})


@router.post("/delete/")
async def delete(items: list[dict]):
    for item in items:
        sid = item.get("github_scheduler_id") or item.get("_id")
        if sid:
            await delete_github_scheduler(sid)
    return build_ret(error_map["Success"])


@router.post("/stop/")
async def stop(items: list[dict]):
    for item in items:
        sid = item.get("github_scheduler_id") or item.get("_id")
        if sid:
            await stop_task(sid)
    return build_ret(error_map["Success"])


@router.post("/recover/")
async def recover(items: list[dict]):
    for item in items:
        sid = item.get("github_scheduler_id") or item.get("_id")
        if sid:
            await recover_task(sid)
    return build_ret(error_map["Success"])
