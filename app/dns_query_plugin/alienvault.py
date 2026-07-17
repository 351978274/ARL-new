"""alienvault 子域名查询插件。"""
from __future__ import annotations

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "alienvault"
        self.api_url = "https://otx.alienvault.com/"

    async def sub_domains(self, target: str) -> list[str]:
        url = f"{self.api_url}api/v1/indicators/domain/{target}/passive_dns"
        items = (await http_req(url, 'get', timeout=(30.1, 50.1))).json()
        results = [item["hostname"] for item in items.get("passive_dns", [])]
        return list(set(results))
