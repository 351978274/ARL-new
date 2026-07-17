"""资产站点监控任务 + 添加资产站点任务，移植自原 app/tasks/asset_site.py。"""
from __future__ import annotations

from bson import ObjectId

from ..database import conn_db
from ..helpers.message_notify import push_dingding, push_email
from ..logger import get_logger
from ..modules import TaskStatus
from ..services import webhook
from ..services.asset_site_monitor import AssetSiteMonitor, Domain2SiteMonitor
from ..services.common_task import WebSiteFetch
from ..tasks.risk_cruising import RiskCruising
from ..utils import curr_date

logger = get_logger()


class AssetSiteUpdateTask:
    def __init__(self, task_id: str, scope_id: str):
        self.task_id = task_id
        self.scope_id = scope_id

    async def update_status(self, value: str):
        await conn_db('task').update_one({"_id": ObjectId(self.task_id)}, {"$set": {"status": value}})

    async def set_start_time(self):
        await conn_db('task').update_one({"_id": ObjectId(self.task_id)}, {"$set": {"start_time": curr_date()}})

    async def set_end_time(self):
        await conn_db('task').update_one({"_id": ObjectId(self.task_id)}, {"$set": {"end_time": curr_date()}})

    async def save_task_site(self, site_info_list: list[dict]):
        for si in site_info_list:
            si["task_id"] = self.task_id
            await conn_db('site').insert_one(si)
        logger.info(f"save {len(site_info_list)} to {self.task_id}")

    async def monitor(self):
        await self.update_status("fetch site")
        monitor = AssetSiteMonitor(scope_id=self.scope_id)
        await monitor._init_scope_name()
        await monitor.build_change_list()
        if monitor.site_change_info_list:
            await self.save_task_site(monitor.site_change_info_list)

        await self.update_status("domain site monitor")
        d2s = Domain2SiteMonitor(scope_id=self.scope_id)
        d2s_result = await d2s.run()
        if d2s_result:
            await self.save_task_site(d2s.site_info_list)

        await self.update_status("send notify")
        html_report = monitor.build_html_report() if monitor.site_change_info_list else ""
        if d2s.site_info_list:
            html_report += "\n<br/>" + d2s.html_report
        if html_report:
            await push_email(title=f"[站点监控-{monitor.scope_name}] 灯塔消息推送", html_report=html_report)

        markdown_report = monitor.build_markdown_report() if monitor.site_change_info_list else ""
        if d2s.site_info_list:
            markdown_report += "\n" + d2s.dingding_markdown
        if markdown_report:
            await push_dingding(markdown_report=markdown_report)

        if html_report or markdown_report:
            await webhook.site_asset_web_hook(task_id=self.task_id, scope_id=self.scope_id)

    async def insert_task_stat(self):
        from ..utils import arl as arl_util
        stat = await arl_util.task_statistic(self.task_id)
        await conn_db('task').update_one({"_id": ObjectId(self.task_id)}, {"$set": {"statistic": stat}})

    async def run(self):
        await self.set_start_time()
        await self.monitor()
        await self.insert_task_stat()
        await self.update_status(TaskStatus.DONE)
        await self.set_end_time()


async def asset_site_update_task(task_id: str, scope_id: str, scheduler_id: str):
    from ..scheduler.jobs import update_job_run
    task = AssetSiteUpdateTask(task_id=task_id, scope_id=scope_id)
    try:
        await update_job_run(job_id=scheduler_id)
        await task.run()
    except Exception as e:
        logger.exception(e)
        await task.update_status(TaskStatus.ERROR)
        await task.set_end_time()


class AddAssetSiteTask(RiskCruising):
    async def asset_site_deduplication(self):
        related_scope_id = self.options.get("related_scope_id", "")
        if not related_scope_id:
            raise Exception(f"not found related_scope_id, task_id:{self.task_id}")
        new_targets = []
        for url in (self.targets or []):
            if "://" not in url:
                url = "http://" + url
            url = url.strip("/")
            exists = await conn_db('asset_site').find_one({"site": url, "scope_id": related_scope_id})
            if exists:
                logger.info(f"{url} is in scope")
                continue
            new_targets.append(url)
        self.targets = new_targets

    async def work(self):
        await self.asset_site_deduplication()
        self.pre_set_site()
        if self.user_target_site_set:
            web_site_fetch = WebSiteFetch(task_id=self.task_id,
                                          sites=list(self.user_target_site_set), options=self.options)
            await web_site_fetch.run()
        await self.common_run()


async def run_add_asset_site_task(task_id: str):
    task_data = await conn_db('task').find_one({"_id": ObjectId(task_id)})
    if not task_data or task_data["status"] != "waiting":
        return
    r = AddAssetSiteTask(task_id)
    await r._load()
    try:
        await r.update_task_field("start_time", curr_date())
        await r.work()
        await r.update_task_field("status", TaskStatus.DONE)
    except Exception as e:
        await r.update_task_field("status", TaskStatus.ERROR)
        logger.exception(e)
    await r.update_task_field("end_time", curr_date())
