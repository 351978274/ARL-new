"""异步 HTTP 客户端，移植自原 app/utils/conn.py 的 http_req + patch_content。

关键点：
- 用 httpx.AsyncClient 替代 requests
- 流式读取 + 读超时（对应原 patch_content 的逐块超时机制）
- verify=False / allow_redirects=False / 自定义 UA / 代理（Config.PROXY_URL）
"""
from __future__ import annotations

import json as _json
import time
from typing import Any

import httpx

from ..config import Config

CONTENT_CHUNK_SIZE = 10 * 1024
DEFAULT_CONNECT_TIMEOUT = 10.1
DEFAULT_READ_TIMEOUT = 30.1
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


def _parse_timeout(raw_timeout) -> tuple[float, float]:
    """解析 timeout 为 (connect, read)；空值回退到默认。"""
    if isinstance(raw_timeout, (tuple, list)):
        connect = raw_timeout[0] if raw_timeout and raw_timeout[0] else DEFAULT_CONNECT_TIMEOUT
        read = (raw_timeout[1] if len(raw_timeout) > 1 and raw_timeout[1]
                else DEFAULT_READ_TIMEOUT)
        return float(connect), float(read)
    if raw_timeout:
        return float(raw_timeout), float(raw_timeout)
    return DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT


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
        return _json.loads(self._content)


async def _stream_read(response: httpx.Response, read_timeout: float) -> bytes:
    """流式读取响应体，超过 read_timeout 秒抛 httpx.ReadTimeout（对应 patch_content）。"""
    body = bytearray()
    start_at = time.time()
    async for chunk in response.aiter_bytes(CONTENT_CHUNK_SIZE):
        body.extend(chunk)
        if read_timeout and (time.time() - start_at) >= read_timeout:
            raise httpx.ReadTimeout(f"read http response timeout: {read_timeout}", request=response.request)
    return bytes(body)


def _build_client_kwargs(verify, raw_timeout, allow_redirects, headers) -> dict[str, Any]:
    connect_timeout, read_timeout = _parse_timeout(raw_timeout)
    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout,
                            write=read_timeout, pool=connect_timeout)
    client_kwargs: dict[str, Any] = {
        "verify": verify,
        "timeout": timeout,
        "follow_redirects": allow_redirects,
        "headers": headers,
        "trust_env": False,
    }
    client_kwargs.update(_proxy_kwargs())
    return client_kwargs, read_timeout


async def http_req(url: str, method: str = 'get', **kwargs) -> HttpResponse:
    """异步 HTTP 请求，等价于原 http_req。

    默认 verify=False, allow_redirects=False, timeout=(10.1, 30.1)。
    流式读取以支持读超时控制。
    """
    verify = kwargs.pop('verify', False)
    raw_timeout = kwargs.pop('timeout', (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT))
    allow_redirects = kwargs.pop('allow_redirects', False)
    headers = _default_headers(kwargs.pop("headers", None))

    client_kwargs, read_timeout = _build_client_kwargs(verify, raw_timeout, allow_redirects, headers)

    async with httpx.AsyncClient(**client_kwargs) as client:
        # client.get/post/... 返回的是 coroutine，无法直接用作 async context manager；
        # 流式读取必须使用 client.stream(...)，它才是 async context manager。
        async with client.stream(method, url, **kwargs) as response:
            content = await _stream_read(response, read_timeout)
            return HttpResponse(response, content)


async def http_req_simple(url: str, method: str = 'get', **kwargs) -> HttpResponse:
    """简易版：不强制流式读超时，适合小响应（如 favicon）。"""
    verify = kwargs.pop('verify', False)
    raw_timeout = kwargs.pop('timeout', (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT))
    allow_redirects = kwargs.pop('allow_redirects', False)
    headers = _default_headers(kwargs.pop("headers", None))

    client_kwargs, _ = _build_client_kwargs(verify, raw_timeout, allow_redirects, headers)
    async with httpx.AsyncClient(**client_kwargs) as client:
        request_method = getattr(client, method.lower(), client.get)
        r = await request_method(url, **kwargs)
        return HttpResponse(r, r.content)
