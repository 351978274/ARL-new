"""页面信息对象，对应 MongoDB url 集合。"""
from __future__ import annotations

from .models import BaseInfo


class PageInfo(BaseInfo):
    """文档结构: {title, url, content_length, status_code}"""

    def __init__(self, title: str, url: str, content_length: int, status_code: int):
        self.title = title
        self.url = url
        self.content_length = content_length
        self.status_code = status_code

    def __eq__(self, other):
        return isinstance(other, PageInfo) and self.url == other.url

    def __hash__(self):
        return hash(self.url)

    def _dump_json(self):
        return {
            "title": self.title,
            "url": self.url,
            "content_length": self.content_length,
            "status_code": self.status_code,
        }
