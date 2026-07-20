"""异步 DNS 解析，移植自原 app/utils/__init__.py 的 get_ip / get_cname。

使用 dnspython 的 async resolver。
"""
from __future__ import annotations

import dns.resolver
import dns.exception

_resolver: dns.resolver.Resolver | None = None


def _get_resolver() -> dns.resolver.Resolver:
    global _resolver
    if _resolver is None:
        _resolver = dns.resolver.Resolver()
        _resolver.timeout = 5
        _resolver.lifetime = 6
    return _resolver


async def get_ip(domain: str, log_flag: bool = True) -> list[str]:
    """异步解析 A 记录，过滤 0.0.0.1。"""
    from ..logger import get_logger
    logger = get_logger()
    domain = domain.strip()
    ips: list[str] = []
    try:
        answers = _get_resolver().resolve(domain, 'A')
        for rdata in answers:
            if str(rdata) == '0.0.0.1':
                continue
            ips.append(str(rdata))
    except dns.resolver.NXDOMAIN as e:
        if log_flag:
            logger.info(f"{domain} {e}")
    except Exception as e:
        if log_flag:
            logger.warning(f"{domain} {e}")
    return ips


async def get_cname(domain: str, log_flag: bool = True) -> list[str]:
    """异步解析 CNAME 记录。"""
    from ..logger import get_logger
    logger = get_logger()
    domain = domain.strip()
    cnames: list[str] = []
    try:
        answers = _get_resolver().resolve(domain, 'CNAME')
        for rdata in answers:
            cnames.append(str(rdata.target).strip(".").lower())
    except dns.resolver.NoAnswer as e:
        if log_flag:
            logger.debug(e)
    except Exception as e:
        logger.warning(f"{domain} {e}")
    return cnames


def domain_parsed(domain: str, fail_silently: bool = True) -> dict | None:
    """解析域名结构 {subdomain, domain, fld}（同步，tld 库）。"""
    from tld import get_tld
    try:
        res = get_tld(domain, fix_protocol=True, as_object=True)
        return {"subdomain": res.subdomain, "domain": res.domain, "fld": res.fld}
    except Exception:
        if not fail_silently:
            raise
        return None


def get_fld(d: str) -> str | None:
    """获取主域。"""
    res = domain_parsed(d)
    return res["fld"] if res else None
