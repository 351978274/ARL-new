"""tasks 包：任务流水线入口（异步），移植自原 app/tasks/__init__.py。

对外暴露各任务顶层函数。
"""
from __future__ import annotations

from .asset_site import (AddAssetSiteTask, AssetSiteUpdateTask, asset_site_update_task,
                         run_add_asset_site_task)
from .asset_wih import AssetWihUpdateTask, asset_wih_update_task
from .domain_task import DomainTask, domain_task
from .github import GithubTaskMonitor, GithubTaskTask, github_task_monitor, github_task_task
from .ip_task import IPTask, ip_task
from .risk_cruising import RiskCruising, run_risk_cruising_task
from .scheduler_exec import DomainExecutor, IPExecutor, domain_executors, ip_executor

__all__ = [
    "domain_task", "DomainTask",
    "ip_task", "IPTask",
    "domain_executors", "ip_executor", "DomainExecutor", "IPExecutor",
    "run_risk_cruising_task", "RiskCruising",
    "asset_site_update_task", "run_add_asset_site_task", "AssetSiteUpdateTask", "AddAssetSiteTask",
    "asset_wih_update_task", "AssetWihUpdateTask",
    "github_task_task", "github_task_monitor", "GithubTaskTask", "GithubTaskMonitor",
]
