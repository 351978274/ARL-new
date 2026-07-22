"""系统/子进程工具，移植自原 app/utils/__init__.py 的 exec_system / check_output。"""
from __future__ import annotations

import asyncio
import hashlib
import os
import random
import re
import string
import subprocess
from typing import Optional

from ..logger import get_logger

logger = get_logger()


async def exec_system(cmd: list[str], timeout: int | float = 4 * 60 * 60,
                      **kwargs) -> subprocess.CompletedProcess:
    """异步运行系统命令（对应原 exec_system，原为同步 subprocess.run + shlex）。

    用 asyncio 线程池执行 subprocess.run，避免阻塞事件循环。
    自动注入 tool_tool_env（包含常见 PATH），避免 systemd 等最小化环境下找不到工具。
    """
    if "env" not in kwargs:
        kwargs["env"] = tool_subprocess_env()

    def _run():
        return subprocess.run(cmd, timeout=timeout, check=False, close_fds=True, **kwargs)

    return await asyncio.to_thread(_run)


async def check_output(cmd: list[str], timeout: int | float = 4 * 60 * 60, **kwargs) -> bytes:
    """异步获取命令输出（对应原 check_output）。"""
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    if "env" not in kwargs:
        kwargs["env"] = tool_subprocess_env()

    def _run():
        return subprocess.run(cmd, stdout=subprocess.PIPE, timeout=timeout, check=False, **kwargs).stdout

    return await asyncio.to_thread(_run)


# 标准 Linux/macOS 可执行文件目录——systemd 等最小化环境的默认 PATH 可能不含全部，
# 这里显式补齐，确保从用户 shell 启动 vs 从 systemd 启动行为一致。
_EXTRA_PATH_DIRS = (
    "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin",
    "/sbin", "/bin", "/opt/local/bin", "/snap/bin",
)


def tool_subprocess_env() -> dict[str, str]:
    """构造调用外部工具时使用的环境变量。

    保留当前进程的 env（含 HOME/LANG 等），但在 PATH 前部补齐常见可执行目录，
    避免 systemd 服务默认 PATH 不全导致 'not found binary'。
    """
    env = dict(os.environ)
    existing_path = env.get("PATH", "")
    # 把缺失的标准目录补到最前面
    needed = [d for d in _EXTRA_PATH_DIRS if d not in existing_path.split(":")]
    env["PATH"] = ":".join([*_EXTRA_PATH_DIRS, existing_path]) if needed else existing_path
    return env


def check_tool_available(name: str, probe_args: Optional[list[str]] = None,
                         alt_args: Optional[list[str]] = None) -> tuple[bool, str]:
    """同步探测外部工具是否可用，返回 (是否可用, 实际可执行路径或错误描述)。

    解决两个常见问题：
      1. systemd 等环境 PATH 不全 → 用 tool_subprocess_env() 补齐标准目录
      2. 工具的 --version/-h 退出码不规范（hydra -h 返回 255，部分 Kali 包装脚本
         返回非零）→ 只要进程成功启动（未抛 FileNotFoundError），就视为可用

    Args:
        name: 工具名（如 "dirsearch"）
        probe_args: 主探测参数（如 ["--version"]）
        alt_args: 备用探测参数（如 ["--help"] 或 ["-h"]），主参数失败时尝试
    """
    env = tool_subprocess_env()
    tried: list[str] = []

    for args in [probe_args, alt_args]:
        if not args:
            continue
        cmd = [name, *args]
        tried.append(" ".join(cmd))
        try:
            pro = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, timeout=15,
            )
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            logger.debug(f"{name} 探测超时: {' '.join(cmd)}")
            continue
        except Exception as e:
            logger.debug(f"{name} 探测异常 ({' '.join(cmd)}): {e}")
            continue
        # 进程能启动就算可用（无论退出码 —— 很多工具 --version 不返回 0）
        # 顺带解析真实路径，便于后续直接用绝对路径调用
        abs_path = _resolve_tool_path(name, env)
        logger.debug(
            f"{name} 可用 (cmd='{' '.join(cmd)}' returncode={pro.returncode} path={abs_path})"
        )
        return True, abs_path or name

    logger.warning(
        f"{name} 不可用：尝试过 {tried}，PATH={env['PATH']}"
    )
    return False, ""


def _resolve_tool_path(name: str, env: dict[str, str]) -> str:
    """用给定的 env 解析 name 的绝对路径（等价于 which），失败返回空串。"""
    try:
        pro = subprocess.run(
            ["which", name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, timeout=5,
        )
        if pro.returncode == 0:
            return pro.stdout.decode("utf-8", errors="ignore").strip()
    except Exception:
        pass
    return ""


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
