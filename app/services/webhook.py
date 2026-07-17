"""资产监控 Webhook 推送，移植自原 app/services/webhook.py。

监控任务结束后向配置的 URL POST 提交 JSON（Header 带 Token）。
"""
from __future__ import annotations

import json

from bson import json_util, ObjectId

from ..config import Config
from ..core.http_client import http_req
from ..database import conn_db
from ..logger import get_logger

logger = get_logger()


def _build_show_field_map(fields: list[str]) -> dict:
    """构造 mongo projection {field: 1, _id: 0}。"""
    show_map = {f: 1 for f in fields}
    show_map["_id"] = 0
    return show_map


class BaseAssetWebHook:
    def __init__(self, task_id: str, scope_id: str):
        self.task_id = task_id
        self.scope_id = scope_id
        self.limit_num = 100

    async def get_domain_info(self):
        show_map = _build_show_field_map(["domain", "record", "type", "ips"])
        items = await conn_db('domain').find({"task_id": self.task_id}, show_map).to_list(self.limit_num)
        return items

    async def get_site_info(self):
        show_map = _build_show_field_map(["site", "title", "status", "http_server", "body_length"])
        items = await conn_db('site').find({"task_id": self.task_id}, show_map).to_list(self.limit_num)
        return items

    async def get_ip_info(self):
        show_map = _build_show_field_map(["ip", "port_info", "ip_type", "geo_asn", "geo_city", "cdn_name"])
        items = await conn_db('ip').find({"task_id": self.task_id}, show_map).to_list(self.limit_num)
        return items

    async def get_asset_scope_data(self):
        show_map = _build_show_field_map(["name", "scope_type"])
        return await conn_db('asset_scope').find_one({"_id": ObjectId(self.scope_id)}, show_map)

    async def get_task_data(self):
        show_map = _build_show_field_map(["name", "target", "start_time", "status", "end_time", "options"])
        return await conn_db('task').find_one({"_id": ObjectId(self.task_id)}, show_map)


class DomainAssetWebHook(BaseAssetWebHook):
    def __init__(self, task_id, scope_id, web_hook_url, web_hook_token):
        super().__init__(task_id, scope_id)
        self.web_hook_url = web_hook_url
        self.web_hook_token = web_hook_token

    async def build_data(self):
        return {
            "type": "domain_monitor", "task_id": self.task_id,
            "task_data": await self.get_task_data(), "scope_id": self.scope_id,
            "scope_data": await self.get_asset_scope_data(),
            "asset": {"domain_info": await self.get_domain_info(), "site_info": await self.get_site_info()},
        }

    async def run_web_hook(self):
        data = await self.build_data()
        data = json.loads(json_util.dumps(data))
        domain_info_list = data["asset"]["domain_info"]
        site_info_list = data["asset"]["site_info"]
        if domain_info_list or site_info_list:
            logger.info(f"send web_hook to {self.web_hook_url} domain:{len(domain_info_list)} site:{len(site_info_list)}")
            await http_req(self.web_hook_url, method="post", json=data,
                           headers={"Token": self.web_hook_token})


class IPAssetWebHook(BaseAssetWebHook):
    def __init__(self, task_id, scope_id, web_hook_url, web_hook_token):
        super().__init__(task_id, scope_id)
        self.web_hook_url = web_hook_url
        self.web_hook_token = web_hook_token

    async def build_data(self):
        return {
            "type": "ip_monitor", "task_id": self.task_id,
            "task_data": await self.get_task_data(), "scope_id": self.scope_id,
            "scope_data": await self.get_asset_scope_data(),
            "asset": {"ip_info": await self.get_ip_info(), "site_info": await self.get_site_info()},
        }

    async def run_web_hook(self):
        data = json.loads(json_util.dumps(await self.build_data()))
        ip_info_list = data["asset"]["ip_info"]
        site_info_list = data["asset"]["site_info"]
        if ip_info_list or site_info_list:
            logger.info(f"send web_hook to {self.web_hook_url} ip:{len(ip_info_list)} site:{len(site_info_list)}")
            await http_req(self.web_hook_url, method="post", json=data,
                           headers={"Token": self.web_hook_token})


class SiteAssetWebHook(BaseAssetWebHook):
    def __init__(self, task_id, scope_id, web_hook_url, web_hook_token):
        super().__init__(task_id, scope_id)
        self.web_hook_url = web_hook_url
        self.web_hook_token = web_hook_token

    async def run_web_hook(self):
        data = json.loads(json_util.dumps({
            "type": "site_monitor", "task_id": self.task_id,
            "task_data": await self.get_task_data(), "scope_id": self.scope_id,
            "scope_data": await self.get_asset_scope_data(),
            "asset": {"site_info": await self.get_site_info()},
        }))
        site_info_list = data["asset"]["site_info"]
        if site_info_list:
            logger.info(f"send web_hook to {self.web_hook_url} site:{len(site_info_list)}")
            await http_req(self.web_hook_url, method="post", json=data,
                           headers={"Token": self.web_hook_token})


async def domain_asset_web_hook(task_id: str, scope_id: str):
    if not Config.WEB_HOOK_URL:
        return
    try:
        await DomainAssetWebHook(task_id, scope_id, Config.WEB_HOOK_URL, Config.WEB_HOOK_TOKEN).run_web_hook()
    except Exception as e:
        logger.error(str(e))


async def ip_asset_web_hook(task_id: str, scope_id: str):
    if not Config.WEB_HOOK_URL:
        return
    try:
        await IPAssetWebHook(task_id, scope_id, Config.WEB_HOOK_URL, Config.WEB_HOOK_TOKEN).run_web_hook()
    except Exception as e:
        logger.error(str(e))


async def site_asset_web_hook(task_id: str, scope_id: str):
    if not Config.WEB_HOOK_URL:
        return
    try:
        await SiteAssetWebHook(task_id, scope_id, Config.WEB_HOOK_URL, Config.WEB_HOOK_TOKEN).run_web_hook()
    except Exception as e:
        logger.error(str(e))
