"""敏感文件/备份文件爆破 + soft-404 检测，移植自原 app/services/fileLeak.py。

soft-404 检测逻辑（Page.__eq__）保持原样；HTTP 部分用 httpx 异步流式读取。
"""
from __future__ import annotations

import difflib
import itertools
import os
import time
from typing import List
from urllib.parse import urljoin, urlparse

from tld import get_tld

from ..core.base_task import AsyncBaseTask
from ..core.http_client import http_req
from ..logger import get_logger
from ..utils import get_title

logger = get_logger()

min_length = 100
max_length = 50 * 1024
read_timeout = 60
bool_ratio = 0.8
concurrency_count = 6


class URL:
    def __init__(self, url: str, payload: str):
        self.url = url
        self.payload = payload
        self._scope = None
        self._path = None

    def __eq__(self, other):
        return isinstance(other, URL) and self.url == other.url

    __ne__ = lambda self, other: not self.__eq__(other)

    def __hash__(self):
        return hash(self.url)

    def __str__(self):
        return self.url

    __repr__ = lambda self: "<URL> " + self.url

    def __lt__(self, other):
        return self.url < other.url

    def __gt__(self, other):
        return self.url > other.url

    @property
    def scope(self) -> str:
        if self._scope is None:
            p = urlparse(self.url)
            self._scope = f"{p.scheme}://{p.netloc}"
        return self._scope

    @property
    def path(self) -> str:
        if self._path is None:
            self._path = urlparse(self.url).path
        return self._path


class HTTPReq:
    """异步 HTTP 请求封装，限制读取长度与超时。"""

    def __init__(self, url: URL, read_timeout: int = 60, max_length: int = 50 * 1024):
        self.url = url
        self.read_timeout = read_timeout
        self.max_length = max_length
        self.conn = None
        self.status_code = None
        self.content: bytes = b""

    async def req(self):
        conn = await http_req(self.url.url, 'get', timeout=(3, 6))
        self.conn = conn
        # http_req 已流式读取并截断；这里再按 max_length 截断
        content = conn.content[: self.max_length]
        self.status_code = conn.status_code
        self.content = content
        return self.status_code, self.content


class Page:
    def __init__(self, req: HTTPReq):
        self.raw_req = req
        self.url = req.url
        self.content = req.content
        self.body_length = len(self.content)
        self.times = 0
        self.status_code = req.status_code
        self._title = None
        self._location_url = None
        self._is_back_up_path = None
        self._is_back_up_page = None
        self.back_up_suffix_list = [".tar", ".tar.gz", ".zip", ".rar", ".7z", ".bz2", ".gz", ".war"]

    def __eq__(self, other):
        if not isinstance(other, Page):
            return False
        if self.status_code != other.status_code:
            return False
        if self.is_302() and other.is_302():
            self_new_url = urljoin(self.url.url, self.location_url)
            other_new_url = urljoin(other.url.url, other.location_url)
            if self_new_url.endswith(self.url.payload + "/"):
                if other_new_url.endswith(other.url.payload + "/"):
                    if not self.url.payload.endswith("/") and not other.url.payload.endswith("/"):
                        return False
            self_new_path = urlparse(self_new_url).path
            other_new_path = urlparse(other_new_url).path
            path1 = self_new_path.replace(self.url.payload, "$AAAA$")
            path2 = other_new_path.replace(other.url.payload, "$AAAA$")
            if urlparse(self_new_url).netloc == urlparse(other_new_url).netloc:
                if path1 == path2 and self_new_path.endswith("$AAAA$/"):
                    if not self.url.payload.endswith("/") and not other.url.payload.endswith("/"):
                        return False
            if path1 == path2:
                self.times += 1
                return True
            return False

        self_content = self.content.replace(self.url.payload.encode(), b"")
        other_content = other.content.replace(other.url.payload.encode(), b"")
        if abs(len(self_content) - len(other_content)) <= 5:
            self.times += 1
            return True
        min_len_content = min(len(self_content), len(other_content))
        if abs(len(self_content) - len(other_content)) >= max(500, int(min_len_content * 0.1)):
            return False
        if len(self.title) > 2 and self.title == other.title:
            return True
        quick_ratio = difflib.SequenceMatcher(None, self_content, other_content).quick_ratio()
        if quick_ratio >= bool_ratio:
            self.times += 1
            return True
        return False

    __ne__ = lambda self, other: not self.__eq__(other)

    def __hash__(self):
        p = urlparse(self.url.url)
        return hash(p.scheme + "://" + p.netloc)

    @property
    def location_url(self) -> str:
        if self._location_url is None:
            location = self.raw_req.conn.headers.get("Location", "") if self.raw_req.conn else ""
            new_url = urljoin(self.url.url, location)
            self._location_url = new_url.split("?")[0]
        return self._location_url

    def is_302(self):
        return self.status_code in [301, 302, 307, 308]

    @property
    def title(self) -> str:
        if self._title is None:
            self._title = get_title(self.content).strip()
        return self._title

    @property
    def is_backup_path(self) -> bool:
        if self._is_back_up_path is None:
            self._is_back_up_path = any(self.url.path.endswith(s) for s in self.back_up_suffix_list)
        return self._is_back_up_path

    @property
    def is_backup_page(self) -> bool:
        if self._is_back_up_page is None:
            ct = self.raw_req.conn.headers.get("Content-Type", "") if self.raw_req.conn else ""
            self._is_back_up_page = "application" in ct.lower()
        return self._is_back_up_page

    def __str__(self):
        return f"[{self.status_code}][{self.title}][{len(self.content)}]{self.url}"

    __repr__ = __str__

    def dump_json(self):
        return {
            "title": self.title,
            "url": str(self.url),
            "content_length": len(self.content),
            "status_code": self.status_code,
        }


def _normal_url(url: str) -> str:
    scheme_map = {'http': 80, "https": 443}
    o = urlparse(url)
    if o.scheme not in scheme_map:
        return ""
    path = o.path or "/"
    if o.port == scheme_map[o.scheme] or o.port is None:
        ret_url = f"{o.scheme}://{o.hostname}{path}"
    else:
        ret_url = f"{o.scheme}://{o.hostname}:{o.port}{path}"
    if o.query:
        ret_url += "?" + o.query
    return ret_url


class FileLeak(AsyncBaseTask):
    def __init__(self, target: str, urls, concurrency: int = 8):
        super().__init__(urls, concurrency=concurrency)
        self.target = target.rstrip("/") + "/"
        self.urls = urls
        self.path_404 = "not_found_2222_111"
        self.page404_set: set[Page] = set()
        self.page200_set: set[Page] = set()
        self.page200_code_list = [200, 301, 302, 500]
        self.page404_title = ["404", "不存在", "错误", "403", "禁止访问", "请求含有不合法的参数",
                              "网络防火墙", "访问拦截", "由于安全原因JSP功能默认关闭"]
        self.page404_content = [b'<script>document.getElementById("a-link").click();</script>']
        self.location404 = ["/auth/login/", "error.html"]
        self.error_times = 0
        self.skip_302 = False
        self.location_404_url: set[str] = set()

    async def http_req_wrap(self, url: URL) -> HTTPReq:
        try:
            req = HTTPReq(url)
            await req.req()
            return req
        except Exception as e:
            self.error_times += 1
            logger.warning(f"error on {e}")
            raise

    async def work(self, url: URL) -> None:
        if self.error_times >= 20:
            return
        try:
            req = await self.http_req_wrap(url)
        except Exception:
            return
        page = Page(req)
        if self.is_404_page(page):
            self.page404_set.add(page)
            return
        if page not in self.page404_set:
            self.page200_set.add(page)

    async def build_404_page(self):
        url_404 = URL(self.target + self.path_404, self.path_404)
        logger.info(f"req => {url_404}")
        try:
            page_404 = Page(await self.http_req_wrap(url_404))
        except Exception:
            return
        self.page404_set.add(page_404)
        if page_404.is_302():
            self.location_404_url.add(page_404.location_url)
        if page_404.is_302() and page_404.location_url.endswith(page_404.url.payload + "/"):
            self.skip_302 = True

    async def run(self) -> set[Page]:
        t1 = time.time()
        logger.info(f"start fileleak {len(self.targets)}")
        await self.build_404_page()
        await self._run()
        await self.check_page_200()
        logger.info(f"end fileleak elapse {time.time()-t1:.2f}s")
        return self.page200_set

    def is_404_page(self, page: Page) -> bool:
        if page.status_code not in self.page200_code_list:
            return True
        if page.is_backup_path and not page.is_backup_page:
            return True
        if any(t in page.title for t in self.page404_title):
            return True
        if any(c in page.content for c in self.page404_content):
            return True
        if "/." in page.url.url and page.status_code == 200 and len(page.content) == 0:
            return True
        if page.is_302():
            for loc in self.location404:
                if loc in page.location_url:
                    return True
            if not page.location_url.endswith(page.url.payload + "/"):
                self.location_404_url.add(page.location_url)
                return True
            return page.location_url in self.location_404_url
        return False

    async def check_page_200(self):
        for page in list(self.page200_set):
            if page in self.page404_set:
                continue
            if self.skip_302:
                self.page404_set.add(page)
                continue
            for url_404 in self.gen_check_url(page.url):
                try:
                    page_404 = Page(await self.http_req_wrap(url_404))
                except Exception:
                    continue
                self.page404_set.add(page_404)
                if page_404.is_302() and page_404.location_url.endswith(page_404.url.payload + "/"):
                    self.page404_set.add(page)
                    self.skip_302 = True
        self.page200_set -= self.page404_set

    def gen_check_url(self, url: URL):
        payload = url.payload
        if url.path in url.scope:
            check_url = url.url + "1337"
        else:
            check_url = url.url.replace(url.path, url.path + "1337")
        end_check_url = URL(check_url, payload + "1337")

        for p in ["..", "?", "etc/passwd"]:
            if p in payload:
                check_url = url.url.replace(p, p + "a1337")
                payload = payload.replace(p, p + "a1337")
                return [URL(check_url, payload)]
        if "." in url.path and "." in payload:
            path = url.path.replace(".", "a1337.")
            check_url = f"{url.scope}{path}"
            payload = payload.replace(".", "a1337.")
            return [URL(check_url, payload), end_check_url]
        if url.path.endswith("/"):
            path = url.path[:-1] + "a1337/"
            check_url = f"{url.scope}{path}"
            return [URL(check_url, payload + "a1337/")]
        return [end_check_url]


class GenBackDicts:
    def __init__(self, url: str):
        self.target = _normal_url(url)
        self.suffixs = [".tar", ".tar.gz", ".zip", ".rar", ".7z", ".bz2", ".gz", "_bak.rar", ".war"]
        self.path = urlparse(self.target).path

    def gen_dict_from_domain(self):
        result = []
        res = get_tld(self.target, as_object=True, fail_silently=True)
        if res:
            result = [x for x in [str(res.parsed_url.netloc).split(":")[0], res.fld, res.subdomain,
                                  res.domain] + res.subdomain.split(".") if x != ""]
        return set(result)

    def gen_backup_dicts(self, names):
        return ["".join(x) for x in itertools.product(names, self.suffixs)]

    def gen_dict_from_path(self):
        out = []
        dirs = os.path.dirname(self.path).split("/")
        if len(dirs) > 1 and dirs[-1]:
            out = self.gen_backup_dicts([dirs[-1]])
        return out

    def gen(self):
        ret = set()
        names = self.gen_dict_from_domain()
        for x in self.gen_backup_dicts(names):
            ret.add(URL(urljoin(self.target, x), x))
        for x in self.gen_dict_from_path():
            ret.add(URL(urljoin(self.target, x), x))
            ret.add(URL(urljoin(self.target, "./../" + x), x))
        return ret


class GenURL:
    def __init__(self, target: str, dicts):
        self.target = _normal_url(target).split("?")[0]
        self.dicts = set(dicts)
        self.urls: set[URL] = set()

    def build_urls(self):
        target = os.path.dirname(self.target)
        for d in self.dicts:
            u = URL(f"{target}/{d.strip()}", d.strip())
            self.urls.add(u)

    def gen(self, flag: bool = True):
        if urlparse(self.target).path == "/":
            self.dicts |= GenBackDicts(self.target).gen_dict_from_domain()
        self.build_urls()
        if flag:
            self.urls |= GenBackDicts(self.target).gen()
        return self.urls


async def file_leak(targets, dicts, gen_dict: bool = True) -> List[Page]:
    all_gen_url: set[URL] = set()
    map_url: dict[str, set[URL]] = {}

    for site in targets:
        site = _normal_url(site.strip())
        if not site:
            continue
        map_url[URL(site, "").scope] = set()
        a = GenURL(site, dicts)
        all_gen_url |= a.gen(gen_dict)

    for url in all_gen_url:
        map_url[url.scope].add(url)

    ret: list[Page] = []
    for target in map_url:
        try:
            f = FileLeak(target, map_url[target], concurrency_count)
            pages = await f.run()
            for page in pages:
                logger.info(f"found => {page}")
            ret.extend(pages)
        except Exception as e:
            logger.info(f"error on {target}, {e}")
    return ret
