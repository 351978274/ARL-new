"""securitytrails 子域名查询插件。"""
from __future__ import annotations

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "securitytrails"
        self.api_url = "https://api.securitytrails.com/"
        self.api_key = None

    def init_key(self, api_key=None, **kwargs):
        self.api_key = api_key

    async def sub_domains(self, target: str) -> list[str]:
        params = {"children_only": "false", "include_inactive": "true"}
        url = f"{self.api_url}v1/domain/{target}/subdomains"
        headers = {"Accept": "application/json", "APIKEY": self.api_key}
        conn = await http_req(url, params=params, headers=headers, timeout=(20, 120))
        data = conn.json()
        message = data.get("message")
        if message:
            self.logger.error(f"{self.source_name} error: {message}")
            return []
        return list(set(f"{item}.{target}" for item in data.get("subdomains", [])))
