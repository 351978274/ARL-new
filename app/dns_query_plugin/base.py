"""子域名查询插件基类 + 批量执行器，移植自原 app/services/dns_query.py。

DNSQueryBase 提供插件契约（init_key / sub_domains）与统一过滤逻辑。
run_query_plugin 并发执行多个插件，返回 [{"domain","source"}]。
"""
from __future__ import annotations

import asyncio
import time

from ..config import Config
from ..logger import get_logger
from ..utils import check_domain_black, is_valid_domain
from ..core.dns import domain_parsed

logger = get_logger()


class DNSQueryBase:
    """所有数据源插件的基类。子类实现 init_key 与 sub_domains。"""

    def __init__(self):
        self.source_name: str | None = None
        self.logger = get_logger()

    def init_key(self, **kwargs):
        """初始化各数据源所需的 key / 参数。"""
        raise NotImplementedError()

    async def sub_domains(self, target: str) -> list[str]:
        """返回原始子域名列表（由 query 统一过滤）。"""
        raise NotImplementedError()

    async def query(self, target: str) -> list[str]:
        """模板方法：调用 sub_domains 后做统一过滤。"""
        t1 = time.time()
        self.logger.info(f"start query {target} on {self.source_name}")
        try:
            domains = await self.sub_domains(target)
        except Exception as e:
            self.logger.error(f"{self.source_name} error: {e}")
            return []

        if not isinstance(domains, list):
            self.logger.warning(f"{domains} is not list")
            return []

        subdomains: list[str] = []
        for domain in domains:
            domain = domain.strip("*.")
            domain = domain.lower()
            if not domain:
                continue
            if not domain.endswith(f".{target}"):
                continue
            # 删除过长的域名
            if len(domain) - len(target) >= Config.DOMAIN_MAX_LEN:
                continue
            if not is_valid_domain(domain):
                continue
            if check_domain_black(domain):
                continue
            if domain_parsed(domain):
                subdomains.append(domain)

        subdomains = list(set(subdomains))
        self.logger.info(f"end query {target} on {self.source_name}, "
                         f"source:{len(domains)}, real:{len(subdomains)} ({time.time()-t1:.2f}s)")
        return subdomains


async def run_plugin(p: DNSQueryBase, target: str):
    """运行单个插件：读取配置、判断 enable、init_key 后执行 query。"""
    source_name = p.source_name
    source_kwargs_raw = Config.QUERY_PLUGIN_CONFIG.get(source_name, {})
    if source_kwargs_raw:
        if not isinstance(source_kwargs_raw, dict):
            logger.warning(f"{source_name} config {source_kwargs_raw} is not dict")
            return source_name, []
        source_kwargs = dict(source_kwargs_raw)
        plugin_enable = source_kwargs.pop("enable", True)
        if not plugin_enable:
            logger.debug(f"skip {source_name}, enable is set false")
            return source_name, []
        if source_kwargs:
            if all(source_kwargs.values()):
                p.init_key(**source_kwargs)
            else:
                logger.debug(f"skip {source_name}, config is not set")
                return source_name, []
    results = await p.query(target)
    logger.debug(f"run {source_name} target:{target}, result:{len(results)}")
    return source_name, results


async def run_query_plugin(target: str, sources: list[str] | None = None) -> list[dict]:
    """并发运行多个数据源插件，返回去重的 [{"domain","source"}]。"""
    from ..utils.query_loader import load_query_plugins
    if sources is None:
        sources = []
    plugins = load_query_plugins(Config.dns_query_plugin_path)
    if sources:
        plugins = [p for p in plugins if p.source_name in sources]
    logger.debug(f"load plugins len:{len(plugins)} sources: {sources}")

    ret: list[dict] = []
    subdomains: set[str] = set()
    t1 = time.time()

    async def _safe_run(p):
        try:
            return await run_plugin(p, target)
        except Exception as e:
            err = str(e)
            if "please set fofa key" in err:
                logger.debug(err)
            else:
                logger.error(f"{p.source_name} error {type(e).__name__} {err}")
            return None

    results = await asyncio.gather(*[_safe_run(p) for p in plugins])
    for r in results:
        if not r:
            continue
        source_name, domain_list = r
        for domain in domain_list:
            if domain in subdomains:
                continue
            ret.append({"domain": domain, "source": source_name})
            subdomains.add(domain)

    logger.info(f"{target} subdomains result {len(subdomains)} ({time.time()-t1:.2f}s)")
    return ret
