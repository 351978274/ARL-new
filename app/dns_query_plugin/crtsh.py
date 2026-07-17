"""crtsh 子域名查询插件（证书透明度日志，无需 key）。"""
from __future__ import annotations

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "crtsh"
        self.api_url = "https://crt.sh/"

    async def sub_domains(self, target: str) -> list[str]:
        param = {"output": "json", "q": target, "exclude": "expired"}
        items = (await http_req(self.api_url, 'get', params=param, timeout=(30.1, 50.1))).json()
        results: list[str] = []
        for item in items:
            for name in item.get("name_value", "").split():
                if name.endswith("." + target):
                    results.append(name)
        return list(set(results))
