"""fingerprint 引擎包：expr DSL + 本地规则 + DB 规则缓存。"""
from __future__ import annotations

from .expr import (
    ExprError,
    check_expression,
    check_expression_with_error,
    evaluate,
    evaluate_expression,
    parse_expression,
)
from .identify import (
    FingerPrint,
    FingerPrintCache,
    finger_db_cache,
    finger_db_identify,
    have_human_rule_from_db,
)
from .rules import (
    fetch_fingerprint,
    load_fingerprint,
    parse_human_rule,
    transform_rule_map,
)

__all__ = [
    # expr
    "ExprError", "parse_expression", "evaluate_expression", "evaluate",
    "check_expression", "check_expression_with_error",
    # rules
    "load_fingerprint", "fetch_fingerprint", "parse_human_rule", "transform_rule_map",
    # identify / cache
    "FingerPrint", "FingerPrintCache", "finger_db_cache", "finger_db_identify",
    "have_human_rule_from_db",
]
