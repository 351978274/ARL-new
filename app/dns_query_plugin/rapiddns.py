"""rapiddns 子域名查询插件（HTML 解析，无需 key）。"""
from __future__ import annotations

from pyquery import PyQuery as pq

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "rapiddns"
        self.api_url = "https://rapiddns.io/"

    async def sub_domains(self, target: str) -> list[str]:
        url = f"{self.api_url}subdomain/{target}?full=1"
        html = (await http_req(url, timeout=(30.1, 50.1))).content
        results: list[str] = []
        dom = pq(html)
        for item in dom("#table > tbody > tr"):
            subdomain = pq(item)("td:nth-child(2)").text()
            if subdomain:
                results.append(subdomain)
        return list(set(results))
