"""GitHub 代码搜索，移植自原 app/services/githubSearch.py。

通过 GitHub Code Search API 搜索关键字，返回 GithubResult 列表。
含限流重试逻辑。
"""
from __future__ import annotations

import asyncio
import base64
from collections import deque

from ..config import Config
from ..core.http_client import http_req
from ..logger import get_logger
from ..utils import gen_md5
from ..utils.time_util import parse_datetime

logger = get_logger()


async def github_client(url: str, params: dict | None = None, cnt: int = 0) -> dict:
    headers = {
        "Authorization": f"Bearer {Config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    await asyncio.sleep(2.5)
    conn = await http_req(url, params=params, headers=headers)
    data = conn.json()
    if conn.status_code != 200:
        message = data.get("message", "Github 错误")
        if cnt < 3:
            cnt += 1
            if ("You have triggered an abuse detection mechanism" in message
                    or "API rate limit exceeded for user ID" in message
                    or "You have exceeded a secondary rate limit" in message):
                sleep_time = 20 + 15 * cnt
                logger.info(f"rate-limit retry {cnt} {params}, time sleep {sleep_time}")
                await asyncio.sleep(sleep_time)
                return await github_client(url, params=params, cnt=cnt)
        raise Exception(message)
    return data


class GithubResult:
    def __init__(self, item: dict):
        self.raw_data = item
        self.git_url = item["git_url"]
        self.html_url = item["html_url"]
        self.repo_full_name = item["repository"]["full_name"]
        self.path = item["path"]
        self.hash_md5 = gen_md5(self.repo_full_name + "/" + item["path"])
        self._commit_date = None
        self._content = None

    def __hash__(self):
        return hash(self.hash_md5)

    def __eq__(self, other):
        return isinstance(other, GithubResult) and self.hash_md5 == other.hash_md5

    def __repr__(self):
        return f"<GithubResult>{self.hash_md5} {self.repo_full_name} {self.path}"

    @property
    async def content(self) -> str:
        if self._content is None:
            try:
                data = await github_client(self.git_url)
                content_base64 = data["content"]
                decode_bytes = base64.decodebytes(content_base64.encode("utf-8"))
                self._content = decode_bytes.decode("utf-8", errors="replace")
            except Exception as e:
                logger.info(f"error on {self.git_url}: {e}")
                self._content = ""
        return self._content

    @property
    async def commit_date(self) -> str:
        if self._commit_date is None:
            commit_url = f"https://api.github.com/repos/{self.repo_full_name}/commits"
            params = {"per_page": 1, "path": self.path}
            try:
                commit_info = await github_client(commit_url, params=params)
                assert commit_info
                self._commit_date = str(parse_datetime(commit_info[0]["commit"]["author"]["date"]))
            except Exception as e:
                logger.info(f"error on {commit_url}, {self.path}: {e}")
                self._commit_date = ""
        return self._commit_date

    async def human_content(self, keyword: str) -> str:
        content = await self.content
        lines = content.split("\n")
        max_len = 8
        before_lines: deque[str] = deque(maxlen=max_len)
        index = 0
        for line in lines:
            if keyword in line:
                break
            before_lines.append(line)
            index += 1
        after_lines = lines[index:index + max_len]
        return "{}\n{}".format("\n".join(before_lines), "\n".join(after_lines))

    def to_dict(self):
        return {
            "git_url": self.git_url, "html_url": self.html_url,
            "repo_full_name": self.repo_full_name, "path": self.path,
            "hash_md5": self.hash_md5, "commit_date": self._commit_date,
        }


async def github_search_code(query: str, order: str = "desc", sort: str = "indexed",
                             per_page: int = 100, page: int = 1):
    url = "https://api.github.com/search/code"
    params = {"q": query, "order": order, "sort": sort, "per_page": per_page, "page": page}
    data = await github_client(url, params=params)
    logger.info(f"search {query} count {data['total_count']}")
    ret_list = [GithubResult(item=item) for item in data["items"]]
    return ret_list, data["total_count"]


class GithubSearch:
    def __init__(self, query: str):
        self.results: list[GithubResult] = []
        self.query = query
        lq1 = ('language:Dockerfile language:"Java Properties" language:"Protocol Buffer" '
               'language:Gradle language:"Maven POM"')
        lq2 = ('language:Python language:"Git Config" language:INI '
               'language:Shell language:"SSH Config"')
        eq1 = ('extension:java extension:js extension:json extension:sql extension:yaml '
               'extension:yml extension:conf extension:config extension:jsp')
        eq2 = ('extension:php extension:py extension:go extension:bat extension:cfg extension:env '
               'extension:exs extension:ini extension:pem extension:ppk extension:cs')
        self.built_in_rules = [lq1, lq2, eq1, eq2]
        self.max_page = 3
        self.per_page = 100
        self.total_count = 0

    async def search(self) -> list[GithubResult]:
        try:
            for build_in in self.built_in_rules:
                build_in = build_in.strip()
                if not build_in:
                    continue
                curr_page = 1
                query = f"{self.query} {build_in}"
                results, total_count = await github_search_code(
                    query=query, per_page=self.per_page, page=curr_page)
                self.total_count += total_count
                if "filename:" not in build_in:
                    while (total_count / 100) > curr_page and curr_page < self.max_page:
                        curr_page += 1
                        next_results, total_count = await github_search_code(
                            query=query, per_page=self.per_page, page=curr_page)
                        results.extend(next_results)
                for result in results:
                    if result not in self.results:
                        self.results.append(result)
        except Exception as e:
            logger.info(f"Error on {self.query} {e}")
        logger.info(f"{self.query} search result {len(self.results)}")
        return self.results


async def github_search(keyword: str) -> list[GithubResult]:
    return await GithubSearch(keyword).search()
