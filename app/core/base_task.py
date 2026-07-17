"""异步并发基类，移植自原 app/services/baseThread.py 的 BaseThread。

用 asyncio.Semaphore + asyncio.gather 替代 threading。
子类实现 async work(target)，基类负责限流并发执行。
"""
from __future__ import annotations

import asyncio
import collections
from typing import Any, Awaitable, Callable

from ..logger import get_logger


class AsyncBaseTask:
    """所有并发扫描器的基类。

    子类：
        async def work(self, target): ...
        结果写入 self.result_list / 自定义属性。
    """

    def __init__(self, targets, concurrency: int = 6):
        self.targets = list(targets)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.logger = get_logger()

    async def work(self, target: Any) -> None:
        raise NotImplementedError()

    async def _work(self, target: Any) -> None:
        """包装单任务：限流 + 异常吞并（与原 _work 行为一致）。"""
        async with self.semaphore:
            try:
                await self.work(target)
            except Exception as e:
                # 吞并普通异常（请求错误等），记录日志
                self.logger.debug(f"_work error on {target}: {type(e).__name__} {e}")
            except BaseException:
                raise

    async def _run(self) -> None:
        """并发执行所有 target 的 work。"""
        tasks = [asyncio.create_task(self._work(t)) for t in self.targets]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False)


class AsyncMapTask(AsyncBaseTask):
    """通用 map：对每个 item 调用 fun(item, arg)，收集非空结果到结果字典。

    对应原 ThreadMap + thread_map。
    """

    def __init__(self, fun: Callable[..., Awaitable[Any]], items, arg: Any = None, concurrency: int = 6):
        super().__init__(items, concurrency)
        self.fun = fun
        self.arg = arg
        self._result_map: dict[str, Any] = {}

    async def work(self, item: Any) -> None:
        try:
            if self.arg is None:
                result = await self.fun(item)
            else:
                result = await self.fun(item, self.arg)
        except Exception as e:
            self.logger.debug(f"map error on {item}: {e}")
            return
        if result:
            self._result_map[str(item)] = result

    async def run(self) -> dict[str, Any]:
        await self._run()
        return self._result_map


async def thread_map(fun: Callable[..., Awaitable[Any]], items, arg: Any = None,
                     concurrency: int = 6) -> dict[str, Any]:
    """通用异步 map，等价于原 thread_map。"""
    task = AsyncMapTask(fun, items, arg, concurrency)
    return await task.run()
