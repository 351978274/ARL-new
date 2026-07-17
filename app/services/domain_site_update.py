"""域名→站点更新，移植自原 app/services/domainSiteUpdate.py。

将 WIH/搜索引擎发现的域名补充进任务（仅写 domain + site 表），并探测站点。
"""
from __future__ import annotations

import time

from ..logger import get_logger
from ..utils import domain_parsed, gen_filename
from .build_domain_info import build_domain_info
from .probe_http import probe_http
from .fetch_site import fetch_site
from .base_update_task import BaseUpdateTask

logger = get_logger()


class DomainSiteUpdate:
    def __init__(self, task_id: str, domains: list, source: str):
        self.task_id = task_id
        self.domains = domains
        self.source = source
        self.domain_info_list = []
        self.available_sites: list[str] = []
        self.base_update_task = BaseUpdateTask(task_id)

    async def save_domain_info(self):
        self.domain_info_list = await build_domain_info(self.domains)
        from ..database import conn_db
        for obj in self.domain_info_list:
            info = obj.dump_json(flag=False)
            info["task_id"] = self.task_id
            info["source"] = self.source
            dp = domain_parsed(info["domain"])
            if dp:
                info["fld"] = dp["fld"]
            await conn_db('domain').insert_one(info)

    async def probe_sites(self):
        available_domains = [obj.domain for obj in self.domain_info_list]
        self.available_sites = await probe_http(available_domains, 15)

    async def save_site_info(self):
        from ..database import conn_db
        site_info_list = await fetch_site(self.available_sites)
        for site_info in site_info_list:
            curr_site = site_info["site"]
            site_path = "/image/" + self.task_id
            file_name = f'{site_path}/{gen_filename(curr_site)}.jpg'
            site_info["task_id"] = self.task_id
            site_info["screenshot"] = file_name
        if site_info_list:
            await conn_db('site').insert_many(site_info_list)

    async def set_and_check_domains(self):
        from ..helpers.domain import find_domain_by_task_id
        task_domains = await find_domain_by_task_id(self.task_id)
        self.domains = list(set(self.domains) - set(task_domains))

    async def run(self):
        status_name = f"{self.source}_domain_update"
        await self.set_and_check_domains()
        logger.info(f"start domain site update task_id:{self.task_id} len:{len(self.domains)} source:{self.source}")
        await self.base_update_task.update_task_field("status", status_name)
        t1 = time.time()
        await self.save_domain_info()
        await self.probe_sites()
        await self.save_site_info()
        elapsed = time.time() - t1
        await self.base_update_task.update_services(status_name, elapsed)
        logger.info(f"end domain site update elapse {elapsed:.2f}s")


async def domain_site_update(task_id: str, domains: list, source: str):
    await DomainSiteUpdate(task_id, domains, source).run()
