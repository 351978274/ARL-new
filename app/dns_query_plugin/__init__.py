"""dns_query_plugin 包：13 个子域名数据源插件（异步）。

对外暴露：
    DNSQueryBase, run_plugin, run_query_plugin
插件由 query_loader 动态加载（每个 .py 文件需定义 class Query(DNSQueryBase)）。
"""
from __future__ import annotations

from .base import DNSQueryBase, run_plugin, run_query_plugin

__all__ = ["DNSQueryBase", "run_plugin", "run_query_plugin"]
