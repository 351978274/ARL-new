"""端口扫描（nmap），移植自原 app/services/portScan.py。

python-nmap 为同步库，故用 asyncio.to_thread 包裹执行。
"""
from __future__ import annotations

import asyncio

from ..config import Config
from ..logger import get_logger
from ..utils import is_valid_exclude_ports, not_in_black_ips
from ..utils.nmap import PortScanner

logger = get_logger()


class PortScan:
    def __init__(self, targets, ports: str | None = None, service_detect: bool = False,
                 os_detect: bool = False, port_parallelism: int | None = None,
                 port_min_rate: int | None = None, custom_host_timeout: int | None = None,
                 exclude_ports: str | None = None):
        self.targets = " ".join(targets)
        self.ports = ports
        self.max_host_group = 32
        self.alive_port = ("22,80,443,843,3389,8007-8011,8443,9090,8080-8091,8093,8099,"
                           "5000-5004,2222,3306,1433,21,25")
        self.nmap_arguments = "-sT -n --open"
        self.max_retries = 3
        self.host_timeout = 60 * 5
        self.parallelism = port_parallelism if port_parallelism else 32
        self.min_rate = port_min_rate if port_min_rate else 64
        self.exclude_ports = exclude_ports

        if service_detect:
            self.host_timeout += 60 * 5
            self.nmap_arguments += " -sV"
        if os_detect:
            self.host_timeout += 60 * 4
            self.nmap_arguments += " -O"

        if len(self.ports.split(",")) > 60:
            self.nmap_arguments += f" -PE -PS{self.alive_port}"
            self.max_retries = 2
        else:
            if self.ports != "0-65535":
                self.nmap_arguments += " -Pn"

        if self.ports == "0-65535":
            self.max_host_group = 2
            self.min_rate = max(self.min_rate, 800)
            self.parallelism = max(self.parallelism, 128)
            self.nmap_arguments += f" -PE -PS{self.alive_port}"
            self.host_timeout += 60 * 5
            self.max_retries = 2

        self.nmap_arguments += " --max-rtt-timeout 800ms"
        self.nmap_arguments += f" --min-rate {self.min_rate}"
        self.nmap_arguments += " --script-timeout 6s"
        self.nmap_arguments += f" --max-hostgroup {self.max_host_group}"

        if custom_host_timeout is not None and int(custom_host_timeout) > 0:
            self.host_timeout = custom_host_timeout
        self.nmap_arguments += f" --host-timeout {self.host_timeout}s"
        self.nmap_arguments += f" --min-parallelism {self.parallelism}"
        self.nmap_arguments += f" --max-retries {self.max_retries}"

        if self.exclude_ports and self.exclude_ports != "" and is_valid_exclude_ports(self.exclude_ports):
            self.nmap_arguments += f" --exclude-ports {self.exclude_ports}"

    def _scan_sync(self) -> list[dict]:
        logger.info(f"nmap target {self.targets[:20]} ports {self.ports[:20]} args {self.nmap_arguments}")
        nm = PortScanner()
        nm.scan(hosts=self.targets, ports=self.ports, arguments=self.nmap_arguments)
        ip_info_list = []
        for host in nm.all_hosts():
            port_info_list = []
            for proto in nm[host].all_protocols():
                port_len = len(nm[host][proto])
                for port in nm[host][proto]:
                    if port_len > 600 and port not in [80, 443]:
                        continue
                    p = nm[host][proto][port]
                    port_info_list.append({
                        "port_id": port,
                        "service_name": p["name"],
                        "version": p["version"],
                        "product": p["product"],
                        "protocol": proto,
                    })
            osmatch_list = nm[host].get("osmatch", [])
            ip_info_list.append({
                "ip": host,
                "port_info": port_info_list,
                "os_info": self.os_match_by_accuracy(osmatch_list),
            })
        return ip_info_list

    def os_match_by_accuracy(self, os_match_list):
        for os_match in os_match_list:
            accuracy = os_match.get('accuracy', '0')
            if int(accuracy) > 90:
                return os_match
        return {}

    async def run(self) -> list[dict]:
        return await asyncio.to_thread(self._scan_sync)


async def port_scan(targets, ports: str = Config.TOP_10, service_detect: bool = False,
                    os_detect: bool = False, port_parallelism: int = 32, port_min_rate: int = 64,
                    custom_host_timeout: int | None = None, exclude_ports: str | None = None) -> list[dict]:
    targets = list({t for t in targets if not_in_black_ips(t)})
    ps = PortScan(targets=targets, ports=ports, service_detect=service_detect, os_detect=os_detect,
                  port_parallelism=port_parallelism, port_min_rate=port_min_rate,
                  custom_host_timeout=custom_host_timeout, exclude_ports=exclude_ports)
    return await ps.run()
