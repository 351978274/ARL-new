"""modules 包：数据模型 + 枚举 + 错误码。

保持与原 ARL 调用方式兼容：
    from app.modules import DomainInfo, IPInfo, PortInfo, PageInfo, WihRecord
    from app.modules import TaskStatus, TaskTag, TaskType, TaskAction, ...
    from app.modules import error_map, ErrorMsg, build_ret
"""
from __future__ import annotations

from .enums import (
    AssetScopeType,
    CollectSource,
    DomainDictType,
    PoCCategory,
    ScanPortType,
    SchedulerStatus,
    SiteAutoTag,
    TaskAction,
    TaskQueue,
    TaskScheduleStatus,
    TaskSyncStatus,
    TaskStatus,
    TaskTag,
    TaskType,
    WebSiteFetchOption,
    WebSiteFetchStatus,
    # 兼容别名
    CeleryAction,
    CeleryRoutingKey,
)
from .error_map import ErrorMsg, build_ret, error_map
from .models import BaseInfo
from .domain_info import DomainInfo
from .ip_info import IPInfo, PortInfo
from .page_info import PageInfo
from .wih_record import WihRecord

__all__ = [
    # 模型
    "BaseInfo", "DomainInfo", "IPInfo", "PortInfo", "PageInfo", "WihRecord",
    # 枚举
    "ScanPortType", "DomainDictType", "CollectSource", "TaskStatus",
    "TaskScheduleStatus", "TaskTag", "TaskType", "SiteAutoTag",
    "TaskSyncStatus", "SchedulerStatus", "AssetScopeType", "PoCCategory",
    "WebSiteFetchOption", "WebSiteFetchStatus", "TaskQueue", "TaskAction",
    "CeleryAction", "CeleryRoutingKey",
    # 错误
    "error_map", "ErrorMsg", "build_ret",
]
