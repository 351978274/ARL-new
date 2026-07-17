"""chaos (projectdiscovery) 子域名查询插件。"""
from __future__ import annotations

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "chaos"
        self.api_url = "https://dns.projectdiscovery.io/"
        self.api_key = None

    def init_key(self, api_key=None, **kwargs):
        self.api_key = api_key

    async def sub_domains(self, target: str) -> list[str]:
        headers = {"Authorization": self.api_key}
        url = f"{self.api_url}dns/{target}/subdomains"
        items = (await http_req(url, 'get', headers=headers)).json()
        results = [f"{name}.{target}" for name in items.get("subdomains", [])]
        return list(set(results))
