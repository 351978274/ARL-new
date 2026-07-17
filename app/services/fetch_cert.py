"""SSL 证书获取，移植自原 app/services/fetchCert.py。"""
from __future__ import annotations

import asyncio
import time

from ..core.base_task import AsyncBaseTask
from ..logger import get_logger
from ..utils import get_cert

logger = get_logger()


class FetchCert(AsyncBaseTask):
    def __init__(self, targets, concurrency: int = 15):
        super().__init__(targets, concurrency=concurrency)
        self.fetch_map: dict[str, dict] = {}

    async def work(self, target: str) -> None:
        try:
            ip, port = target.split(":")
            port = int(port)
        except (ValueError, AttributeError):
            return
        # get_cert 为同步 ssl 调用，放线程池
        cert = await asyncio.to_thread(get_cert, ip, port)
        if cert:
            self.fetch_map[target] = cert

    async def run(self) -> dict[str, dict]:
        t1 = time.time()
        logger.info(f"start fetch cert {len(self.targets)}")
        await self._run()
        logger.info(f"end fetch cert {len(self.fetch_map)} elapse {time.time()-t1:.2f}s")
        return self.fetch_map


async def fetch_cert(targets, concurrency: int = 15) -> dict[str, dict]:
    return await FetchCert(targets, concurrency=concurrency).run()


class SSLCert:
    """从 IPInfo 列表或 ip:port 字符串列表构建证书抓取目标，委托给 fetch_cert。"""

    def __init__(self, ip_info_list, base_domain: str | None = None):
        self.ip_info_list = ip_info_list
        self.base_domain = base_domain

    async def run(self) -> dict[str, dict]:
        from ..modules import IPInfo
        from ..utils import is_vaild_ip_target
        target_temp_list: list[str] = []
        for info in self.ip_info_list:
            if isinstance(info, IPInfo):
                for port_info in info.port_info_list:
                    if port_info.port_id == 80:
                        continue
                    target_temp_list.append(f"{info.ip}:{port_info.port_id}")
            elif isinstance(info, str) and is_vaild_ip_target(info):
                target_temp_list.append(f"{info}:443")
            elif isinstance(info, str) and ":" in info:
                target_temp_list.append(info)
        return await fetch_cert(target_temp_list)
