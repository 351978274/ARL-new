"""core 包：核心扫描引擎（异步）— HTTP 客户端、DNS、指纹引擎、并发基类、任务执行器。"""
from __future__ import annotations

from .base_task import AsyncBaseTask, AsyncMapTask, thread_map
from .dns import domain_parsed, get_cname, get_fld, get_ip
from .http_client import HttpResponse, http_req, http_req_simple
from .fingerprint import (
    ExprError,
    FingerPrint,
    check_expression,
    check_expression_with_error,
    evaluate,
    evaluate_expression,
    fetch_fingerprint,
    finger_db_cache,
    finger_db_identify,
    load_fingerprint,
    parse_expression,
)

__all__ = [
    "AsyncBaseTask", "AsyncMapTask", "thread_map",
    "get_ip", "get_cname", "domain_parsed", "get_fld",
    "http_req", "http_req_simple", "HttpResponse",
    "ExprError", "FingerPrint", "check_expression", "check_expression_with_error",
    "evaluate", "evaluate_expression", "parse_expression",
    "fetch_fingerprint", "finger_db_cache", "finger_db_identify", "load_fingerprint",
]
