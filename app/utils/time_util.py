"""时间工具，移植自原 app/utils/time.py。"""
from __future__ import annotations

import datetime
import time


def time2date(secs: float | int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(secs))


def time2hms(secs: int) -> str:
    return str(datetime.timedelta(seconds=secs))


def date2time(date: str) -> float:
    return time.mktime(time.strptime(date, '%Y-%m-%d %H:%M:%S'))


def curr_date() -> str:
    return time2date(time.time())


def curr_date_obj() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


def parse_datetime(s: str) -> datetime.datetime:
    """解析 ISO8601 时间字符串（GitHub 返回）。"""
    if len(s) == 24:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.000Z")
    elif len(s) >= 25:
        return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + (
            1 if s[19] == "-" else -1
        ) * datetime.timedelta(hours=int(s[20:22]), minutes=int(s[23:25]))
    else:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(hours=8)
