"""通用只读资源路由：为只读资产集合提供统一的分页查询 + 导出。

这些集合在原 ARL 中都是相同模式的 GET 查询 + 导出：
domain, site, ip, url, cert, service, fileleak, vuln, poc, cip, stat_finger,
npoc_service, nuclei_result, wih, asset_domain, asset_ip, asset_site, asset_wih,
github_task, github_result, github_scheduler, github_monitor_result, task_schedule, console。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import require_auth
from .base import build_data, export_collection, parse_query_params


def make_readonly_router(prefix: str, collection: str, tag: str) -> APIRouter:
    """构造一个只读资源路由（list + export）。"""
    router = APIRouter(prefix=f"/{prefix}", tags=[tag], dependencies=[Depends(require_auth)])

    @router.get("/")
    async def _list(request: Request):
        return await build_data(parse_query_params(request), collection)

    @router.get("/export/")
    async def _export(request: Request):
        return await export_collection(parse_query_params(request), collection)

    return router


# 注册所有只读集合
routers: list[APIRouter] = [
    make_readonly_router("domain", "domain", "域名"),
    make_readonly_router("site", "site", "站点"),
    make_readonly_router("ip", "ip", "IP"),
    make_readonly_router("url", "url", "URL"),
    make_readonly_router("cert", "cert", "证书"),
    make_readonly_router("service", "service", "系统服务"),
    make_readonly_router("fileleak", "fileleak", "文件泄漏"),
    make_readonly_router("vuln", "vuln", "漏洞"),
    make_readonly_router("poc", "poc", "PoC"),
    make_readonly_router("cip", "cip", "C段统计"),
    make_readonly_router("stat_finger", "stat_finger", "指纹统计"),
    make_readonly_router("npoc_service", "npoc_service", "系统服务(python)"),
    make_readonly_router("nuclei_result", "nuclei_result", "nuclei结果"),
    make_readonly_router("wih", "wih", "WIH"),
    make_readonly_router("asset_domain", "asset_domain", "资产组域名"),
    make_readonly_router("asset_ip", "asset_ip", "资产组IP"),
    make_readonly_router("asset_site", "asset_site", "资产组站点"),
    make_readonly_router("asset_wih", "asset_wih", "资产组WIH"),
    make_readonly_router("github_task", "github_task", "Github任务"),
    make_readonly_router("github_result", "github_result", "Github结果"),
    make_readonly_router("github_monitor_result", "github_monitor_result", "Github监控结果"),
    make_readonly_router("task_schedule", "task_schedule", "计划任务"),
]
