"""DNS 查询插件加载与基础契约测试。"""
import pytest

from app.config import Config
from app.utils.query_loader import load_query_plugins
from app.dns_query_plugin.base import DNSQueryBase, run_query_plugin


EXPECTED_SOURCES = {
    "alienvault", "certspotter", "chaos", "crtsh", "fofa", "hunter_qax",
    "passivetotal", "quake_360", "rapiddns", "securitytrails", "virustotal", "zoomeye",
}


class TestPluginLoading:
    def test_all_plugins_load(self):
        plugins = load_query_plugins(Config.dns_query_plugin_path)
        names = {p.source_name for p in plugins}
        missing = EXPECTED_SOURCES - names
        assert not missing, f"缺少插件: {missing}"
        assert len(plugins) == 12

    def test_plugins_are_dnsquerybase(self):
        plugins = load_query_plugins(Config.dns_query_plugin_path)
        for p in plugins:
            assert isinstance(p, DNSQueryBase)
            assert p.source_name is not None

    def test_each_plugin_has_sub_domains(self):
        plugins = load_query_plugins(Config.dns_query_plugin_path)
        for p in plugins:
            # sub_domains 与 init_key 必须存在
            assert hasattr(p, "sub_domains")
            assert callable(getattr(p, "sub_domains"))


class TestBaseQueryFiltering:
    """测试 DNSQueryBase.query 的过滤逻辑（用 mock sub_domains）。"""

    @pytest.mark.asyncio
    async def test_query_filters_invalid(self):
        class FakePlugin(DNSQueryBase):
            def __init__(self):
                super().__init__()
                self.source_name = "fake"

            async def sub_domains(self, target):
                # 包含：合法、过长、非法字符、非后缀匹配、通配
                return [
                    f"www.{target}",            # 合法
                    f"{'a' * 30}.{target}",     # 过长（超过 DOMAIN_MAX_LEN）
                    f"bad@.{target}",           # 非法字符
                    "other.com",                # 非后缀匹配
                    f"*.wild.{target}",         # 通配符（应去 *）
                    f"api.{target}",            # 合法
                ]

        p = FakePlugin()
        result = await p.query("example.com")
        assert "www.example.com" in result
        assert "api.example.com" in result
        assert "wild.example.com" in result  # 去 * 后合法
        assert "other.com" not in result
        # 过长和非法字符应被过滤
        assert not any("@" in r for r in result)
