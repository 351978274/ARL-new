"""错误码表与错误信息，移植自原 app/modules/__init__.py 的 error_map / ErrorMsg。"""
from __future__ import annotations

error_map = {
    'CeleryIdNotFound': {"message": "没有找到Celery id", "code": 102},
    'NotFoundTask': {"message": "没有找到任务", "code": 103},
    "TaskIsRunning": {"message": "任务运行中", "code": 104},
    "TaskIsDone": {"message": "任务已经完成", "code": 105},
    "Success": {"message": "success", "code": 200},
    "NotLogin": {"message": "未登录", "code": 401},
    "NotFoundScopeID": {"message": "没有找到资产范围ID", "code": 601},
    "NotFoundScope": {"message": "没有找到对应的资产范围", "code": 602},
    "ExistScope": {"message": "已存在对应的资产范围", "code": 603},
    "IntervalLessThan3600": {"message": "监控任务时间间隔不能小于6小时（21600s）", "code": 700},
    "DomainNotFoundViaScope": {"message": "域名不在给定的资产范围中", "code": 701},
    "DomainViaJob": {"message": "给定资产范围中的域名已经存在监控任务", "code": 699},
    "DomainNotViaJob": {"message": "给定资产范围中的域名不存在监控任务", "code": 698},
    "JobNotFound": {"message": "监控任务未找到", "code": 702},
    "DomainInvalid": {"message": "域名无效", "code": 703},
    "TargetInvalid": {"message": "任务目标无效", "code": 704},
    "IPInBlackIps": {"message": "目标IP不允许下发", "code": 705},
    "TaskTargetIsEmpty": {"message": "任务目标为空", "code": 706},
    "TaskSyncDealing": {"message": "任务资产同步处理中", "code": 801},
    "TaskTypeIsNotDomain": {"message": "不是域名发现任务", "code": 802},
    "TaskTargetNotInScope": {"message": "任务目标不在资产组中", "code": 802},
    "DomainInScope": {"message": "域名已经存在指定资产组中", "code": 803},
    "URLInvalid": {"message": "URL无效", "code": 804},
    "SiteURLNotDomain": {"message": "非域名类型URL", "code": 805},
    "SiteInScope": {"message": "站点已在指定资产中", "code": 806},
    "DomainNotFoundNotInScope": {"message": "没有发现可以添加的域名", "code": 807},
    "SchedulerStatusNotRunning": {"message": "监控任务非运行状态", "code": 901},
    "SchedulerStatusNotStop": {"message": "监控任务非停止状态", "code": 902},
    "ResultSetIDNotFound": {"message": "结果集 ID 没有找到", "code": 1001},
    "ResultSetIsEmpty": {"message": "结果集中目标为空", "code": 1002},
    "PoCTargetIsEmpty": {"message": "PoC 任务目标为空", "code": 1003},
    "QueryResultIsEmpty": {"message": "查询结果为空", "code": 1004},
    "PolicyIDNotFound": {"message": "策略不存在", "code": 1100},
    "RiskCruisingPoCConfigIsEmpty": {"message": "风险巡航任务选择的策略PoC配置字段不能为空", "code": 1101},
    "BruteTaskBruteConfigIsEmpty": {"message": "弱口令任务选择的策略爆破配置字段不能为空", "code": 1102},
    "PolicyDataIsEmpty": {"message": "策略数据为空", "code": 1103},
    "FofaConnectError": {"message": "连接Fofa API异常", "code": 1201},
    "FofaKeyError": {"message": "Fofa 认证信息错误", "code": 1202},
    "FofaResultEmpty": {"message": "Fofa 查询结果为空", "code": 1203},
    "SiteIdNotFound": {"message": "站点没有找到", "code": 1300},
    "SiteTagIsExist": {"message": "站点标签已经存在", "code": 1301},
    "SiteTagNotExist": {"message": "站点标签没有找到", "code": 1302},
    "ScopeTypeIsNotIP": {"message": "资产组IP范围无效", "code": 1303},
    "IsForbiddenDomain": {"message": "包含在禁止域名内", "code": 1401},
    "RuleInvalid": {"message": "规则无效", "code": 1402},
    "GithubKeywordEmpty": {"message": "关键字为空", "code": 1501},
    "Error": {"message": "系统异常", "code": 500},
    "CronError": {"message": "Cron 表达式错误", "code": 1502},
    "IPInvalid": {"message": "IP 无效", "code": 1503},
    "IPNotFoundViaScope": {"message": "不在给定的资产范围中", "code": 1504},
    "PortCustomInvalid": {"message": "自定义端口信息错误", "code": 1506},
    "TaskScheduleTypeInvalid": {"message": "计划任务类型错误", "code": 1601},
    "DateInvalid": {"message": "时间错误", "code": 1602},
    "TaskTagInvalid": {"message": "任务类型错误", "code": 1603},
    "FutureDateInvalid": {"message": "时间已经过去了", "code": 1604},
    "TaskScheduleNotFound": {"message": "计划任务没有找到", "code": 1605},
    "DomainSiteViaJob": {"message": "资产站点更新任务已存在", "code": 1607},
    "AddAssetSiteNotSupportIP": {"message": "不支持对IP资产组添加站点", "code": 1608},
    "RuleAlreadyExists": {"message": "规则已存在", "code": 1609},
    "ExcludePortsInvalid": {"message": "nmap 排除端口错误", "code": 1610},
}


class ErrorMsg:
    """以属性方式访问 error_map，保持与原代码 `modules.ErrorMsg.XXX` 调用兼容。"""

    def __getattr__(self, name):
        if name in error_map:
            return error_map[name]
        raise AttributeError(f"ErrorMsg 没有属性 {name!r}")


def build_ret(error, data: dict | None = None) -> dict:
    """构造统一返回结构，移植自原 app/utils/__init__.py build_ret。

    返回: {"message", "code", "data"}。code != 200 时把 data 中非空字段拼进 message。
    """
    if data is None:
        data = {}
    if isinstance(error, str):
        error = {"message": error, "code": 999}

    ret = dict(error)
    ret["data"] = data
    msg = error["message"]
    if error["code"] != 200:
        for k, v in data.items():
            if k.endswith("id"):
                continue
            if not v:
                continue
            if isinstance(v, str):
                msg += f" {k}:{v}"
    ret["message"] = msg
    return ret
