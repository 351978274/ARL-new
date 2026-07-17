"""域名解析记录对象，对应 MongoDB domain 集合。"""
from __future__ import annotations

from .models import BaseInfo


class DomainInfo(BaseInfo):
    """与原 app/modules/domainInfo.py 字段一致。

    文档结构: {domain, record: [], type: "A"|"CNAME", ips: []}
    """

    def __init__(self, domain: str, record, type: str, ips):
        self.record_list = record
        self.domain = domain
        self.type = type  # "A" 或 "CNAME"
        self.ip_list = ips

    def __eq__(self, other):
        return isinstance(other, DomainInfo) and self.domain == other.domain

    def __hash__(self):
        return hash(self.domain)

    def _dump_json(self):
        return {
            "domain": self.domain,
            "record": self.record_list,
            "type": self.type,
            "ips": self.ip_list,
        }
