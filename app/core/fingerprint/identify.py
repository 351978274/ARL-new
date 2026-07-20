"""单个指纹规则对象 + DB 规则缓存，移植自原 app/services/fingerprint.py + fingerprint_cache.py。"""
from __future__ import annotations

from . import expr


class FingerPrint:
    """一条 human_rule 指纹规则，可对 variables 求值。"""

    def __init__(self, app_name: str, human_rule: str):
        self.app_name = app_name
        self.human_rule = human_rule
        self._parsed = None

    @property
    def parsed(self):
        if self._parsed is None:
            self._parsed = expr.parse_expression(self.human_rule)
        return self._parsed

    def identify(self, variables: dict) -> bool:
        return expr.evaluate_expression(self.parsed, variables)


class FingerPrintCache:
    """MongoDB 指纹规则缓存（异步刷新）。"""

    def __init__(self):
        self.cache: list[FingerPrint] | None = None

    def is_cache_valid(self) -> bool:
        return self.cache is not None

    async def get_data(self) -> list[FingerPrint]:
        if not self.is_cache_valid():
            await self.update_cache()
        return self.cache  # type: ignore[return-value]

    async def update_cache(self):
        from ...database import conn_db
        items = await conn_db('fingerprint').find({}).to_list(length=None)
        self.cache = [FingerPrint(r['name'], r['human_rule']) for r in items]


finger_db_cache = FingerPrintCache()


async def finger_db_identify(variables: dict) -> list[str]:
    """用 DB 规则匹配，返回命中应用名列表。"""
    from ...logger import get_logger
    logger = get_logger()
    finger_list = await finger_db_cache.get_data()
    finger_name_list: list[str] = []
    for finger in finger_list:
        try:
            if finger.identify(variables):
                finger_name_list.append(finger.app_name)
        except Exception as e:
            logger.warning(f"error on identify {finger.app_name} {e}")
    return finger_name_list


async def have_human_rule_from_db(rule: str) -> bool:
    from ...database import conn_db
    return bool(await conn_db('fingerprint').find_one({"human_rule": rule}))
