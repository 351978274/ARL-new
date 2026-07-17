"""域名解析记录构建，移植自原 app/services/buildDomainInfo.py。

对每个域名并发解析 A/CNAME，生成 DomainInfo 对象。
"""
from __future__ import annotations

import time

from ..core.base_task import AsyncBaseTask
from ..core.dns import get_cname, get_ip
from ..logger import get_logger
from ..modules import DomainInfo

logger = get_logger()


class BuildDomainInfo(AsyncBaseTask):
    def __init__(self, domains, concurrency: int = 15):
        super().__init__(domains, concurrency=concurrency)
        self.domain_info_list: list[DomainInfo] = []

    async def work(self, target) -> None:
        domain = target.domain if hasattr(target, "domain") else target

        ips = await get_ip(domain, log_flag=False)
        if not ips:
            return

        cnames = await get_cname(domain, log_flag=False)

        info = {"domain": domain, "type": "A", "record": ips, "ips": ips}
        if cnames:
            info["type"] = "CNAME"
            info["record"] = cnames

        self.domain_info_list.append(DomainInfo(**info))

    async def run(self) -> list[DomainInfo]:
        t1 = time.time()
        logger.info(f"start build Domain info {len(self.targets)}")
        await self._run()
        logger.info(f"end build Domain info {len(self.domain_info_list)} elapse {time.time()-t1:.2f}s")
        return self.domain_info_list


async def build_domain_info(domains, concurrency: int = 15) -> list[DomainInfo]:
    return await BuildDomainInfo(domains, concurrency=concurrency).run()
