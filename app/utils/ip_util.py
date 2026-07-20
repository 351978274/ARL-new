"""IP 工具，移植自原 app/utils/ip.py。

geoip2 reader 在每次调用时打开/关闭，避免多线程共享。
GeoIP 数据库路径来自 Config.GEOIP_{CITY,ASN,COUNTRY}，缺失时对应函数返回空。
"""
from __future__ import annotations

import re

import geoip2.database

from ..config import Config
from .IPy import IP


def is_vaild_ip_target(ip: str) -> bool:
    """支持 单IP / CIDR / IP段(1.2.3.4-10)。"""
    return bool(re.match(
        r"^\d+\.\d+\.\d+\.\d+$|^\d+\.\d+\.\d+\.\d+/\d+$|^\d+\.\d+\.\d+.\d+-\d+$", ip))


def transfer_ip_scope(target: str) -> str | None:
    """目标 IP/IP段 转合法 CIDR。"""
    from ..logger import get_logger
    logger = get_logger()
    try:
        return IP(target, make_net=True).strNormal(1)
    except Exception as e:
        logger.warning(f"error on ip_scope {target} {e}")
        return None


def not_in_black_ips(target: str) -> bool:
    """目标 IP 是否不在黑名单中。"""
    from ..logger import get_logger
    logger = get_logger()
    try:
        if "-" in target:
            target = target.split("-")[0]
        if "/" in target:
            target = target.split("/")[0]
        for ip in Config.BLACK_IPS:
            if IP(target) in IP(ip):
                return False
    except Exception as e:
        logger.warning(f"error on check black ip {target} {e}")
    return True


def get_ip_asn(ip: str) -> dict:
    from ..logger import get_logger
    logger = get_logger()
    if not Config.GEOIP_ASN:
        return {}
    item: dict = {}
    try:
        reader = geoip2.database.Reader(Config.GEOIP_ASN)
        response = reader.asn(ip)
        item["number"] = response.autonomous_system_number
        item["organization"] = response.autonomous_system_organization
        reader.close()
    except Exception as e:
        logger.warning(f"{e} {ip}")
    return item


def get_ip_city(ip: str) -> dict:
    from ..logger import get_logger
    logger = get_logger()
    if not Config.GEOIP_CITY:
        return {}
    try:
        reader = geoip2.database.Reader(Config.GEOIP_CITY)
        response = reader.city(ip)
        item = {
            "city": response.city.name,
            "latitude": response.location.latitude,
            "longitude": response.location.longitude,
            "country_name": response.country.name,
            "country_code": response.country.iso_code,
            "region_name": response.subdivisions.most_specific.name,
            "region_code": response.subdivisions.most_specific.iso_code,
        }
        reader.close()
        return item
    except Exception as e:
        logger.warning(f"{e} {ip}")
        return {}


def get_ip_country(ip: str) -> dict:
    """仅依赖 GeoLite2-Country 数据库，比 City 库小很多，适合只关心国家的场景。"""
    from ..logger import get_logger
    logger = get_logger()
    if not Config.GEOIP_COUNTRY:
        return {}
    try:
        reader = geoip2.database.Reader(Config.GEOIP_COUNTRY)
        response = reader.country(ip)
        item = {
            "country_name": response.country.name,
            "country_code": response.country.iso_code,
        }
        reader.close()
        return item
    except Exception as e:
        logger.warning(f"{e} {ip}")
        return {}


def get_ip_type(ip: str) -> str:
    from ..logger import get_logger
    logger = get_logger()
    try:
        # 国内好多企业把这两个段当内网
        if ip.startswith("9.") or ip.startswith("11."):
            return "PRIVATE"
        ip_type = IP(ip).iptype()
        if ip_type in ["CARRIER_GRADE_NAT", "LOOPBACK", "RESERVED"]:
            return "PRIVATE"
        return ip_type
    except Exception as e:
        logger.warning(f"{e} {ip}")
        return "ERROR"


def ip_in_scope(ip: str, scope_list: list[str]) -> bool:
    from ..logger import get_logger
    logger = get_logger()
    for item in scope_list:
        try:
            if IP(ip) in IP(item):
                return True
        except Exception as e:
            logger.warning(f"{e} {ip} {item}")
    return False
