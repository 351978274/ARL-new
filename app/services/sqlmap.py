"""sqlmap SQL 注入检测调用。

外部工具 sqlmap（https://github.com/sqlmapproject/sqlmap）通过 asyncio 线程池执行。
自动检测并利用 SQL 注入，支持数据库指纹、数据枚举、文件读取、OS 命令执行等。

与 dirsearch.py / hydra.py / nuclei_scan.py / info_hunter.py 保持一致的调用风格：
    生成临时批量目标文件（可选）-> 拼装命令 -> exec_system 异步执行 -> 解析结果 -> 清理。

sqlmap 结果解析：
    sqlmap 会在 outputDir/<target>/ 下生成 log.txt / session.sqlite 等文件。
    本模块解析 log.txt，提取关键注入信息（注入点、参数、技术、Payload）入库。

options 字段（前端勾选 / 填值），完整参数清单见 PARAM_META。
参数命名与 sqlmap.conf 一致（camelCase），CLI flag 通过下划线/驼峰转 kebab 自动生成。
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from ..config import Config
from ..logger import get_logger
from ..utils import exec_system, random_choices

logger = get_logger()

# sqlmap 可执行文件名（按 PATH 解析；如需固定路径可设置环境变量 SQLMAP_BIN 或 SQLMAP_PATH）
SQLMAP_BIN = os.environ.get("SQLMAP_BIN", "sqlmap")


def _camel_to_kebab(name: str) -> str:
    """camelCase -> kebab-case（sqlmap CLI 风格）。

    例：getAll -> get-all；testParameter -> test-parameter；
        dropSetCookie -> drop-set-cookie；url -> url。
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


# 布尔型参数：勾选即追加 --xxx（无需值）
# key 与 sqlmap.conf / sqlmap CLI 一致（camelCase）
_BOOL_FLAGS: dict[str, str] = {
    # Request
    "drop_set_cookie": "--drop-set-cookie",
    "http10": "--http10",
    "http2": "--http2",
    "mobile": "--mobile",
    "random_agent": "--random-agent",
    "ignore_proxy": "--ignore-proxy",
    "ignore_redirects": "--ignore-redirects",
    "ignore_timeouts": "--ignore-timeouts",
    "tor": "--tor",
    "check_tor": "--check-tor",
    "skip_url_encode": "--skip-urlencode",
    "skip_xml_encode": "--skip-xml-encode",
    "force_ssl": "--force-ssl",
    "chunked": "--chunked",
    "hpp": "--hpp",
    # Optimization
    "optimize": "--optimize",
    "predict_output": "--predict-output",
    "keep_alive": "--keep-alive",
    "null_connection": "--null-connection",
    # Injection
    "skip_static": "--skip-static",
    "invalid_bignum": "--invalid-bignum",
    "invalid_logical": "--invalid-logical",
    "invalid_string": "--invalid-string",
    "no_cast": "--no-cast",
    "no_escape": "--no-escape",
    # Detection
    "smart": "--smart",
    "text_only": "--text-only",
    "titles": "--titles",
    # Techniques
    "disable_stats": "--disable-stats",
    # Fingerprint
    "extensive_fp": "--extensive-fp",
    # Enumeration
    "is_dba": "--is-dba",
    "get_banner": "--banner",
    "get_current_user": "--current-user",
    "get_current_db": "--current-db",
    "get_hostname": "--hostname",
    "get_users": "--users",
    "get_password_hashes": "--passwords",
    "get_privileges": "--privileges",
    "get_roles": "--roles",
    "get_dbs": "--dbs",
    "get_tables": "--tables",
    "get_columns": "--columns",
    "get_schema": "--schema",
    "get_count": "--count",
    "dump_table": "--dump",
    "dump_all": "--dump-all",
    "get_all": "--all",
    "search": "--search",
    "get_comments": "--comments",
    "get_statements": "--statements",
    "exclude_sys_dbs": "--exclude-sysdbs",
    "sql_shell": "--sql-shell",
    # Brute force
    "common_tables": "--common-tables",
    "common_columns": "--common-columns",
    "common_files": "--common-files",
    # UDF
    "udf_inject": "--udf-inject",
    # Takeover
    "os_shell": "--os-shell",
    "os_pwn": "--os-pwn",
    "os_smb": "--os-smb",
    "os_bof": "--os-bof",
    "priv_esc": "--priv-esc",
    # General
    "batch": "--batch",
    "flush_session": "--flush-session",
    "forms": "--forms",
    "fresh_queries": "--fresh-queries",
    "hex_convert": "--hex-convert",
    "parse_errors": "--parse-errors",
    "skip_heuristics": "--skip-heuristics",
    "skip_waf": "--skip-waf",
    "eta": "--eta",
    "cleanup": "--cleanup",
    # Miscellaneous
    "beep": "--beep",
    "dependencies": "--dependencies",
    "disable_coloring": "--disable-coloring",
    "disable_hashing": "--disable-hashing",
    "list_tampers": "--list-tampers",
    "offline": "--offline",
    "update_all": "--update-all",
    "wizard": "--wizard",
}

# 带值型参数：勾选后取值，参数名 -> (CLI flag, 类型)
# 注：部分参数 sqlmap CLI 名与 camelCase 不规则，这里显式映射。
_VALUE_FLAGS: dict[str, tuple[str, type]] = {
    # Target（url 由 targets 列表驱动，单独处理）
    "direct": ("-d", str),
    "log_file": ("-l", str),
    "bulk_file": ("-m", str),
    "request_file": ("-r", str),
    "google_dork": ("-g", str),
    # Request
    "method": "--method",
    "data": "--data",
    "param_del": "--param-del",
    "cookie": "--cookie",
    "cookie_del": "--cookie-del",
    "live_cookies": "--live-cookies",
    "load_cookies": "--load-cookies",
    "agent": "--user-agent",
    "host": "--host",
    "referer": "--referer",
    "headers": "--headers",
    "auth_type": "--auth-type",
    "auth_cred": "--auth-cred",
    "auth_file": "--auth-file",
    "abort_code": "--abort-code",
    "ignore_code": "--ignore-code",
    "proxy": "--proxy",
    "proxy_cred": "--proxy-cred",
    "proxy_file": "--proxy-file",
    "tor_port": "--tor-port",
    "tor_type": "--tor-type",
    "delay": ("--delay", float),
    "timeout": ("--timeout", float),
    "retries": ("--retries", int),
    "retry_on": "--retry-on",
    "r_param": "--rparam",
    "safe_url": "--safe-url",
    "safe_post": "--safe-post",
    "safe_req_file": "--safe-req",
    "safe_freq": ("--safe-freq", int),
    "csrf_token": "--csrf-token",
    "csrf_url": "--csrf-url",
    "csrf_method": "--csrf-method",
    "csrf_data": "--csrf-data",
    "csrf_retries": ("--csrf-retries", int),
    "eval_code": "--eval",
    # Optimization
    "threads": ("--threads", int),
    # Injection
    "test_parameter": "-p",
    "skip": "--skip",
    "param_exclude": "--param-exclude",
    "param_filter": "--param-filter",
    "dbms": "--dbms",
    "dbms_cred": "--dbms-cred",
    "os": "--os",
    "prefix": "--prefix",
    "suffix": "--suffix",
    "tamper": "--tamper",
    # Detection
    "level": ("--level", int),
    "risk": ("--risk", int),
    "string": "--string",
    "not_string": "--not-string",
    "regexp": "--regexp",
    "code": ("--code", int),
    # Techniques
    "technique": "--technique",
    "time_sec": ("--time-sec", int),
    "u_cols": "--union-cols",
    "u_char": "--union-char",
    "u_from": "--union-from",
    "u_values": "--union-values",
    "dns_domain": "--dns-domain",
    "second_url": "--second-url",
    "second_req": "--second-req",
    # Enumeration
    "db": "-D",
    "tbl": "-T",
    "col": "-C",
    "exclude": "--exclude",
    "pivot_column": "--pivot-column",
    "dump_where": "--dump-where",
    "user": "-U",
    "limit_start": ("--start", int),
    "limit_stop": ("--stop", int),
    "first_char": ("--first", int),
    "last_char": ("--last", int),
    "sql_query": "--sql-query",
    "sql_file": "--sql-file",
    # UDF
    "sh_lib": "--shared-lib",
    # File system
    "file_read": "--file-read",
    "file_write": "--file-write",
    "file_dest": "--file-dest",
    # Takeover
    "os_cmd": "--os-cmd",
    "msf_path": "--msf-path",
    "tmp_path": "--tmp-path",
    # General
    "session_file": "-s",
    "traffic_file": "-t",
    "answers": "--answers",
    "base64_parameter": "--base64-parameter",
    "base64_safe": ("--base64-safe", bool),
    "binary_fields": "--binary-fields",
    "crawl_depth": ("--crawl", int),
    "crawl_exclude": "--crawl-exclude",
    "csv_del": "--csv-del",
    "dump_file": "--dump-file",
    "dump_format": "--dump-format",
    "encoding": "--encoding",
    "google_page": ("--google-page", int),
    "output_dir": "--output-dir",
    "preprocess": "--preprocess",
    "postprocess": "--postprocess",
    "scope": "--scope",
    "table_prefix": "--table-prefix",
    "test_filter": "--test-filter",
    "test_skip": "--test-skip",
    "time_limit": ("--time-limit", int),
    "web_root": "--web-root",
    # Miscellaneous
    "results_file": "--results-file",
    "tmp_dir": "--tmp-dir",
    "verbose": ("-v", int),
}


class SqlmapScan:
    """封装一次 sqlmap 扫描。

    Args:
        targets: 目标 URL 列表（GET 带 id 参数最有效）。
        options: 前端勾选/填值的参数字典（见模块文档字符串）。
    """

    def __init__(self, targets: list[str], options: dict | None = None):
        self.targets = [t.strip() for t in targets if t and t.strip()]
        self.options = options or {}
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        # 多目标时写入 bulkfile (-m)
        self.bulk_file = os.path.join(tmp_path, f"sqlmap_target_{rand_str}.txt")
        # 自定义 outputDir，便于解析
        self.output_dir = os.path.join(tmp_path, f"sqlmap_out_{rand_str}")

    # ---------- 临时文件 ----------
    def _gen_bulk_file(self) -> None:
        with open(self.bulk_file, "w", encoding="utf-8") as f:
            for t in self.targets:
                f.write(t + "\n")

    def _delete_file(self) -> None:
        for p in (self.bulk_file,):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning(f"清理 sqlmap 临时文件失败 {p}: {e}")
        # outputDir 内可能有 session.sqlite 等文件，递归清理
        if os.path.isdir(self.output_dir):
            import shutil
            try:
                shutil.rmtree(self.output_dir, ignore_errors=True)
            except OSError as e:
                logger.warning(f"清理 sqlmap outputDir 失败: {e}")

    # ---------- 探测 ----------
    def check_have_sqlmap(self) -> bool:
        """探测 sqlmap 是否可用。"""
        try:
            pro = subprocess.run(
                [SQLMAP_BIN, "--version"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            return pro.returncode == 0
        except Exception as e:
            logger.debug(str(e))
            return False

    # ---------- 命令拼装 ----------
    def _build_command(self) -> list[str]:
        """根据 options 拼装 sqlmap CLI。

        - 单目标：-u <url>
        - 多目标：-m <bulkfile>
        - 固定追加：--batch（非交互）、--output-dir、--random-agent（默认开）
        """
        cmd: list[str] = [SQLMAP_BIN, "--batch",
                          "--output-dir", self.output_dir]

        # 目标
        if len(self.targets) == 1:
            cmd.extend(["-u", self.targets[0]])
        elif len(self.targets) > 1:
            self._gen_bulk_file()
            cmd.extend(["-m", self.bulk_file])

        # 布尔开关
        for key, flag in _BOOL_FLAGS.items():
            if self.options.get(key):
                cmd.append(flag)

        # 带值参数
        for key, spec in _VALUE_FLAGS.items():
            val = self.options.get(key)
            if val is None:
                continue
            flag, typ = spec if isinstance(spec, tuple) else (spec, str)
            try:
                if typ is int:
                    n = int(val)
                    if n == 0 and key not in ("verbose", "crawl_depth"):
                        # 多数 int 参数 0 表示「用默认」，跳过；verbose/crawl 允许显式 0
                        # 但 verbose 默认 1，用户传 0 应保留；crawl_depth 默认 0
                        continue
                    val = str(n)
                elif typ is float:
                    f = float(val)
                    if f == 0:
                        # float 参数 0 视为「用默认」，跳过（如 delay/timeout）
                        continue
                    val = str(f)
                else:
                    val = str(val).strip()
            except (TypeError, ValueError):
                logger.warning(f"sqlmap 参数 {key} 取值非法: {val}，已忽略")
                continue
            if val:
                cmd.append(flag)
                cmd.append(val)
        return cmd

    # ---------- 执行 ----------
    async def exec_sqlmap(self) -> None:
        cmd = self._build_command()
        logger.info("sqlmap cmd: " + " ".join(cmd))
        # sqlmap 深度枚举可能很长，沿用 24h 上限
        await exec_system(cmd, timeout=24 * 60 * 60)

    # ---------- 结果解析 ----------
    def _find_log_files(self) -> list[str]:
        """查找 outputDir 下所有 log.txt（每个目标一个子目录）。"""
        logs: list[str] = []
        if not os.path.isdir(self.output_dir):
            return logs
        for root, _dirs, files in os.walk(self.output_dir):
            if "log.txt" in files:
                logs.append(os.path.join(root, "log.txt"))
        return logs

    def dump_result(self) -> list[dict]:
        """解析 sqlmap log.txt，提取注入点信息。

        典型可识别行（sqlmap 输出）：
            GET parameter 'id' is vulnerable. ...
            Parameter: id (GET)
                Type: boolean-based blind
                Title: ...
                Payload: ...
            available databases [5]: [...]
            back-end DBMS: MySQL >= 5.0
        """
        results: list[dict] = []
        for log_path in self._find_log_files():
            # 从路径推断 target（outputDir/<target>/log.txt）
            target_dir = os.path.basename(os.path.dirname(log_path))
            base_result = {
                "target": target_dir,
                "vulnerable": False,
                "parameter": "",
                "techniques": [],
                "payloads": [],
                "dbms": "",
                "banner": "",
                "current_db": "",
                "current_user": "",
                "log_path": log_path,
            }
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError as e:
                logger.warning(f"读取 sqlmap log 失败 {log_path}: {e}")
                continue

            # 注入点参数（"Parameter: xxx (METHOD)" 块仅在确认注入时出现）
            m = re.search(r"Parameter:\s*(\S+)\s*\((\w+)\)", content)
            if m:
                base_result["parameter"] = f"{m.group(1)} ({m.group(2)})"
                base_result["vulnerable"] = True
            # 兜底：捕获 "GET/POST parameter 'x' is vulnerable" 旧式表述
            vuln_m = re.search(r"(\w+\s+parameter\s+'?[^']+'?)\s+is vulnerable", content, re.I)
            if vuln_m:
                base_result["vulnerable"] = True
                if not base_result["parameter"]:
                    base_result["parameter"] = vuln_m.group(1)
            # 技术
            for tech in re.findall(r"Type:\s*(.+)", content):
                tech = tech.strip()
                if tech and tech not in base_result["techniques"]:
                    base_result["techniques"].append(tech)
            # Payload
            for pl in re.findall(r"Payload:\s*(.+)", content):
                pl = pl.strip()
                if pl and pl not in base_result["payloads"]:
                    base_result["payloads"].append(pl)
            # DBMS / banner / 当前库 / 当前用户
            m = re.search(r"back-end DBMS:\s*(.+)", content)
            if m:
                base_result["dbms"] = m.group(1).strip()
            m = re.search(r"banner:\s*['\"](.+?)['\"]", content)
            if m:
                base_result["banner"] = m.group(1).strip()
            m = re.search(r"current database:\s*['\"](.+?)['\"]", content, re.I)
            if m:
                base_result["current_db"] = m.group(1).strip()
            m = re.search(r"current user:\s*['\"](.+?)['\"]", content, re.I)
            if m:
                base_result["current_user"] = m.group(1).strip()

            base_result["techniques"] = ", ".join(base_result["techniques"])
            # payloads 可能很长，截断到首条+总数
            if base_result["payloads"]:
                base_result["payloads"] = (f"{base_result['payloads'][0]}"
                                           f" (共 {len(base_result['payloads'])} 条)")
            else:
                base_result["payloads"] = ""
            results.append(base_result)
        return results

    # ---------- 主流程 ----------
    async def run(self) -> list[dict]:
        if not self.targets:
            return []
        if not self.check_have_sqlmap():
            logger.warning(f"not found sqlmap binary: {SQLMAP_BIN}")
            return []
        try:
            await self.exec_sqlmap()
            return self.dump_result()
        finally:
            self._delete_file()


async def run_sqlmap(targets: list[str], options: dict | None = None) -> list[dict]:
    """模块级入口：执行一次 sqlmap 扫描并返回结构化结果。"""
    logger.info(f"run sqlmap, targets: {len(targets)}")
    results = await SqlmapScan(targets=targets, options=options or {}).run()
    logger.info(f"sqlmap result: {len(results)}")
    return results


# 供前端展示的参数元数据（精选常用项，分组 + 说明 + 默认值 + 类型）
# 完整参数列表见 _BOOL_FLAGS / _VALUE_FLAGS；前端元数据聚焦高频参数避免界面过载。
PARAM_META: list[dict[str, Any]] = [
    # Request
    {"group": "请求设置", "key": "data", "flag": "--data", "name": "POST 数据",
     "desc": "POST 请求体（如 id=1&name=test），指定后 sqlmap 测试 POST 参数", "type": "str", "default": ""},
    {"group": "请求设置", "key": "cookie", "flag": "--cookie", "name": "Cookie",
     "desc": "HTTP Cookie 头（如 PHPSESSID=xxx）", "type": "str", "default": ""},
    {"group": "请求设置", "key": "method", "flag": "--method", "name": "HTTP 方法",
     "desc": "强制使用的 HTTP 方法（如 PUT）", "type": "str", "default": ""},
    {"group": "请求设置", "key": "agent", "flag": "--user-agent", "name": "User-Agent",
     "desc": "自定义 User-Agent（默认随机）", "type": "str", "default": ""},
    {"group": "请求设置", "key": "random_agent", "flag": "--random-agent", "name": "随机 UA",
     "desc": "随机选择 User-Agent（默认启用）", "type": "bool", "default": True},
    {"group": "请求设置", "key": "headers", "flag": "--headers", "name": "额外请求头",
     "desc": "额外 HTTP 头（如 'X-Forwarded-For: 1.2.3.4'）", "type": "str", "default": ""},
    {"group": "请求设置", "key": "referer", "flag": "--referer", "name": "Referer",
     "desc": "HTTP Referer 头", "type": "str", "default": ""},
    {"group": "请求设置", "key": "auth_type", "flag": "--auth-type", "name": "认证类型",
     "desc": "HTTP 认证类型：Basic/Digest/Bearer/NTLM/PKI", "type": "str", "default": ""},
    {"group": "请求设置", "key": "auth_cred", "flag": "--auth-cred", "name": "认证凭据",
     "desc": "认证凭据 user:password", "type": "str", "default": ""},
    {"group": "请求设置", "key": "proxy", "flag": "--proxy", "name": "代理",
     "desc": "HTTP/SOCKS 代理（如 http://127.0.0.1:8080）", "type": "str", "default": ""},
    {"group": "请求设置", "key": "tor", "flag": "--tor", "name": "使用 Tor",
     "desc": "通过 Tor 网络连接", "type": "bool", "default": False},
    {"group": "请求设置", "key": "delay", "flag": "--delay", "name": "请求间隔",
     "desc": "每个 HTTP 请求之间的延迟（秒）", "type": "float", "default": 0},
    {"group": "请求设置", "key": "timeout", "flag": "--timeout", "name": "超时",
     "desc": "连接超时（秒，默认 30）", "type": "float", "default": 30},
    {"group": "请求设置", "key": "retries", "flag": "--retries", "name": "重试次数",
     "desc": "连接超时时的重试次数（默认 3）", "type": "int", "default": 3},
    {"group": "请求设置", "key": "force_ssl", "flag": "--force-ssl", "name": "强制 SSL",
     "desc": "强制使用 HTTPS", "type": "bool", "default": False},
    # Optimization
    {"group": "性能设置", "key": "threads", "flag": "--threads", "name": "并发线程",
     "desc": "最大并发 HTTP 请求数（默认 1，盲注时建议 ≤10）", "type": "int", "default": 1},
    {"group": "性能设置", "key": "optimize", "flag": "--optimize", "name": "启用所有优化",
     "desc": "开启所有性能优化开关", "type": "bool", "default": False},
    {"group": "性能设置", "key": "keep_alive", "flag": "--keep-alive", "name": "持久连接",
     "desc": "使用 HTTP 持久连接", "type": "bool", "default": False},
    # Injection
    {"group": "注入设置", "key": "test_parameter", "flag": "-p", "name": "测试参数",
     "desc": "只测试指定参数（逗号分隔，如 id,name）", "type": "str", "default": ""},
    {"group": "注入设置", "key": "skip", "flag": "--skip", "name": "跳过参数",
     "desc": "跳过指定参数不测试", "type": "str", "default": ""},
    {"group": "注入设置", "key": "dbms", "flag": "--dbms", "name": "指定 DBMS",
     "desc": "强制后端数据库类型（mysql/mssql/oracle/pgsql/sqlite/...），留空自动识别", "type": "str", "default": ""},
    {"group": "注入设置", "key": "os", "flag": "--os", "name": "指定 OS",
     "desc": "强制后端操作系统（linux/windows）", "type": "str", "default": ""},
    {"group": "注入设置", "key": "tamper", "flag": "--tamper", "name": "tamper 脚本",
     "desc": "篡改注入数据的脚本（如 space2comment,between），绕过 WAF", "type": "str", "default": ""},
    {"group": "注入设置", "key": "prefix", "flag": "--prefix", "name": "Payload 前缀",
     "desc": "注入 payload 前缀字符串", "type": "str", "default": ""},
    {"group": "注入设置", "key": "suffix", "flag": "--suffix", "name": "Payload 后缀",
     "desc": "注入 payload 后缀字符串", "type": "str", "default": ""},
    {"group": "注入设置", "key": "skip_waf", "flag": "--skip-waf", "name": "跳过 WAF 检测",
     "desc": "跳过 WAF/IPS 启发式检测", "type": "bool", "default": False},
    # Detection
    {"group": "检测设置", "key": "level", "flag": "--level", "name": "测试级别",
     "desc": "测试级别 1-5，越高测试越全（默认 1，含 Cookie/UA 等需 ≥2）", "type": "int", "default": 1},
    {"group": "检测设置", "key": "risk", "flag": "--risk", "name": "风险级别",
     "desc": "风险级别 1-3，越高越激进（默认 1，OR 注入需 3）", "type": "int", "default": 1},
    {"group": "检测设置", "key": "smart", "flag": "--smart", "name": "智能检测",
     "desc": "仅在正向启发后才做完整测试", "type": "bool", "default": False},
    # Techniques
    {"group": "技术设置", "key": "technique", "flag": "--technique", "name": "注入技术",
     "desc": "使用的注入技术：B=布尔盲注 E=错误 U=UNION S=堆叠 T=时间 Q=内联（默认 BEUSTQ）", "type": "str", "default": "BEUSTQ"},
    {"group": "技术设置", "key": "time_sec", "flag": "--time-sec", "name": "延时秒数",
     "desc": "时间盲注的响应延迟秒数（默认 5）", "type": "int", "default": 5},
    # Enumeration（高频开关）
    {"group": "数据枚举", "key": "get_banner", "flag": "--banner", "name": "获取 banner",
     "desc": "获取数据库 banner", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "get_current_db", "flag": "--current-db", "name": "当前库",
     "desc": "获取当前数据库名", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "get_current_user", "flag": "--current-user", "name": "当前用户",
     "desc": "获取当前数据库用户", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "is_dba", "flag": "--is-dba", "name": "是否 DBA",
     "desc": "检测当前用户是否为 DBA", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "get_dbs", "flag": "--dbs", "name": "枚举数据库",
     "desc": "枚举所有数据库名", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "get_tables", "flag": "--tables", "name": "枚举表",
     "desc": "枚举指定库的表（配合 -D）", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "get_columns", "flag": "--columns", "name": "枚举列",
     "desc": "枚举指定表的列（配合 -T）", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "dump_table", "flag": "--dump", "name": "导出表数据",
     "desc": "导出指定表的数据（配合 -T）", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "dump_all", "flag": "--dump-all", "name": "导出所有",
     "desc": "导出所有库的所有表数据（耗时极长）", "type": "bool", "default": False},
    {"group": "数据枚举", "key": "db", "flag": "-D", "name": "指定库",
     "desc": "枚举/导出时指定的数据库", "type": "str", "default": ""},
    {"group": "数据枚举", "key": "tbl", "flag": "-T", "name": "指定表",
     "desc": "枚举/导出时指定的表", "type": "str", "default": ""},
    {"group": "数据枚举", "key": "col", "flag": "-C", "name": "指定列",
     "desc": "枚举/导出时指定的列", "type": "str", "default": ""},
    {"group": "数据枚举", "key": "exclude_sys_dbs", "flag": "--exclude-sysdbs", "name": "排除系统库",
     "desc": "枚举表时排除系统数据库", "type": "bool", "default": False},
    # General
    {"group": "通用设置", "key": "flush_session", "flag": "--flush-session", "name": "清空会话",
     "desc": "清空当前目标的会话文件（重新检测）", "type": "bool", "default": False},
    {"group": "通用设置", "key": "crawl_depth", "flag": "--crawl", "name": "爬虫深度",
     "desc": "从目标 URL 开始爬取的深度（>0 时启用爬虫）", "type": "int", "default": 0},
    {"group": "通用设置", "key": "forms", "flag": "--forms", "name": "解析表单",
     "desc": "解析并测试目标 URL 上的表单", "type": "bool", "default": False},
    {"group": "通用设置", "key": "batch", "flag": "--batch", "name": "批处理模式",
     "desc": "非交互模式，使用默认行为（默认启用）", "type": "bool", "default": True},
    {"group": "通用设置", "key": "verbose", "flag": "-v", "name": "详细级别",
     "desc": "输出详细级别 0-6（默认 1）", "type": "int", "default": 1},
]
