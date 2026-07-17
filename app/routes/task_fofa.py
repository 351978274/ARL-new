"""FOFA 任务路由，移植自原 app/routes/taskFofa.py。

通过 FOFA 查询 IP 列表后下发 IP 扫描任务。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import require_auth
from ..helpers.task import build_task_data, submit_task
from ..logger import get_logger
from ..modules import TaskTag, TaskType, build_ret, error_map
from ..services.fofa_client import fofa_query

logger = get_logger()
router = APIRouter(prefix="/task_fofa", tags=["FOFA任务"], dependencies=[Depends(require_auth)])


class FofaTaskBody(BaseModel):
    name: str
    query: str
    options: dict = {}


@router.post("/")
async def add_fofa_task(body: FofaTaskBody):
    result = await fofa_query(body.query, fields="ip")
    if isinstance(result, str):
        return build_ret(error_map["FofaConnectError"], {"error": result})
    if not result:
        return build_ret(error_map["FofaResultEmpty"])
    fofa_ip = list(set(result))
    task_data = build_task_data(body.name, " ".join(fofa_ip), TaskType.FOFA, TaskTag.TASK, body.options)
    task_data["fofa_ip"] = fofa_ip
    task_data = await submit_task(task_data)
    return {"code": 200, "message": "success", "data": task_data}
