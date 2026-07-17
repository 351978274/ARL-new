"""任务执行器与查询构造测试。

task_runner 的派发/取消逻辑（不依赖 MongoDB，用 monkeypatch 替换 run_task）。
build_db_query 的查询语法（移植自 ARLResource.build_db_query）。
"""
import asyncio

import pytest

from app.routes.base import build_db_query, _parse_order
from app.modules import TaskAction


class TestBuildDbQuery:
    def test_equal_field(self):
        q = build_db_query({"task_id": "abc", "name": "test"})
        assert q["task_id"] == "abc"  # EQUAL_FIELDS 等值
        assert q["name"] == {"$regex": "test", "$options": "i"}  # 模糊

    def test_neq(self):
        q = build_db_query({"status__neq": "done"})
        assert q["status"] == {"$ne": "done"}

    def test_not(self):
        q = build_db_query({"title__not": "spam"})
        assert "$not" in q["title"]

    def test_gt_lt_int(self):
        # __gt / __lt 是不同的 key，分别生成查询；同目标 key 后写覆盖前写（与原版一致）
        q1 = build_db_query({"site_cnt__gt": 5})
        assert q1["site_cnt"] == {"$gt": 5}
        q2 = build_db_query({"site_cnt__lt": 100})
        assert q2["site_cnt"] == {"$lt": 100}

    def test_dgt_dlt_date(self):
        from datetime import datetime
        q = build_db_query({"save_date__dgt": "2024-01-01 00:00:00"})
        assert "$gt" in q["save_date"]
        assert isinstance(q["save_date"]["$gt"], datetime)

    def test_objectid(self):
        from bson import ObjectId
        q = build_db_query({"_id": "507f1f77bcf86cd799439011"})
        assert isinstance(q["_id"], ObjectId)

    def test_skip_none_and_base(self):
        q = build_db_query({"page": 1, "size": 10, "order": "-_id", "name": None})
        assert "page" not in q and "size" not in q and "order" not in q
        assert "name" not in q  # None 被跳过

    def test_order_parse(self):
        assert _parse_order("-_id") == [("_id", -1)]
        assert _parse_order("+name") == [("name", 1)]
        assert _parse_order("name,-age") == [("name", 1), ("age", -1)]


class TestTaskRunnerDispatch:
    """task_runner.submit_task_action 的派发（mock run_task）。"""

    @pytest.mark.asyncio
    async def test_submit_and_dispatch(self, monkeypatch):
        from app.core import task_runner

        called = {}

        async def fake_run_task(options):
            called["action"] = options["celery_action"]
            called["data"] = options["data"]

        monkeypatch.setattr(task_runner, "run_task", fake_run_task)

        options = {"celery_action": TaskAction.DOMAIN_TASK, "data": {"task_id": "t1", "target": "x.com"}}
        run_id = await task_runner.submit_task_action(options)
        assert run_id  # 返回 run_id
        # 让后台任务执行
        await asyncio.sleep(0.05)
        assert called.get("action") == TaskAction.DOMAIN_TASK
        assert called.get("data", {}).get("target") == "x.com"
        # 任务完成后应从 _running_tasks 移除
        assert run_id not in task_runner._running_tasks

    @pytest.mark.asyncio
    async def test_cancel(self, monkeypatch):
        from app.core import task_runner

        async def slow_run_task(options):
            await asyncio.sleep(10)  # 长任务

        monkeypatch.setattr(task_runner, "run_task", slow_run_task)
        options = {"celery_action": TaskAction.IP_TASK, "data": {"task_id": "t2"}}
        run_id = await task_runner.submit_task_action(options)
        await asyncio.sleep(0.02)  # 等任务启动
        assert run_id in task_runner._running_tasks
        assert task_runner._task_id_to_run_id.get("t2") == run_id
        cancelled = await task_runner.cancel_task_by_task_id("t2")
        assert cancelled is True
