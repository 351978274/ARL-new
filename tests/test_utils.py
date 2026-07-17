"""核心工具函数测试：域名/IP/URL 校验、端口解析、时间。"""
import pytest

from app.utils import (
    build_port_custom,
    is_in_scope,
    is_vaild_ip_target,
    is_valid_domain,
    is_valid_exclude_ports,
    not_in_black_ips,
    domain_parsed,
    get_fld,
    normal_url,
    cut_filename,
    get_hostname,
    same_netloc,
    urlsimilar,
)
from app.utils.time_util import curr_date, time2date


class TestDomain:
    def test_valid(self):
        assert is_valid_domain("www.example.com")
        assert is_valid_domain("a.b.example.cn")

    def test_invalid_no_dot(self):
        assert not is_valid_domain("localhost")

    def test_invalid_special_chars(self):
        assert not is_valid_domain("a@b.com")
        assert not is_valid_domain("a*b.com")

    def test_special_tld(self):
        assert not is_valid_domain("com.cn")
        assert not is_valid_domain("gov.cn")

    def test_parsed(self):
        p = domain_parsed("www.example.com")
        assert p["fld"] == "example.com"
        assert p["subdomain"] == "www"

    def test_fld(self):
        assert get_fld("a.b.example.com") == "example.com"

    def test_in_scope(self):
        assert is_in_scope("a.example.com", "example.com")
        assert not is_in_scope("a.other.com", "example.com")


class TestIP:
    @pytest.mark.parametrize("t", ["1.2.3.4", "10.0.0.0/24", "192.168.1.1-50"])
    def test_valid_ip_target(self, t):
        assert is_vaild_ip_target(t)

    def test_invalid_ip_target(self):
        assert not is_vaild_ip_target("not-an-ip")
        assert not is_vaild_ip_target("1.2.3")

    def test_not_in_black(self):
        assert not_in_black_ips("8.8.8.8")
        assert not not_in_black_ips("127.0.0.1")


class TestPort:
    def test_build_simple(self):
        assert build_port_custom("80,443") == ["80", "443"]

    def test_build_range(self):
        result = build_port_custom("8080-8082")
        assert result == ["8080", "8081", "8082"]

    def test_exclude_valid(self):
        assert is_valid_exclude_ports("80,443")
        assert is_valid_exclude_ports("1000-2000")

    def test_exclude_invalid(self):
        assert not is_valid_exclude_ports("abc")
        assert not is_valid_exclude_ports("70000")


class TestURL:
    def test_normal_url(self):
        assert normal_url("http://example.com:80/a") == "http://example.com/a"
        assert normal_url("https://x.com:443/") == "https://x.com/"

    def test_normal_url_port(self):
        assert normal_url("http://example.com:8080/a") == "http://example.com:8080/a"

    def test_hostname(self):
        assert get_hostname("http://a.com/x") == "a.com"
        assert get_hostname("b.com") == "b.com"

    def test_cut_filename(self):
        assert cut_filename("http://a.com/path/to/file.js") == "http://a.com/path/to"

    def test_same_netloc(self):
        assert same_netloc("http://a.com/x", "http://a.com/y")
        assert not same_netloc("http://a.com/x", "http://b.com/y")

    def_url_similar = "http://auto.sohu.com/7/0903/70/column213227075.shtml"

    def test_similar(self):
        u1 = "http://auto.sohu.com/7/0903/70/column213227075.shtml"
        u2 = "http://auto.sohu.com/7/4354/34/column443243545.shtml"
        assert urlsimilar(u1) == urlsimilar(u2)


class TestTime:
    def test_curr_date(self):
        d = curr_date()
        assert len(d) == 19  # YYYY-MM-DD HH:MM:SS

    def test_time2date(self):
        assert time2date(0) == "1970-01-01 08:00:00"  # CST
