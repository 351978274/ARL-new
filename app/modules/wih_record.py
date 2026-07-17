"""WebInfoHunter 记录对象，对应 MongoDB wih 集合。"""
from __future__ import annotations


class WihRecord:
    """WebInfoHunter 记录。fnv_hash 用于去重。

    文档结构: {record_type, content, site, source, fnv_hash: str}
    """

    def __init__(self, record_type: str, content: str, source: str, site: str, fnv_hash: int):
        self.recordType = record_type
        self.content = content
        self.source = source
        self.site = site
        self.fnv_hash = fnv_hash

    def __str__(self):
        return f"{self.recordType} {self.content} {self.source} {self.site}"

    __repr__ = __str__

    def __eq__(self, other):
        return isinstance(other, WihRecord) and self.fnv_hash == other.fnv_hash

    def __hash__(self):
        return self.fnv_hash

    def dump_json(self):
        return {
            "record_type": self.recordType,
            "content": self.content,
            "site": self.site,
            "source": self.source,
            "fnv_hash": str(self.fnv_hash),
        }
