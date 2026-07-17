"""Web 应用识别（phantomjs + wappalyzer driver.js），移植自原 app/services/webAnalyze.py。"""
from __future__ import annotations

import asyncio
import json
import time

from ..config import Config
from ..core.base_task import AsyncBaseTask
from ..logger import get_logger
from ..utils import check_output

logger = get_logger()


class WebAnalyze(AsyncBaseTask):
    def __init__(self, sites, concurrency: int = 3):
        super().__init__(sites, concurrency=concurrency)
        self.analyze_map: dict[str, list] = {}

    async def work(self, site: str) -> None:
        cmd_parameters = ['phantomjs', '--ignore-ssl-errors true', '--ssl-protocol any',
                          '--ssl-ciphers ALL', Config.DRIVER_JS, site]
        logger.debug("WebAnalyze=> " + " ".join(cmd_parameters))
        try:
            output = await check_output(cmd_parameters, timeout=20)
            self.analyze_map[site] = json.loads(output.decode('utf-8'))["applications"]
        except Exception as e:
            logger.debug(f"web_analyze {site}: {e}")

    async def run(self) -> dict[str, list]:
        t1 = time.time()
        logger.info(f"start WebAnalyze {len(self.targets)}")
        await self._run()
        logger.info(f"end WebAnalyze elapse {time.time()-t1:.2f}s")
        return self.analyze_map


async def web_analyze(sites, concurrency: int = 3) -> dict[str, list]:
    return await WebAnalyze(sites, concurrency=concurrency).run()
