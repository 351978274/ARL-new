"""域名工具，移植自原 app/utils/domain.py。

提供域名有效性、黑名单、范围、fuzz 校验等。
"""
from __future__ import annotations

import tld

from ..config import Config

# 黑名单缓存（惰性加载）
_blackdomain_list: list[str] | None = None
_blackhexie_list: list[str] | None = None


def _load_blackdomain() -> list[str]:
    global _blackdomain_list
    if _blackdomain_list is None:
        try:
            with open(Config.black_domain_path, encoding="utf-8") as f:
                _blackdomain_list = f.readlines()
        except FileNotFoundError:
            _blackdomain_list = []
    return _blackdomain_list


def _load_blackhexie() -> list[str]:
    global _blackhexie_list
    if _blackhexie_list is None:
        try:
            with open(Config.black_hexie_path, encoding="utf-8") as f:
                _blackhexie_list = f.readlines()
        except FileNotFoundError:
            _blackhexie_list = []
    return _blackhexie_list


def reload_blacklist():
    """重新加载黑名单（测试/热更新用）。"""
    global _blackdomain_list, _blackhexie_list
    _blackdomain_list = None
    _blackhexie_list = None
    _load_blackdomain()
    _load_blackhexie()


def check_domain_black(domain: str) -> bool:
    """域名是否在黑名单或和谐词列表中。解析异常时 fail-closed 返回 True。"""
    from ..logger import get_logger
    logger = get_logger()

    # 黑名单后缀匹配
    for item in _load_blackdomain():
        item = item.strip()
        if item and domain.endswith(item):
            return True

    # 和谐词匹配（子域名部分）
    try:
        for item in _load_blackhexie():
            item = item.strip()
            _, _, subdomain = tld.parse_tld(domain, fix_protocol=True, fail_silently=True)
            if subdomain and item and item.strip() in subdomain:
                return True
    except Exception as e:
        logger.warning(f"Error on: {domain}, {e}")
        return True

    return False


def is_forbidden_domain(domain: str) -> bool:
    """域名是否匹配禁止域名列表。"""
    for f_domain in Config.FORBIDDEN_DOMAINS:
        if not f_domain:
            continue
        if domain.endswith("." + f_domain):
            return True
        if domain == f_domain:
            return True
    return False


def is_valid_domain(domain: str) -> bool:
    """基础域名有效性校验。"""
    from . import domain_parsed
    if "." not in domain:
        return False

    invalid_chars = "!@#$%&*():_\\"
    for c in invalid_chars:
        if c in domain:
            return False

    # 不允许下发特殊二级域名
    if domain in ["com.cn", "gov.cn", "edu.cn"]:
        return False

    return bool(domain_parsed(domain))


def is_valid_fuzz_domain(domain: str) -> bool:
    """fuzz 模板有效性校验（必须含 {fuzz}）。"""
    from . import domain_parsed
    if "{fuzz}" not in domain:
        return False

    domain = domain.replace("{fuzz}", "12fuzz12")
    parsed = domain_parsed(domain)
    if not parsed:
        return False

    if "12fuzz12" in parsed['fld']:
        return False
    return True


def is_in_scope(src_domain: str, target_domain: str) -> bool:
    """src 是否与 target 同主域且为其子域或相等。"""
    from . import get_fld
    fld1 = get_fld(src_domain)
    fld2 = get_fld(target_domain)
    if not fld1 or not fld2:
        return False
    if fld1 != fld2:
        return False
    if src_domain == target_domain:
        return True
    return src_domain.endswith("." + target_domain)


def is_in_scopes(domain: str, scopes: list[str]) -> bool:
    for target_scope in scopes:
        if is_in_scope(domain, target_scope):
            return True
    return False


def cut_first_name(domain: str) -> str | None:
    """剔除子域名最左侧一节标签。"""
    domain_parts, non_zero_i, _ = tld.utils.process_url(domain, fix_protocol=True, fail_silently=True)
    if not domain_parts:
        return None
    if non_zero_i == 1:
        return None
    return ".".join(domain_parts[1:])
