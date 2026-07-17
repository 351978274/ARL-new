"""quake_360 子域名查询插件。"""
from __future__ import annotations

import json

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "quake_360"
        self.api_url = "https://quake.360.net/api/v3/search/quake_service"
        self.quake_token = None
        self.max_size = 500

    def init_key(self, quake_token=None, max_size=500, **kwargs):
        self.quake_token = quake_token
        self.max_size = max_size

    async def sub_domains(self, target: str) -> list[str]:
        json_data = {
            "query": f'domain:"{target}"',
            "include": ["service.http.host"],
            "start": 0, "size": self.max_size, "latest": True,
        }
        headers = {"X-QuakeToken": self.quake_token}
        conn = await http_req(self.api_url, 'post', json=json_data, headers=headers, timeout=(30.1, 100.1))
        if conn.status_code != 200:
            raise Exception(f"{self.source_name}: {self.quake_token} QuakeToken is invalid")
        data = conn.json()
        if data["code"] != 0:
            raise Exception(f"{self.source_name} error: {json.dumps(data, ensure_ascii=False)}")
        results: list[str] = []
        for item in data.get("data", []):
            hostname = item.get("service", {}).get("http", {}).get("host", "")
            if hostname.endswith("." + target):
                results.append(hostname)
        return list(set(results))
