"""域名任务流水线（9 阶段），移植自原 app/tasks/domain.py。

阶段：domain_fetch(爆破/插件/arl/alt_dns) → search_engines → start_ip_fetch(端口/证书/服务)
→ start_site_fetch(站点识别) → start_find_vhost → start_poc_run(npoc/PoC/弱口令)
→ start_wih_domain_update → common_run(统计/同步)。
"""
from __future__ import annotations

import copy
import random
import time
from collections import Counter
from urllib.parse import urlparse

from ..config import Config
from ..database import conn_db
from ..dns_query_plugin.base import run_query_plugin
from ..helpers.domain import find_private_domain_by_task_id, find_public_ip_by_task_id
from ..logger import get_logger
from ..modules import (CollectSource, DomainDictType, DomainInfo, IPInfo, PortInfo,
                       ScanPortType, TaskStatus)
from ..services import (find_vhost, run_risk_cruising, run_sniffer)
from ..services import (build_domain_info, check_http, domain_site_update,
                        page_fetch, port_scan, probe_http, search_engines)
from ..services.base_update_task import BaseUpdateTask
from ..services.common_task import CommonTask, WebSiteFetch
from ..services.fetch_cert import SSLCert
from ..services.massdns import mass_dns
from ..services.alt_dns import alt_dns as _alt_dns
from ..services.resolver_domain import resolver_domain
from ..utils import (arl_domain, check_domain_black, curr_date, domain_parsed,
                     get_cdn_name_by_cname, get_cdn_name_by_ip, get_cname, get_fld, get_ip,
                     load_file, random_choices)

logger = get_logger()

MAX_MAP_COUNT = 35


# ============ 域名爆破 ============
class DomainBrute:
    def __init__(self, base_domain: str, word_file: str = Config.DOMAIN_DICT_2W, wildcard_domain_ip=None):
        self.base_domain = base_domain
        self.base_domain_scope = "." + base_domain.strip(".")
        self.dicts = load_file(word_file)
        self.brute_out: list[dict] = []
        self.resolver_map: dict = {}
        self.domain_info_list: list[DomainInfo] = []
        self.domain_cnames: list[str] = []
        self.brute_domain_map: dict = {}
        self.wildcard_domain_ip = wildcard_domain_ip or []

    async def _brute_domain(self):
        self.brute_out = await mass_dns(self.base_domain, self.dicts, self.wildcard_domain_ip)

    async def _resolver(self):
        domains: list[str] = []
        domain_cname_record: list[str] = []
        for x in self.brute_out:
            current_domain = x["domain"].lower()
            if not domain_parsed(current_domain):
                continue
            if len(current_domain) - len(self.base_domain) >= Config.DOMAIN_MAX_LEN:
                continue
            if check_domain_black(current_domain):
                continue
            if current_domain not in domains:
                domains.append(current_domain)
            self.brute_domain_map[current_domain] = x["record"]
            if x["type"] == 'CNAME':
                self.domain_cnames.append(current_domain)
                current_record_domain = x['record']
                if not domain_parsed(current_record_domain):
                    continue
                if check_domain_black(current_record_domain):
                    continue
                if current_record_domain not in domain_cname_record:
                    domain_cname_record.append(current_record_domain)
        for domain in domain_cname_record:
            if not domain.endswith(self.base_domain_scope):
                continue
            if domain not in domains:
                domains.append(domain)
        start_time = time.time()
        logger.info(f"start resolver {self.base_domain} {len(domains)}")
        self.resolver_map = await resolver_domain(domains)
        logger.info(f"end resolver {self.base_domain} result {len(self.resolver_map)} "
                    f"elapse {time.time()-start_time:.2f}s")

    async def run(self) -> list[DomainInfo]:
        start_time = time.time()
        logger.info(f"start brute {self.base_domain} with dict {len(self.dicts)}")
        await self._brute_domain()
        logger.info(f"end brute {self.base_domain}, result {len(self.brute_out)} "
                    f"elapse {time.time()-start_time:.2f}s")
        await self._resolver()
        for domain, ips in self.resolver_map.items():
            if not ips:
                continue
            if domain in self.domain_cnames:
                item = {"domain": domain, "type": "CNAME",
                        "record": [self.brute_domain_map[domain]], "ips": ips}
            else:
                item = {"domain": domain, "type": "A", "record": ips, "ips": ips}
            self.domain_info_list.append(DomainInfo(**item))
        self.domain_info_list = list(set(self.domain_info_list))
        return self.domain_info_list


async def domain_brute(base_domain, word_file=Config.DOMAIN_DICT_2W, wildcard_domain_ip=None):
    return await DomainBrute(base_domain, word_file, wildcard_domain_ip).run()


# ============ 端口扫描 ============
class ScanPort:
    def __init__(self, domain_info_list, option):
        self.domain_info_list = domain_info_list
        self.ipv4_map: dict[str, set] = {}
        self.ip_cdn_map: dict[str, str] = {}
        self.have_cdn_ip_list: list[str] = []
        self.skip_scan_cdn_ip = False
        if option is None:
            option = {"ports": ScanPortType.TEST, "service_detect": False, "os_detect": False,
                      "port_parallelism": 32, "port_min_rate": 64,
                      "custom_host_timeout": None, "exclude_ports": None}
        if 'skip_scan_cdn_ip' in option:
            self.skip_scan_cdn_ip = option["skip_scan_cdn_ip"]
            del option["skip_scan_cdn_ip"]
        self.option = option

    def get_cdn_name(self, ip, domain_info: DomainInfo) -> str:
        cdn_name = get_cdn_name_by_ip(ip)
        if cdn_name:
            return cdn_name
        if domain_info.type != "CNAME" or not domain_info.record_list:
            return ""
        cname = domain_info.record_list[0]
        cdn_name = get_cdn_name_by_cname(cname)
        if cdn_name:
            return cdn_name
        if len(domain_info.ip_list) >= 4:
            return "CDN"
        return ""

    async def run(self) -> list[IPInfo]:
        for info in self.domain_info_list:
            for ip in info.ip_list:
                self.ipv4_map.setdefault(ip, set()).add(info.domain)
                if ip not in self.ip_cdn_map:
                    cdn_name = self.get_cdn_name(ip, info)
                    self.ip_cdn_map[ip] = cdn_name
                    if cdn_name:
                        self.have_cdn_ip_list.append(ip)
        all_ipv4_list = list(self.ipv4_map.keys())
        if self.skip_scan_cdn_ip:
            all_ipv4_list = list(set(all_ipv4_list) - set(self.have_cdn_ip_list))
        start_time = time.time()
        logger.info(f"start port_scan {len(all_ipv4_list)}")
        ip_port_result: list[dict] = []
        if all_ipv4_list:
            ip_port_result = await port_scan(all_ipv4_list, **self.option)
            logger.info(f"end port_scan result {len(ip_port_result)} elapse {time.time()-start_time:.2f}s")
        ip_info_obj: list[IPInfo] = []
        for result in ip_port_result:
            curr_ip = result["ip"]
            result["domain"] = list(self.ipv4_map[curr_ip])
            result["cdn_name"] = self.ip_cdn_map.get(curr_ip, "")
            result["port_info"] = [PortInfo(**pi) for pi in result["port_info"]]
            ip_info_obj.append(IPInfo(**result))
        if self.skip_scan_cdn_ip:
            ip_info_obj.extend(self.build_fake_cdn_ip_info())
        return ip_info_obj

    def build_fake_cdn_ip_info(self) -> list[IPInfo]:
        ret: list[IPInfo] = []
        fake_80 = PortInfo(80, "http")
        fake_443 = PortInfo(443, "https")
        for ip, cdn_name in self.ip_cdn_map.items():
            if not cdn_name:
                continue
            ret.append(IPInfo(ip=ip, domain=list(self.ipv4_map[ip]),
                              port_info=copy.deepcopy([fake_80, fake_443]),
                              os_info={}, cdn_name=cdn_name))
        return ret


async def scan_port(domain_info_list, option=None) -> list[IPInfo]:
    return await ScanPort(domain_info_list, option).run()


# ============ 站点发现 ============
class FindSite:
    def __init__(self, ip_info_list: list[IPInfo]):
        self.ip_info_list = ip_info_list

    def _build(self) -> list[str]:
        url_temp_list: list[str] = []
        for info in self.ip_info_list:
            for domain in info.domain:
                for port_info in info.port_info_list:
                    port_id = port_info.port_id
                    if port_id == 80:
                        url_temp_list.append(f"http://{domain}")
                    elif port_id == 443:
                        url_temp_list.append(f"https://{domain}")
                    else:
                        url_temp_list.append(f"http://{domain}:{port_id}")
                        url_temp_list.append(f"https://{domain}:{port_id}")
        return url_temp_list

    async def run(self) -> list[str]:
        url_temp_list = set(self._build())
        start_time = time.time()
        check_map = await check_http(url_temp_list)
        alive_site: list[str] = []
        for x in check_map:
            if x.startswith("https://"):
                alive_site.append(x)
            elif x.startswith("http://"):
                if "https://" + x[7:] not in check_map:
                    alive_site.append(x)
        logger.info(f"end check_http result {len(alive_site)} elapse {time.time()-start_time:.2f}s")
        return alive_site


async def find_site(ip_info_list) -> list[str]:
    return await FindSite(ip_info_list).run()


# ============ AltDNS ============
class AltDNS:
    def __init__(self, domain_info_list, base_domain, wildcard_domain_ip=None):
        self.domain_info_list = domain_info_list
        self.base_domain = base_domain
        self.domains: list[str] = []
        self.subdomains: list[str] = []
        inner = "test adm admin api app beta demo dev front int internal intra ops pre pro prod qa sit staff stage test uat"
        self.dicts = inner.split()
        self.wildcard_domain_ip = wildcard_domain_ip or []

    def _fetch_domains(self):
        base_len = len(self.base_domain)
        for item in self.domain_info_list:
            if not item.domain.endswith("." + self.base_domain):
                continue
            if check_domain_black("a." + item.domain):
                continue
            self.domains.append(item.domain)
            subdomain = item.domain[:-(base_len + 1)]
            if "." in subdomain:
                self.subdomains.append(subdomain.split(".")[-1])
        random.shuffle(self.subdomains)
        most_cnt = 50
        if len(self.domains) < 1000:
            most_cnt = 30
            self.dicts.extend(self._load_dict())
        sub_dicts = list(dict(Counter(self.subdomains).most_common(most_cnt)).keys())
        self.dicts.extend(sub_dicts)
        self.dicts = list(set(self.dicts))

    def _load_dict(self):
        d: set[str] = set()
        for x in load_file(Config.altdns_dict_path):
            x = x.strip()
            if x:
                d.add(x)
        return list(d)

    async def run(self) -> list[dict]:
        t1 = time.time()
        self._fetch_domains()
        logger.info(f"start {self.base_domain} AltDNS {len(self.domains)} dict {len(self.dicts)}")
        out = await _alt_dns(self.domains, self.base_domain, self.dicts,
                             wildcard_domain_ip=self.wildcard_domain_ip)
        logger.info(f"end AltDNS result {len(out)} elapse {time.time()-t1:.2f}s")
        return out


async def alt_dns(domain_info_list, base_domain, wildcard_domain_ip=None):
    return await AltDNS(domain_info_list, base_domain, wildcard_domain_ip).run()


async def ssl_cert(ip_info_list, base_domain=None) -> dict:
    try:
        f = SSLCert(ip_info_list, base_domain)
        return await f.run()
    except Exception as e:
        logger.exception(e)
    return {}


def build_url_item(site: str, task_id: str, source: str) -> dict:
    item = {"site": site, "task_id": task_id, "source": source}
    dp = domain_parsed(site)
    if dp:
        item["fld"] = dp["fld"]
    return item


# ============ DomainTask 主流水线 ============
class DomainTask(CommonTask):
    def __init__(self, base_domain=None, task_id=None, options=None):
        super().__init__(task_id=task_id)
        self.base_domain = base_domain
        self.task_id = task_id
        self.options = options or {}
        self.domain_info_list: list[DomainInfo] = []
        self.ip_info_list: list[IPInfo] = []
        self.ip_set: set[str] = set()
        self.site_list: list[str] = []
        self.record_map: dict = {}
        self.ipv4_map: dict = {}
        self.cert_map: dict = {}
        self.service_info_list: list[dict] = []
        self.task_tag = "task"
        self._not_found_domain_ips = None
        self._domain_dict_size = None
        self._domain_word_file = None
        self.npoc_service_target_set: set[str] = set()
        self.web_site_fetch: WebSiteFetch | None = None
        self.wih_domain_set: set[str] = set()

        scan_port_map = {"test": ScanPortType.TEST, "top100": ScanPortType.TOP100,
                         "top1000": ScanPortType.TOP1000, "all": ScanPortType.ALL,
                         "custom": self.options.get("port_custom", "80,443")}
        option_scan_port_type = self.options.get("port_scan_type", "test")
        self.scan_port_option = {
            "ports": scan_port_map.get(option_scan_port_type, ScanPortType.TEST),
            "service_detect": self.options.get("service_detection", False),
            "os_detect": self.options.get("os_detection", False),
            "skip_scan_cdn_ip": self.options.get("skip_scan_cdn_ip", False),
            "port_parallelism": self.options.get("port_parallelism", 32),
            "port_min_rate": self.options.get("port_min_rate", 64),
            "custom_host_timeout": None,
            "exclude_ports": self.options.get("exclude_ports", None),
        }
        if self.options.get("host_timeout_type") == "custom":
            self.scan_port_option["custom_host_timeout"] = self.options.get("host_timeout", 60 * 15)
        self.base_update_task = BaseUpdateTask(task_id)

    @property
    def domain_word_file(self) -> str:
        if self._domain_word_file is None:
            brute_dict_map = {"test": DomainDictType.TEST, "big": DomainDictType.BIG}
            self._domain_word_file = brute_dict_map.get(
                self.options.get("domain_brute_type", "test"), DomainDictType.TEST)
        return self._domain_word_file

    @property
    async def not_found_domain_ips(self) -> list[str]:
        if self._not_found_domain_ips is None:
            fake_domain = "at" + random_choices(4) + "." + self.base_domain
            ips = await get_ip(fake_domain, log_flag=False)
            if ips:
                ips.extend(await get_cname(fake_domain, log_flag=False))
            if ips:
                logger.info(f"not_found_domain_ips {fake_domain} {ips}")
            self._not_found_domain_ips = ips
        return self._not_found_domain_ips

    async def save_domain_info_list(self, domain_info_list, source=CollectSource.DOMAIN_BRUTE):
        for obj in domain_info_list:
            info = obj.dump_json(flag=False)
            info["task_id"] = self.task_id
            info["source"] = source
            dp = domain_parsed(info["domain"])
            if dp:
                info["fld"] = dp["fld"]
            await conn_db('domain').insert_one(info)

    async def clear_domain_info_by_record(self, domain_info_list):
        new_list = []
        for info in domain_info_list:
            if not info.record_list:
                continue
            record = info.record_list[0]
            ip = info.ip_list[0]
            if ip in await self.not_found_domain_ips:
                continue
            cnt = self.record_map.get(record, 0) + 1
            self.record_map[record] = cnt
            if cnt > MAX_MAP_COUNT:
                continue
            new_list.append(info)
        return new_list

    async def build_domain_info(self, domains) -> list[DomainInfo]:
        fake_list: list[DomainInfo] = []
        domains_set: set[str] = set()
        for item in domains:
            domain = item["domain"] if isinstance(item, dict) else item
            domain = domain.lower().strip()
            if domain in domains_set:
                continue
            domains_set.add(domain)
            if check_domain_black(domain):
                continue
            fake_info = DomainInfo(domain=domain, type="CNAME", record=[], ips=[])
            if fake_info not in self.domain_info_list:
                fake_list.append(fake_info)
        if self.task_tag == "monitor":
            return fake_list
        return await build_domain_info(fake_list)

    async def domain_brute(self):
        wildcard = await self.not_found_domain_ips
        domain_info_list = await domain_brute(self.base_domain, self.domain_word_file, wildcard)
        domain_info_list = await self.clear_domain_info_by_record(domain_info_list)
        if self.task_tag == "task":
            await self.save_domain_info_list(domain_info_list, CollectSource.DOMAIN_BRUTE)
        self.domain_info_list.extend(domain_info_list)

    async def arl_search(self):
        arl_t1 = time.time()
        logger.info(f"start arl fetch {self.base_domain}")
        arl_all_domains = await arl_domain(self.base_domain)
        domain_info_list = await self.build_domain_info(arl_all_domains)
        if self.task_tag == "task":
            domain_info_list = await self.clear_domain_info_by_record(domain_info_list)
            await self.save_domain_info_list(domain_info_list, CollectSource.ARL)
        self.domain_info_list.extend(domain_info_list)
        logger.info(f"end arl fetch {self.base_domain} {len(domain_info_list)} "
                    f"elapse {time.time()-arl_t1:.2f}s")

    async def dns_query_plugin(self):
        logger.info(f"start run dns_query_plugin {self.base_domain}")
        results = await run_query_plugin(self.base_domain, [])
        sources_map: dict[str, list[str]] = {}
        for result in results:
            sources_map.setdefault(result["source"], []).append(result["domain"])
        cnt = 0
        for source, source_domains in sources_map.items():
            if not source_domains:
                continue
            logger.info(f"start build domain info, source:{source}")
            domain_info_list = await self.build_domain_info(source_domains)
            if self.task_tag == "task":
                domain_info_list = await self.clear_domain_info_by_record(domain_info_list)
                await self.save_domain_info_list(domain_info_list, source)
            cnt += len(domain_info_list)
            self.domain_info_list.extend(domain_info_list)
        logger.info(f"end run dns_query_plugin {self.base_domain}, result {len(results)}, real {cnt}")

    async def alt_dns(self):
        if self.task_tag == "monitor" and len(self.domain_info_list) >= 800:
            logger.info(f"skip alt_dns on monitor {self.base_domain}")
            return
        wildcard = await self.not_found_domain_ips
        if len(self.domain_info_list) > 300 and len(wildcard) > 0:
            logger.warning(f"{self.base_domain} 域名泛解析, 子域名 {len(self.domain_info_list)} >300, 不进行 alt_dns")
            return
        alt_dns_out = await alt_dns(self.domain_info_list, self.base_domain, wildcard)
        if not alt_dns_out:
            return
        alt_domain_info_list = await self.build_domain_info(alt_dns_out)
        if self.task_tag == "task":
            alt_domain_info_list = await self.clear_domain_info_by_record(alt_domain_info_list)
            logger.info(f"alt_dns real result:{len(alt_domain_info_list)}")
            if alt_domain_info_list:
                await self.save_domain_info_list(alt_domain_info_list, CollectSource.ALTDNS)
        self.domain_info_list.extend(alt_domain_info_list)

    async def build_single_domain_info(self, domain) -> DomainInfo | None:
        cname = await get_cname(domain)
        _type = "CNAME" if cname else "A"
        ips = await get_ip(domain)
        if not ips:
            return None
        record = cname if _type == "CNAME" else ips
        return DomainInfo(domain=domain, type=_type, record=record, ips=ips)

    async def domain_fetch(self):
        if self.options.get("domain_brute"):
            await self.update_task_field("status", "domain_brute")
            t1 = time.time()
            await self.domain_brute()
            await self.update_services("domain_brute", time.time() - t1)
        else:
            di = await self.build_single_domain_info(self.base_domain)
            if di:
                self.domain_info_list.append(di)
                await self.save_domain_info_list([di])
        if "{fuzz}" in self.base_domain:
            return
        if self.options.get("dns_query_plugin"):
            await self.update_task_field("status", "dns_query_plugin")
            t1 = time.time()
            await self.dns_query_plugin()
            await self.update_services("dns_query_plugin", time.time() - t1)
        if self.options.get("arl_search"):
            await self.update_task_field("status", "arl_search")
            t1 = time.time()
            await self.arl_search()
            await self.update_services("arl_search", time.time() - t1)
        if self.options.get("alt_dns"):
            await self.update_task_field("status", "alt_dns")
            t1 = time.time()
            await self.alt_dns()
            await self.update_services("alt_dns", time.time() - t1)

    async def update_services(self, service_name, elapsed):
        await self.base_update_task.update_services(service_name, elapsed)

    async def update_task_field(self, field=None, value=None):
        await self.base_update_task.update_task_field(field, value)

    async def gen_ipv4_map(self):
        ipv4_map: dict[str, set] = {}
        for info in self.domain_info_list:
            for ip in info.ip_list:
                ipv4_map.setdefault(ip, set()).add(info.domain)
                self.ip_set.add(ip)
        self.ipv4_map = ipv4_map

    async def port_scan(self):
        ip_info_list = await scan_port(self.domain_info_list, self.scan_port_option)
        for ip_info_obj in ip_info_list:
            ip_info = ip_info_obj.dump_json(flag=False)
            ip_info["task_id"] = self.task_id
            await conn_db('ip').insert_one(ip_info)
        self.ip_info_list.extend(ip_info_list)

    async def save_ip_info(self):
        fake_list = []
        for ip in self.ipv4_map:
            info_obj = IPInfo(ip=ip, domain=list(self.ipv4_map[ip]), port_info=[], os_info={},
                              cdn_name=get_cdn_name_by_ip(ip))
            if info_obj not in self.ip_info_list:
                fake_list.append(info_obj)
        for obj in fake_list:
            ip_info = obj.dump_json(flag=False)
            ip_info["task_id"] = self.task_id
            await conn_db('ip').insert_one(ip_info)

    async def save_service_info(self):
        self.service_info_list = []
        services_list: set[str] = set()
        for _data in self.ip_info_list:
            for _info in _data.port_info_list:
                if not _info.service_name:
                    continue
                entry = {'ip': _data.ip, 'port_id': _info.port_id,
                         'product': _info.product, 'version': _info.version}
                if _info.service_name not in services_list:
                    self.service_info_list.append({"service_name": _info.service_name,
                                                   "service_info": [entry], "task_id": self.task_id})
                    services_list.add(_info.service_name)
                else:
                    for si in self.service_info_list:
                        if si["service_name"] == _info.service_name:
                            si["service_info"].append(entry)
        if self.service_info_list:
            await conn_db('service').insert_many(self.service_info_list)

    async def ssl_cert(self):
        if self.options.get("port_scan"):
            self.cert_map = await ssl_cert(self.ip_info_list, self.base_domain)
        else:
            self.cert_map = await ssl_cert(list(self.ip_set), self.base_domain)
        for target, cert in self.cert_map.items():
            if ":" not in target:
                continue
            ip, port = target.split(":")[0], int(target.split(":")[1])
            await conn_db('cert').insert_one(
                {"ip": ip, "port": port, "cert": cert, "task_id": self.task_id})

    async def start_ip_fetch(self):
        await self.gen_ipv4_map()
        if self.options.get("port_scan"):
            await self.update_task_field("status", "port_scan")
            t1 = time.time()
            await self.port_scan()
            await self.update_services("port_scan", time.time() - t1)
        if self.options.get("ssl_cert"):
            await self.update_task_field("status", "ssl_cert")
            t1 = time.time()
            await self.ssl_cert()
            await self.update_services("ssl_cert", time.time() - t1)
        if self.options.get("service_detection"):
            await self.save_service_info()
        await self.save_ip_info()

    async def find_site_run(self):
        if self.options.get("port_scan"):
            sites = await find_site(self.ip_info_list)
        else:
            sites = await probe_http(self.domain_info_list)
        self.site_list.extend(sites)

    async def start_site_fetch(self):
        await self.update_task_field("status", "find_site")
        t1 = time.time()
        await self.find_site_run()
        await self.update_services("find_site", time.time() - t1)
        self.domain_info_list = []  # 释放内存
        web_site_fetch = WebSiteFetch(task_id=self.task_id, sites=self.site_list,
                                      options=self.options, scope_domain=[self.base_domain])
        await web_site_fetch.run()
        self.wih_domain_set = web_site_fetch.wih_domain_set
        self.web_site_fetch = web_site_fetch

    async def npoc_service_detection(self):
        targets = []
        for ip_info in self.ip_info_list:
            for port_info in ip_info.port_info_list:
                if port_info.port_id in [80, 443, 843]:
                    continue
                targets.append(f"{ip_info.ip}:{port_info.port_id}")
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

    async def start_poc_run(self):
        if self.options.get("npoc_service_detection"):
            await self.update_task_field("status", "npoc_service_detection")
            t1 = time.time()
            await self.npoc_service_detection()
            await self.update_services("npoc_service_detection", time.time() - t1)
        if self.options.get("poc_config"):
            await self.update_task_field("status", "poc_run")
            t1 = time.time()
            await self.web_site_fetch.risk_cruising(self.npoc_service_target_set)
            await self.update_services("poc_run", time.time() - t1)
        if self.options.get("brute_config"):
            await self.update_task_field("status", "weak_brute")
            t1 = time.time()
            await self.brute_config()
            await self.update_services("weak_brute", time.time() - t1)

    async def find_vhost_vuln(self):
        domains = await find_private_domain_by_task_id(self.task_id)
        if not domains:
            return
        ips = await find_public_ip_by_task_id(self.task_id)
        results = await find_vhost(ips=ips, domains=domains)
        for result in results:
            await conn_db('vuln').insert_one({
                "plg_name": "FindVhost", "plg_type": "scan", "vul_name": "发现Host碰撞漏洞",
                "app_name": "web", "target": result["url"],
                "verify_data": f"{result['domain']}-{result['title']}-{result['status_code']}-{result['body_length']}",
                "verify_obj": result, "task_id": self.task_id, "save_date": curr_date(),
            })

    async def start_find_vhost(self):
        if self.options.get("findvhost"):
            await self.update_task_field("status", "findvhost")
            t1 = time.time()
            await self.find_vhost_vuln()
            await self.update_services("findvhost", time.time() - t1)

    async def search_engines_run(self):
        if not self.options.get("search_engines") or "{fuzz}" in self.base_domain:
            return
        await self.update_task_field("status", "search_engines")
        search_engines_urls = await search_engines(self.base_domain)
        t1 = time.time()
        urls: set[str] = set()
        domains: set[str] = set()
        for url in search_engines_urls:
            parse = urlparse(url)
            netloc_domain = parse.netloc.split(":")[0]
            if netloc_domain.endswith("." + self.base_domain) or self.base_domain == netloc_domain:
                domains.add(netloc_domain)
            else:
                continue
            if parse.path in ("/", ""):
                continue
            urls.add(url)
        domain_info_list: list[DomainInfo] = []
        if domains:
            domain_info_list = await self.build_domain_info(domains)
            if self.task_tag == "task":
                domain_info_list = await self.clear_domain_info_by_record(domain_info_list)
                await self.save_domain_info_list(domain_info_list, CollectSource.SEARCHENGINE)
            self.domain_info_list.extend(domain_info_list)
        await self.update_services("search_engines", time.time() - t1)
        logger.info(f"search_engines {self.base_domain}, domain:{len(domain_info_list)} url:{len(urls)}")
        if urls:
            page_map = await page_fetch(urls)
            for url, item in page_map.items():
                full_item = build_url_item(url, self.task_id, CollectSource.SEARCHENGINE)
                full_item.update(item)
                await conn_db('url').insert_one(full_item)

    async def start_wih_domain_update(self):
        if self.wih_domain_set:
            await domain_site_update(self.task_id, list(self.wih_domain_set), "wih")

    async def run(self):
        await self.update_task_field("start_time", curr_date())
        await self.domain_fetch()
        await self.search_engines_run()
        await self.start_ip_fetch()
        await self.start_site_fetch()
        await self.start_find_vhost()
        await self.start_poc_run()
        await self.start_wih_domain_update()
        await self.common_run()
        await self.update_task_field("status", TaskStatus.DONE)
        await self.update_task_field("end_time", curr_date())


async def domain_task(base_domain, task_id, options):
    d = DomainTask(base_domain=base_domain, task_id=task_id, options=options)
    try:
        await d.run()
    except Exception as e:
        logger.exception(e)
        await d.update_task_field("status", TaskStatus.ERROR)
        await d.update_task_field("end_time", curr_date())
