"""异步 HTTP 客户端，移植自原 app/utils/conn.py 的 http_req + patch_content。

关键点：
- 用 httpx.AsyncClient 替代 requests
- 流式读取 + 读超时（对应原 patch_content 的逐块超时机制）
- verify=False / allow_redirects=False / 自定义 UA / 代理（Config.PROXY_URL）
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import Config

CONTENT_CHUNK_SIZE = 10 * 1024
UA = ("Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36")

# 禁用 SSL 警告（httpx 默认不打印，无需 urllib3 disable）


def _proxy_kwargs() -> dict:
    if Config.PROXY_URL:
        return {"proxy": Config.PROXY_URL}
    return {}


def _default_headers(headers: dict | None) -> dict:
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    headers.setdefault("Cache-Control", "max-age=0")
    return headers


class HttpResponse:
    """对 httpx 流式响应的包装，提供 content（带读超时）与原始 header 字节。"""

    def __init__(self, response: httpx.Response, content: bytes):
        self._response = response
        self._content = content

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> httpx.Headers:
        return self._response.headers

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def text(self) -> str:
        return self._content.decode("utf-8", errors="replace")

    @property
    def url(self) -> str:
        return str(self._response.url)

    def json(self) -> Any:
        import json as _json
        return _json.loads(self._content)


async def _stream_read(response: httpx.Response, read_timeout: float) -> bytes:
    """流式读取响应体，超过 read_timeout 秒抛 httpx.ReadTimeout（对应 patch_content）。"""
    body = b""
    start_at = time.time()
    async for chunk in response.aiter_bytes(CONTENT_CHUNK_SIZE):
        body += chunk
        if read_timeout and (time.time() - start_at) >= read_timeout:
            raise httpx.ReadTimeout(f"read http response timeout: {read_timeout}", request=response.request)
    return body


async def http_req(url: str, method: str = 'get', **kwargs) -> HttpResponse:
    """异步 HTTP 请求，等价于原 http_req。

    默认 verify=False, allow_redirects=False, timeout=(10.1, 30.1)。
    流式读取以支持读超时控制。
    """
    # 分离自定义参数
    verify = kwargs.pop('verify', False)
    raw_timeout = kwargs.pop('timeout', (10.1, 30.1))
    allow_redirects = kwargs.pop('allow_redirects', False)
    headers = _default_headers(kwargs.pop("headers", None))

    # 解析 timeout：元组(connect, read) 或单值
    if isinstance(raw_timeout, (tuple, list)):
        connect_timeout = raw_timeout[0] if raw_timeout[0] else 10.1
        read_timeout = raw_timeout[1] if len(raw_timeout) > 1 and raw_timeout[1] else 30.1
    else:
        connect_timeout = raw_timeout
        read_timeout = raw_timeout

    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout)

    client_kwargs: dict[str, Any] = {
        "verify": verify,
        "timeout": timeout,
        "follow_redirects": allow_redirects,
        "headers": headers,
        "trust_env": False,
    }
    client_kwargs.update(_proxy_kwargs())

    method_lower = method.lower()
    async with httpx.AsyncClient(**client_kwargs) as client:
        request_method = getattr(client, method_lower, client.get)
        async with request_method(url, **kwargs) as response:
            content = await _stream_read(response, read_timeout)
            return HttpResponse(response, content)


async def http_req_simple(url: str, method: str = 'get', **kwargs) -> HttpResponse:
    """简易版：不强制流式读超时，适合小响应（如 favicon）。"""
    kwargs.setdefault('verify', False)
    kwargs.setdefault('timeout', (10.1, 30.1))
    kwargs.setdefault('follow_redirects', False)
    headers = _default_headers(kwargs.pop("headers", None))
    client_kwargs = {"verify": kwargs.pop('verify'), "timeout": kwargs.pop('timeout'),
                     "follow_redirects": kwargs.pop('follow_redirects'), "headers": headers,
                     "trust_env": False}
    client_kwargs.update(_proxy_kwargs())
    async with httpx.AsyncClient(**client_kwargs) as client:
        request_method = getattr(client, method.lower(), client.get)
        r = await request_method(url, **kwargs)
        return HttpResponse(r, r.content)
