"""资产 WIH 监控任务提交，移植自原 app/helpers/asset_wih_monitor.py。"""
from __future__ import annotations

from ..modules import TaskStatus, TaskType


async def submit_asset_wih_monitor_job(scope_id: str, name: str, scheduler_id: str) -> None:
    from .task import submit_task
    task_data = {
        'name': name, 'target': "资产分组 WIH 更新", 'start_time': '-',
        'status': TaskStatus.WAITING, 'type': TaskType.ASSET_WIH_UPDATE,
        "task_tag": TaskType.ASSET_WIH_UPDATE,
        'options': {"scope_id": scope_id, "scheduler_id": scheduler_id},
        "end_time": "-", "service": [], "celery_id": "",
    }
    await submit_task(task_data)
