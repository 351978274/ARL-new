"""域名批量解析，移植自原 app/services/resolverDomain.py。"""
from __future__ import annotations

from ..core.base_task import AsyncBaseTask
from ..core.dns import get_ip
from ..modules import DomainInfo


class ResolverDomain(AsyncBaseTask):
    def __init__(self, domains, concurrency: int = 15):
        super().__init__(domains, concurrency=concurrency)
        self.resolver_map: dict[str, list[str]] = {}

    async def work(self, domain) -> None:
        curr_domain = domain
        if isinstance(domain, dict):
            curr_domain = domain.get("domain")
        elif isinstance(domain, DomainInfo):
            curr_domain = domain.domain
        if not curr_domain or curr_domain in self.resolver_map:
            return
        self.resolver_map[curr_domain] = await get_ip(curr_domain)

    async def run(self) -> dict[str, list[str]]:
        await self._run()
        return self.resolver_map


async def resolver_domain(domains, concurrency: int = 15) -> dict[str, list[str]]:
    return await ResolverDomain(domains, concurrency).run()
