"""FOFA API 客户端，移植自原 app/services/fofaClient.py。"""
from __future__ import annotations

import asyncio
import base64

from ..config import Config
from ..core.http_client import http_req
from ..logger import get_logger

logger = get_logger()


class FofaClient:
    def __init__(self, key, page_size: int = 2000, max_page: int = 5, fields: str = "host,ip,port"):
        self.key = key
        self.page_size = page_size
        self.max_page = max_page
        self.base_url = Config.FOFA_URL.rstrip("/")
        self.search_all_path = "/api/v1/search/all"
        self.base_params = {"key": self.key}
        self.fields = fields

    async def search(self, query: str):
        """生成器：逐页返回结果列表。"""
        page = 1
        while True:
            if page > self.max_page:
                break
            if page > 1:
                await asyncio.sleep(0.2)
            data = await self.fofa_search_all(query, page)
            logger.debug(f"Page:{page} Query: {data['query']}")
            results = data["results"]
            logger.debug(f"Current: {len(results)} All Size: {data['size']}")
            if results:
                yield results
            if len(results) < self.page_size:
                break
            page += 1

    async def fofa_search_all(self, query: str, page: int = 1) -> dict:
        q_base64 = base64.b64encode(query.encode()).decode('utf-8')
        params = {"qbase64": q_base64, "page": page, "size": self.page_size, "fields": self.fields}
        return await self._api(self.search_all_path, params)

    async def _api(self, path, params=None) -> dict:
        if params is None:
            params = self.base_params
        else:
            params.update(self.base_params)
        url = self.base_url + path
        conn = await http_req(url, 'get', params=params)
        if conn.status_code != 200:
            raise Exception(f"{url} http status code: {conn.status_code}")
        data = conn.json()
        if data.get("error") and data.get("errmsg"):
            raise Exception(data["errmsg"])
        return data


async def fofa_query(query: str, fields: str = "host,ip,port",
                     page_size: int = Config.FOFA_PAGE_SIZE,
                     max_page: int = Config.FOFA_MAX_PAGE):
    """查询 FOFA。返回结果列表；出错返回错误字符串。"""
    ret: list = []
    try:
        if not Config.FOFA_KEY:
            return "please set fofa key in config.yaml"
        client = FofaClient(Config.FOFA_KEY, page_size=page_size, max_page=max_page, fields=fields)
        async for results in client.search(query):
            ret.extend(results)
        logger.info(f"fofa query: {query} result size: {len(ret)}")
        return ret
    except Exception as e:
        error_msg = str(e)
        if Config.FOFA_KEY and len(Config.FOFA_KEY) > 10:
            error_msg = error_msg.replace(Config.FOFA_KEY[10:], "***")
        if ret:
            logger.warning(f"fofa query error: {error_msg}")
            return ret
        return error_msg
