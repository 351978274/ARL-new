"""资产 WIH 更新监控任务，移植自原 app/tasks/asset_wih.py。"""
from __future__ import annotations

import time

from ..database import conn_db
from ..helpers.scope import get_scope_by_scope_id
from ..logger import get_logger
from ..modules import TaskStatus
from ..services import domain_site_update, sync_asset
from ..services.asset_wih_monitor import asset_wih_monitor
from ..services.base_update_task import BaseUpdateTask
from ..services.common_task import CommonTask
from ..utils import curr_date

logger = get_logger()


class AssetWihUpdateTask(CommonTask):
    def __init__(self, task_id: str, scope_id: str):
        super().__init__(task_id=task_id)
        self.task_id = task_id
        self.scope_id = scope_id
        self.base_update_task = BaseUpdateTask(task_id)
        self.wih_results = []
        self._scope_sub_domains: set[str] | None = None

    async def run(self):
        logger.info(f"run AssetWihUpdateTask, task_id:{self.task_id} scope_id:{self.scope_id}")
        await self.run_wih_monitor()
        await self.wih_results_save()
        if self.wih_results:
            await self.run_wih_domain_update()
        await self.insert_stat()
        logger.info(f"end AssetWihUpdateTask, task_id:{self.task_id} results:{len(self.wih_results)}")

    async def insert_stat(self):
        await self.insert_finger_stat()
        await self.insert_task_stat()

    async def wih_results_save(self):
        for record in self.wih_results:
            item = record.dump_json()
            item["task_id"] = self.task_id
            await conn_db('wih').insert_one(item)

    async def run_wih_monitor(self):
        service_name = "wih_monitor"
        await self.base_update_task.update_task_field("status", service_name)
        t1 = time.time()
        self.wih_results = await asset_wih_monitor(self.scope_id)
        await self.base_update_task.update_services(service_name, time.time() - t1)

    @property
    async def scope_sub_domains(self) -> set[str]:
        if self._scope_sub_domains is None:
            self._scope_sub_domains = set(await conn_db('asset_domain').distinct("domain", {"scope_id": self.scope_id}))
        return self._scope_sub_domains

    async def run_wih_domain_update(self):
        scope_data = await get_scope_by_scope_id(self.scope_id)
        if not scope_data or scope_data.get("scope_type") != "domain":
            return
        sub_domains = await self.scope_sub_domains
        domains = [item.content for item in self.wih_results
                   if item.recordType == "domain" and item.content not in sub_domains]
        if domains:
            await domain_site_update(self.task_id, domains, "wih")
            await sync_asset(task_id=self.task_id, scope_id=self.scope_id)


async def asset_wih_update_task(task_id: str, scope_id: str, scheduler_id: str):
    from ..scheduler.jobs import update_job_run
    task = AssetWihUpdateTask(task_id=task_id, scope_id=scope_id)
    await task.base_update_task.update_task_field("start_time", curr_date())
    try:
        await update_job_run(job_id=scheduler_id)
        await task.run()
        await task.base_update_task.update_task_field("status", TaskStatus.DONE)
    except Exception as e:
        logger.exception(e)
        await task.base_update_task.update_task_field("status", TaskStatus.ERROR)
    await task.base_update_task.update_task_field("end_time", curr_date())
