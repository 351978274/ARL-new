"""hunter_qax（奇安信鹰图）子域名查询插件。"""
from __future__ import annotations

import asyncio
import base64
import json

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "hunter_qax"
        self.api_url = "https://hunter.qianxin.com/openApi/search"
        self.api_key = None
        self.page_size = 10
        self.max_page = 10

    def init_key(self, api_key=None, page_size=10, max_page=5, **kwargs):
        self.api_key = api_key
        self.page_size = page_size
        self.max_page = max_page

    async def sub_domains(self, target: str) -> list[str]:
        search = f'domain.suffix="{target}"'
        results: list[str] = []
        curr_page = 1
        while True:
            self.logger.debug(f"hunter_qax target:{target} page_size:{self.page_size} curr_page:{curr_page}")
            param = {
                "search": base64.urlsafe_b64encode(search.encode("utf-8")),
                "page": curr_page, "page_size": self.page_size,
                "is_web": "1", "api-key": self.api_key,
            }
            data = (await http_req(self.api_url, 'get', params=param)).json()
            if data["code"] != 200 and data["code"] != 40205:
                self.logger.error(f"hunter_qax query error:{json.dumps(data, ensure_ascii=False)}")
                break
            if data["code"] == 40205:
                self.logger.info(data.get("message"))
            arr = data.get("data", {}).get("arr") if data.get("data") else None
            if arr is None:
                break
            for item in arr:
                name = item.get("domain", "")
                if name.endswith("." + target):
                    results.append(name)
            if len(arr) < self.page_size:
                break
            await asyncio.sleep(2)
            curr_page += 1
            if curr_page > self.max_page:
                break
        return list(set(results))
