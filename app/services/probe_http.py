"""HTTP 站点探测（从域名生成 http/https 候选并探活），移植自原 app/services/probeHTTP.py。"""
from __future__ import annotations

import time

import httpx

from ..core.base_task import AsyncBaseTask
from ..core.http_client import http_req
from ..logger import get_logger

logger = get_logger()


class ProbeHTTP(AsyncBaseTask):
    def __init__(self, domains, concurrency: int = 10):
        super().__init__(self._build_targets(domains), concurrency=concurrency)
        self.sites: list[str] = []

    def _build_targets(self, domains):
        _targets = []
        for item in domains:
            domain = item.domain if hasattr(item, 'domain') else item
            _targets.append(f"https://{domain}")
            _targets.append(f"http://{domain}")
        return _targets

    async def work(self, target: str) -> None:
        try:
            conn = await http_req(target, 'get', timeout=(3, 2))
        except Exception as e:
            logger.debug(f"probe_http {target}: {e}")
            return
        if conn.status_code in [502, 504, 501, 422, 410]:
            logger.debug(f"{target} 状态码为 {conn.status_code} 跳过")
            return
        self.sites.append(target)

    async def run(self) -> list[str]:
        t1 = time.time()
        logger.info(f"start ProbeHTTP {len(self.targets)}")
        await self._run()
        # 去重：https 优先，去掉与 https 同源的 http
        alive_site: list[str] = []
        for x in self.sites:
            if x.startswith("https://"):
                alive_site.append(x)
            elif x.startswith("http://"):
                if "https://" + x[7:] not in self.sites:
                    alive_site.append(x)
        logger.info(f"end ProbeHTTP {len(alive_site)} elapse {time.time()-t1:.2f}s")
        return alive_site


async def probe_http(domain, concurrency: int = 10) -> list[str]:
    return await ProbeHTTP(domain, concurrency=concurrency).run()
