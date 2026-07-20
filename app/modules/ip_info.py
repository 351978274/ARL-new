"""IP 信息对象，对应 MongoDB ip 集合。"""
from __future__ import annotations

from .models import BaseInfo


class PortInfo(BaseInfo):
    """单个端口信息。

    文档结构: {port_id, service_name, version, protocol, product}
    """

    def __init__(self, port_id, service_name: str = "", version: str = "",
                 protocol: str = "tcp", product: str = ""):
        self.port_id = port_id
        self.service_name = service_name
        self.version = version
        self.protocol = protocol
        self.product = product

    def __eq__(self, other):
        return isinstance(other, PortInfo) and self.port_id == other.port_id

    def __hash__(self):
        return hash(self.port_id)

    def _dump_json(self):
        return {
            "port_id": self.port_id,
            "service_name": self.service_name,
            "version": self.version,
            "protocol": self.protocol,
            "product": self.product,
        }


class IPInfo(BaseInfo):
    """IP 信息，包含端口/OS/GeoIP/CDN。

    geo_asn/geo_city/ip_type 惰性计算，仅对 PUBLIC 类型 IP 计算 GeoIP。
    文档结构: {ip, domain: [], port_info: [], os_info: {}, ip_type, geo_asn, geo_city, geo_country, cdn_name}
    """

    def __init__(self, ip: str, port_info, os_info, domain, cdn_name: str = ""):
        self.ip = ip
        self.port_info_list = port_info
        self.os_info = os_info
        self.domain = domain
        self.cdn_name = cdn_name
        self._geo_asn = None
        self._geo_city = None
        self._geo_country = None
        self._ip_type = None

    @property
    def ip_type(self):
        if self._ip_type is None:
            from ..utils.ip_util import get_ip_type
            self._ip_type = get_ip_type(self.ip)
        return self._ip_type

    @property
    def geo_asn(self):
        if self._geo_asn is None:
            if self.ip_type == "PUBLIC":
                from ..utils.ip_util import get_ip_asn
                self._geo_asn = get_ip_asn(self.ip)
            else:
                self._geo_asn = {}
        return self._geo_asn

    @property
    def geo_city(self):
        if self._geo_city is None:
            if self.ip_type == "PUBLIC":
                from ..utils.ip_util import get_ip_city
                self._geo_city = get_ip_city(self.ip)
            else:
                self._geo_city = {}
        return self._geo_city

    @property
    def geo_country(self):
        if self._geo_country is None:
            if self.ip_type == "PUBLIC":
                from ..utils.ip_util import get_ip_country
                self._geo_country = get_ip_country(self.ip)
            else:
                self._geo_country = {}
        return self._geo_country

    def __eq__(self, other):
        return isinstance(other, IPInfo) and self.ip == other.ip

    def __hash__(self):
        return hash(self.ip)

    def _dump_json(self):
        return {
            "ip": self.ip,
            "domain": self.domain,
            "port_info": [p.dump_json(flag=False) for p in self.port_info_list],
            "os_info": self.os_info,
            "ip_type": self.ip_type,
            "geo_asn": self.geo_asn,
            "geo_city": self.geo_city,
            "geo_country": self.geo_country,
            "cdn_name": self.cdn_name,
        }
