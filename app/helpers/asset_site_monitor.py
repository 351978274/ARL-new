"""资产站点监控任务提交，移植自原 app/helpers/asset_site_monitor.py。"""
from __future__ import annotations

from ..config import Config
from ..modules import TaskStatus, TaskType

_black_asset_site_list: list[str] | None = None


def is_black_asset_site(site: str) -> bool:
    """站点是否在黑名单中（前缀匹配）。"""
    global _black_asset_site_list
    if _black_asset_site_list is None:
        try:
            with open(Config.black_asset_site, encoding="utf-8") as f:
                _black_asset_site_list = f.readlines()
        except FileNotFoundError:
            _black_asset_site_list = []
    for item in _black_asset_site_list:
        item = item.strip()
        if item and site.startswith(item):
            return True
    return False


async def submit_asset_site_monitor_job(scope_id: str, name: str, scheduler_id: str) -> None:
    from .task import submit_task
    task_data = {
        'name': name, 'target': "资产站点更新", 'start_time': '-',
        'status': TaskStatus.WAITING, 'type': TaskType.ASSET_SITE_UPDATE,
        "task_tag": TaskType.ASSET_SITE_UPDATE,
        'options': {"scope_id": scope_id, "scheduler_id": scheduler_id},
        "end_time": "-", "service": [], "celery_id": "",
    }
    await submit_task(task_data)
