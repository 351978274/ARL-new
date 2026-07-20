"""Host 碰撞检测，移植自原 app/services/findVhost.py。

对 IP 用不同 Host 头请求，检测 vhost 配置不当。
"""
from __future__ import annotations

import difflib

from ..core.base_task import AsyncBaseTask, thread_map
from ..core.http_client import http_req
from ..logger import get_logger
from ..utils import get_title

logger = get_logger()

bool_ratio = 0.9


class Page:
    def __init__(self, url, domain, content, status_code, content_type):
        self.url = url
        self.domain = domain
        self.content = content
        self.body_length = len(content)
        self.status_code = status_code
        self.title = get_title(self.content)
        self.content_type = content_type.lower()

    def __eq__(self, other):
        if not isinstance(other, Page):
            return False
        if self.status_code != other.status_code:
            return False
        if self.content_type != other.content_type:
            return False
        if abs(self.body_length - other.body_length) > 20:
            return False
        if self.status_code == 200 and abs(self.body_length - other.body_length) <= 3:
            return True
        quick_ratio = difflib.SequenceMatcher(None, self.content, other.content).quick_ratio()
        return quick_ratio > bool_ratio

    __ne__ = lambda self, other: not self.__eq__(other)

    def __hash__(self):
        return hash(self.url)

    def dump_json_obj(self):
        return {
            "url": self.url, "domain": self.domain, "body_length": self.body_length,
            "title": self.title, "status_code": self.status_code,
        }


class BruteVhost(AsyncBaseTask):
    def __init__(self, ip, domains, scheme, concurrency: int = 8):
        super().__init__(domains, concurrency=concurrency)
        self.ip = ip
        self.scheme = scheme
        self.url_ip = f"{self.scheme}://{self.ip}"
        self.domains = domains
        self.not_found_set: set[Page] = set()
        self.success_set: set[Page] = set()
        self.cnt = 0
        self.total_cnt = len(self.domains)
        self.error_cnt = 0
        self.print_skip_warning_flag = False

    async def brute_domain(self, domain: str) -> Page | None:
        try:
            res = await http_req(self.url_ip, headers={"Host": domain}, timeout=(3, 6))
            content = res.content.replace(domain.encode(), b"")
            return Page(self.url_ip, domain, content, res.status_code,
                        res.headers.get("Content-Type", ""))
        except Exception as e:
            logger.debug(f"{self.url_ip} {domain} {e}")

    async def work(self, domain: str) -> None:
        if self.error_cnt >= 10:
            if not self.print_skip_warning_flag:
                logger.warning(f"skip {self.url_ip}")
            self.print_skip_warning_flag = True
            return
        self.cnt += 1
        page = await self.brute_domain(domain)
        if not page:
            return
        if "百度一下" in page.title:
            return
        if page.status_code not in [301, 302, 200]:
            return
        if "json" not in page.content_type and "text" not in page.content_type:
            return
        if "text" in page.content_type and page.body_length < 150:
            return
        if "text" in page.content_type and b"<" not in page.content:
            return
        if page in self.not_found_set:
            return
        if page not in self.success_set:
            logger.success(f"found {page.dump_json_obj()}")
            self.success_set.add(page)

    async def run(self) -> set[Page]:
        domain_404_list = [self.ip, "not123abc" + self.domains[0], "wfaz.zljhaz.com", "n0ta." + self.domains[0]]
        for item in domain_404_list:
            page = await self.brute_domain(item)
            if page:
                self.not_found_set.add(page)
        await self._run()
        if self.success_set:
            logger.info(f"found {self.url_ip} {len(self.success_set)}")
        return self.success_set


async def brute_vhost(ip: str, args):
    domains, scheme = args
    logger.info(f"brute_vhost >>> ip: {ip}, domain: {len(domains)}, scheme: {scheme}")
    brute = BruteVhost(ip=ip, domains=domains, scheme=scheme, concurrency=8)
    return await brute.run()


async def find_vhost(ips, domains) -> list[dict]:
    """对 ips 用 domains 做 Host 碰撞，返回命中页面对象列表。"""
    results: list[dict] = []
    same_set: set[str] = set()
    for scheme in ["http", "https"]:
        result_map = await thread_map(brute_vhost, items=list(ips), arg=(domains, scheme), concurrency=3)
        for ip in result_map:
            for page in result_map[ip]:
                key = f"{page.domain}-{page.title}-{page.status_code}"
                if key in same_set:
                    continue
                same_set.add(key)
                results.append(page.dump_json_obj())
    return results
