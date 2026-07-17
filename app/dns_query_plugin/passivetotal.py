"""passivetotal (RiskIQ) 子域名查询插件。"""
from __future__ import annotations

from .base import DNSQueryBase
from ..core.http_client import http_req


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "passivetotal"
        self.subdomain_api = "https://api.passivetotal.org/v2/enrichment/subdomains"
        self.quota_api = "https://api.passivetotal.org/v2/account/quota"
        self.auth_email = None
        self.auth_key = None

    def init_key(self, auth_email=None, auth_key=None, **kwargs):
        self.auth_email = auth_email
        self.auth_key = auth_key

    async def quota(self):
        conn = await http_req(self.quota_api, auth=(self.auth_email, self.auth_key))
        data = conn.json()
        count = data["user"]["counts"]["search_api"]
        limit = data["user"]["limits"]["search_api"]
        return count, limit

    async def sub_domains(self, target: str) -> list[str]:
        try:
            count, limit = await self.quota()
            quota = limit - count
            if quota == 0:
                raise Exception(f"{self.source_name} api quota is zero {self.auth_email}")
            self.logger.info(f"{self.source_name} api quota:{quota} [{count}/{limit}][{self.auth_email}]")
        except Exception as e:
            if "'user'" == str(e):
                raise Exception(f"{self.source_name} api auth error ({self.auth_email}, {self.auth_key})")
            raise

        params = {"query": f"*.{target}"}
        conn = await http_req(self.subdomain_api, params=params,
                              auth=(self.auth_email, self.auth_key), timeout=(20, 120))
        data = conn.json()
        subdomains: list[str] = []
        for item in data.get("subdomains", []):
            # passivetotal 数据污染严重，过滤
            if "." not in item and len(item) >= 18:
                continue
            if len(item) >= 25:
                continue
            subdomains.append(f"{item}.{target}")
        return subdomains
