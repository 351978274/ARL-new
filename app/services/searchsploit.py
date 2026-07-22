"""searchsploit Exploit-DB 离线搜索调用。

外部工具 searchsploit（https://www.exploit-db.com/searchsploit）通过 asyncio 线程池执行。
searchsploit 是 Exploit-DB 的本地命令行搜索工具，基于本地 checked-out 仓库离线搜索，
适用于隔离/气隙网络的安全评估。

与 dirsearch.py / hydra.py / sqlmap.py / aircrack.py 保持一致的调用风格：
    拼装命令 -> exec_system 异步执行 -> 解析 JSON 结果 -> 清理临时文件。

为便于解析，固定使用 -j（JSON 输出）+ --disable-colour（去除颜色转义字符）。
searchsploit 的 JSON 输出结构（RESULTS_EXPLOIT 数组）：
    [{"EDB-ID","Exploit","Date","Author","Type","Platform","Path","Codes","Verified"}, ...]

options 字段（前端勾选 / 填值），完整参数清单见 PARAM_META。
"""
from __future__ import annotations

import json
import os
from typing import Any

from ..config import Config
from ..logger import get_logger
from ..utils import check_output, check_tool_available, random_choices

logger = get_logger()

# searchsploit 可执行文件名（按 PATH 解析；如需固定路径可设置环境变量 SEARCHSPLOIT_BIN）
SEARCHSPLOIT_BIN = os.environ.get("SEARCHSPLOIT_BIN", "searchsploit")

# 布尔型参数：勾选即追加 flag（值为 searchsploit 的开关选项）
_BOOL_FLAGS: dict[str, str] = {
    # Search Terms
    "case_sensitive": "-c",          # 区分大小写
    "exact_match": "-e",             # 精确匹配标题（隐含 -t）
    "strict": "-s",                  # 严格匹配，禁用版本范围模糊搜索
    "title_only": "-t",              # 仅搜索标题（默认搜标题 + 路径）
    # Output
    "overflow": "-o",                # 允许标题溢出列宽
    "verbose": "-v",                 # 显示更多信息
    "www": "-w",                     # 显示 Exploit-DB.com URL 而非本地路径
    "show_id": "--id",               # 显示 EDB-ID 而非本地路径
    "disable_colour": "--disable-colour",  # 禁用颜色高亮（本服务固定启用，前端可冗余勾选）
}

# 带值型参数：勾选后取值，参数名 -> (CLI flag, 类型)
_VALUE_FLAGS: dict[str, tuple[str, type]] = {
    # Search Terms
    "exclude": ("--exclude", str),   # 排除结果，| 分隔多个
    "cve": ("--cve", str),           # 按 CVE 编号搜索
    # Output
    "path": ("-p", str),             # 显示指定 EDB-ID 的完整路径
    # Non-Searching
    "mirror": ("-m", str),           # 复制指定 EDB-ID 的 exploit 到当前目录
    "examine": ("-x", str),          # 用 $PAGER 打开指定 EDB-ID
    # Automation
    "nmap": ("--nmap", str),         # 检查 Nmap XML 输出中的服务版本
}


class SearchsploitScan:
    """封装一次 searchsploit 搜索。

    Args:
        terms: 搜索关键词列表（如 ["linux", "kernel", "3.2"]）。
        options: 前端勾选/填值的参数字典（见模块文档字符串）。
    """

    def __init__(self, terms: list[str], options: dict | None = None):
        self.terms = [t.strip() for t in terms if t and t.strip()]
        self.options = options or {}
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        # JSON 输出重定向到文件，便于解析
        self.output_path = os.path.join(tmp_path, f"searchsploit_out_{rand_str}.json")
        self._bin_path = SEARCHSPLOIT_BIN  # 探测成功后更新为绝对路径

    # ---------- 探测 ----------
    def check_have_searchsploit(self) -> bool:
        """探测 searchsploit 是否可用（兼容 systemd 最小化 PATH + 非零退出码）。"""
        ok, abs_path = check_tool_available(SEARCHSPLOIT_BIN, ["-h"], ["--help"])
        if ok and abs_path and "/" in abs_path:
            self._bin_path = abs_path
        else:
            self._bin_path = SEARCHSPLOIT_BIN
        return ok

    # ---------- 命令拼装 ----------
    def _build_command(self) -> list[str]:
        """根据 options 拼装 searchsploit CLI。

        - 固定追加：-j（JSON 输出）+ --disable-colour（去颜色，避免破坏 JSON）
        - -p/-m/-x/--nmap 等非搜索模式：直接执行对应操作，忽略 terms
        """
        # 固定参数：JSON 输出 + 禁用颜色（颜色转义会破坏 JSON 解析）
        cmd: list[str] = [self._bin_path, "-j", "--disable-colour"]

        # 布尔开关
        for key, flag in _BOOL_FLAGS.items():
            if self.options.get(key):
                cmd.append(flag)

        # 带值参数
        for key, (flag, typ) in _VALUE_FLAGS.items():
            val = self.options.get(key)
            if val is None or val == "":
                continue
            try:
                val = str(val).strip() if typ is str else str(typ(val))
            except (TypeError, ValueError):
                logger.warning(f"searchsploit 参数 {key} 取值非法: {val}，已忽略")
                continue
            if val:
                cmd.append(flag)
                cmd.append(val)

        # 搜索关键词（位置参数）；非搜索模式（-p/-m/-x/--nmap 已带值）下也可追加
        for term in self.terms:
            cmd.append(term)
        return cmd

    # ---------- 执行 ----------
    async def exec_searchsploit(self) -> None:
        """执行 searchsploit，捕获 stdout 写入 output_path。

        使用 check_output（stdout=PIPE）捕获输出，避免 shell 重定向（exec_system 不解析 shell 语法）。
        searchsploit 的 -j 输出全部在 stdout。
        """
        cmd = self._build_command()
        logger.info("searchsploit cmd: " + " ".join(cmd))
        # searchsploit 通常秒级返回；--nmap 模式可能稍长。1h 超时足够
        output = await check_output(cmd, timeout=60 * 60)
        try:
            with open(self.output_path, "wb") as f:
                f.write(output)
        except OSError as e:
            logger.warning(f"写入 searchsploit 输出文件失败: {e}")

    # ---------- 结果解析 ----------
    def dump_result(self) -> list[dict]:
        """解析 searchsploit -j 的 JSON 输出。

        searchsploit -j 输出结构：
            {
              "SEARCH": "...",
              "DB_PATH": "...",
              "RESULTS_EXPLOIT": [ {...}, ... ],
              "RESULTS_SHELLCODE": [ {...}, ... ],
              "RESULTS_PAPER": [ {...}, ... ]
            }
        本方法合并三类结果，标注 source 字段。
        """
        if not os.path.exists(self.output_path):
            return []
        try:
            with open(self.output_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"searchsploit JSON 解析失败: {e}")
            return []

        if not isinstance(data, dict):
            return []

        results: list[dict] = []
        for source_key in ("RESULTS_EXPLOIT", "RESULTS_SHELLCODE", "RESULTS_PAPER"):
            source_label = {"RESULTS_EXPLOIT": "exploit",
                            "RESULTS_SHELLCODE": "shellcode",
                            "RESULTS_PAPER": "paper"}.get(source_key, source_key.lower())
            for item in data.get(source_key, []) or []:
                if not isinstance(item, dict):
                    continue
                # searchsploit -j 真实字段名（含空格）：
                #   "Exploit Title", "EDB-ID", "Date", "Author", "Type",
                #   "Platform", "Path", "Codes", "Verified"
                # 兼容多种写法，避免字段名差异导致空值
                results.append({
                    "source": source_label,
                    "edb_id": str(item.get("EDB-ID", "") or item.get("edb-id", "")),
                    "title": (item.get("Exploit Title", "") or item.get("Exploit", "")
                              or item.get("Title", "")),
                    "date": item.get("Date", ""),
                    "author": item.get("Author", ""),
                    "type": item.get("Type", ""),
                    "platform": item.get("Platform", ""),
                    "path": item.get("Path", ""),
                    "codes": item.get("Codes", "") or "",
                    "verified": "Verified" in item and item["Verified"],
                    "url": f"https://www.exploit-db.com/exploits/{item.get('EDB-ID', '')}"
                           if item.get("EDB-ID") else "",
                })
        return results

    # ---------- 主流程 ----------
    async def run(self) -> list[dict]:
        # 非搜索模式（-p/-m/-x/--nmap）允许 terms 为空；搜索模式必须有关键词
        non_search = any(self.options.get(k) for k in ("path", "mirror", "examine", "nmap"))
        if not self.terms and not non_search:
            return []
        if not self.check_have_searchsploit():
            logger.warning(f"not found searchsploit binary: {SEARCHSPLOIT_BIN}")
            return []
        try:
            await self.exec_searchsploit()
            return self.dump_result()
        finally:
            if os.path.exists(self.output_path):
                try:
                    os.unlink(self.output_path)
                except OSError:
                    pass


async def run_searchsploit(terms: list[str], options: dict | None = None) -> list[dict]:
    """模块级入口：执行一次 searchsploit 搜索并返回结构化结果。"""
    logger.info(f"run searchsploit, terms: {terms}")
    results = await SearchsploitScan(terms=terms, options=options or {}).run()
    logger.info(f"searchsploit result: {len(results)}")
    return results


# 供前端展示的参数元数据（分组 + 说明 + 默认值 + 类型）
# searchsploit 选项较少（约 15 个），全部展示
PARAM_META: list[dict[str, Any]] = [
    # Search Terms
    {"group": "搜索设置", "key": "case_sensitive", "flag": "-c", "name": "区分大小写",
     "desc": "执行区分大小写的搜索（默认不区分）", "type": "bool", "default": False},
    {"group": "搜索设置", "key": "exact_match", "flag": "-e", "name": "精确匹配",
     "desc": "对 exploit 标题执行精确且有序匹配（默认是各关键词 AND 匹配，隐含 -t）",
     "type": "bool", "default": False},
    {"group": "搜索设置", "key": "strict", "flag": "-s", "name": "严格匹配",
     "desc": "严格搜索，输入值必须存在，禁用版本范围模糊搜索（如 1.1 不会匹配 1.0 < 1.3）",
     "type": "bool", "default": False},
    {"group": "搜索设置", "key": "title_only", "flag": "-t", "name": "仅搜标题",
     "desc": "仅搜索 exploit 标题（默认搜标题 + 文件路径）", "type": "bool", "default": False},
    {"group": "搜索设置", "key": "exclude", "flag": "--exclude", "name": "排除关键词",
     "desc": "从结果中排除指定值，| 分隔多个（如 --exclude=\"(PoC)|/dos/\"）",
     "type": "str", "default": ""},
    {"group": "搜索设置", "key": "cve", "flag": "--cve", "name": "按 CVE 搜索",
     "desc": "按 CVE 编号搜索（如 2021-44228）", "type": "str", "default": ""},
    # Output
    {"group": "输出设置", "key": "overflow", "flag": "-o", "name": "允许标题溢出",
     "desc": "允许 exploit 标题超出列宽（不截断显示）", "type": "bool", "default": False},
    {"group": "输出设置", "key": "verbose", "flag": "-v", "name": "详细输出",
     "desc": "在输出中显示更多信息（--nmap 模式下会搜索更多组合）", "type": "bool", "default": False},
    {"group": "输出设置", "key": "www", "flag": "-w", "name": "显示在线 URL",
     "desc": "显示 Exploit-DB.com 的 URL 而非本地路径", "type": "bool", "default": False},
    {"group": "输出设置", "key": "show_id", "flag": "--id", "name": "显示 EDB-ID",
     "desc": "显示 EDB-ID 值而非本地路径", "type": "bool", "default": False},
    {"group": "输出设置", "key": "disable_colour", "flag": "--disable-colour", "name": "禁用颜色",
     "desc": "禁用搜索结果的颜色高亮（本服务固定启用以保证 JSON 解析，前端勾选为冗余）",
     "type": "bool", "default": True},
    # Non-Searching
    {"group": "非搜索操作", "key": "path", "flag": "-p", "name": "查看完整路径",
     "desc": "显示指定 EDB-ID 的完整路径（并尝试复制到剪贴板）", "type": "str", "default": ""},
    {"group": "非搜索操作", "key": "mirror", "flag": "-m", "name": "复制 exploit",
     "desc": "将指定 EDB-ID 的 exploit 复制到当前工作目录", "type": "str", "default": ""},
    {"group": "非搜索操作", "key": "examine", "flag": "-x", "name": "查看 exploit 内容",
     "desc": "用 $PAGER 打开指定 EDB-ID 的 exploit 文件", "type": "str", "default": ""},
    # Automation
    {"group": "自动化", "key": "nmap", "flag": "--nmap", "name": "Nmap XML 批量搜索",
     "desc": "检查 Nmap XML 输出中的所有服务版本结果（需先 nmap -sV -oX file.xml）",
     "type": "str", "default": ""},
]
