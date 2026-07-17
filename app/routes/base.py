"""FastAPI 路由辅助，移植自原 app/routes/__init__.py 的 ARLResource。

提供分页查询构造、统一返回、导出 .txt 等通用方法，供各路由复用。
查询语法与原版一致：__dgt/__dlt（日期）/__neq/__not/__gt/__lt + EQUAL_FIELDS 等值匹配。
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

from bson import ObjectId
from fastapi import Request
from fastapi.responses import Response

from ..database import conn_db

# 只能用等号进行 mongo 查询的字段
EQUAL_FIELDS = ["task_id", "task_tag", "ip_type", "scope_id", "type"]

# 各集合的导出字段映射
EXPORT_FIELD_MAP = {
    "site": "site", "domain": "domain", "ip": "ip", "asset_site": "site",
    "asset_domain": "domain", "asset_ip": "ip", "asset_wih": "content",
    "url": "url", "cip": "cidr_ip", "wih": "content",
}


def build_db_query(args: dict[str, Any]) -> dict:
    """根据查询参数构造 mongo query（移植自 ARLResource.build_db_query）。"""
    query_args: dict[str, Any] = {}
    base_keys = {"page", "size", "order"}

    for key, value in args.items():
        if key in base_keys or value is None:
            continue
        if key == "_id":
            if value:
                query_args[key] = ObjectId(value)
            continue

        if key.endswith("__dgt"):
            real_key = key[:-5]
            query_args.setdefault(real_key, {}).update(
                {"$gt": datetime.strptime(value, "%Y-%m-%d %H:%M:%S")})
        elif key.endswith("__dlt"):
            real_key = key[:-5]
            query_args.setdefault(real_key, {}).update(
                {"$lt": datetime.strptime(value, "%Y-%m-%d %H:%M:%S")})
        elif key.endswith("__neq"):
            query_args[key[:-5]] = {"$ne": value}
        elif key.endswith("__not"):
            query_args[key[:-5]] = {"$not": re.compile(re.escape(str(value)))}
        elif key.endswith("__gt") and isinstance(value, int):
            query_args[key[:-4]] = {"$gt": value}
        elif key.endswith("__lt") and isinstance(value, int):
            query_args[key[:-4]] = {"$lt": value}
        elif isinstance(value, str):
            if key in EQUAL_FIELDS:
                query_args[key] = value
            else:
                query_args[key] = {"$regex": re.escape(value), "$options": "i"}
        else:
            query_args[key] = value
    return query_args


def _parse_order(order: str) -> list[tuple[str, int]]:
    """解析排序字符串，如 '-_id,name' -> [('_id',-1),('name',1)]。"""
    orderby_list: list[tuple[str, int]] = []
    for field in order.split(","):
        field = field.strip()
        if field.startswith("-"):
            orderby_list.append((field[1:], -1))
        elif field.startswith("+"):
            orderby_list.append((field[1:], 1))
        else:
            orderby_list.append((field, 1))
    return orderby_list


def _serialize_items(items: list[dict]) -> list[dict]:
    """把 _id/save_date/update_date 转 str。"""
    special = ["_id", "save_date", "update_date"]
    for item in items:
        for key in special:
            if key in item and not isinstance(item[key], str):
                item[key] = str(item[key])
    return items


async def build_data(args: dict[str, Any], collection: str) -> dict:
    """分页查询集合，返回 {page,size,total,items,query,code}。"""
    page = args.pop("page", 1) or 1
    size = args.pop("size", 10) or 10
    if size <= 0:
        size = 10
    if size > 100000:
        size = 100000
    if page <= 0:
        page = 1
    orderby_list = _parse_order(args.pop("order", "-_id"))
    query = build_db_query(args)

    col = conn_db(collection)
    cursor = col.find(query).sort(orderby_list).skip(size * (page - 1)).limit(size)
    items = _serialize_items(await cursor.to_list(length=size))
    total = await col.count_documents(query)

    # query 序列化用于返回
    serial_query = {}
    for k, v in query.items():
        if k in ("_id", "save_date", "update_date"):
            serial_query[k] = str(v)
        elif isinstance(v, dict) and "$not" in v and isinstance(v["$not"], re.Pattern):
            serial_query[k] = {"$not": v["$not"].pattern}
        else:
            serial_query[k] = v
    return {"page": page, "size": size, "total": total, "items": items,
            "query": serial_query, "code": 200}


def make_export_file(items: list[str], _type: str) -> Response:
    """构造 .txt 附件下载响应。"""
    filename = f"{_type}_{len(items)}_{int(time.time())}.txt"
    content = "\r\n".join(items)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/octet-stream",
        headers={
            "Access-Control-Expose-Headers": "Content-Disposition",
            "Content-Disposition": f"attachment; filename={quote(filename)}",
        },
    )


async def export_collection(args: dict[str, Any], _type: str) -> Response:
    """导出集合主字段为 .txt。"""
    field = EXPORT_FIELD_MAP.get(_type, "")
    data = await build_data(args, _type)
    items_set: set[str] = set()
    for item in data["items"]:
        if field and field in item:
            if field == "ip":
                for pi in item.get("port_info", []):
                    items_set.add(f"{item['ip']}:{pi['port_id']}")
            else:
                items_set.add(str(item[field]))
    return make_export_file(list(items_set), _type)


async def batch_export(task_id_list: list[str], _type: str) -> Response:
    """跨任务批量导出。"""
    field = EXPORT_FIELD_MAP.get(_type, "")
    items_set: set[str] = set()
    for task_id in task_id_list:
        if not task_id or not field:
            continue
        items = await conn_db(_type).distinct(field, {"task_id": task_id})
        items_set |= set(items)
    return make_export_file(list(items_set), _type)


async def scope_batch_export(scope_id_list: list[str], _type: str) -> Response:
    """跨资产组批量导出。"""
    field = {"asset_site": "site", "asset_domain": "domain",
             "asset_ip": "ip", "asset_wih": "content"}.get(_type, "")
    items_set: set[str] = set()
    for scope_id in scope_id_list:
        if not scope_id or not field:
            continue
        items = await conn_db(_type).distinct(field, {"scope_id": scope_id})
        items_set |= set(items)
    return make_export_file(list(items_set), _type)


def parse_query_params(request: Request) -> dict[str, Any]:
    """从 request.query_params 解析查询参数，自动转换 int/bool。"""
    args: dict[str, Any] = {}
    for key, value in request.query_params.items():
        # 尝试 int
        if value.isdigit():
            args[key] = int(value)
        elif value.lower() in ("true", "false"):
            args[key] = value.lower() == "true"
        else:
            args[key] = value
    return args
