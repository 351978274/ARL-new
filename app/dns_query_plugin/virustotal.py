"""virustotal 子域名查询插件。"""
from __future__ import annotations

import asyncio
import json
import re

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "virustotal"
        self.api_url = "https://www.virustotal.com/"
        self.api_key = None

    def init_key(self, api_key=None, **kwargs):
        self.api_key = api_key

    async def sub_domains(self, target: str) -> list[str]:
        first_url = f"{self.api_url}api/v3/domains/{target}/subdomains?limit=40"
        headers = {"x-apikey": self.api_key}
        next_url: str | None = first_url
        results: list[str] = []
        curr_page = 1
        while next_url:
            self.logger.debug(f"{self.source_name} target:{target} curr_page:{curr_page}")
            conn = await http_req(next_url, 'get', headers=headers)
            data = conn.json()
            if data.get("error"):
                self.logger.error(f"{self.source_name} query error:{json.dumps(data, ensure_ascii=False)}")
                break
            for item in re.findall(r'"([^"]+)"', conn.text):
                if item.endswith("." + target):
                    results.append(item)
            next_url = data.get("links", {}).get("next")
            curr_page += 1
            if not next_url:
                break
            await asyncio.sleep(2)
        return list(set(results))
