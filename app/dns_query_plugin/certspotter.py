"""certspotter 子域名查询插件。"""
from __future__ import annotations

import asyncio
import json

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "certspotter"
        self.api_url = "https://api.certspotter.com/v1/issuances"
        self.after_id = 0
        self.max_page = 5

    def init_key(self, after_id=0, max_page=5, **kwargs):
        self.after_id = after_id
        self.max_page = max_page

    async def sub_domains(self, target: str) -> list[str]:
        results: set[str] = set()
        next_id = self.after_id
        for i in range(self.max_page):
            self.logger.info(f"{self.source_name}: domain:{target} page:[{i+1}/{self.max_page}] after_id:{next_id}")
            items, next_id = await self.cert_spotter_client(target, next_id)
            results |= items
            if next_id <= 0:
                break
        return list(results)

    async def cert_spotter_client(self, domain: str, after: int = 0):
        param = {"domain": domain, "include_subdomains": "true", "expand": "dns_names", "after": after}
        conn = await http_req(self.api_url, params=param, timeout=(30.1, 50.1))
        data = conn.json()
        if isinstance(data, dict):
            if data.get("code") == "rate_limited":
                retry_after = conn.headers.get("Retry-After", "0")
                sleep_time = int(retry_after) + 5
                self.logger.info(f"{self.source_name}: Retry-After {sleep_time}s")
                if sleep_time < 300:
                    await asyncio.sleep(sleep_time)
                    conn = await http_req(self.api_url, 'get', params=param, timeout=(30.1, 50.1))
                    data = conn.json()
            else:
                self.logger.error(f"{self.source_name}: error: {json.dumps(data, ensure_ascii=False)}")

        dns_names: set[str] = set()
        next_id = 0
        if isinstance(data, list):
            for item in data:
                dns_names |= set(item.get("dns_names", []))
            if data:
                next_id = data[-1].get("id", 0)
            if len(data) < 100:
                next_id = 0
        return dns_names, int(next_id)
