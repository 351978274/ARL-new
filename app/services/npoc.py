"""NPoC（PoC/弱口令/协议识别）封装，移植自原 app/services/npoc.py。

依赖外部 xing 库（ARL-NPoC，pip install xing-arlpoc 或源码安装）。
若 xing 未安装，相关方法降级为空实现并打印警告。
"""
from __future__ import annotations

import asyncio
import json
import os

from ..config import Config
from ..database import conn_db
from ..logger import get_logger
from ..modules import PoCCategory
from ..utils import curr_date, load_file, random_choices

logger = get_logger()

try:
    from xing.core import PluginType, PluginRunner
    from xing.utils import load_plugins
    from xing.conf import Conf as npoc_conf
    _HAVE_XING = True
except ImportError:
    _HAVE_XING = False
    PluginType = PluginRunner = load_plugins = npoc_conf = None  # type: ignore[assignment]
    logger.warning("未安装 xing（ARL-NPoC）库，PoC/弱口令/协议识别功能不可用。"
                   "项目已内置 xing 源码（yang/xing），请确认在项目根目录运行。")


class NPoC:
    """PoC 运行器。xing 缺失时方法降级。"""

    def __init__(self, concurrency: int = 6, tmp_dir: str = "./"):
        self._plugins = None
        self._poc_info_list = None
        self.concurrency = concurrency
        self._plugin_name_list = None
        self.plugin_name_set: set[str] = set()
        self._db_plugin_name_list = None
        self.tmp_dir = tmp_dir
        self.runner = None
        self.result: list = []
        self.brute_plugin_name_set: set[str] = set()
        self.poc_plugin_name_set: set[str] = set()
        self.sniffer_plugin_name_set: set[str] = set()

    @property
    def db_plugin_name_list(self) -> list:
        if self._db_plugin_name_list is None:
            self._db_plugin_name_list = []
            # 同步遍历（启动期），用 to_thread
            pass
        return self._db_plugin_name_list

    @property
    def plugin_name_list(self) -> list:
        if self._plugin_name_list is None:
            _ = self.poc_info_list  # 触发生成
            self._plugin_name_list = list(self.plugin_name_set)
        return self._plugin_name_list

    @property
    def plugins(self) -> list:
        if self._plugins is None:
            self._plugins = self.load_all_poc()
        return self._plugins

    @property
    def poc_info_list(self) -> list:
        if self._poc_info_list is None:
            self._poc_info_list = self.gen_poc_info()
        return self._poc_info_list

    def load_all_poc(self) -> list:
        if not _HAVE_XING:
            return []
        plugins = load_plugins(os.path.join(npoc_conf.PROJECT_DIRECTORY, "plugins"))
        return [p for p in plugins if p.plugin_type in (PluginType.POC, PluginType.BRUTE, PluginType.SNIFFER)]

    def gen_poc_info(self) -> list:
        info_list = []
        for p in self.plugins:
            info = {"plugin_name": getattr(p, "_plugin_name", "")}
            if p.plugin_type == PluginType.SNIFFER:
                self.sniffer_plugin_name_set.add(info["plugin_name"])
                continue
            info["app_name"] = p.app_name
            info["scheme"] = ",".join(p.scheme)
            info["vul_name"] = p.vul_name
            info["plugin_type"] = p.plugin_type
            if p.plugin_type == PluginType.POC:
                info["category"] = PoCCategory.POC
                self.poc_plugin_name_set.add(info["plugin_name"])
            if p.plugin_type == PluginType.BRUTE:
                self.brute_plugin_name_set.add(info["plugin_name"])
                info["category"] = PoCCategory.WEBB_RUTE if "http" in info["scheme"] else PoCCategory.SYSTEM_BRUTE
            if info["plugin_name"] in self.plugin_name_set:
                logger.warning(f"plugin {info['plugin_name']} already exists")
                continue
            self.plugin_name_set.add(info["plugin_name"])
            info_list.append(info)
        return info_list

    async def sync_to_db(self):
        db_names: list[str] = [item["plugin_name"] async for item in conn_db('poc').find({}, {"plugin_name": 1})]
        for old in self.poc_info_list:
            plugin_name = old["plugin_name"]
            if plugin_name in db_names:
                continue
            new = old.copy()
            new["update_date"] = curr_date()
            logger.info(f"insert {plugin_name} info to db")
            await conn_db('poc').insert_one(new)
        return True

    def run_poc(self, plugin_name_list, targets) -> list:
        if not _HAVE_XING:
            logger.warning("xing 未安装，跳过 PoC 执行")
            return []
        self.result = []
        npoc_conf.SAVE_TEXT_RESULT_FILENAME = ""
        random_file = os.path.join(self.tmp_dir, f"npoc_result_{random_choices()}.txt")
        npoc_conf.SAVE_JSON_RESULT_FILENAME = random_file
        plugins = self.filter_plugin_by_name(plugin_name_list)
        runner = PluginRunner.PluginRunner(plugins=plugins, targets=targets, concurrency=self.concurrency)
        self.runner = runner
        runner.run()
        if not os.path.exists(random_file):
            return self.result
        for item in load_file(random_file):
            self.result.append(json.loads(item))
        os.unlink(random_file)
        return self.result

    def filter_plugin_by_name(self, plugin_name_list):
        return [p for p in self.plugins
                if getattr(p, "_plugin_name", "") and getattr(p, "_plugin_name") in plugin_name_list]


def sync_to_db(del_flag: bool = False):
    """xing 插件信息同步到 poc 集合（同步入口，内部异步）。"""
    n = NPoC()
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # 在已有事件循环中：返回协程
        async def _run():
            await n.sync_to_db()
            return True
        return _run()
    loop.run_until_complete(n.sync_to_db())
    return True


async def run_risk_cruising(plugins, targets) -> list:
    n = NPoC(tmp_dir=Config.TMP_PATH, concurrency=8)
    return await asyncio.to_thread(n.run_poc, plugins, targets)


async def run_sniffer(targets) -> list:
    """协议识别（跳过 80/443）。"""
    n = NPoC(concurrency=15, tmp_dir=Config.TMP_PATH)
    _ = n.plugin_name_list  # 触发加载
    new_targets = [t.strip() for t in targets if not t.strip().endswith((":80", ":443"))]
    items = await asyncio.to_thread(n.run_poc, n.sniffer_plugin_name_set, new_targets)
    ret = []
    for x in items:
        target = x.get("verify_data", "")
        if "://" not in target:
            continue
        split = target.split("://")
        scheme = split[0]
        rest = split[1].split(":")
        ret.append({"scheme": scheme, "host": rest[0], "port": rest[1], "target": target})
    return ret
