"""枚举常量与错误码表，移植自原 app/modules/__init__.py。

注意：原 CeleryAction / CeleryRoutingKey 已更名为 TaskAction / TaskQueue，
以反映从 Celery 迁移到 asyncio 任务执行器。
"""
from __future__ import annotations

from ..config import Config, ScanPortPresets


def load_port_list(path: str, fallback: str) -> str:
    """从端口字典文件加载端口列表，逗号拼接为 nmap 可接受的字符串。

    文件每行一个端口或范围（如 ``8080-8090``）。文件缺失/读取失败/为空时
    返回 ``fallback``（对应 ``ScanPortPresets`` 硬编码值），保证扫描始终可用。
    """
    if not path:
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            ports = [line.strip() for line in f if line.strip()]
    except OSError:
        return fallback
    return ",".join(ports) if ports else fallback


class ScanPortType:
    """端口扫描预设。

    优先从 ``Config.PORT_DICT_*`` 指向的字典文件读取（可经 config.yaml
    ``ARL.PORT_DICT_*`` 覆盖）；文件缺失或为空时回退到 ``ScanPortPresets``
    硬编码常量，与原 ARL 行为一致。
    """
    TEST = load_port_list(Config.PORT_DICT_TEST, ScanPortPresets.TOP_10)
    TOP100 = load_port_list(Config.PORT_DICT_TOP100, ScanPortPresets.TOP_100)
    TOP1000 = load_port_list(Config.PORT_DICT_TOP1000, ScanPortPresets.TOP_1000)
    ALL = load_port_list(Config.PORT_DICT_ALL, ScanPortPresets.ALL)


class DomainDictType:
    TEST = Config.DOMAIN_DICT_TEST
    BIG = Config.DOMAIN_DICT_2W


class CollectSource:
    DOMAIN_BRUTE = "domain_brute"
    BAIDU = "baidu"
    ALTDNS = "alt_dns"
    ARL = "arl"
    SITESPIDER = "site_spider"
    SEARCHENGINE = "search_engine"
    MONITOR = "monitor"


class TaskStatus:
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"
    STOP = "stop"


class TaskScheduleStatus:
    DONE = "done"
    SCHEDULED = "scheduled"
    STOP = "stop"
    ERROR = "error"


class TaskTag:
    """任务标签。"""
    TASK = "task"            # 带资产发现的任务
    MONITOR = "monitor"      # 域名监控任务
    RISK_CRUISING = "risk_cruising"  # 风险巡航任务


class TaskType:
    """任务目标类别。"""
    IP = "ip"
    DOMAIN = "domain"
    RISK_CRUISING = "risk_cruising"
    ASSET_SITE_UPDATE = "asset_site_update"
    FOFA = "fofa"
    ASSET_SITE_ADD = "asset_site_add"
    ASSET_WIH_UPDATE = "asset_wih_update"


class SiteAutoTag:
    ENTRY = "入口"
    INVALID = "无效"


class TaskSyncStatus:
    WAITING = "waiting"
    RUNNING = "running"
    ERROR = "error"
    DEFAULT = "default"


# 补充导入别名（兼容外部使用 TaskSyncStatus）


class SchedulerStatus:
    RUNNING = "running"
    STOP = "stop"


class AssetScopeType:
    DOMAIN = "domain"
    IP = "ip"


class PoCCategory:
    POC = "漏洞PoC"
    SNIFFER = "协议识别"
    SYSTEM_BRUTE = "服务弱口令"
    WEBB_RUTE = "应用弱口令"  # 保留历史拼写以兼容外部代码
    WEB_BRUTE = "应用弱口令"  # 修正后的拼写别名（与 WEBB_RUTE 等价）


class WebSiteFetchOption:
    """针对 WEB 站点可选功能选项。"""
    SITE_CAPTURE = "site_capture"
    SEARCH_ENGINES = "search_engines"
    SITE_SPIDER = "site_spider"
    FILE_LEAK = "file_leak"
    POC_RUN = "poc_config"
    SITE_IDENTIFY = "site_identify"
    NUCLEI_SCAN = "nuclei_scan"
    Info_Hunter = "web_info_hunter"


class WebSiteFetchStatus:
    """针对 WEB 站点任务可能的状态。"""
    FETCH_SITE = "fetch_site"
    SITE_CAPTURE = "site_capture"
    SEARCH_ENGINES = "search_engines"
    SITE_SPIDER = "site_spider"
    FILE_LEAK = "file_leak"
    SITE_IDENTIFY = "site_identify"
    POC_RUN = "poc_run"
    NUCLEI_SCAN = "nuclei_scan"
    Info_Hunter = "web_info_hunter"


# 原 CeleryRoutingKey（保留兼容，已不再使用 RabbitMQ）
class TaskQueue:
    ASSET_TASK = "arltask"
    GITHUB_TASK = "arlgithub"


# 原 CeleryAction，迁移到 asyncio 后含义不变，仅改名为 TaskAction
class TaskAction:
    """异步任务 task_action 字段。"""
    IP_TASK = "ip_task"
    DOMAIN_TASK = "domain_task"
    DOMAIN_EXEC_TASK = "domain_exec_task"
    IP_EXEC_TASK = "ip_exec_task"
    DOMAIN_TASK_SYNC_TASK = "domain_task_sync_task"
    RUN_RISK_CRUISING = "run_risk_cruising"
    FOFA_TASK = "fofa_task"
    GITHUB_TASK_TASK = "github_task_task"
    GITHUB_TASK_MONITOR = "github_task_monitor"
    ASSET_SITE_UPDATE = "asset_site_update"
    ADD_ASSET_SITE_TASK = "add_asset_site_task"
    ASSET_WIH_UPDATE = "asset_wih_update"


# 向后兼容别名
CeleryAction = TaskAction
CeleryRoutingKey = TaskQueue
