"""数据模型（pydantic），移植自原 app/modules/。

字段结构与原始 _dump_json() 输出保持一致，保证 MongoDB 文档可互通。
geo_asn/geo_city/geo_country/ip_type 仍采用惰性计算（通过 utils.ip_util 模块）。
"""
from __future__ import annotations

from typing import Any


class BaseInfo:
    """所有资产信息对象的基类，保留原 dump_json 语义。"""

    def __str__(self):
        return self.dump_json()

    __repr__ = __str__

    def dump_json(self, flag: bool = False) -> Any:
        """flag=True 返回 json 字符串，flag=False 返回 dict（默认 dict，便于 motor 写入）。"""
        import json
        item = self._dump_json()
        if flag:
            return json.dumps(item, ensure_ascii=False, default=str)
        return item

    def _dump_json(self) -> dict:
        raise NotImplementedError
