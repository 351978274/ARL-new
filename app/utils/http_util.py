"""HTTP 响应解析工具，移植自原 app/utils/http.py。"""
from __future__ import annotations

import re

_title_pattern = re.compile(rb'<title>([^<]{1,200})</title>', re.I)


def get_title(body: bytes) -> str:
    """从页面源码提取 <title>。"""
    result = ''
    title = _title_pattern.findall(body or b'')
    if title:
        try:
            result = title[0].decode("utf-8")
        except Exception:
            result = title[0].decode("gbk", errors="replace")
    return result.strip()


def get_headers_text(status: int, reason: str, raw_headers: bytes, content: bytes,
                     content_length: int | None = None) -> str:
    """重建原始 HTTP 响应头文本（移植自原 get_headers）。

    httpx 没有 raw._fp.headers，故由调用方传入原始 header 字节。
    """
    version = "1.1"
    first_line = f"HTTP/{version} {status} {reason}\n"
    headers = raw_headers.decode("utf-8", errors="replace").strip() if raw_headers else ""
    if content_length is None:
        content_length = len(content) if content else 0
    if "Content-Length" not in headers:
        headers = f"{headers}\nContent-Length: {content_length}"
    return first_line + headers
