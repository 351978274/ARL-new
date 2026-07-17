"""cron 表达式校验。

原项目用 python-crontab 的 CronSlices，但该 API 不稳定。
改用 croniter（更标准、活跃维护），支持 5 段标准 cron。
"""
from __future__ import annotations

from croniter import croniter


def check_cron(cron_str: str) -> bool:
    """校验 cron 表达式合法性（5 段：分 时 日 月 周）。"""
    if not cron_str or not isinstance(cron_str, str):
        return False
    try:
        return croniter.is_valid(cron_str.strip())
    except Exception:
        return False


def check_cron_interval(interval: int, min_interval: int = 21600) -> bool:
    """校验监控间隔（秒），默认最小 6 小时。"""
    try:
        return int(interval) >= min_interval
    except Exception:
        return False
