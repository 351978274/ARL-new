"""站点截图（phantomjs），移植自原 app/services/siteScreenshot.py。"""
from __future__ import annotations

import os
import re
import time

from ..config import Config
from ..core.base_task import AsyncBaseTask
from ..logger import get_logger
from ..utils import exec_system

logger = get_logger()


class SiteScreenshot(AsyncBaseTask):
    def __init__(self, sites, concurrency: int = 3, capture_dir: str = "./"):
        super().__init__(sites, concurrency=concurrency)
        self.capture_dir = capture_dir
        self.screenshot_map: dict[str, str] = {}
        os.makedirs(self.capture_dir, 0o777, True)

    async def work(self, site: str) -> None:
        file_name = f'{self.capture_dir}/{self.gen_filename(site)}.jpg'
        cmd_parameters = ['phantomjs', '--ignore-ssl-errors true', '--ssl-protocol any',
                          '--ssl-ciphers ALL', Config.SCREENSHOT_JS,
                          f'-u={site}', f'-s={file_name}']
        logger.debug("screenshot " + " ".join(cmd_parameters))
        await exec_system(cmd_parameters)
        self.screenshot_map[site] = file_name

    def gen_filename(self, site: str) -> str:
        filename = site.replace('://', '_')
        return re.sub(r'[^\w\-_\. ]', '_', filename)

    async def run(self) -> dict[str, str]:
        t1 = time.time()
        logger.info(f"start screen shot {len(self.targets)}")
        await self._run()
        logger.info(f"end screen shot elapse {time.time()-t1:.2f}s")
        return self.screenshot_map


async def site_screenshot(sites, concurrency: int = 3, capture_dir: str = "./") -> dict[str, str]:
    s = SiteScreenshot(sites, concurrency=concurrency, capture_dir=capture_dir)
    return await s.run()
