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
        # 注意：exec_system 走 subprocess.run(list) 不做 shell 分词，
        # flag 与值必须拆成独立的 argv 元素，否则 massdns 报 unknown flag 且不产出结果。
        # concurrent 为 int，argv 必须是 str，故显式转换。
        command = [self.mass_dns_bin, "-q", "-r", self.dns_server, "-o", "S",
                   "-w", self.mass_dns_output_path, "-s", str(self.concurrent),
                   self.domain_gen_output_path, "--root"]
        logger.info(" ".join(command))
        await exec_system(command, timeout=5 * 24 * 60 * 60)

    def parse_mass_dns_output(self) -> list[dict]:
        output = []
        try:
            with open(self.mass_dns_output_path, "r", encoding="utf-8") as f:
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
        except FileNotFoundError:
            logger.warning(f"massdns 输出文件不存在: {self.mass_dns_output_path}")
        finally:
            self._delete_file()
        return output

    def _delete_file(self):
        for p in (self.domain_gen_output_path, self.mass_dns_output_path):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning(f"清理 massdns 临时文件失败 {p}: {e}")

    async def run(self) -> list[dict]:
        self.domain_write()
        try:
            await self.mass_dns()
            return self.parse_mass_dns_output()
        finally:
            self._delete_file()


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
