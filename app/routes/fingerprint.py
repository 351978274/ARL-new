"""指纹规则路由，移植自原 app/routes/fingerprint.py。

CRUD + 批量上传（兼容 ADD-ARL-Finger 的 new 方式）。
"""
from __future__ import annotations

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, UploadFile, File
from pydantic import BaseModel

from ..database import conn_db
from ..deps import require_auth
from ..modules import build_ret, error_map
from .base import build_data, parse_query_params

router = APIRouter(prefix="/fingerprint", tags=["指纹"], dependencies=[Depends(require_auth)])


class FingerBody(BaseModel):
    name: str
    human_rule: str
    category: list | None = None


@router.get("/")
async def list_finger(request: Request):
    return await build_data(parse_query_params(request), "fingerprint")


@router.post("/")
async def add_finger(body: FingerBody):
    # 校验规则
    from ..core.fingerprint import check_expression_with_error
    ok, err = check_expression_with_error(body.human_rule)
    if not ok:
        return build_ret(error_map["RuleInvalid"], {"error": str(err)})
    exists = await conn_db('fingerprint').find_one({"human_rule": body.human_rule})
    if exists:
        return build_ret(error_map["RuleAlreadyExists"])
    data = {"name": body.name, "human_rule": body.human_rule, "update_date": None}
    if body.category:
        data["category"] = body.category
    await conn_db('fingerprint').insert_one(data)
    return build_ret(error_map["Success"], {"name": body.name, "human_rule": body.human_rule})


@router.post("/upload/")
async def upload_finger(file: UploadFile = File(...)):
    """上传 finger.json（name + human_rule 数组）批量导入。"""
    import json
    content = (await file.read()).decode("utf-8")
    try:
        data = json.loads(content)
    except Exception as e:
        return build_ret(error_map["Error"], {"error": f"json 解析失败: {e}"})
    # 兼容两种格式：列表 [{name,rule/human_rule}] 或 {fingerprint:[...]}
    items = data if isinstance(data, list) else data.get("fingerprint", [])
    from ..core.fingerprint import check_expression
    cnt = 0
    for item in items:
        name = item.get("name") or item.get("cms")
        rule = item.get("human_rule") or item.get("rule")
        if not name or not rule:
            continue
        if not check_expression(rule):
            continue
        if await conn_db('fingerprint').find_one({"human_rule": rule}):
            continue
        await conn_db('fingerprint').insert_one({"name": name, "human_rule": rule})
        cnt += 1
    return build_ret(error_map["Success"], {"count": cnt})


@router.post("/delete/")
async def delete_finger(items: list[dict]):
    for item in items:
        fid = item.get("fingerprint_id") or item.get("_id")
        if fid:
            await conn_db('fingerprint').delete_one({"_id": ObjectId(fid)})
    return build_ret(error_map["Success"])
