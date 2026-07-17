"""系统/子进程工具，移植自原 app/utils/__init__.py 的 exec_system / check_output。"""
from __future__ import annotations

import asyncio
import hashlib
import random
import re
import shlex
import string
import subprocess


async def exec_system(cmd: list[str], timeout: int | float = 4 * 60 * 60,
                      **kwargs) -> subprocess.CompletedProcess:
    """异步运行系统命令（对应原 exec_system，原为同步 subprocess.run + shlex）。

    用 asyncio 线程池执行 subprocess.run，避免阻塞事件循环。
    """
    def _run():
        return subprocess.run(cmd, timeout=timeout, check=False, close_fds=True, **kwargs)

    return await asyncio.to_thread(_run)


async def check_output(cmd: list[str], timeout: int | float = 4 * 60 * 60, **kwargs) -> bytes:
    """异步获取命令输出（对应原 check_output）。"""
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')

    def _run():
        return subprocess.run(cmd, stdout=subprocess.PIPE, timeout=timeout, check=False, **kwargs).stdout

    return await asyncio.to_thread(_run)


def random_choices(k: int = 6) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=k))


def gen_md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def gen_filename(site: str) -> str:
    """URL 转安全文件名。"""
    filename = site.replace('://', '_')
    return re.sub(r'[^\w\-_\\. ]', '_', filename)


def truncate_string(s: str) -> str:
    if len(s) > 30:
        return s[:30] + "..."
    return s


def is_valid_exclude_ports(exclude_ports: str) -> bool:
    """检查 nmap 排除端口范围合法性。"""
    port_pattern = r'(\d+(-\d+)?,?)+'
    if not re.fullmatch(port_pattern, exclude_ports):
        return False
    for part in exclude_ports.split(','):
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
            except ValueError:
                return False
            if start > end or not (0 <= start <= 65535) or not (0 <= end <= 65535):
                return False
        else:
            try:
                if not (0 <= int(part) <= 65535):
                    return False
            except ValueError:
                return False
    return True


def build_port_custom(port_custom: str) -> list[str]:
    """解析自定义端口字符串为列表（支持范围 80-90）。"""
    if not port_custom:
        return []
    port_list: list[int] = []
    for item in port_custom.split(","):
        item = item.strip()
        if not re.match(r'^[\d\-]+$', item):
            return [port_custom]  # 原逻辑：非法则原样返回
        if "-" in item:
            start, end = item.split("-")
            port_list.extend(range(int(start), int(end) + 1))
        else:
            port_list.append(int(item))
    return [str(p) for p in port_list]
