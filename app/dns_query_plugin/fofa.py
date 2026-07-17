"""fofa 子域名查询插件。"""
from __future__ import annotations

from .base import DNSQueryBase
from ..core.dns import get_fld
from ..services.fofa_client import fofa_query


class Query(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "fofa"

    async def sub_domains(self, target: str) -> list[str]:
        query = f'domain="{target}"'
        domain = get_fld(target)
        if not domain:
            self.logger.warning(f"Invalid domain: {target}")
            return []
        # 子域名用 host + domain 一起查询
        if domain != target:
            query = f'host="{target}" && domain="{domain}"'
        self.logger.debug(f"target:{target}, fofa query: {query}")

        fofa_results = await fofa_query(query)
        if isinstance(fofa_results, str):
            raise Exception(fofa_results)

        results: list[str] = []
        for item in fofa_results:
            domain_data = item[0]
            if "://" in domain_data:
                domain_data = domain_data.split(":")[1].strip("/")
            results.append(domain_data.split(":")[0])
        return list(set(results))
