"""搜索引擎爬取（百度/Bing），移植自原 app/services/searchEngines.py。"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlparse

from pyquery import PyQuery as pq

from ..core.http_client import http_req
from ..logger import get_logger
from ..utils import rm_similar_url

logger = get_logger()


class BaiduSearch:
    def __init__(self, keyword=None, page_num: int = 6):
        self.search_url = "https://www.baidu.com/s?rn=100&pn={page}&wd={keyword}"
        self.num_pattern = re.compile(r'百度为您找到相关结果约?([\d,]*)个')
        self.first_html = ""
        self.keyword = keyword
        self.page_num = page_num
        self.pq_query = "#content_left h3.t a"
        self.headers = {"Accept-Language": "zh-cn"}
        self.search_result_num = 0
        self.default_interval = 3

    async def result_num(self) -> int:
        url = self.search_url.format(page=0, keyword=quote(self.keyword))
        conn = await http_req(url, headers=self.headers)
        self.first_html = conn.text
        result = re.findall(self.num_pattern, self.first_html)
        if not result:
            logger.warning(f"Unable to get baidu search results, {self.keyword}")
            return 0
        num = int("".join(result[0].split(",")))
        self.search_result_num = num
        return num

    async def match_urls(self, html: str) -> list[str]:
        result = re.findall(self.num_pattern, html)
        if not result:
            raise Exception("获取百度结果异常")
        dom = pq(html)
        urls_result = [item.attr("href") for item in dom(self.pq_query).items()]
        urls: set[str] = set()
        for u in urls_result:
            try:
                if not re.match(r'^https?:/{2}\w.+$', u):
                    continue
                resp = await http_req(u, "head")
                real_url = resp.headers.get('Location')
                if real_url:
                    urls.add(real_url)
            except Exception as e:
                logger.debug(e)
        return list(urls)

    async def run(self) -> list[str]:
        await self.result_num()
        logger.info(f"baidu search {self.search_result_num} results for {self.keyword}")
        urls: list[str] = []
        if self.search_result_num == 0:
            return urls
        for page in range(1, min(int(self.search_result_num / 10) + 2, self.page_num + 1)):
            if page == 1:
                _urls = await self.match_urls(self.first_html)
                urls.extend(_urls)
            else:
                await asyncio.sleep(self.default_interval)
                url = self.search_url.format(page=(page - 1) * 10, keyword=quote(self.keyword))
                conn = await http_req(url, headers=self.headers)
                _urls = await self.match_urls(conn.text)
                urls.extend(_urls)
        return urls


class BingSearch:
    def __init__(self, keyword=None, page_num: int = 6):
        self.search_url = "https://cn.bing.com/search?q={keyword}&qs=n&form=QBRE&sp=-1&first={page}"
        self.num_pattern = re.compile(r'<span class="sb_count">([^<]+)</span>')
        self.pq_query = "#b_results > li h2 > a"
        self.keyword = keyword
        self.page_num = page_num
        self.headers = {"Accept-Language": "zh-cn"}
        self.default_interval = 3
        self.search_result_num = 0
        self.first_html = ""

    async def result_num(self) -> int:
        url = self.search_url.format(page=1, keyword=quote(self.keyword))
        conn = await http_req(url, headers=self.headers)
        self.first_html = conn.text
        result = re.findall(self.num_pattern, self.first_html)
        if result:
            result_num = re.findall(r"共 ([\d,]*) 条", result[0])
            if result_num:
                self.search_result_num = int("".join(result_num[0].split(",")))
            else:
                result_num_2 = re.findall(r" ([\d,]*) 个结果", result[0])
                if result_num_2:
                    self.search_result_num = int("".join(result_num_2[0].split(",")))
        else:
            logger.warning(f"Unable to get bing search results, {self.keyword}")
        return self.search_result_num

    async def match_urls(self, html: str) -> list[str]:
        if "搜索</title>" not in html:
            raise Exception("获取Bing结果异常")
        dom = pq(html)
        urls_result = [item.attr("href") for item in dom(self.pq_query).items()]
        return list(set(urls_result))

    async def run(self) -> list[str]:
        await self.result_num()
        urls: list[str] = []
        if self.search_result_num == 0:
            return urls
        for page in range(1, min(int(self.search_result_num / 10) + 2, self.page_num + 1)):
            if page == 1:
                urls.extend(await self.match_urls(self.first_html))
            else:
                await asyncio.sleep(self.default_interval)
                url = self.search_url.format(page=(page - 1) * 10, keyword=quote(self.keyword))
                conn = await http_req(url, headers=self.headers)
                urls.extend(await self.match_urls(conn.text))
        return urls


async def baidu_search(domain: str, page_num: int = 6) -> list[str]:
    keyword = f"site:{domain}"
    urls = await BaiduSearch(keyword, page_num).run()
    urls = [u for u in urls if domain in urlparse(u).netloc]
    return rm_similar_url(urls)


async def bing_search(domain: str, page_num: int = 5) -> list[str]:
    keyword = f"site:{domain}"
    b = BingSearch(keyword, page_num)
    urls = await b.run()
    if b.search_result_num > 1000 and len(urls) > 25:
        for k in ["admin", "管理|后台", "登陆|密码", "login", "manage", "dashboard", "api", "console"]:
            try:
                await asyncio.sleep(15)
                urls.extend(await BingSearch(f"site:{domain} {k}", page_num=1).run())
            except Exception as e:
                logger.warning(e)
    urls = [u for u in urls if domain in urlparse(u).netloc]
    return rm_similar_url(urls)


async def search_engines(base_domain: str) -> list[str]:
    urls: list[str] = []
    for engine in [bing_search, baidu_search]:
        try:
            urls.extend(await engine(base_domain))
            urls = rm_similar_url(urls)
        except Exception as e:
            logger.exception(e)
    return urls
