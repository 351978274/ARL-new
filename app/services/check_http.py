"""URL 存活性探测，移植自原 app/services/checkHTTP.py。

过滤不可达或伪存活（400/410/422/5xx/403-WAF），返回 {url: {status, content-type}}。
"""
from __future__ import annotations

import time

import httpx

from ..core.base_task import AsyncBaseTask
from ..core.http_client import http_req
from ..logger import get_logger

logger = get_logger()

# 403 WAF 拦截页特征
_WAF_SIGN = b'</title><style type="text/css">body{margin:5% auto 0 auto;padding:0 18px}'


class CheckHTTP(AsyncBaseTask):
    def __init__(self, urls, concurrency: int = 15):
        super().__init__(urls, concurrency=concurrency)
        self.timeout = (5, 3)
        self.checkout_map: dict[str, dict] = {}

    async def check(self, url: str) -> dict | None:
        conn = await http_req(url, method="get", timeout=self.timeout)
        if conn.status_code == 400:
            etag = conn.headers.get("ETag")
            date = conn.headers.get("Date")
            if not etag or not date:
                return None

        if conn.status_code in (422, 410):
            return None
        if 501 <= conn.status_code < 600:
            return None

        if conn.status_code == 403:
            conn2 = await http_req(url)
            if _WAF_SIGN in conn2.content:
                return None

        return {"status": conn.status_code, "content-type": conn.headers.get("Content-Type", "")}

    async def work(self, url: str) -> None:
        try:
            out = await self.check(url)
            if out is not None:
                self.checkout_map[url] = out
        except (httpx.HTTPError, Exception) as e:
            logger.debug(f"check_http error on {url}: {e}")

    async def run(self) -> dict[str, dict]:
        t1 = time.time()
        logger.info(f"start check http {len(self.targets)}")
        await self._run()
        logger.info(f"end check http {len(self.checkout_map)} elapse {time.time()-t1:.2f}s")
        return self.checkout_map


async def check_http(urls, concurrency: int = 15) -> dict[str, dict]:
    return await CheckHTTP(urls, concurrency=concurrency).run()
