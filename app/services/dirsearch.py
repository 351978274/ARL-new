"""dirsearch 目录爆破调用。

外部工具 dirsearch（https://github.com/maurosoria/dirsearch）通过 asyncio 线程池执行。
支持以 JSON 格式输出结果，便于解析入库。

与 nuclei_scan.py / info_hunter.py 保持一致的调用风格：
    生成临时目标文件 -> 拼装命令 -> exec_system 异步执行 -> 解析 JSON 结果 -> 清理临时文件。

options 字段（前端勾选 / 填值）：
    extensions, wordlists, force_extensions, overwrite_extensions, remove_extensions,
    threads, recursive, max_recursion_depth, async_mode, include_status, exclude_status,
    subdirs, max_time, http_method, follow_redirects, random_agent, cookie,
    timeout, proxy, tor, retries
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..config import Config
from ..logger import get_logger
from ..utils import exec_system, random_choices

logger = get_logger()

# dirsearch 可执行文件名（按 PATH 解析；如需固定路径可在 config.yaml 增配）
DIRSEARCH_BIN = os.environ.get("DIRSEARCH_BIN", "dirsearch")

# 布尔型参数：勾选即追加 flag
_BOOL_FLAGS = {
    "force_extensions": "-f",
    "overwrite_extensions": "-O",
    "remove_extensions": "--remove-extensions",
    "recursive": "-r",
    "async_mode": "--async",
    "follow_redirects": "-F",
    "random_agent": "--random-agent",
    "tor": "--tor",
}

# 带值型参数：勾选后取值，参数名 -> (CLI flag, 类型)
_VALUE_FLAGS = {
    "extensions": ("-e", str),
    "wordlists": ("-w", str),
    "threads": ("-t", int),
    "max_recursion_depth": ("-R", int),
    "include_status": ("-i", str),
    "exclude_status": ("-x", str),
    "subdirs": ("--subdirs", str),
    "max_time": ("--max-time", int),
    "http_method": ("-m", str),
    "cookie": ("--cookie", str),
    "timeout": ("--timeout", float),
    "proxy": ("-p", str),
    "retries": ("--retries", int),
}


class DirSearch:
    """封装一次 dirsearch 扫描。

    Args:
        targets: 目标 URL 列表（每个形如 https://example.com）。
        options: 前端勾选/填值的参数字典（见模块文档字符串）。
    """

    def __init__(self, targets: list[str], options: dict | None = None):
        self.targets = [t.strip() for t in targets if t and t.strip()]
        self.options = options or {}
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        self.target_path = os.path.join(tmp_path, f"dirsearch_target_{rand_str}.txt")
        self.result_path = os.path.join(tmp_path, f"dirsearch_result_{rand_str}.json")

    # ---------- 临时文件 ----------
    def _gen_target_file(self) -> None:
        with open(self.target_path, "w", encoding="utf-8") as f:
            for url in self.targets:
                f.write(url + "\n")

    def _delete_file(self) -> None:
        for p in (self.target_path, self.result_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning(f"清理 dirsearch 临时文件失败 {p}: {e}")

    # ---------- 探测 ----------
    def check_have_dirsearch(self) -> bool:
        """探测 dirsearch 是否可用。"""
        try:
            pro = subprocess.run(
                [DIRSEARCH_BIN, "--version"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            return pro.returncode == 0
        except Exception as e:
            logger.debug(str(e))
            return False

    # ---------- 命令拼装 ----------
    def _build_command(self) -> list[str]:
        """根据 options 拼装 CLI 参数列表。

        - 布尔参数：勾选则追加对应 flag
        - 带值参数：值非空才追加 `flag value`
        - 固定追加：-l 目标文件、--format json、-o 结果文件、--full-url
        """
        cmd: list[str] = [DIRSEARCH_BIN, "-l", self.target_path,
                          "--format", "json", "-o", self.result_path, "--full-url"]

        for key, flag in _BOOL_FLAGS.items():
            if self.options.get(key):
                cmd.append(flag)

        for key, (flag, typ) in _VALUE_FLAGS.items():
            val = self.options.get(key)
            if val in (None, ""):
                continue
            try:
                if typ is int:
                    val = str(int(val))
                elif typ is float:
                    val = str(float(val))
                else:
                    val = str(val).strip()
            except (TypeError, ValueError):
                logger.warning(f"dirsearch 参数 {key} 取值非法: {val}，已忽略")
                continue
            if val:
                cmd.append(flag)
                cmd.append(val)
        return cmd

    # ---------- 执行 ----------
    async def exec_dirsearch(self) -> None:
        cmd = self._build_command()
        logger.info("dirsearch cmd: " + " ".join(cmd))
        # dirsearch 单次扫描可能很长，沿用 nuclei 的超时上限
        await exec_system(cmd, timeout=24 * 60 * 60)

    # ---------- 结果解析 ----------
    def dump_result(self) -> list[dict]:
        """解析 dirsearch 的 JSON 输出。

        dirsearch --format json 会输出一个 JSON 数组（每条结果为一对象），
        兼容历史版本可能的「每行一个 JSON 对象」格式。
        """
        if not os.path.exists(self.result_path):
            return []
        with open(self.result_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return []

        items: list[dict] = []
        # 优先按 JSON 数组解析
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
        except json.JSONDecodeError:
            # 兼容 JSONL：逐行解析
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        results: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            results.append({
                "url": it.get("url", ""),
                "path": it.get("path", ""),
                "status_code": int(it.get("status") or it.get("status_code") or 0),
                "content_length": int(it.get("length") or it.get("content-length") or 0),
                "redirect": it.get("redirect", "") or "",
            })
        return results

    # ---------- 主流程 ----------
    async def run(self) -> list[dict]:
        if not self.targets:
            return []
        if not self.check_have_dirsearch():
            logger.warning(f"not found dirsearch binary: {DIRSEARCH_BIN}")
            return []
        self._gen_target_file()
        try:
            await self.exec_dirsearch()
            return self.dump_result()
        finally:
            self._delete_file()


async def run_dirsearch(targets: list[str], options: dict | None = None) -> list[dict]:
    """模块级入口：执行一次 dirsearch 扫描并返回结构化结果。"""
    logger.info(f"run dirsearch, targets: {len(targets)}")
    results = await DirSearch(targets=targets, options=options or {}).run()
    logger.info(f"dirsearch result: {len(results)}")
    return results


# 供前端展示的参数元数据（说明 + 默认值 + 类型）
PARAM_META: list[dict[str, Any]] = [
    # 字典设置
    {"group": "字典设置", "key": "extensions", "flag": "-e", "name": "扩展名",
     "desc": "扩展名列表，逗号分隔（如 php,html,js）", "type": "str", "default": "php,html,js"},
    {"group": "字典设置", "key": "wordlists", "flag": "-w", "name": "自定义字典",
     "desc": "自定义字典文件路径，多个用逗号分隔", "type": "str", "default": ""},
    {"group": "字典设置", "key": "force_extensions", "flag": "-f", "name": "强制扩展",
     "desc": "为字典中每一条都追加扩展名（适用于无 %EXT% 关键字的字典）", "type": "bool", "default": False},
    {"group": "字典设置", "key": "overwrite_extensions", "flag": "-O", "name": "覆盖扩展",
     "desc": "用 -e 指定的扩展名覆盖字典中已有的扩展", "type": "bool", "default": False},
    {"group": "字典设置", "key": "remove_extensions", "flag": "--remove-extensions", "name": "移除扩展",
     "desc": "移除所有路径中的扩展名（如 admin.php -> admin）", "type": "bool", "default": False},
    # 通用设置
    {"group": "通用设置", "key": "threads", "flag": "-t", "name": "线程数",
     "desc": "并发线程数，默认 25", "type": "int", "default": 25},
    {"group": "通用设置", "key": "recursive", "flag": "-r", "name": "递归爆破",
     "desc": "对发现的目录递归爆破", "type": "bool", "default": False},
    {"group": "通用设置", "key": "max_recursion_depth", "flag": "-R", "name": "递归深度",
     "desc": "递归的最大深度", "type": "int", "default": 0},
    {"group": "通用设置", "key": "async_mode", "flag": "--async", "name": "异步模式",
     "desc": "使用协程替代线程，CPU 占用更低", "type": "bool", "default": False},
    {"group": "通用设置", "key": "include_status", "flag": "-i", "name": "包含状态码",
     "desc": "仅显示指定状态码（如 200,301-399）", "type": "str", "default": ""},
    {"group": "通用设置", "key": "exclude_status", "flag": "-x", "name": "排除状态码",
     "desc": "排除指定状态码（如 404,500-599）", "type": "str", "default": ""},
    {"group": "通用设置", "key": "subdirs", "flag": "--subdirs", "name": "扫描子目录",
     "desc": "扫描指定的子目录（如 /,admin/,api/）", "type": "str", "default": ""},
    {"group": "通用设置", "key": "max_time", "flag": "--max-time", "name": "最大运行时间",
     "desc": "扫描最大耗时（秒），超过则退出", "type": "int", "default": 0},
    # 请求设置
    {"group": "请求设置", "key": "http_method", "flag": "-m", "name": "HTTP 方法",
     "desc": "请求方法，默认 GET", "type": "str", "default": "GET"},
    {"group": "请求设置", "key": "follow_redirects", "flag": "-F", "name": "跟随重定向",
     "desc": "跟随 HTTP 重定向", "type": "bool", "default": False},
    {"group": "请求设置", "key": "random_agent", "flag": "--random-agent", "name": "随机 UA",
     "desc": "为每个请求随机选择 User-Agent", "type": "bool", "default": False},
    {"group": "请求设置", "key": "cookie", "flag": "--cookie", "name": "Cookie",
     "desc": "请求携带的 Cookie", "type": "str", "default": ""},
    # 连接设置
    {"group": "连接设置", "key": "timeout", "flag": "--timeout", "name": "连接超时",
     "desc": "单请求连接超时（秒），默认 7.5", "type": "float", "default": 7.5},
    {"group": "连接设置", "key": "proxy", "flag": "-p", "name": "代理",
     "desc": "HTTP/SOCKS 代理（如 http://127.0.0.1:8080）", "type": "str", "default": ""},
    {"group": "连接设置", "key": "tor", "flag": "--tor", "name": "使用 Tor",
     "desc": "通过 Tor 网络作为代理", "type": "bool", "default": False},
    {"group": "连接设置", "key": "retries", "flag": "--retries", "name": "重试次数",
     "desc": "失败请求的重试次数", "type": "int", "default": 1},
]
