"""域名/IP 监控执行器，移植自原 app/tasks/scheduler.py。

DomainExecutor / IPExecutor 分别继承 DomainTask / IPTask，覆写 run 以实现
增量监控（仅处理新发现的域名/IP/端口），并同步到资产组 + webhook。
"""
from __future__ import annotations

import time
from bson import ObjectId

from ..database import conn_db as conn
from ..logger import get_logger
from ..modules import CollectSource, SchedulerStatus, TaskStatus
from ..services import build_domain_info, sync_asset
from ..services import webhook
from ..utils import curr_date, curr_date_obj, get_asset_domain_by_id, random_choices
from ..utils.domain_util import cut_first_name
from .domain_task import DomainTask
from .ip_task import IPTask

logger = get_logger()


async def domain_executors(base_domain=None, job_id=None, scope_id=None, options=None, name=""):
    logger.info(f"start domain_executors {base_domain} {scope_id} {options}")
    try:
        item = await conn('scheduler').find_one({"_id": ObjectId(job_id)})
        if not item:
            logger.info(f"stop domain_executors {base_domain} not found job_id {job_id}")
            return
        if item.get("status") == SchedulerStatus.STOP:
            logger.info(f"stop domain_executors {base_domain} job_id {job_id} is stop")
            return
        await wrap_domain_executors(base_domain=base_domain, job_id=job_id,
                                    scope_id=scope_id, options=options, name=name)
    except Exception as e:
        logger.exception(e)


async def wrap_domain_executors(base_domain=None, job_id=None, scope_id=None, options=None, name=""):
    task_data = {
        'name': name, 'target': base_domain, 'start_time': '-', 'status': 'waiting',
        'type': 'domain', 'task_tag': 'monitor',
        'options': {
            'domain_brute': True, 'domain_brute_type': 'test', 'alt_dns': False,
            'arl_search': True, 'port_scan_type': 'test', 'port_scan': True,
            'service_detection': False, 'service_brute': False, 'os_detection': False,
            'site_identify': False, 'site_capture': False, 'file_leak': False,
            'site_spider': False, 'search_engines': False, 'ssl_cert': False,
            'fofa_search': False, 'dns_query_plugin': False, 'web_info_hunter': False,
            'scope_id': scope_id,
        },
        'celery_id': '',
    }
    if options:
        task_data["options"].update(options)
    await conn('task').insert_one(task_data)
    task_id = str(task_data.pop("_id"))
    domain_executor = DomainExecutor(base_domain, task_id, task_data["options"])
    try:
        from ..scheduler.jobs import update_job_run
        await update_job_run(job_id)
        new_domain = await domain_executor.run()
        if new_domain:
            await sync_asset(task_id, scope_id, update_flag=True, push_flag=True, task_name=name)
            await webhook.domain_asset_web_hook(task_id=task_id, scope_id=scope_id)
    except Exception as e:
        logger.exception(e)
        await domain_executor.update_task_field("status", TaskStatus.ERROR)
        await domain_executor.update_task_field("end_time", curr_date())
    logger.info(f"end domain_executors {base_domain} {scope_id} {options}")


class DomainExecutor(DomainTask):
    def __init__(self, base_domain, task_id, options):
        super().__init__(base_domain, task_id, options)
        self.domain_set: set[str] = set()
        self.scope_id = options["scope_id"]
        self.scope_domain_set: set[str] | None = None
        self.new_domain_set: set[str] | None = None
        self.task_tag = "monitor"
        self.wildcard_ip_set: set[str] | None = None

    async def run(self):
        await self.update_task_field("start_time", curr_date())
        await self.domain_fetch()
        for di in self.domain_info_list:
            self.domain_set.add(di.domain)
        await self.set_scope_domain()
        self.new_domain_set = self.domain_set - self.scope_domain_set
        await self.set_wildcard_ip_set()
        await self.set_domain_info_list()
        ret_new_domain_set = {di.domain for di in self.domain_info_list}
        await self.start_ip_fetch()
        await self.start_site_fetch()
        await self.insert_cip_stat()
        await self.insert_finger_stat()
        await self.insert_task_stat()
        await self.update_task_field("status", TaskStatus.DONE)
        await self.update_task_field("end_time", curr_date())
        return ret_new_domain_set

    async def set_scope_domain(self):
        self.scope_domain_set = set(await get_asset_domain_by_id(self.scope_id))

    async def set_domain_info_list(self):
        self.domain_info_list = []
        self.record_map = {}
        logger.info(f"start build domain monitor task, new domain {len(self.new_domain_set)}")
        t1 = time.time()
        self.task_tag = "task"  # 让 build_domain_info 工作
        new = await self.build_domain_info(self.new_domain_set)
        new = await self.clear_domain_info_by_record(new)
        self.task_tag = "monitor"
        if self.wildcard_ip_set:
            new = await self.clear_wildcard_domain_info(new)
        logger.info(f"end build domain monitor task {len(new)} elapse {time.time()-t1:.2f}s")
        await conn('domain').delete_many({"task_id": self.task_id})
        await self.save_domain_info_list(new, CollectSource.MONITOR)
        self.domain_info_list = new

    async def set_wildcard_ip_set(self):
        cut_set: set[str] = set()
        random_name = random_choices(6)
        for domain in self.new_domain_set:
            cut_name = cut_first_name(domain)
            if cut_name:
                cut_set.add(f"{random_name}.{cut_name}")
        info_list = await build_domain_info(cut_set)
        wildcard_ip_set: set[str] = set()
        for info in info_list:
            wildcard_ip_set |= set(info.ip_list)
        self.wildcard_ip_set = wildcard_ip_set
        logger.info(f"start get wildcard_ip_set {len(wildcard_ip_set)}")

    async def clear_wildcard_domain_info(self, info_list):
        cnt = 0
        new = []
        for info in info_list:
            if self.wildcard_ip_set & set(info.ip_list):
                cnt += 1
                continue
            new.append(info)
        logger.info(f"clear_wildcard_domain_info {cnt}")
        return new


class IPExecutor(IPTask):
    def __init__(self, target, scope_id, task_name, options):
        super().__init__(ip_target=target, task_id=None, options=options)
        self.scope_id = scope_id
        self.task_name = task_name
        self.task_tag = "monitor"

    async def insert_task_data(self):
        task_data = {
            'name': self.task_name, 'target': self.ip_target, 'start_time': '-', 'end_time': '-',
            'status': TaskStatus.WAITING, 'type': 'ip', 'task_tag': 'monitor',
            'options': {
                "port_scan_type": "test", "port_scan": True, "service_detection": False,
                "os_detection": False, "site_identify": False, "site_capture": False,
                "file_leak": False, "site_spider": False, "ssl_cert": False,
                'web_info_hunter': False, 'scope_id': self.scope_id,
            },
            'celery_id': '',
        }
        if self.options:
            task_data["options"].update(self.options)
        await conn('task').insert_one(task_data)
        self.task_id = str(task_data.pop("_id"))
        self.base_update_task.task_id = self.task_id

    async def set_asset_ip(self):
        if self.task_tag != 'monitor':
            return
        items = await conn('asset_ip').find({"scope_id": self.scope_id}, {"ip": 1, "port_info": 1}).to_list(None)
        for item in items:
            self.asset_ip_info_map[item["ip"]] = item
            for port_info in item.get("port_info", []):
                self.asset_ip_port_set.add(f"{item['ip']}:{port_info['port_id']}")

    async def async_ip_info(self):
        new_ip_info_list = []
        for ip_info in self.ip_info_list:
            curr_ip = ip_info["ip"]
            now_obj = curr_date_obj()
            if curr_ip not in self.asset_ip_info_map:
                asset_ip_info = ip_info.copy()
                asset_ip_info["scope_id"] = self.scope_id
                asset_ip_info["domain"] = []
                asset_ip_info["save_date"] = now_obj
                asset_ip_info["update_date"] = now_obj
                await conn('asset_ip').insert_one(asset_ip_info)
                await conn('ip').insert_one(ip_info)
                new_ip_info_list.append(ip_info)
                continue
            new_port_info_list = [pi for pi in ip_info["port_info"]
                                  if f"{curr_ip}:{pi['port_id']}" not in self.asset_ip_port_set]
            if new_port_info_list:
                asset_ip_info = self.asset_ip_info_map[curr_ip]
                asset_ip_info["port_info"].extend(new_port_info_list)
                await conn('asset_ip').update_one(
                    {"_id": asset_ip_info["_id"]},
                    {"$set": {"update_date": now_obj, "port_info": asset_ip_info["port_info"]}})
                ip_info["port_info"] = new_port_info_list
                await conn('ip').insert_one(ip_info)
                new_ip_info_list.append(ip_info)
        self.ip_info_list = new_ip_info_list
        logger.info(f"found new ip_info {len(self.ip_info_list)}")

    async def sync_asset_site_wih(self):
        query = {"task_id": self.task_id}
        site_cnt = await conn('site').count_documents(query)
        wih_cnt = await conn('wih').count_documents(query)
        if not (site_cnt or wih_cnt):
            return
        await sync_asset(self.task_id, self.scope_id, update_flag=False,
                         category=["site", "wih"], push_flag=True, task_name=self.task_name)


async def ip_executor(target, scope_id, task_name, job_id, options):
    try:
        item = await conn('scheduler').find_one({"_id": ObjectId(job_id)})
        if not item:
            logger.info(f"stop ip_executors {target} not found job_id {job_id}")
            return
        if item.get("status") == SchedulerStatus.STOP:
            logger.info(f"stop ip_executors {target} job_id {job_id} is stop")
            return
        from ..scheduler.jobs import update_job_run
        await update_job_run(job_id)
    except Exception as e:
        logger.exception(e)
        return

    executor = IPExecutor(target, scope_id, task_name, options)
    try:
        await executor.insert_task_data()
        await executor.run()
        await executor.sync_asset_site_wih()
    except Exception as e:
        logger.warning(f"error on ip_executor {executor.ip_target}")
        logger.exception(e)
        await executor.base_update_task.update_task_field("status", TaskStatus.ERROR)
