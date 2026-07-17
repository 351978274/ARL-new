"""资产站点变化监控，移植自原 app/services/asset_site_monitor.py。

包含：
- AssetSiteCompare: 并发对比站点当前 title/status 与历史
- AssetSiteMonitor: 站点标题/状态码变化检测 + 报告
- Domain2SiteMonitor: 为 scope 中无站点的域名补站点
"""
from __future__ import annotations

import asyncio

from ..core.base_task import AsyncBaseTask
from ..core.http_client import http_req
from ..database import conn_db
from ..helpers.scope import get_scope_by_scope_id
from ..logger import get_logger
from ..utils import curr_date_obj, get_hostname, get_title
from ..utils.push import dict2dingding_mark, dict2table

logger = get_logger()


def _is_black_asset_site(site: str) -> bool:
    from ..config import Config
    try:
        with open(Config.black_asset_site, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and site.startswith(line):
                    return True
    except Exception:
        pass
    return False


class AssetSiteCompare(AsyncBaseTask):
    def __init__(self, scope_id: str, sites: list, concurrency: int = 15):
        super().__init__(sites, concurrency=concurrency)
        self.scope_id = scope_id
        self.new_site_info_map: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self.site_change_map: dict[str, dict] = {}

    async def work(self, site: str) -> None:
        if _is_black_asset_site(site):
            return
        try:
            conn = await http_req(site)
        except Exception as e:
            logger.debug(f"compare {site}: {e}")
            return
        async with self._lock:
            self.new_site_info_map[site] = {"title": get_title(conn.content), "status": conn.status_code}

    async def compare(self):
        cursor = conn_db('asset_site').find({"scope_id": self.scope_id}, {"site": 1, "title": 1, "status": 1})
        async for site_info in cursor:
            curr_site = site_info["site"]
            if curr_site not in self.new_site_info_map:
                continue
            new_info = self.new_site_info_map[curr_site]
            if new_info["status"] in [404, 502, 504]:
                continue
            if new_info["title"] != site_info.get("title"):
                if new_info["title"]:
                    self.site_change_map[curr_site] = site_info
            elif new_info["status"] != site_info.get("status"):
                if new_info["status"] == 200:
                    self.site_change_map[curr_site] = site_info

    async def run_compare(self) -> dict[str, dict]:
        await self._run()
        await self.compare()
        self.new_site_info_map.clear()
        return self.site_change_map


class AssetSiteMonitor:
    def __init__(self, scope_id: str):
        self.scope_id = scope_id
        self.status_change_list: list[dict] = []
        self.title_change_list: list[dict] = []
        self.site_change_info_list: list[dict] = []
        self.scope_name = ""

    async def _init_scope_name(self):
        scope_data = await get_scope_by_scope_id(self.scope_id)
        if not scope_data:
            raise Exception(f"没有找到资产组 {self.scope_id}")
        self.scope_name = scope_data["name"]

    async def compare_status(self, site_info, old_site_info) -> bool:
        if site_info["status"] != old_site_info["status"]:
            self.status_change_list.append({"site": site_info["site"],
                                            "status": site_info["status"],
                                            "old_status": old_site_info["status"]})
            await self.update_asset_site(old_site_info["_id"], site_info)
            return True
        return False

    async def compare_title(self, site_info, old_site_info) -> bool:
        if site_info["title"] != old_site_info.get("title"):
            self.title_change_list.append({"site": site_info["site"],
                                           "title": site_info["title"],
                                           "old_title": old_site_info.get("title", "")})
            await self.update_asset_site(old_site_info["_id"], site_info)
            return True
        return False

    async def build_change_list(self):
        sites = await conn_db('asset_site').distinct("site", {"scope_id": self.scope_id})
        compare = AssetSiteCompare(scope_id=self.scope_id, sites=list(sites))
        site_change_map = await compare.run_compare()
        sites_changed = list(site_change_map.keys())
        if not sites_changed:
            logger.info(f"not found change ok site, scope_id: {self.scope_id}")
            return
        from .fetch_site import fetch_site
        site_info_list = await fetch_site(sites_changed)
        for site_info in site_info_list:
            curr_site = site_info["site"]
            if curr_site not in site_change_map or "入口" not in site_info.get("tag", []):
                continue
            old_site_info = site_change_map[curr_site]
            if await self.compare_title(site_info, old_site_info):
                self.site_change_info_list.append(site_info)
                continue
            if await self.compare_status(site_info, old_site_info):
                self.site_change_info_list.append(site_info)
                continue

    async def update_asset_site(self, asset_id, site_info):
        copy_info = site_info.copy()
        copy_info["scope_id"] = self.scope_id
        now = curr_date_obj()
        copy_info["save_date"] = now
        copy_info["update_date"] = now
        await conn_db("asset_site").delete_one({"_id": asset_id})
        await conn_db("asset_site").insert_one(copy_info)

    def build_html_report(self) -> str:
        html = f" <br/><br/> 新发现标题变化 {len(self.title_change_list)}， 状态码变化 {len(self.status_change_list)}<br/><br/><br/>"
        if self.title_change_list:
            info = [{"站点": i["site"], "变化前标题": i["old_title"], "当前标题": i["title"]}
                    for i in self.title_change_list[:10]]
            html += dict2table(info) + "<br/><br/>"
        if self.status_change_list:
            info = [{"站点": i["site"], "变化前状态码": i["old_status"], "当前状态码": i["status"]}
                    for i in self.status_change_list[:10]]
            html += dict2table(info)
        return html

    def build_markdown_report(self) -> str:
        md = f"\n站点监控-{self.scope_name} 灯塔消息推送\n\n 新发现标题变化 {len(self.title_change_list)}， 状态码变化 {len(self.status_change_list)}\n\n"
        if self.title_change_list:
            md += "标题变化\n\n"
            for i, item in enumerate(self.title_change_list[:5], 1):
                md += f"{i}. {item['site']}  {item['old_title']} => {item['title']}\n"
            md += "\n"
        if self.status_change_list:
            md += "状态码变化\n\n"
            for i, item in enumerate(self.status_change_list[:5], 1):
                md += f"{i}. {item['site']}  {item['old_status']} => {item['status']}\n"
        return md


class Domain2SiteMonitor:
    def __init__(self, scope_id: str):
        self.scope_id = scope_id
        self.site_info_list: list[dict] = []
        self.html_report = ""
        self.dingding_markdown = ""

    async def find_not_domain_site(self) -> list[str]:
        sites = await conn_db('asset_site').distinct("site", {"scope_id": self.scope_id})
        domains = await conn_db('asset_domain').distinct("domain", {"scope_id": self.scope_id})
        if not domains:
            return []
        have = {get_hostname(s).split(":")[0] for s in sites}
        return [f"https://{d}" for d in set(domains) - have]

    async def run(self) -> list[dict]:
        sites = await self.find_not_domain_site()
        if not sites:
            return []
        from .fetch_site import fetch_site
        site_info_list = await fetch_site(sites, concurrency=20, http_timeout=(5, 6))
        for si in site_info_list:
            if si["status"] in [502, 504, 501, 422, 410]:
                continue
            if si["status"] == 400 and "400" in si.get("title", ""):
                continue
            self.site_info_list.append(si)
        self.build_report()
        if self.site_info_list:
            await self.insert_asset_site()
        return self.site_info_list

    async def insert_asset_site(self):
        now = curr_date_obj()
        for si in self.site_info_list:
            data = si.copy()
            data["scope_id"] = self.scope_id
            data["save_date"] = now
            data["update_date"] = now
            await conn_db('asset_site').insert_one(data)

    def build_report(self):
        info_list = [{"站点": s['site'], "标题": s.get('title', ''), "状态码": s.get('status', ''),
                      "页面长度": s.get('body_length', 0)} for s in self.site_info_list[:8]]
        self.html_report = f" <br/> 新发现站点 {len(self.site_info_list)} <br/>" + dict2table(info_list)
        self.dingding_markdown = f"  新发现站点 {len(self.site_info_list)}  " + dict2dingding_mark(info_list)


async def build_change_list(scope_id: str, task_id: str | None = None) -> list[dict]:
    """兼容旧入口：对比变化站点并写入 site 表。"""
    monitor = AssetSiteMonitor(scope_id)
    await monitor._init_scope_name()
    await monitor.build_change_list()
    if monitor.site_change_info_list and task_id:
        for si in monitor.site_change_info_list:
            si["task_id"] = task_id
        await conn_db('site').insert_many(monitor.site_change_info_list)
    return monitor.site_change_info_list
