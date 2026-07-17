"""CDN 识别，移植自原 app/utils/cdn.py。"""
from __future__ import annotations

import json

from ..config import Config
from .IPy import IP

cdn_ip_cidr_list: list[str] = []
cdn_cname_list: list[str] = []
cdn_info: list[dict] = []


def _init_cdn_info():
    global cdn_ip_cidr_list, cdn_cname_list, cdn_info
    if not cdn_info:
        cdn_ip_cidr_list = []
        cdn_cname_list = []
        with open(Config.CDN_JSON_PATH, encoding="utf-8") as f:
            cdn_info = json.load(f)
        for item in cdn_info:
            cdn_cname_list.extend(item["cname_domain"])
            if item.get("ip_cidr"):
                cdn_ip_cidr_list.extend(item["ip_cidr"])


def _ip_in_cidr_list(ip: str) -> bool:
    for item in cdn_ip_cidr_list:
        if IP(ip) in IP(item):
            return True
    return False


def _cname_in_cname_list(cname: str) -> bool:
    for item in cdn_cname_list:
        if cname.endswith("." + item):
            return True
    return False


def get_cdn_name_by_ip(ip: str) -> str:
    from ..logger import get_logger
    logger = get_logger()
    try:
        _init_cdn_info()
        if not _ip_in_cidr_list(ip):
            return ""
        for item in cdn_info:
            if item.get("ip_cidr"):
                for ip_cidr in item["ip_cidr"]:
                    if IP(ip) in IP(ip_cidr):
                        return item["name"]
    except Exception as e:
        logger.warning(f"{e} {ip}")
        return ""
    return ""


def _get_cdn_name_by_cname(cname: str) -> str:
    from ..logger import get_logger
    logger = get_logger()
    try:
        _init_cdn_info()
        if not _cname_in_cname_list(cname):
            return ""
        for item in cdn_info:
            for target in item["cname_domain"]:
                if cname.endswith("." + target):
                    return item["name"]
    except Exception as e:
        logger.warning(f"{e} {cname}")
        return ""
    return ""


def get_cdn_name_by_cname(cname: str) -> str:
    cdn_name = _get_cdn_name_by_cname(cname)
    if not cdn_name:
        for check in ["gslb", "dns", "cache"]:
            if check in cname:
                return "CDN"
    return cdn_name
