"""AltDNS 域名智能生成 + 爆破，移植自原 app/services/altDNS.py。

DnsGen 域名排列生成器（移植自 dnsgen），AltDNS 调用 massdns 爆破。
"""
from __future__ import annotations

import re
from collections import Counter

import tld

from ..config import Config
from ..logger import get_logger
from .massdns import MassDNS

logger = get_logger()
NUM_COUNT = 4


class DnsGen:
    """域名排列生成器（移植自 dnsgen）。"""

    def __init__(self, subdomains, words, base_domain=None):
        self.subdomains = subdomains
        self.base_domain = base_domain
        self.words = words

    def partiate_domain(self, domain):
        if self.base_domain:
            subdomain = re.sub(re.escape("." + self.base_domain) + "$", '', domain)
            return subdomain.split(".") + [self.base_domain]
        ext = tld.get_tld(domain.lower(), fail_silently=True, as_object=True, fix_protocol=True)
        base_domain = f"{ext.domain}.{ext.suffix}"
        parts = ext.subdomain.split('.') + [base_domain]
        return [p for p in parts if p]

    def insert_word_every_index(self, parts):
        domains = []
        for w in self.words:
            for i in range(len(parts)):
                if i + 1 == len(parts):
                    break
                if w in parts[:-1]:
                    continue
                tmp_parts = parts[:-1]
                tmp_parts.insert(i, w)
                domains.append(f"{'.'.join(tmp_parts)}.{parts[-1]}")
        return domains

    def insert_num_every_index(self, parts):
        domains = []
        for num in range(NUM_COUNT):
            for i in range(len(parts[:-1])):
                if num == 0:
                    continue
                tmp_parts = parts[:-1]
                tmp_parts[i] = f"{tmp_parts[i]}{num}"
                domains.append(f"{'.'.join(tmp_parts)}.{parts[-1]}")
        return domains

    def prepend_word_every_index(self, parts):
        domains = []
        for w in self.words:
            for i in range(len(parts[:-1])):
                if w in parts[:-1]:
                    continue
                tmp_parts = parts[:-1]
                tmp_parts[i] = f"{w}{tmp_parts[i]}"
                domains.append(f"{'.'.join(tmp_parts)}.{parts[-1]}")
                tmp_parts = parts[:-1]
                tmp_parts[i] = f"{w}-{tmp_parts[i]}"
                domains.append(f"{'.'.join(tmp_parts)}.{parts[-1]}")
        return domains

    def append_word_every_index(self, parts):
        domains = []
        for w in self.words:
            for i in range(len(parts[:-1])):
                if w in parts[:-1]:
                    continue
                tmp_parts = parts[:-1]
                tmp_parts[i] = f"{tmp_parts[i]}{w}"
                domains.append(f"{'.'.join(tmp_parts)}.{parts[-1]}")
                tmp_parts = parts[:-1]
                tmp_parts[i] = f"{tmp_parts[i]}-{w}"
                domains.append(f"{'.'.join(tmp_parts)}.{parts[-1]}")
        return domains

    def replace_word_with_word(self, parts):
        domains = []
        for w in self.words:
            if len(w) <= 3:
                continue
            if w in '.'.join(parts[:-1]):
                for w_alt in self.words:
                    if w == w_alt:
                        continue
                    if w in parts[:-1]:
                        continue
                    domains.append(f"{'.'.join(parts[:-1]).replace(w, w_alt)}.{parts[-1]}")
        return domains

    def run(self):
        for domain in set(self.subdomains):
            parts = self.partiate_domain(domain)
            permutations = []
            permutations += self.insert_word_every_index(parts)
            permutations += self.insert_num_every_index(parts)
            permutations += self.prepend_word_every_index(parts)
            permutations += self.append_word_every_index(parts)
            permutations += self.replace_word_with_word(parts)
            for perm in permutations:
                yield perm


class AltDNS:
    def __init__(self, subdomains, base_domain, words, wildcard_domain_ip=None):
        self.subdomains = subdomains
        self.base_domain = base_domain
        self.words = words
        self.wildcard_domain_ip = wildcard_domain_ip or []

    async def run(self) -> list[dict]:
        domains = list(DnsGen(set(self.subdomains), self.words, base_domain=self.base_domain).run())
        logger.info(f"start AltDNS:{self.base_domain} wildcard_record:{','.join(self.wildcard_domain_ip)}")
        mass = MassDNS(domains, mass_dns_bin=Config.MASSDNS_BIN, dns_server=Config.DNS_SERVER,
                       tmp_dir=Config.TMP_PATH, wildcard_domain_ip=self.wildcard_domain_ip,
                       concurrent=Config.ALT_DNS_CONCURRENT)
        return await mass.run()


async def alt_dns(subdomains, base_domain=None, words=None, wildcard_domain_ip=None) -> list[dict]:
    """组合生成域名爆破，过滤泛解析（单 record 出现 >=15 次）。"""
    if not subdomains:
        return []
    raw_domains_info = await AltDNS(subdomains, base_domain, words=words,
                                    wildcard_domain_ip=wildcard_domain_ip).run()
    records = [x['record'] for x in raw_domains_info]
    records_count = Counter(records)
    return [info for info in raw_domains_info if records_count[info['record']] < 15]
