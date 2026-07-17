"""站点信息获取 + favicon + 指纹识别，移植自原 app/services/fetchSite.py。

并发抓取站点，提取 title/status/headers/server/body_length/favicon，做本地+DB 指纹识别，
跟随同源 301/302 跳转，最后 auto_tag 打标签。
"""
from __future__ import annotations

import base64
import binascii
import time
from urllib.parse import urljoin, urlparse

import mmh3
import httpx
from pyquery import PyQuery as pq

from ..core.base_task import AsyncBaseTask
from ..core.fingerprint import fetch_fingerprint as _fetch_fingerprint, finger_db_cache, finger_db_identify, load_fingerprint
from ..core.http_client import http_req
from ..logger import get_logger
from ..utils import get_headers_text, get_hostname, get_ip, get_title, normal_url
from .auto_tag import auto_tag

logger = get_logger()


def _encode_base64_lines(s: bytes) -> str:
    """对应原 encode_bas64_lines，每行 76 字符。"""
    MAXLINESIZE = 76
    MAXBINSIZE = (MAXLINESIZE // 4) * 3
    pieces = []
    for i in range(0, len(s), MAXBINSIZE):
        chunk = s[i:i + MAXBINSIZE]
        pieces.append(binascii.b2a_base64(chunk).decode())
    return "".join(pieces)


def _same_netloc_and_scheme(u1: str, u2: str) -> bool:
    u1 = normal_url(u1) or ""
    u2 = normal_url(u2) or ""
    p1 = urlparse(u1)
    p2 = urlparse(u2)
    return p1.scheme == p2.scheme and p1.netloc == p2.netloc


class FetchFavicon:
    def __init__(self, url: str):
        self.url = url
        self.favicon_url: str | None = None

    def build_result(self, data: str) -> dict:
        return {"data": data, "url": self.favicon_url, "hash": mmh3.hash(data)}

    async def run(self) -> dict:
        try:
            favicon_url = urljoin(self.url, "/favicon.ico")
            data = await self.get_favicon_data(favicon_url)
            if data:
                self.favicon_url = favicon_url
                return self.build_result(data)

            favicon_url = await self.find_icon_url_from_html()
            if not favicon_url:
                return {}
            data = await self.get_favicon_data(favicon_url)
            if data:
                self.favicon_url = favicon_url
                return self.build_result(data)
        except Exception as e:
            logger.warning(f"error on {self.url} {e}")
        return {}

    async def get_favicon_data(self, favicon_url: str) -> str | None:
        conn = await http_req(favicon_url)
        if conn.status_code != 200:
            return None
        if len(conn.content) <= 80:
            return None
        if "image" in conn.headers.get("Content-Type", ""):
            return _encode_base64_lines(conn.content)
        return None

    async def find_icon_url_from_html(self) -> str | None:
        conn = await http_req(self.url)
        if b"<link" not in conn.content:
            return None
        d = pq(conn.content)
        icon_link_list = []
        for link in d('link').items():
            href = link.attr("href")
            rel = link.attr("rel") or ""
            if href and 'icon' in rel:
                icon_link_list.append(link)
        for link in icon_link_list:
            rel = link.attr("rel") or ""
            if "shortcut" in rel:
                return urljoin(self.url, link.attr('href'))
        if icon_link_list:
            return urljoin(self.url, icon_link_list[0].attr('href'))
        return None


async def fetch_favicon(url: str) -> dict:
    return await FetchFavicon(url).run()


def _finger_identify_db(content: bytes, header: str, title: str, favicon_hash: str) -> list[str]:
    """同步部分：把 content decode 后调用 DB 指纹（DB 指纹内部异步，这里不直接调用）。"""
    # 实际异步调用在 FetchSite.fetch_fingerprint 中处理
    raise NotImplementedError  # 仅占位，避免误用


class FetchSite(AsyncBaseTask):
    def __init__(self, sites, concurrency: int = 15, http_timeout=None):
        super().__init__(sites, concurrency=concurrency)
        self.site_info_list: list[dict] = []
        self.fingerprint_list = load_fingerprint()
        self.http_timeout = http_timeout or (10.1, 30.1)

    async def fetch_fingerprint(self, item: dict, content: bytes) -> None:
        favicon_hash = item["favicon"].get("hash", 0)
        result = _fetch_fingerprint(content=content, headers=item["headers"],
                                    title=item["title"], favicon_hash=favicon_hash,
                                    finger_list=self.fingerprint_list)
        # DB 指纹（异步）
        try:
            content_str = content.decode("utf-8", errors="replace")
        except Exception:
            content_str = ""
        variables = {"body": content_str, "header": item["headers"],
                     "title": item["title"], "icon_hash": str(favicon_hash)}
        result_db = await finger_db_identify(variables)
        result = list(set(result + result_db))

        finger = [{
            "icon": "default.png", "name": name, "confidence": "80",
            "version": "", "website": "https://www.riskivy.com", "categories": []
        } for name in result]
        if finger:
            item["finger"] = finger

    async def work(self, site: str, max_redirect: int = 5) -> None:
        if max_redirect <= 0:
            return
        hostname = get_hostname(site)

        try:
            conn = await http_req(site, timeout=self.http_timeout)
        except Exception as e:
            logger.debug(f"fetch_site http error {site}: {e}")
            return

        # 构造原始 header 文本
        raw_headers = conn.headers.raw
        raw_header_bytes = b"\r\n".join(b"%s: %s" % (k, v) for k, v in raw_headers)
        header_text = get_headers_text(conn.status_code, "",
                                       raw_header_bytes, conn.content)

        item = {
            "site": site[:200],
            "hostname": hostname,
            "ip": "",
            "title": get_title(conn.content),
            "status": conn.status_code,
            "headers": header_text,
            "http_server": conn.headers.get("Server", ""),
            "body_length": len(conn.content),
            "finger": [],
            "favicon": await fetch_favicon(site),
        }

        await self.fetch_fingerprint(item, content=conn.content)

        dp = None
        from ..core.dns import domain_parsed
        dp = domain_parsed(hostname)
        if dp:
            item["fld"] = dp["fld"]
            ips = await get_ip(hostname)
            if ips:
                item["ip"] = ips[0]
        else:
            item["ip"] = hostname

        # 保存站点信息（跳转链路控制）
        if (max_redirect == 5 or max_redirect == 1
                or (conn.status_code not in (301, 302))):
            self.site_info_list.append(item)

        if conn.status_code in (301, 302):
            url_302 = urljoin(site, conn.headers.get("Location", ""))
            url_302 = normal_url(url_302)
            if not url_302 or len(url_302) > 260:
                return
            if url_302 != site and _same_netloc_and_scheme(url_302, site):
                await self.work(url_302, max_redirect=max_redirect - 1)

    async def run(self) -> list[dict]:
        t1 = time.time()
        logger.info(f"start fetch site {len(self.targets)}")
        await self._run()
        logger.info(f"end fetch site elapse {time.time()-t1:.2f}s")
        auto_tag(self.site_info_list)
        return self.site_info_list


async def fetch_site(sites, concurrency: int = 15, http_timeout=None) -> list[dict]:
    """刷新 DB 指纹缓存后抓取站点。"""
    await finger_db_cache.update_cache()
    return await FetchSite(sites, concurrency=concurrency, http_timeout=http_timeout).run()
