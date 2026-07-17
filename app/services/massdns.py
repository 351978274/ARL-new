"""massdns 域名爆破，移植自原 app/services/massdns.py。

外部二进制 massdns 通过 asyncio 线程池执行。
"""
from __future__ import annotations

import os

from ..config import Config
from ..logger import get_logger
from ..utils import exec_system, random_choices

logger = get_logger()


class MassDNS:
    def __init__(self, domains=None, mass_dns_bin=None, dns_server=None, tmp_dir=None,
                 wildcard_domain_ip=None, concurrent: int = 0):
        self.domains = domains or []
        self.tmp_dir = tmp_dir
        self.dns_server = dns_server
        self.domain_gen_output_path = os.path.join(tmp_dir, f"domain_gen_{random_choices()}")
        self.mass_dns_output_path = os.path.join(tmp_dir, f"mass_dns_{random_choices()}")
        self.mass_dns_bin = mass_dns_bin
        self.wildcard_domain_ip = wildcard_domain_ip or []
        self.concurrent = concurrent or 100

    def domain_write(self):
        cnt = 0
        with open(self.domain_gen_output_path, "w") as f:
            for domain in self.domains:
                domain = domain.strip()
                if domain:
                    f.write(domain + "\n")
                    cnt += 1
        logger.info(f"MassDNS dict {cnt}")

    async def mass_dns(self):
        command = [self.mass_dns_bin, "-q", f"-r {self.dns_server}", "-o S",
                   f"-w {self.mass_dns_output_path}", f"-s {self.concurrent}",
                   self.domain_gen_output_path, "--root"]
        logger.info(" ".join(command))
        await exec_system(command, timeout=5 * 24 * 60 * 60)

    def parse_mass_dns_output(self) -> list[dict]:
        output = []
        with open(self.mass_dns_output_path, "r+", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                data = line.split(" ")
                if len(data) != 3:
                    continue
                domain, _type, record = data
                record = record.strip().strip(".")
                if record in self.wildcard_domain_ip:
                    continue
                output.append({"domain": domain.strip("."), "type": _type, "record": record})
        self._delete_file()
        return output

    def _delete_file(self):
        for p in (self.domain_gen_output_path, self.mass_dns_output_path):
            try:
                os.unlink(p)
            except Exception as e:
                logger.warning(e)

    async def run(self) -> list[dict]:
        self.domain_write()
        await self.mass_dns()
        return self.parse_mass_dns_output()


async def mass_dns(based_domain: str, words, wildcard_domain_ip=None) -> list[dict]:
    """基于主域 + 字典生成子域并爆破。支持 {fuzz} 模板。"""
    wildcard_domain_ip = wildcard_domain_ip or []
    domains: list[str] = []
    is_fuzz_domain = "{fuzz}" in based_domain
    for word in words:
        word = word.strip()
        if word:
            if is_fuzz_domain:
                domains.append(based_domain.replace("{fuzz}", word))
            else:
                domains.append(f"{word}.{based_domain}")
    if not is_fuzz_domain:
        domains.append(based_domain)

    logger.info(f"start brute:{based_domain} words:{len(domains)} wildcard_record:{','.join(wildcard_domain_ip)}")
    mass = MassDNS(domains, mass_dns_bin=Config.MASSDNS_BIN, dns_server=Config.DNS_SERVER,
                   tmp_dir=Config.TMP_PATH, wildcard_domain_ip=wildcard_domain_ip,
                   concurrent=Config.DOMAIN_BRUTE_CONCURRENT)
    return await mass.run()
