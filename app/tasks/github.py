"""GitHub 关键字搜索/监控任务，移植自原 app/tasks/github.py。"""
from __future__ import annotations

from bson import ObjectId

from ..config import Config
from ..database import conn_db
from ..helpers.message_notify import push_dingding
from ..logger import get_logger
from ..modules import TaskStatus
from ..services.github_search import GithubResult, github_search
from ..utils import curr_date, curr_date_obj

logger = get_logger()


class GithubTaskTask:
    def __init__(self, task_id: str, keyword: str):
        self.task_id = task_id
        self.keyword = keyword
        self.collection = "github_task"
        self.results: list[GithubResult] = []

    async def update_status(self, value: str):
        await conn_db(self.collection).update_one({"_id": ObjectId(self.task_id)}, {"$set": {"status": value}})

    async def set_start_time(self):
        await conn_db(self.collection).update_one({"_id": ObjectId(self.task_id)}, {"$set": {"start_time": curr_date()}})

    async def set_end_time(self):
        await conn_db(self.collection).update_one({"_id": ObjectId(self.task_id)}, {"$set": {"end_time": curr_date()}})

    async def search_result(self):
        await self.update_status("search")
        self.results.extend(await github_search(keyword=self.keyword))

    async def save_content(self):
        await self.update_status(f"fetch content-{len(self.results)}")
        for result in self.results:
            if not isinstance(result, GithubResult):
                continue
            if await self.filter_result(result):
                continue
            await conn_db("github_result").insert_one(await self.result_to_dict(result))

    async def result_to_dict(self, result: GithubResult) -> dict:
        item = result.to_dict()
        item["human_content"] = await result.human_content(self.keyword)
        item["keyword"] = self.keyword
        item["github_task_id"] = self.task_id
        return item

    async def filter_result(self, result: GithubResult) -> bool:
        path_keyword_list = ["open-app-filter/", "/adbyby", "/adblock", "luci-app-dnsfilter/",
                             "Spider/", "/spider", "_files/", "alexa_10k.json", "/WeWorkProviderTest.php"]
        if any(p in result.path for p in path_keyword_list):
            return True
        content = await result.content
        content_keyword_list = ["DOMAIN-SUFFIX", "HOST-SUFFIX", "name:[proto;sport;dport;host",
                                '  "websites": [', "import android.app.Application;",
                                "import android.app.Activity;"]
        return any(k in content for k in content_keyword_list)

    async def statistic(self):
        cnt = await conn_db('github_result').count_documents({"github_task_id": self.task_id})
        await conn_db(self.collection).update_one(
            {"_id": ObjectId(self.task_id)}, {"$set": {"statistic": {"github_result_cnt": cnt}}})

    async def run(self):
        await self.set_start_time()
        await self.search_result()
        await self.save_content()
        await self.update_status(TaskStatus.DONE)
        await self.statistic()
        await self.set_end_time()


class GithubTaskMonitor(GithubTaskTask):
    def __init__(self, task_id: str, keyword: str, scheduler_id: str):
        super().__init__(task_id, keyword)
        self.scheduler_id = scheduler_id
        self.hash_md5_list: list[str] = []
        self.new_results: list[GithubResult] = []

    async def init_md5_list(self):
        cursor = conn_db("github_hash").find({"github_scheduler_id": self.scheduler_id}, {"hash_md5": 1})
        async for result in cursor:
            if result["hash_md5"] not in self.hash_md5_list:
                self.hash_md5_list.append(result["hash_md5"])

    async def save_mongo(self):
        cnt = 0
        await self.update_status("fetch content")
        for result in self.results:
            if not isinstance(result, GithubResult):
                continue
            if result.hash_md5 in self.hash_md5_list:
                continue
            self.hash_md5_list.append(result.hash_md5)
            await conn_db("github_hash").insert_one(
                {"hash_md5": result.hash_md5, "github_scheduler_id": self.scheduler_id})
            if await self.filter_result(result):
                continue
            item = await self.result_to_dict(result)
            item["github_scheduler_id"] = self.scheduler_id
            item["update_date"] = curr_date_obj()
            cnt += 1
            self.new_results.append(result)
            await conn_db("github_monitor_result").insert_one(item)
        logger.info(f"github_monitor save {self.keyword} {cnt}")

    def build_markdown_report(self) -> str:
        repo_map: dict[str, list[GithubResult]] = {}
        for r in self.new_results:
            repo_map.setdefault(r.repo_full_name, []).append(r)
        md = f"[监控-Github-{self.keyword}] \n 仓库数:{len(repo_map)}  结果数:{len(self.new_results)} \n --- \n"
        global_cnt = 0
        for repo_name in list(repo_map)[:5]:
            for i, item in enumerate(repo_map[repo_name][:5], 1):
                global_cnt += 1
                md += f"{global_cnt}. [{repo_name} {item.path}]({item.html_url})  \n"
        return md

    async def push_msg(self):
        if not self.new_results:
            return
        logger.info(f"found new result {self.keyword} {len(self.new_results)}")
        await push_dingding(self.build_markdown_report())

    async def run(self):
        await self.set_start_time()
        await self.init_md5_list()
        await self.search_result()
        await self.save_mongo()
        self.results = self.new_results
        await self.save_content()
        await self.push_msg()
        await self.statistic()
        await self.update_status(TaskStatus.DONE)
        await self.set_end_time()


async def github_task_task(task_id: str, keyword: str):
    task = GithubTaskTask(task_id=task_id, keyword=keyword)
    try:
        if not Config.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN is empty")
            await task.update_status(TaskStatus.ERROR)
            await task.set_end_time()
            return
        await task.run()
    except Exception as e:
        logger.exception(e)
        await task.update_status(TaskStatus.ERROR)
        await task.set_end_time()


async def github_task_monitor(task_id: str, keyword: str, scheduler_id: str):
    task = GithubTaskMonitor(task_id=task_id, keyword=keyword, scheduler_id=scheduler_id)
    try:
        await task.run()
    except Exception as e:
        logger.exception(e)
        await task.update_status(TaskStatus.ERROR)
        await task.set_end_time()
