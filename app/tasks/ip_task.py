"""IP 任务流水线，移植自原 app/tasks/ip.py。

端口扫描 → 服务识别 → 证书获取 → 站点发现 → WebSiteFetch → npoc → PoC → 弱口令 → 统计/同步。
"""
from __future__ import annotations

import time

from ..config import Config
from ..database import conn_db
from ..logger import get_logger
from ..modules import ScanPortType, TaskStatus, load_port_list
from ..services import (run_risk_cruising, run_sniffer)
from ..services.fetch_cert import SSLCert
from ..services.base_update_task import BaseUpdateTask
from ..services.common_task import CommonTask, WebSiteFetch
from ..utils import curr_date, get_ip_asn, get_ip_city, get_ip_country, get_ip_type, not_in_black_ips

logger = get_logger()


async def ssl_cert(ip_info_list: list[dict]) -> dict:
    try:
        targets = []
        for ip_info in ip_info_list:
            for port_info in ip_info.get("port_info", []):
                if port_info["port_id"] == 80:
                    continue
                targets.append(f"{ip_info['ip']}:{port_info['port_id']}")
        f = SSLCert(targets)
        return await f.run()
    except Exception as e:
        logger.exception(e)
    return {}


class IPTask(CommonTask):
    def __init__(self, ip_target=None, task_id=None, options=None):
        super().__init__(task_id=task_id)
        self.ip_target = ip_target
        self.task_id = task_id
        self.options = options or {}
        self.ip_info_list: list[dict] = []
        self.ip_set: set[str] = set()
        self.site_list: list[str] = []
        self.cert_map: dict = {}
        self.service_info_list: list[dict] = []
        self.npoc_service_target_set: set[str] = set()
        self.task_tag = "task"
        self.scope_id = None
        self.task_name = None
        self.asset_ip_port_set: set = set()
        self.asset_ip_info_map: dict = {}
        self.base_update_task = BaseUpdateTask(task_id)

    async def set_asset_ip(self):
        raise NotImplementedError()

    async def async_ip_info(self):
        raise NotImplementedError()

    async def port_scan(self):
        scan_port_map = {
            "test": ScanPortType.TEST, "top100": ScanPortType.TOP100,
            "top1000": ScanPortType.TOP1000, "all": ScanPortType.ALL,
            "custom": self.options.get("port_custom")
                      or load_port_list(Config.PORT_DICT_CUSTOM, "80,443"),
        }
        option_scan_port_type = self.options.get("port_scan_type", "test")
        scan_port_option = {
            "ports": scan_port_map.get(option_scan_port_type, ScanPortType.TEST),
            "service_detect": self.options.get("service_detection", False),
            "os_detect": self.options.get("os_detection", False),
            "port_parallelism": self.options.get("port_parallelism", 32),
            "port_min_rate": self.options.get("port_min_rate", 64),
            "custom_host_timeout": None,
            "exclude_ports": self.options.get("exclude_ports", None),
        }
        if self.options.get("host_timeout_type") == "custom":
            scan_port_option["custom_host_timeout"] = self.options.get("host_timeout", 60 * 15)

        from ..services import port_scan
        targets = self.ip_target.split()
        ip_port_result = await port_scan(targets, **scan_port_option)
        self.ip_info_list.extend(ip_port_result)

        if self.task_tag == 'monitor':
            await self.set_asset_ip()

        for ip_info in ip_port_result:
            curr_ip = ip_info["ip"]
            self.ip_set.add(curr_ip)
            if not not_in_black_ips(curr_ip):
                continue
            ip_info["task_id"] = self.task_id
            ip_info["ip_type"] = get_ip_type(curr_ip)
            ip_info["geo_asn"] = {}
            ip_info["geo_city"] = {}
            ip_info["geo_country"] = {}
            if ip_info["ip_type"] == "PUBLIC":
                ip_info["geo_asn"] = get_ip_asn(curr_ip)
                ip_info["geo_city"] = get_ip_city(curr_ip)
                ip_info["geo_country"] = get_ip_country(curr_ip)
            if self.task_tag == 'task':
                await conn_db('ip').insert_one(ip_info)

        if self.task_tag == 'monitor':
            await self.async_ip_info()

    async def find_site(self):
        from ..services import check_http
        url_temp_list: list[str] = []
        for ip_info in self.ip_info_list:
            for port_info in ip_info.get("port_info", []):
                curr_ip = ip_info["ip"]
                port_id = port_info["port_id"]
                if port_id == 80:
                    url_temp_list.append(f"http://{curr_ip}")
                    continue
                if port_id == 443:
                    url_temp_list.append(f"https://{curr_ip}")
                    continue
                url_temp_list.append(f"http://{curr_ip}:{port_id}")
                url_temp_list.append(f"https://{curr_ip}:{port_id}")
        check_map = await check_http(url_temp_list)
        alive_site: list[str] = []
        for x in check_map:
            if x.startswith("https://"):
                alive_site.append(x)
            elif x.startswith("http://"):
                if "https://" + x[7:] not in check_map:
                    alive_site.append(x)
        self.site_list.extend(alive_site)

    async def ssl_cert_run(self):
        if self.options.get("port_scan"):
            self.cert_map = await ssl_cert(self.ip_info_list)
        else:
            self.cert_map = await ssl_cert(list(self.ip_set))
        for target, cert in self.cert_map.items():
            if ":" not in target:
                continue
            ip, port = target.split(":")[0], int(target.split(":")[1])
            await conn_db('cert').insert_one({
                "ip": ip, "port": port, "cert": cert, "task_id": self.task_id})

    async def save_service_info(self):
        self.service_info_list = []
        services_list: set[str] = set()
        for _data in self.ip_info_list:
            for _info in _data.get("port_info", []):
                svc = _info.get("service_name")
                if not svc:
                    continue
                entry = {'ip': _data.get("ip"), 'port_id': _info.get("port_id"),
                         'product': _info.get("product"), 'version': _info.get("version")}
                if svc not in services_list:
                    self.service_info_list.append({
                        "service_name": svc, "service_info": [entry], "task_id": self.task_id})
                    services_list.add(svc)
                else:
                    for si in self.service_info_list:
                        if si["service_name"] == svc:
                            si["service_info"].append(entry)
        if self.service_info_list:
            await conn_db('service').insert_many(self.service_info_list)

    async def npoc_service_detection(self):
        targets = []
        for ip_info in self.ip_info_list:
            for port_info in ip_info.get("port_info", []):
                if port_info["port_id"] in [80, 443, 843]:
                    continue
                targets.append(f"{ip_info['ip']}:{port_info['port_id']}")
        result = await run_sniffer(targets)
        for item in result:
            self.npoc_service_target_set.add(item["target"])
            item["task_id"] = self.task_id
            item["save_date"] = curr_date()
            await conn_db('npoc_service').insert_one(item)

    async def brute_config(self):
        plugins = [x["plugin_name"] for x in self.options.get("brute_config", []) if x.get("enable")]
        if not plugins:
            return
        targets = list(self.site_list) + list(self.npoc_service_target_set)
        result = await run_risk_cruising(targets=targets, plugins=plugins)
        for item in result:
            item["task_id"] = self.task_id
            item["save_date"] = curr_date()
            await conn_db('vuln').insert_one(item)

    async def run(self):
        base_update = self.base_update_task
        await base_update.update_task_field("start_time", curr_date())
        if self.options.get("port_scan"):
            await base_update.update_task_field("status", "port_scan")
            t1 = time.time()
            await self.port_scan()
            await base_update.update_services("port_scan", time.time() - t1)
        if self.options.get("service_detection"):
            await self.save_service_info()
        if self.options.get("ssl_cert"):
            await base_update.update_task_field("status", "ssl_cert")
            t1 = time.time()
            await self.ssl_cert_run()
            await base_update.update_services("ssl_cert", time.time() - t1)

        await base_update.update_task_field("status", "find_site")
        t1 = time.time()
        await self.find_site()
        await base_update.update_services("find_site", time.time() - t1)

        web_site_fetch = WebSiteFetch(task_id=self.task_id, sites=self.site_list, options=self.options)
        await web_site_fetch.run()

        if self.options.get("npoc_service_detection"):
            await base_update.update_task_field("status", "npoc_service_detection")
            t1 = time.time()
            await self.npoc_service_detection()
            await base_update.update_services("npoc_service_detection", time.time() - t1)
        if self.options.get("poc_config"):
            await base_update.update_task_field("status", "poc_run")
            t1 = time.time()
            await web_site_fetch.risk_cruising(self.npoc_service_target_set)
            await base_update.update_services("poc_run", time.time() - t1)
        if self.options.get("brute_config"):
            await base_update.update_task_field("status", "weak_brute")
            t1 = time.time()
            await self.brute_config()
            await base_update.update_services("weak_brute", time.time() - t1)

        await self.insert_finger_stat()
        await self.insert_cip_stat()
        await self.insert_task_stat()
        if self.task_tag == "task":
            await self.sync_asset_category()

        await base_update.update_task_field("status", TaskStatus.DONE)
        await base_update.update_task_field("end_time", curr_date())


async def ip_task(ip_target, task_id, options):
    d = IPTask(ip_target=ip_target, task_id=task_id, options=options)
    try:
        await d.run()
    except Exception as e:
        logger.exception(e)
        await d.base_update_task.update_task_field("status", "error")
