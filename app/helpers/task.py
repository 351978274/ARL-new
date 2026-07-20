"""任务生命周期：构建/校验/下发/重启，移植自原 app/helpers/task.py。

核心改动：submit_task 不再调用 celery，而是调用 app.core.task_runner.submit_task_action
（asyncio 后台任务），并把返回的 task_id 记为 celery_id（兼容字段）。
"""
from __future__ import annotations

import re

from bson import ObjectId

from ..database import conn_db
from ..logger import get_logger
from ..modules import TaskAction, TaskStatus, TaskTag, TaskType

logger = get_logger()


def target2list(target: str) -> list[str]:
    target = target.strip().lower()
    target_lists = re.split(r",|\s", target)
    target_lists = list(filter(None, target_lists))
    return list(set(target_lists))


def get_ip_domain_list(target: str):
    """拆分目标为 (ip_list, domain_list)，校验黑名单/禁止域名/合法性。"""
    from ..utils import (check_domain_black, is_forbidden_domain,
                          is_valid_domain, is_valid_fuzz_domain, is_vaild_ip_target, not_in_black_ips)
    target_lists = target2list(target)
    ip_list: set[str] = set()
    domain_list: set[str] = set()
    for item in target_lists:
        if not item:
            continue
        if is_vaild_ip_target(item):
            if not not_in_black_ips(item):
                raise Exception(f"{item} 在黑名单IP中")
            ip_list.add(item)
        elif is_forbidden_domain(item):
            raise Exception(f"{item} 包含在禁止域名内")
        elif is_valid_domain(item):
            if check_domain_black(item):
                raise Exception(f"{item} 包含在系统黑名单中")
            domain_list.add(item)
        elif is_valid_fuzz_domain(item):
            domain_list.add(item)
        else:
            raise Exception(f"{item} 无效的目标")
    return ip_list, domain_list


def build_task_data(task_name: str, task_target, task_type: str, task_tag: str, options: dict) -> dict:
    avail_task_type = [TaskType.IP, TaskType.DOMAIN, TaskType.RISK_CRUISING]
    if task_type not in avail_task_type:
        raise Exception(f"{task_type} 无效的 task_type")
    avail_task_tag = [TaskTag.RISK_CRUISING, TaskTag.MONITOR, TaskTag.TASK]
    if task_tag not in avail_task_tag:
        raise Exception(f"{task_tag} 无效的 task_tag")
    if not isinstance(options, dict):
        raise Exception(f"{options} 不是 dict")

    options_cp = options.copy()
    # IP 任务关闭域名相关选项
    if task_type == TaskType.IP:
        options_cp.update({"domain_brute": False, "alt_dns": False,
                           "dns_query_plugin": False, "arl_search": False})

    task_data = {
        'name': task_name, 'target': task_target, 'start_time': '-',
        'status': TaskStatus.WAITING, 'type': task_type, "task_tag": task_tag,
        'options': options_cp, "end_time": "-", "service": [], "celery_id": "",
    }

    # 风险巡航任务特殊处理
    if task_tag == TaskType.RISK_CRUISING:
        poc_config = options.get("poc_config", [])
        if options.get("result_set_id"):
            result_set_id = options.pop("result_set_id")
            result_set_len = options.pop("result_set_len")
            target_field = f"目标：{result_set_len}， PoC：{len(poc_config)}"
            task_data["result_set_id"] = result_set_id
        else:
            target_field = f"目标：{len(task_target)}， PoC：{len(poc_config)}"
            task_data["cruising_target"] = task_target
        task_data["target"] = target_field
    return task_data


async def submit_task(task_data: dict) -> dict:
    """插入 task 文档并异步派发执行。

    替代原 submit_task（celery），改为调用 task_runner 的 asyncio 后台任务。
    """
    from ..core.task_runner import submit_task_action
    target = task_data["target"]
    await conn_db('task').insert_one(task_data)
    task_id = str(task_data.pop("_id"))
    task_data["task_id"] = task_id

    type_map_action = {
        TaskType.DOMAIN: TaskAction.DOMAIN_TASK,
        TaskType.IP: TaskAction.IP_TASK,
        TaskType.RISK_CRUISING: TaskAction.RUN_RISK_CRUISING,
        TaskType.ASSET_SITE_UPDATE: TaskAction.ASSET_SITE_UPDATE,
        TaskType.FOFA: TaskAction.FOFA_TASK,
        TaskType.ASSET_SITE_ADD: TaskAction.ADD_ASSET_SITE_TASK,
        TaskType.ASSET_WIH_UPDATE: TaskAction.ASSET_WIH_UPDATE,
    }
    task_type = task_data["type"]
    task_action = type_map_action.get(task_type, "")
    assert task_action, f"未知任务类型 {task_type}"

    task_options = {"celery_action": task_action, "data": task_data}
    try:
        run_id = await submit_task_action(task_options)
        logger.info(f"target:{target} task_id:{task_id} run_id:{run_id}")
        task_data["celery_id"] = run_id
        await conn_db('task').update_one({"_id": ObjectId(task_id)}, {"$set": {"celery_id": run_id}})
    except Exception:
        await conn_db('task').delete_one({"_id": ObjectId(task_id), "status": TaskStatus.WAITING})
        logger.info(f"下发失败 {target}")
        raise
    return task_data


async def submit_task_task(target: str, name: str, options: dict) -> list[dict]:
    """根据目标拆分并下发 IP / 域名任务。"""
    task_data_list: list[dict] = []
    ip_list, domain_list = get_ip_domain_list(target)
    if ip_list:
        ip_target = " ".join(ip_list)
        td = build_task_data(name, ip_target, TaskType.IP, TaskTag.TASK, options)
        task_data_list.append(await submit_task(td))
    for domain_target in domain_list:
        td = build_task_data(name, domain_target, TaskType.DOMAIN, TaskTag.TASK, options)
        task_data_list.append(await submit_task(td))
    return task_data_list


async def submit_risk_cruising(target: str, name: str, options: dict) -> list[dict]:
    target_lists = target2list(target)
    td = build_task_data(name, target_lists, TaskType.RISK_CRUISING, TaskTag.RISK_CRUISING, options)
    return [await submit_task(td)]


async def submit_add_asset_site_task(task_name: str, target: list, options: dict) -> dict:
    task_data = {
        'name': task_name, 'target': f"站点：{len(target)}", 'start_time': '-',
        'status': TaskStatus.WAITING, 'type': TaskType.ASSET_SITE_ADD,
        "task_tag": TaskTag.RISK_CRUISING, 'options': options, "end_time": "-",
        "service": [], "cruising_target": target, "celery_id": "",
    }
    return await submit_task(task_data)


async def get_task_data(task_id: str) -> dict | None:
    return await conn_db('task').find_one({'_id': ObjectId(task_id)})


async def restart_task(task_id: str) -> dict:
    name_pre = "重新运行-"
    task_data = await get_task_data(task_id)
    if not task_data:
        raise Exception(f"没有找到 task_id : {task_id}")

    task_data.pop("_id")
    task_data["start_time"] = "-"
    task_data["status"] = TaskStatus.WAITING
    task_data["end_time"] = "-"
    task_data["service"] = []
    task_data["celery_id"] = ""
    task_data.pop("statistic", None)

    name = task_data["name"]
    if name_pre not in name:
        task_data["name"] = name_pre + name

    task_type = task_data["type"]
    task_tag = task_data.get("task_tag", "")
    if task_type == TaskType.RISK_CRUISING and task_tag == TaskTag.RISK_CRUISING:
        if task_data.get("result_set_id"):
            raise Exception(f"task_id : {task_id}, 不支持该任务重新运行")
    if task_type == TaskType.DOMAIN and task_tag == TaskTag.MONITOR:
        raise Exception(f"task_id : {task_id}, 不支持该任务重新运行")
    elif task_type == TaskType.IP and task_data["options"].get("scope_id"):
        raise Exception(f"task_id : {task_id}, 不支持该任务重新运行")

    await submit_task(task_data)
    return task_data
