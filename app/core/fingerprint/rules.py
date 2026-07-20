"""本地指纹规则加载（webapp.json），移植自原 app/utils/fingerprint.py。

webapp.json 结构: { 应用名: {html:[], title:[], headers:[], favicon_hash:[]} }
"""
from __future__ import annotations

import json

from ...config import Config

_web_app_rules: dict | None = None


def _load_web_app_rules() -> dict:
    global _web_app_rules
    if _web_app_rules is None:
        try:
            with open(Config.web_app_rule, encoding="utf-8") as f:
                _web_app_rules = json.load(f)
        except FileNotFoundError:
            _web_app_rules = {}
    return _web_app_rules


def load_fingerprint() -> list[dict]:
    """加载本地规则为 [{name, rule}] 列表。"""
    items = []
    for rule_name, rule in _load_web_app_rules().items():
        items.append({"name": rule_name, "rule": rule})
    return items


def fetch_fingerprint(content: bytes, headers: str, title: str, favicon_hash,
                      finger_list: list[dict]) -> list[str]:
    """根据规则列表匹配应用名（各字段间为或关系，移植原逻辑，含 gbk 回退）。

    兼容两种规则格式：
    - 旧式数组字段: html/title/headers/favicon_hash
    - 新式 fofa_rule: 表达式 DSL 字符串（如 header="Server: nginx"）
    """
    from .expr import evaluate
    from ...logger import get_logger
    logger = get_logger()
    finger_name_list: list[str] = []
    content_str = content.decode("utf-8", errors="replace") if content else ""

    for finger in finger_list:
        rule = finger["rule"]
        rule_name = finger["name"]

        # 优先尝试新式 fofa_rule（DSL）
        fofa_rule = rule.get("fofa_rule") or rule.get("human_rule")
        if fofa_rule:
            try:
                if evaluate(fofa_rule, {
                    "body": content_str, "header": headers, "title": title,
                    "icon_hash": favicon_hash,
                }):
                    finger_name_list.append(rule_name)
                    continue
            except Exception as e:
                logger.debug(f"fofa_rule error {rule_name}: {e}")
            # fofa_rule 不命中则继续尝试数组字段（部分规则两者并存）

        match_flag = False
        for html in rule.get("html", []):
            if html.encode("utf-8") in content:
                finger_name_list.append(rule_name)
                match_flag = True
                break
            try:
                if html.encode("gbk") in content:
                    finger_name_list.append(rule_name)
                    match_flag = True
                    break
            except Exception:
                logger.debug(f"error on fetch_fingerprint {html} to gbk")

        if match_flag:
            continue
        for header in rule.get("headers", []):
            if header in headers:
                finger_name_list.append(rule_name)
                match_flag = True
                break

        if match_flag:
            continue
        for rule_title in rule.get("title", []):
            if rule_title in title:
                finger_name_list.append(rule_name)
                match_flag = True
                break

        if match_flag:
            continue
        if isinstance(rule.get("favicon_hash"), list):
            for rule_hash in rule["favicon_hash"]:
                if rule_hash == favicon_hash:
                    finger_name_list.append(rule_name)
                    break

    return finger_name_list


def parse_human_rule(rule: str) -> dict | None:
    """解析人类可读规则（|| 分隔），移植自原 parse_human_rule。"""
    rule_map = {"html": [], "title": [], "headers": [], "favicon_hash": []}
    key_map = {"body": "html", "title": "title", "header": "headers", "icon_hash": "favicon_hash"}
    empty_flag = True

    for item in rule.split("||"):
        key_value = item.split("=")
        key = key_value[0].strip()
        if len(key_value) == 2:
            if key not in key_map:
                continue
            value = key_value[1].strip()
            if len(value) <= 6:
                continue
            if value[0] != '"' or value[-1] != '"':
                continue
            empty_flag = False
            value = value[1:-1]
            if key == "icon_hash":
                try:
                    value = int(value)
                except ValueError:
                    continue
            rule_map[key_map[key]].append(value)

    return None if empty_flag else rule_map


def transform_rule_map(rule: dict) -> str:
    """rule_map 转回 human_rule 字符串。"""
    key_map = {"html": "body", "title": "title", "headers": "header", "favicon_hash": "icon_hash"}
    human_rule_list = []
    for key, values in rule.items():
        if key not in key_map:
            continue
        for v in values:
            human_rule_list.append(f'{key_map[key]}="{v}"')
    return " || ".join(human_rule_list)
