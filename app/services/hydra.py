"""THC-Hydra 网络登录爆破调用。

外部工具 hydra（https://github.com/vanhauser-thc/thc-hydra）通过 asyncio 线程池执行。
支持 50+ 协议（ssh/ftp/http-post-form/rdp/smb/mysql/...），使用 -b json 输出便于解析。

与 dirsearch.py / nuclei_scan.py / info_hunter.py 保持一致的调用风格：
    生成临时凭据文件（可选）-> 拼装命令 -> exec_system 异步执行 -> 解析 JSON 结果 -> 清理。

options 字段（前端勾选 / 填值），完整参数清单见 PARAM_META：
    target/service 必填；登录凭据通过 -l/-L/-p/-P/-C 之一提供。

Hydra 输出格式（-b jsonv1）：
    [{"service":"ssh","host":"1.2.3.4","login":"root","password":"123456"}, ...]
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from ..config import Config, DICTS_DIR
from ..logger import get_logger
from ..utils import check_tool_available, exec_system, random_choices

logger = get_logger()

# hydra 可执行文件名（按 PATH 解析；如需固定路径可设置环境变量 HYDRA_BIN）
HYDRA_BIN = os.environ.get("HYDRA_BIN", "hydra")

# 默认密码 / 用户名字典（项目自带）
DEFAULT_PASS_DICT = os.path.join(DICTS_DIR, "passwordtop1000.txt")

# 布尔型参数：勾选即追加 flag（值为 Hydra 的开关选项）
_BOOL_FLAGS: dict[str, str] = {
    "ssl": "-S",
    "old_ssl": "-O",
    "ipv4": "-4",
    "ipv6": "-6",
    "loop_around_users": "-u",
    "exit_on_found": "-f",          # -f: 单主机找到即退出（-M 时按主机）；-F 全局退出
    "exit_on_found_global": "-F",
    "verbose": "-v",
    "show_attempt": "-V",
    "debug": "-d",
    "quiet": "-q",
    "no_redo_failed": "-K",
    "disable_symbols": "-y",
    "non_random_shuffle": "-r",
    "ignore_restore": "-I",
}

# 带值型参数：勾选后取值，参数名 -> (CLI flag, 类型)
_VALUE_FLAGS: dict[str, tuple[str, type]] = {
    "login": ("-l", str),            # 单个用户名
    "login_file": ("-L", str),       # 用户名字典文件
    "pass": ("-p", str),             # 单个密码
    "pass_file": ("-P", str),        # 密码字典文件
    "colon_file": ("-C", str),       # login:pass 格式文件
    "port": ("-s", int),             # 非默认端口
    "tasks": ("-t", int),            # 每目标并行连接数（默认 16）
    "tasks_total": ("-T", int),      # 总并行连接数（-M 时）
    "wait_time": ("-w", int),        # 响应等待时间（秒）
    "wait_between": ("-W", int),     # 每线程连接间隔（秒）
    "timeout_per_login": ("-c", int),# 单次登录总超时（秒，强制 -t 1）
    "extra_check": ("-e", str),      # 额外检查: n=空密码 s=登录名作密码 r=反向登录
    "brute_gen": ("-x", str),        # 密码生成 -x MIN:MAX:CHARSET
    "module_opt": ("-m", str),       # 模块特定选项（如 http-post-form 的页面规则）
    "output_file": ("-o", str),      # 结果输出文件
    "divide": ("-D", str),           # 切分字典: -D XofY
}

# Hydra 支持的常用服务（来自 hydra.c SERVICES）
SUPPORTED_SERVICES = [
    "ssh", "ftp", "ftps", "smb", "smb2", "rdp", "telnet", "snmp",
    "mysql", "mssql", "postgres", "oracle", "oracle-listener", "oracle-sid",
    "vnc", "redis", "mongodb", "memcached",
    "http-get", "http-get-form", "http-post", "http-post-form", "http-head",
    "http-proxy", "http-proxy-urlenum",
    "https-get", "https-get-form", "https-post", "https-post-form",
    "pop3", "pop3s", "imap", "imaps", "smtp", "smtps", "smtp-enum",
    "nntp", "ldap", "ldap2", "ldap3", "ldap3-crammd5", "ldap3-digestmd5",
    "asterisk", "cisco", "cisco-enable", "cvs", "firebird", "icq", "irc",
    "ncp", "pcanywhere", "pcnfs", "rexec", "rlogin", "rsh", "rpcap",
    "rtsp", "s7-300", "sapr3", "sip", "socks5", "sshkey", "svn",
    "teamspeak", "vmauthd", "xmpp", "cobaltstrike", "radmin2",
]


class HydraScan:
    """封装一次 hydra 爆破。

    Args:
        targets: 目标列表，每项形如 "192.168.1.1" 或 "ssh://192.168.1.1:22" 或
                 "192.168.1.1 ssh"（与 hydra 命令尾参一致）。
                 为简化前端，target 与 service 在 options 中单独提供，本类负责拼装。
        options: 前端勾选/填值的参数字典（见模块文档字符串）。
    """

    def __init__(self, targets: list[str], options: dict | None = None):
        self.targets = [t.strip() for t in targets if t and t.strip()]
        self.options = options or {}
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        # 多目标时写入 -M 文件
        self.target_file = os.path.join(tmp_path, f"hydra_target_{rand_str}.txt")
        # -o 输出文件（同时用 -b jsonv1 解析）
        self.output_path = os.path.join(tmp_path, f"hydra_output_{rand_str}.json")
        self._bin_path = HYDRA_BIN  # 探测成功后更新为绝对路径

    # ---------- 临时文件 ----------
    def _gen_target_file(self) -> None:
        """多目标时生成 -M 目标文件（每行一个，可带 :port）。"""
        with open(self.target_file, "w", encoding="utf-8") as f:
            for t in self.targets:
                f.write(t + "\n")

    def _delete_file(self) -> None:
        for p in (self.target_file, self.output_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning(f"清理 hydra 临时文件失败 {p}: {e}")

    # ---------- 探测 ----------
    def check_have_hydra(self) -> bool:
        """探测 hydra 是否可用（兼容 systemd 最小化 PATH + 非零退出码）。"""
        ok, abs_path = check_tool_available(HYDRA_BIN, ["-h"], ["--help"])
        if ok and abs_path and "/" in abs_path:
            self._bin_path = abs_path
        else:
            self._bin_path = HYDRA_BIN
        return ok

    # ---------- 命令拼装 ----------
    def _build_command(self) -> list[str]:
        """根据 options 拼装 hydra CLI。

        单目标：hydra [opts] target service
        多目标：hydra [opts] -M target_file service
        结果固定写入 output_path（-o），并用 -b jsonv1 指定格式。
        """
        cmd: list[str] = [self._bin_path, "-o", self.output_path, "-b", "jsonv1"]

        # 布尔开关
        for key, flag in _BOOL_FLAGS.items():
            if self.options.get(key):
                cmd.append(flag)

        # 带值参数
        for key, (flag, typ) in _VALUE_FLAGS.items():
            val = self.options.get(key)
            if val is None:
                continue
            try:
                if typ is int:
                    # int 类型：0 视为「未设置」，跳过（让 hydra 用默认值）
                    n = int(val)
                    if n == 0:
                        continue
                    val = str(n)
                else:
                    val = str(val).strip()
            except (TypeError, ValueError):
                logger.warning(f"hydra 参数 {key} 取值非法: {val}，已忽略")
                continue
            if val:
                cmd.append(flag)
                cmd.append(val)

        # 目标 + 服务
        service = (self.options.get("service") or "").strip()
        if self.options.get("target"):
            # 单目标模式（target 直接作为命令尾参）
            target = str(self.options["target"]).strip()
            cmd.append(target)
            if service:
                cmd.append(service)
        else:
            # 多目标模式：-M file
            self._gen_target_file()
            cmd.append("-M")
            cmd.append(self.target_file)
            if service:
                cmd.append(service)

        # 模块特定选项（-m）已在 _VALUE_FLAGS 处理
        return cmd

    # ---------- 执行 ----------
    async def exec_hydra(self) -> None:
        cmd = self._build_command()
        logger.info("hydra cmd: " + " ".join(cmd))
        # hydra 爆破耗时可能很长，沿用 24h 上限
        await exec_system(cmd, timeout=24 * 60 * 60)

    # ---------- 结果解析 ----------
    def dump_result(self) -> list[dict]:
        """解析 hydra 的 -b jsonv1 输出。

        hydra v9.x 的 jsonv1 实际是嵌套结构（源码 hydra.c:4062-4640）：
            {
              "generator": { "software":..., "service":..., "server":... },
              "results": [
                {"port":22, "service":"ssh", "host":"...", "login":"...", "password":"..."}
              ],
              "success": true,
              "errormessages": [],
              "quantityfound": 2
            }
        因此优先取 data["results"]。若顶层就是列表（向后兼容），直接用。
        若 -o 文件不存在或 JSON 解析失败，回退到文本正则解析。
        """
        if not os.path.exists(self.output_path):
            return []
        with open(self.output_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read().strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 兜底：用正则提取 host/login/password（旧版或混杂日志时）
            return self._parse_text_output(raw)

        # 嵌套结构：取 generator 元数据 + results 数组
        generator: dict = {}
        creds: list = []
        if isinstance(data, dict):
            generator = data.get("generator", {}) or {}
            creds = data.get("results", []) or []
        elif isinstance(data, list):
            creds = data
        else:
            return []

        # generator 中可补全 service / server（target）
        gen_service = generator.get("service", "") or self.options.get("service", "")
        gen_host = generator.get("server", "") or self.options.get("target", "")

        results: list[dict] = []
        for it in creds:
            if not isinstance(it, dict):
                continue
            port = it.get("port", 0)
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = 0
            results.append({
                "service": it.get("service", "") or gen_service,
                "host": it.get("host", "") or gen_host,
                "port": port,
                "login": it.get("login", "") or "",
                "password": it.get("password", "") or "",
            })
        return results

    @staticmethod
    def _parse_text_output(raw: str) -> list[dict]:
        """从纯文本输出兜底解析（匹配 '[port][service] host: x login: y password: z' 行）。"""
        results: list[dict] = []
        # 例: [22][ssh] host: 1.2.3.4   login: root   password: 123456
        pattern = re.compile(r"login:\s*(\S+)\s+password:\s*(\S+)")
        host_pattern = re.compile(r"host:\s*(\S+)")
        # 同时捕获 port 和 service
        svc_pattern = re.compile(r"\[(\d+)\]\[([^\]]+)\]")
        for line in raw.splitlines():
            m = pattern.search(line)
            if not m:
                continue
            login, password = m.group(1), m.group(2)
            host_m = host_pattern.search(line)
            svc_m = svc_pattern.search(line)
            port = 0
            if svc_m:
                try:
                    port = int(svc_m.group(1))
                except (TypeError, ValueError):
                    port = 0
            results.append({
                "service": svc_m.group(2) if svc_m else "",
                "host": host_m.group(1) if host_m else "",
                "port": port,
                "login": login,
                "password": password,
            })
        return results

    # ---------- 主流程 ----------
    async def run(self) -> list[dict]:
        if not self.options.get("target") and not self.targets:
            return []
        # 多目标场景：把 targets 写入 options
        if not self.options.get("target") and self.targets:
            # 由 _build_command 走 -M 路径
            pass
        if not self.check_have_hydra():
            logger.warning(f"not found hydra binary: {HYDRA_BIN}")
            return []
        try:
            await self.exec_hydra()
            return self.dump_result()
        finally:
            self._delete_file()


async def run_hydra(targets: list[str], options: dict | None = None) -> list[dict]:
    """模块级入口：执行一次 hydra 爆破并返回破解成功的凭据列表。"""
    logger.info(f"run hydra, targets: {len(targets)}")
    results = await HydraScan(targets=targets, options=options or {}).run()
    logger.info(f"hydra cracked: {len(results)}")
    return results


# 供前端展示的参数元数据（分组 + 说明 + 默认值 + 类型）
PARAM_META: list[dict[str, Any]] = [
    # 目标与协议
    {"group": "目标设置", "key": "service", "flag": "service", "name": "目标服务",
     "desc": "要爆破的协议/服务，如 ssh/ftp/smb/rdp/mysql/http-post-form 等", "type": "select",
     "default": "ssh", "options": SUPPORTED_SERVICES},
    {"group": "目标设置", "key": "port", "flag": "-s", "name": "目标端口",
     "desc": "服务运行的非默认端口", "type": "int", "default": 0},
    {"group": "目标设置", "key": "tasks", "flag": "-t", "name": "每目标并发数",
     "desc": "每个目标的并行连接数（默认 16）", "type": "int", "default": 16},
    {"group": "目标设置", "key": "tasks_total", "flag": "-T", "name": "总并发数",
     "desc": "多目标(-M)时的总并行连接数（默认 64）", "type": "int", "default": 0},
    # 凭据
    {"group": "凭据设置", "key": "login", "flag": "-l", "name": "单个用户名",
     "desc": "尝试的单个登录用户名", "type": "str", "default": ""},
    {"group": "凭据设置", "key": "login_file", "flag": "-L", "name": "用户名字典",
     "desc": "用户名字典文件路径", "type": "str", "default": "", "file": True},
    {"group": "凭据设置", "key": "pass", "flag": "-p", "name": "单个密码",
     "desc": "尝试的单个密码", "type": "str", "default": ""},
    {"group": "凭据设置", "key": "pass_file", "flag": "-P", "name": "密码字典",
     "desc": "密码字典文件路径", "type": "str", "default": DEFAULT_PASS_DICT, "file": True},
    {"group": "凭据设置", "key": "colon_file", "flag": "-C", "name": "login:pass 字典",
     "desc": "login:pass 格式的字典文件（与 -L/-P 二选一）", "type": "str", "default": "", "file": True},
    {"group": "凭据设置", "key": "extra_check", "flag": "-e", "name": "额外检查",
     "desc": "n=空密码 / s=登录名作密码 / r=反向登录，可组合如 ns", "type": "str", "default": ""},
    {"group": "凭据设置", "key": "brute_gen", "flag": "-x", "name": "密码生成规则",
     "desc": "暴力生成密码：MIN:MAX:CHARSET（如 4:6:aA1）", "type": "str", "default": ""},
    # 行为
    {"group": "行为设置", "key": "exit_on_found", "flag": "-f", "name": "找到即退出(单主机)",
     "desc": "找到一组凭据即停止该主机（-M 时按主机）", "type": "bool", "default": False},
    {"group": "行为设置", "key": "exit_on_found_global", "flag": "-F", "name": "找到即退出(全局)",
     "desc": "找到一组凭据即停止所有主机（仅 -M 多目标）", "type": "bool", "default": False},
    {"group": "行为设置", "key": "loop_around_users", "flag": "-u", "name": "循环用户",
     "desc": "按用户循环而非按密码（对 -x 隐含启用）", "type": "bool", "default": False},
    {"group": "行为设置", "key": "no_redo_failed", "flag": "-K", "name": "不重试失败",
     "desc": "不重做失败的尝试（适合 -M 大规模扫描）", "type": "bool", "default": False},
    # 超时与重连
    {"group": "超时设置", "key": "wait_time", "flag": "-w", "name": "响应等待",
     "desc": "等待响应的时间（秒，默认 32）", "type": "int", "default": 0},
    {"group": "超时设置", "key": "wait_between", "flag": "-W", "name": "连接间隔",
     "desc": "每线程两次连接之间的间隔（秒）", "type": "int", "default": 0},
    {"group": "超时设置", "key": "timeout_per_login", "flag": "-c", "name": "单次登录超时",
     "desc": "所有线程单次登录的总耗时（秒，强制 -t 1）", "type": "int", "default": 0},
    # 连接选项
    {"group": "连接设置", "key": "ssl", "flag": "-S", "name": "SSL 连接",
     "desc": "使用 SSL 连接（如 https-/ssl 服务）", "type": "bool", "default": False},
    {"group": "连接设置", "key": "old_ssl", "flag": "-O", "name": "旧版 SSL",
     "desc": "使用旧的 SSL v2/v3", "type": "bool", "default": False},
    {"group": "连接设置", "key": "ipv4", "flag": "-4", "name": "使用 IPv4",
     "desc": "使用 IPv4 地址（默认）", "type": "bool", "default": False},
    {"group": "连接设置", "key": "ipv6", "flag": "-6", "name": "使用 IPv6",
     "desc": "使用 IPv6 地址", "type": "bool", "default": False},
    {"group": "连接设置", "key": "disable_symbols", "flag": "-y", "name": "禁用占位符",
     "desc": "禁止 -x 中 a/A/1 作为占位符，按字面字符使用", "type": "bool", "default": False},
    {"group": "连接设置", "key": "non_random_shuffle", "flag": "-r", "name": "非随机顺序",
     "desc": "-x 密码生成使用非随机顺序", "type": "bool", "default": False},
    # 输出与调试
    {"group": "输出设置", "key": "verbose", "flag": "-v", "name": "详细输出",
     "desc": "显示详细信息", "type": "bool", "default": False},
    {"group": "输出设置", "key": "show_attempt", "flag": "-V", "name": "显示每次尝试",
     "desc": "显示每次尝试的 login+pass", "type": "bool", "default": False},
    {"group": "输出设置", "key": "quiet", "flag": "-q", "name": "静默错误",
     "desc": "不打印连接错误信息", "type": "bool", "default": False},
    {"group": "输出设置", "key": "debug", "flag": "-d", "name": "调试模式",
     "desc": "输出调试信息", "type": "bool", "default": False},
    {"group": "输出设置", "key": "ignore_restore", "flag": "-I", "name": "忽略恢复文件",
     "desc": "忽略已有的 hydra.restore 文件（不等待 10 秒）", "type": "bool", "default": False},
    # 模块选项
    {"group": "模块选项", "key": "module_opt", "flag": "-m", "name": "模块参数",
     "desc": "模块特定选项，如 http-post-form 的页面规则，可用 hydra -U <service> 查询",
     "type": "str", "default": ""},
]
