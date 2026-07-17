"""页面抓取（基于 fileLeak 的 Page/HTTPReq），移植自原 app/services/pageFetch.py。"""
from __future__ import annotations

import time

from ..core.base_task import AsyncBaseTask
from ..logger import get_logger
from .file_leak import HTTPReq, Page, URL

logger = get_logger()


class PageFetch(AsyncBaseTask):
    def __init__(self, sites, concurrency: int = 6):
        super().__init__(sites, concurrency=concurrency)
        self.page_map: dict[str, dict] = {}

    async def work(self, site: str) -> None:
        try:
            req = HTTPReq(URL(site, ""))
            await req.req()
            page = Page(req)
            self.page_map[site] = page.dump_json()
        except Exception as e:
            logger.debug(f"page_fetch {site}: {e}")

    async def run(self) -> dict[str, dict]:
        t1 = time.time()
        logger.info(f"start PageFetch {len(self.targets)}")
        await self._run()
        logger.info(f"end PageFetch elapse {time.time()-t1:.2f}s")
        return self.page_map


async def page_fetch(sites, concurrency: int = 6) -> dict[str, dict]:
    return await PageFetch(sites, concurrency=concurrency).run()
