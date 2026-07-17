"""域名查询插件动态加载，移植自原 app/utils/query_loader.py。

原版用 importlib.util.spec_from_file_location 加载，会破坏相对导入。
本版改为用 importlib 按模块路径导入（插件作为 app.dns_query_plugin.<name> 的子模块），
使插件中的 `from .base import DNSQueryBase` 相对导入可用。
"""
from __future__ import annotations

import importlib
import importlib.util
import os


def walk_py(path: str):
    """遍历目录下所有非下划线开头的 .py 文件，返回 (abspath, module_name)。"""
    for dir_path, _dir_names, filenames in os.walk(path):
        if dir_path.endswith("__pycache__"):
            continue
        for f in filenames:
            if f.startswith('_'):
                continue
            split = f.split('.')
            if len(split) == 2 and split[1] == 'py':
                abspath = os.path.abspath(os.path.join(dir_path, f))
                yield abspath, split[0]


def _plugin_to_module(abspath: str, name: str):
    """把插件文件作为 app.dns_query_plugin.<name> 模块导入，保证相对导入可用。"""
    from ..logger import get_logger
    logger = get_logger()
    try:
        mod_name = f"app.dns_query_plugin.{name}"
        # 优先用标准 import（已注册到 sys.modules 则直接取）
        try:
            module = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            # 回退：用文件路径 spec 加载，但需先把包注册到 sys.modules
            spec = importlib.util.spec_from_file_location(mod_name, abspath)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            import sys
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        return getattr(module, 'Query', None)
    except Exception as e:
        logger.warning(f"load query plugin error from {abspath}: {e}")
        return None


def load_query_plugins(path: str):
    """从指定目录加载所有插件（每个文件需定义 class Query）。"""
    plugins = []
    for file_path, name in walk_py(path):
        # 跳过 base.py（非插件）
        if name == "base":
            continue
        QueryCls = _plugin_to_module(file_path, name)
        if QueryCls is not None:
            try:
                plugins.append(QueryCls())
            except Exception as e:
                from ..logger import get_logger
                get_logger().warning(f"instantiate plugin {name} error: {e}")
    return plugins
