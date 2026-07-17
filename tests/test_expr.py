"""指纹表达式 DSL 与指纹匹配测试。"""
import pytest

from app.core.fingerprint import expr
from app.core.fingerprint.rules import fetch_fingerprint, load_fingerprint


VARS = {"body": "xxabcyy welcome", "title": "say hello", "header": "Server: nginx/1.20", "icon_hash": 12345}


class TestExprParse:
    def test_simple_contains(self):
        assert expr.evaluate('body="abc"', VARS)

    def test_and(self):
        assert expr.evaluate('body="abc" && title="hello"', VARS)
        assert not expr.evaluate('body="abc" && title="nope"', VARS)

    def test_or(self):
        assert expr.evaluate('body="nope" || title="hello"', VARS)
        assert not expr.evaluate('body="nope" || title="nope"', VARS)

    def test_not(self):
        assert expr.evaluate('!body="zzz"', VARS)
        assert not expr.evaluate('!body="abc"', VARS)

    def test_paren(self):
        assert expr.evaluate('(body="a" || body="zzz") && title="hello"', VARS)

    def test_str_eq(self):
        assert expr.evaluate('title=="say hello"', VARS)
        assert not expr.evaluate('title=="hello"', VARS)

    def test_not_contains(self):
        assert expr.evaluate('body!="zzz"', VARS)
        assert not expr.evaluate('body!="abc"', VARS)

    def test_icon_hash_int(self):
        # icon_hash 为整数，规则中用整数字面量（无引号），= 退化为相等
        assert expr.evaluate('icon_hash=12345', VARS)
        assert not expr.evaluate('icon_hash=99999', VARS)


class TestExprCheck:
    @pytest.mark.parametrize("rule", [
        'body="abc"', 'header="x" || body="y"', 'title="a" && header="b"',
        '!body="x"', '(body="a" || body="b") && title="t"',
    ])
    def test_valid(self, rule):
        assert expr.check_expression(rule)

    @pytest.mark.parametrize("rule", [
        'body=', '&& body="x"', 'body=', '= "x"', 'body="unterminated',
    ])
    def test_invalid(self, rule):
        assert not expr.check_expression(rule)


class TestFetchFingerprint:
    def test_load_rules(self):
        rules = load_fingerprint()
        assert len(rules) > 100

    def test_match_nginx(self):
        rules = load_fingerprint()
        hit = fetch_fingerprint(b"", "Server: nginx/1.20", "", 0, rules)
        assert "Nginx" in hit

    def test_no_match(self):
        rules = load_fingerprint()
        hit = fetch_fingerprint(b"nothing here xxx", "X-Custom: foo", "blank", 0, rules)
        # 不应误报知名应用
        assert "Nginx" not in hit
