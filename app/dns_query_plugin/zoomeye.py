"""zoomeye 子域名查询插件。"""
from __future__ import annotations

import asyncio
import json

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "zoomeye"
        self.api_url = "https://api.zoomeye.org/domain/search"
        self.api_key = None
        self.max_page = 20

    def init_key(self, api_key=None, max_page=20, **kwargs):
        self.api_key = api_key
        self.max_page = max_page

    async def sub_domains(self, target: str) -> list[str]:
        headers = {"API-KEY": self.api_key}
        results: list[str] = []
        curr_page = 1
        while True:
            self.logger.debug(f"zoomeye target:{target} curr_page:{curr_page}")
            param = {"q": target, "page": curr_page, "type": "1"}
            conn = await http_req(self.api_url, 'get', params=param, headers=headers, timeout=(30.1, 50.1))
            data = conn.json()
            if conn.status_code != 200:
                self.logger.error(f"zoomeye query error:{json.dumps(data, ensure_ascii=False)}")
                break
            items = data.get("list", [])
            if not items:
                break
            for item in items:
                name = item.get("name", "")
                if name.endswith("." + target):
                    results.append(name)
            if len(items) < 30:
                break
            await asyncio.sleep(2)
            curr_page += 1
            if curr_page > self.max_page:
                break
        return list(set(results))
