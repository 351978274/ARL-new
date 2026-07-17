"""任务公共类（CommonTask + WebSiteFetch），移植自原 app/services/commonTask.py。

CommonTask: 统计/指纹统计/C段统计/资产同步。
WebSiteFetch: 对发现的站点执行识别/截图/爬虫/文件泄露/nuclei/PoC/WIH 等后续处理。
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

from bson import ObjectId

from ..config import Config
from ..database import conn_db
from ..logger import get_logger
from ..modules import CollectSource, WebSiteFetchOption, WebSiteFetchStatus
from ..utils import arl as arl_util, curr_date, domain_parsed
from .base_update_task import BaseUpdateTask
from .npoc import run_risk_cruising
from .site_screenshot import site_screenshot
from .site_spider import site_spider_thread
from .page_fetch import page_fetch
from .file_leak import file_leak as file_leak_service
from .nuclei_scan import nuclei_scan
from .info_hunter import run_wih
from .web_analyze import web_analyze
from .sync_asset import sync_asset

logger = get_logger()


class CommonTask:
    """任务统计公共方法。"""

    def __init__(self, task_id: str):
        self.task_id = task_id

    async def insert_task_stat(self):
        stat = await arl_util.task_statistic(self.task_id)
        logger.info("insert task stat")
        await conn_db('task').update_one({"_id": ObjectId(self.task_id)}, {"$set": {"statistic": stat}})

    async def insert_finger_stat(self):
        finger_stat_map = await arl_util.gen_stat_finger_map(self.task_id)
        logger.info(f"insert finger stat {len(finger_stat_map)}")
        for key, data in finger_stat_map.items():
            data = data.copy()
            data["task_id"] = self.task_id
            await conn_db('stat_finger').insert_one(data)

    async def insert_cip_stat(self):
        cip_map = await arl_util.gen_cip_map(self.task_id)
        logger.info(f"insert cip stat {len(cip_map)}")
        for cidr_ip, item in cip_map.items():
            ip_list = list(item["ip_set"])
            domain_list = list(item["domain_set"])
            await conn_db('cip').insert_one({
                "cidr_ip": cidr_ip, "ip_count": len(ip_list), "ip_list": ip_list,
                "domain_count": len(domain_list), "domain_list": domain_list,
                "task_id": self.task_id,
            })

    async def sync_asset_category(self):
        options = getattr(self, 'options', {})
        if not options:
            logger.warning(f"not found options {self.task_id}")
            return
        related_scope_id = options.get("related_scope_id", "")
        if not related_scope_id or len(related_scope_id) != 24:
            return
        await sync_asset(task_id=self.task_id, scope_id=related_scope_id)

    async def common_run(self):
        await self.insert_finger_stat()
        await self.insert_cip_stat()
        await self.insert_task_stat()
        await self.sync_asset_category()


class WebSiteFetch:
    """对用户提交或发现的站点进行后续处理（识别/截图/爬虫/泄露/nuclei/PoC/WIH）。"""

    def __init__(self, task_id: str, sites: list, options: dict, scope_domain: list | None = None):
        self.task_id = task_id
        self.sites = sites
        self.options = options
        self.base_update_task = BaseUpdateTask(task_id)
        self.site_info_list: list[dict] = []
        self.available_sites: list[str] = []
        self.web_analyze_map: dict = {}
        self.wih_domain_set: set[str] = set()
        self.wih_record_set: set = set()
        self.scope_domain = scope_domain or []
        self.page_url_set: set[str] = set()
        self.search_engines_result: dict[str, list[str]] = {}
        self._poc_sites: set[str] | None = None
        self._task_domain_set: set[str] | None = None

    @property
    async def task_domain_set(self) -> set[str]:
        if self._task_domain_set is None:
            self._task_domain_set = set(await arl_util.get_domain_by_id(self.task_id))
        return self._task_domain_set

    async def site_identify(self):
        self.web_analyze_map = await web_analyze(self.available_sites)

    def __str__(self):
        return f"<WebSiteFetch> task_id:{self.task_id}, sites:{len(self.sites)}, available:{len(self.available_sites)}"

    async def save_site_info(self):
        from ..utils import gen_filename
        for site_info in self.site_info_list:
            curr_site = site_info["site"]
            site_path = "/image/" + self.task_id
            file_name = f'{site_path}/{gen_filename(curr_site)}.jpg'
            site_info["task_id"] = self.task_id
            site_info["screenshot"] = file_name
            if self.web_analyze_map:
                finger_list = self.web_analyze_map.get(curr_site, [])
                known = {f["name"].lower() for f in site_info["finger"]}
                for af in finger_list:
                    if af["name"].lower() not in known:
                        site_info["finger"].append(af)
        logger.info(f"save_site_info {len(self.site_info_list)}, {self}")
        if self.site_info_list:
            await conn_db('site').insert_many(self.site_info_list)

    async def do_site_screenshot(self):
        capture_save_dir = Config.SCREENSHOT_DIR + "/" + self.task_id
        await site_screenshot(self.available_sites, concurrency=6, capture_dir=capture_save_dir)

    async def do_site_spider(self):
        entry_urls_list = []
        for site in self.available_sites:
            o = urlparse(site)
            if o.path != "":
                continue
            entry_urls = [site]
            entry_urls.extend(self.search_engines_result.get(site, []))
            entry_urls_list.append(entry_urls)
        site_spider_result = await site_spider_thread(entry_urls_list)
        spider_urls: list[str] = []
        for site, target_urls in site_spider_result.items():
            new_target_urls = []
            for url in target_urls:
                if url in self.page_url_set:
                    continue
                new_target_urls.append(url)
                self.page_url_set.add(url)
            if not new_target_urls:
                continue
            spider_urls.extend(new_target_urls)
        if spider_urls:
            logger.info(f"spider_urls {len(spider_urls)} task_id:{self.task_id}")
            page_map = await page_fetch(spider_urls)
            for url, item in page_map.items():
                full_item = {"site": url, "task_id": self.task_id, "source": CollectSource.SITESPIDER}
                full_item.update(item)
                dp = domain_parsed(url)
                if dp:
                    full_item["fld"] = dp["fld"]
                await conn_db('url').insert_one(full_item)

    async def fetch_site(self):
        from .fetch_site import fetch_site as _fetch_site
        self.site_info_list = await _fetch_site(self.sites)
        for site_info in self.site_info_list:
            self.available_sites.append(site_info["site"])

    async def do_file_leak(self):
        from ..utils import load_file
        for site in self.poc_sites:
            pages = await file_leak_service([site], load_file(Config.FILE_LEAK_TOP_2k))
            for page in pages:
                item = page.dump_json()
                item["task_id"] = self.task_id
                item["site"] = site
                await conn_db('fileleak').insert_one(item)

    @property
    def poc_sites(self) -> set[str]:
        from ..utils.url_util import cut_filename
        if self._poc_sites is None:
            self._poc_sites = set()
            for x in self.available_sites:
                cut_target = cut_filename(x)
                if cut_target:
                    self._poc_sites.add(cut_target)
        return self._poc_sites

    async def risk_cruising(self, npoc_service_target_set: set | None):
        poc_config = self.options.get("poc_config", [])
        plugins = [info["plugin_name"] for info in poc_config if info.get("enable")]
        poc_targets = self.poc_sites
        if npoc_service_target_set is not None:
            poc_targets = self.poc_sites | npoc_service_target_set
        result = await run_risk_cruising(plugins=plugins, targets=poc_targets)
        for item in result:
            item["task_id"] = self.task_id
            item["save_date"] = curr_date()
            await conn_db('vuln').insert_one(item)

    async def do_nuclei_scan(self):
        logger.info(f"start nuclei_scan, poc_sites:{len(self.poc_sites)}")
        scan_results = await nuclei_scan(list(self.poc_sites))
        for item in scan_results:
            item["task_id"] = self.task_id
            item["save_date"] = curr_date()
            await conn_db('nuclei_result').insert_one(item)
        logger.info(f"end nuclei_scan, result:{len(scan_results)}")

    async def run_func(self, name: str, func):
        logger.info(f"start run {name}, {self}")
        await self.base_update_task.update_task_field("status", name)
        t1 = time.time()
        await func()
        elapsed = time.time() - t1
        await self.base_update_task.update_services(name, elapsed)
        logger.info(f"end run {name} ({elapsed:.2f}s), {self}")

    async def update_page_url_set(self):
        from ..helpers.url import get_url_by_task_id
        urls = await get_url_by_task_id(self.task_id)
        self.page_url_set |= set(urls)
        for u in self.page_url_set:
            o = urlparse(u)
            ret_url = f"{o.scheme}://{o.netloc}"
            self.search_engines_result.setdefault(ret_url, []).append(u)

    def add_wih_domain_set(self, record):
        if self.scope_domain:
            if record.recordType == "domain":
                if not _domain_in_scope_domain(record.content, self.scope_domain):
                    return
                from ..utils import check_domain_black
                if check_domain_black(record.content):
                    return
                if record.content in self.wih_domain_set:
                    return
                self.wih_domain_set.add(record.content)

    async def run_web_info_hunter(self):
        records = set(await run_wih(self.sites))
        for record in records:
            if record.fnv_hash in self.wih_record_set:
                continue
            self.add_wih_domain_set(record)
            item = record.dump_json()
            item["task_id"] = self.task_id
            await conn_db('wih').insert_one(item)
            self.wih_record_set.add(record.fnv_hash)

    async def run(self):
        await self.run_func(WebSiteFetchStatus.FETCH_SITE, self.fetch_site)
        if self.options.get(WebSiteFetchOption.SITE_IDENTIFY):
            await self.run_func(WebSiteFetchStatus.SITE_IDENTIFY, self.site_identify)
        await self.save_site_info()
        self.site_info_list = []
        if self.options.get(WebSiteFetchOption.SITE_CAPTURE):
            await self.run_func(WebSiteFetchStatus.SITE_CAPTURE, self.do_site_screenshot)
        if self.options.get(WebSiteFetchOption.SITE_SPIDER):
            await self.update_page_url_set()
            await self.run_func(WebSiteFetchStatus.SITE_SPIDER, self.do_site_spider)
        if self.options.get(WebSiteFetchOption.FILE_LEAK):
            await self.run_func(WebSiteFetchStatus.FILE_LEAK, self.do_file_leak)
        if self.options.get(WebSiteFetchOption.NUCLEI_SCAN):
            await self.run_func(WebSiteFetchStatus.NUCLEI_SCAN, self.do_nuclei_scan)
        if self.options.get(WebSiteFetchOption.Info_Hunter):
            await self.run_func(WebSiteFetchStatus.Info_Hunter, self.run_web_info_hunter)


def _domain_in_scope_domain(domain: str, scope_domain: list) -> bool:
    return any(domain.endswith("." + s) for s in scope_domain)
