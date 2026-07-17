"""风险巡航（PoC/弱口令）任务，移植自原 app/tasks/poc.py。

单独的 PoC 任务：解析用户提交的目标，进行站点识别、协议识别、PoC 与弱口令爆破。
原版用 Thread 跑 npoc，本版用 asyncio.to_thread 包裹。
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from bson import ObjectId

from ..config import Config
from ..database import conn_db
from ..logger import get_logger
from ..modules import TaskStatus
from ..services import npoc
from ..services.common_task import CommonTask, WebSiteFetch
from ..utils import curr_date

logger = get_logger()


async def run_risk_cruising_task(task_id: str):
    task_data = await conn_db('task').find_one({"_id": ObjectId(task_id)})
    if not task_data or task_data["status"] != "waiting":
        return
    r = RiskCruising(task_id)
    await r.run()


class RiskCruising(CommonTask):
    def __init__(self, task_id: str):
        super().__init__(task_id=task_id)
        self.task_id = task_id
        self.query = {"_id": ObjectId(task_id)}
        self.task_data = None
        self.options: dict = {}
        self.poc_plugin_name: list[str] = []
        self.brute_plugin_name: list[str] = []
        self.result_set_id = None
        self.targets = None
        self.sniffer_target_set: set[str] = set()
        self.npoc_service_target_set: set[str] = set()
        self.user_target_site_set: set[str] = set()
        self.available_sites: list[str] = []

    async def _load(self):
        self.task_data = await conn_db('task').find_one(self.query)
        self.options = (self.task_data or {}).get("options", {})
        self.result_set_id = (self.task_data or {}).get("result_set_id")
        self.targets = (self.task_data or {}).get("cruising_target")

    def init_plugin_name(self):
        self.poc_plugin_name = [i["plugin_name"] for i in self.options.get("poc_config", []) if i.get("enable")]
        self.brute_plugin_name = [i["plugin_name"] for i in self.options.get("brute_config", []) if i.get("enable")]

    async def set_relay_targets(self):
        if self.targets:
            for x in self.targets:
                o = urlparse(x)
                if not o.scheme and x:
                    self.sniffer_target_set.add(x)
                    continue
                if o.scheme in ["http", "https"]:
                    continue
                if o.netloc:
                    self.sniffer_target_set.add(o.netloc)
        if not self.result_set_id:
            return
        item = await conn_db('result_set').find_one({"_id": ObjectId(self.result_set_id)})
        if item:
            self.targets = item["items"]
            await conn_db('result_set').delete_one({"_id": ObjectId(self.result_set_id)})

    async def npoc_service_detection(self):
        logger.info(f"start npoc_service_detection {len(self.sniffer_target_set)}")
        result = await npoc.run_sniffer(self.sniffer_target_set)
        for item in result:
            self.npoc_service_target_set.add(item["target"])
            item["task_id"] = self.task_id
            item["save_date"] = curr_date()
            await conn_db('npoc_service').insert_one(item)

    async def _run_poc_or_brute(self, plugin_names: list[str], label: str):
        targets = self.available_sites + list(self.npoc_service_target_set)
        logger.info(f"start run {label} {len(plugin_names)}*{len(targets)}")
        npoc_instance = npoc.NPoC(tmp_dir=Config.TMP_PATH, concurrency=10)
        # npoc run_poc 是同步阻塞，放线程池
        await asyncio.to_thread(npoc_instance.run_poc, plugin_names, targets)
        for item in npoc_instance.result:
            item["task_id"] = self.task_id
            item["save_date"] = curr_date()
            await conn_db('vuln').insert_one(item)

    async def update_services(self, status, elapsed):
        await self.update_task_field("status", status)
        await conn_db('task').update_one(
            self.query, {"$push": {"service": {"name": status, "elapsed": float(f"{elapsed:.2f}")}}})

    async def update_task_field(self, field=None, value=None):
        await conn_db('task').update_one(self.query, {"$set": {field: value}})

    def pre_set_site(self):
        for x in (self.targets or []):
            if "://" not in x:
                self.user_target_site_set.add(f"http://{x}")
                continue
            if not x.startswith("http"):
                continue
            self.user_target_site_set.add(x)

    async def work(self):
        await self.set_relay_targets()
        self.pre_set_site()
        web_site_fetch = WebSiteFetch(task_id=self.task_id,
                                      sites=list(self.user_target_site_set), options=self.options)
        await web_site_fetch.run()
        self.available_sites = web_site_fetch.available_sites

        self.init_plugin_name()
        if self.options.get("npoc_service_detection"):
            await self.update_task_field("status", "npoc_service_detection")
            t1 = time.time()
            await self.npoc_service_detection()
            await self.update_services("npoc_service_detection", time.time() - t1)
        if self.brute_plugin_name:
            await self.update_task_field("status", "weak_brute")
            t1 = time.time()
            await self._run_poc_or_brute(self.brute_plugin_name, "brute")
            await self.update_services("weak_brute", time.time() - t1)
        if self.poc_plugin_name:
            await self.update_task_field("status", "PoC")
            t1 = time.time()
            await self._run_poc_or_brute(self.poc_plugin_name, "poc")
            await self.update_services("PoC", time.time() - t1)
        await self.common_run()

    async def run(self):
        await self._load()
        try:
            await self.update_task_field("start_time", curr_date())
            await self.work()
            await self.update_task_field("status", TaskStatus.DONE)
        except Exception as e:
            await self.update_task_field("status", TaskStatus.ERROR)
            logger.exception(e)
        await self.update_task_field("end_time", curr_date())
