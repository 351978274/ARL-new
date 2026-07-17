"""站点 URL 静态爬虫，移植自原 app/services/siteUrlSpider.py。

广度优先爬取 a/form/iframe 的 href/action/src，URL 相似去重，深度与数量限制。
"""
from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse

from pyquery import PyQuery as pq

from ..core.base_task import AsyncBaseTask
from ..core.http_client import http_req
from ..logger import get_logger
from ..utils import normal_url, same_netloc, url_ext, urlsimilar

logger = get_logger()


class URLTYPE:
    document = "document"
    js = "js"
    css = "css"


class URLInfo:
    def __init__(self, entry_url, crawl_url, url_type):
        self.entry_url = entry_url
        self.crawl_url = crawl_url
        self._similar_hash = urlsimilar(self.crawl_url)
        self.type = url_type or URLTYPE.document

    def to_dict(self):
        return {"base_url": self.entry_url, "crawl_url": self.crawl_url, "type": self.type}

    def __eq__(self, other):
        return isinstance(other, URLInfo) and self.crawl_url == other.crawl_url

    __ne__ = lambda self, other: not self.__eq__(other)

    def __repr__(self):
        return str(self.to_dict())

    __str__ = __repr__

    def __hash__(self):
        return self._similar_hash

    def similar_hash(self):
        return self._similar_hash


class URLList:
    def __init__(self):
        self.result: list[URLInfo] = []
        self.similar_hash_pool: list[int] = []

    def __iter__(self):
        return iter(self.result)

    def __getitem__(self, item):
        return self.result[item]

    def __len__(self):
        return len(self.result)

    def add(self, element: URLInfo):
        if not isinstance(element, URLInfo):
            raise TypeError("need URLInfo")
        if element not in self.result:
            self.result.append(element)

    def __contains__(self, item):
        return isinstance(item, URLInfo) and item.similar_hash() in self.similar_hash_pool


class URLSimilarList(URLList):
    def add(self, element: URLInfo):
        if not isinstance(element, URLInfo):
            raise TypeError("need URLinfo")
        if element.similar_hash() not in self.similar_hash_pool:
            self.result.append(element)
            self.similar_hash_pool.append(element.similar_hash())


class SiteURLSpider:
    def __init__(self, entry_urls=None, deep_num: int = 3):
        entry_url_list = URLSimilarList()
        for url in entry_urls:
            entry_url_list.add(URLInfo(url, url, URLTYPE.document))
        self.entry_url_list = entry_url_list
        self.done_url_list = URLSimilarList()
        self.deep_num = deep_num
        self.all_url_list = URLSimilarList()
        self.max_url = max(60, len(entry_urls) * 6)
        self.scope_url = entry_urls[0]
        self.tagMap = [
            {'name': 'a', 'attr': 'href', 'type': URLTYPE.document},
            {'name': 'form', 'attr': 'action', 'type': URLTYPE.document},
            {'name': 'iframe', 'attr': 'src', 'type': URLTYPE.document},
        ]
        self.ignore_ext = [".pdf", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx",
                           ".zip", ".rar", ".png", ".jpg", ".gif", ".js", ".css", ".ico"]

    async def get_urls(self, entry_url: str):
        return await self._work(entry_url)

    async def _work(self, entry_url: str) -> URLSimilarList:
        try:
            logger.debug(f"[{len(self.done_url_list)}] req => {entry_url}")
            if url_ext(entry_url) in self.ignore_ext:
                return URLSimilarList()
            conn = await http_req(entry_url)
            if conn.status_code in [301, 302, 307]:
                _url = urljoin(entry_url, conn.headers.get("Location", "")).strip()
                _url = normal_url(_url)
                if not _url:
                    return URLSimilarList()
                url_info = URLInfo(entry_url, _url, URLTYPE.document)
                if same_netloc(entry_url, _url) and (url_info not in self.done_url_list):
                    entry_url = _url
                    logger.info(f"[{len(self.done_url_list)}] req 302 => {entry_url}")
                    conn = await http_req(_url)
                    self.done_url_list.add(url_info)
                    self.all_url_list.add(url_info)
            html = conn.content
            if "html" not in conn.headers.get("Content-Type", "").lower():
                return URLSimilarList()
            dom = pq(html)
            ret_url = URLSimilarList()
            for tag in self.tagMap:
                for i in dom(tag['name']).items():
                    _url = urljoin(entry_url, i.attr(tag['attr']) or "").strip()
                    _url = normal_url(_url)
                    if not _url:
                        continue
                    if url_ext(_url) in self.ignore_ext:
                        continue
                    if same_netloc(_url, entry_url):
                        url_info = URLInfo(entry_url, _url, tag["type"])
                        ret_url.add(url_info)
                        self.all_url_list.add(url_info)
            return ret_url
        except Exception as e:
            logger.error(f"error on {entry_url} {e}")
            return URLSimilarList()

    async def run(self) -> URLSimilarList:
        tmp_urls = self.entry_url_list
        for num in range(self.deep_num):
            if len(tmp_urls) > 0:
                logger.info(f"{self.scope_url} deep num {num + 1}, len {len(tmp_urls)}")
            new_url = URLSimilarList()
            for info in tmp_urls:
                self.all_url_list.add(info)
                if len(self.done_url_list) > self.max_url:
                    logger.warning(f"exit on request max url {self.scope_url}")
                    return self.all_url_list
                if info not in self.done_url_list:
                    ret_urls = await self.get_urls(info.crawl_url)
                    self.done_url_list.add(info)
                    for x in ret_urls:
                        new_url.add(x)
            tmp_urls = new_url
        return self.all_url_list


async def site_spider(entry_url, deep_num: int = 3) -> list[str]:
    if isinstance(entry_url, str):
        entry_url = [entry_url]
    ret = []
    s = SiteURLSpider(entry_url, deep_num)
    for x in await s.run():
        path = urlparse(x.crawl_url).path
        if path == "/" or not path:
            continue
        if x.type == URLTYPE.document:
            ret.append(x.crawl_url)
    return ret


class SiteURLSpiderThread(AsyncBaseTask):
    """对多站点并发爬取。targets 是二维数组（每个元素是入口 URL 列表）。"""

    def __init__(self, entry_urls_list, concurrency: int = 6, deep_num: int = 5):
        super().__init__(entry_urls_list, concurrency=concurrency)
        self.site_url_map: dict[str, list[str]] = {}
        self.deep_num = deep_num

    async def work(self, entry_urls) -> None:
        site = entry_urls[0]
        self.site_url_map[site] = await site_spider(entry_urls, self.deep_num)

    async def run(self) -> dict[str, list[str]]:
        t1 = time.time()
        logger.info(f"start site url spider entry_urls_list:{len(self.targets)}")
        await self._run()
        logger.info(f"end site url spider ({time.time()-t1:.2f}s)")
        return self.site_url_map


async def site_spider_thread(entry_urls_list, deep_num: int = 5) -> dict[str, list[str]]:
    return await SiteURLSpiderThread(entry_urls_list, concurrency=6, deep_num=deep_num).run()
