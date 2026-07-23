"""hashcat 密码哈希恢复调用。

外部工具 hashcat（https://github.com/hashcat/hashcat）通过 asyncio 线程池执行。
支持 CPU/GPU 加速，400+ 哈希算法，6 种攻击模式（字典/组合/掩码/混合等）。

与 dirsearch/hydra/sqlmap/aircrack/searchsploit 保持一致的调用风格：
    拼装命令 -> exec_system 异步执行 -> 解析 outfile 结果 -> 清理临时文件。

【输出格式关键决策】固定使用 --outfile-format=1,2（hash + plain）+ --potfile-disable，
使每条破解结果为可控的 "<hash>:<plain>" 文本，避免依赖 hashcat 内部 potfile 格式
（这正是之前 hydra/dirsearch 解析 bug 的教训：不要假设工具的输出结构）。

options 字段（前端勾选 / 填值），完整参数清单见 PARAM_META。
"""
from __future__ import annotations

import os
from typing import Any

from ..config import Config, DICTS_DIR
from ..logger import get_logger
from ..utils import check_tool_available, exec_system, random_choices

logger = get_logger()

# hashcat 可执行文件名（按 PATH 解析；如需固定路径可设置环境变量 HASHCAT_BIN）
HASHCAT_BIN = os.environ.get("HASHCAT_BIN", "hashcat")

# 默认字典（项目自带）
DEFAULT_WORDLIST = os.path.join(DICTS_DIR, "passwordtop1000.txt")

# 布尔型参数：勾选即追加 flag
_BOOL_FLAGS: dict[str, str] = {
    # 基础
    "quiet": "--quiet",
    "force": "--force",                  # 忽略警告（如强制在不完全支持的 GPU 上运行）
    "keep_guessing": "--keep-guessing",  # 破解出后继续找其它明文
    # 状态/输出
    "status": "--status",                # 启用状态屏自动刷新
    "status_json": "--status-json",      # 状态屏用 JSON 格式
    "machine_readable": "--machine-readable",
    "show": "--show",                    # 与 potfile 比对，显示已破解的哈希
    "left": "--left",                    # 显示未破解的哈希
    "username": "--username",            # 哈希文件含用户名前缀时忽略用户名
    "remove": "--remove",                # 破解后从哈希文件移除
    # 性能/调试
    "self_test_disable": "--self-test-disable",
    "loopback": "--loopback",
    "markov_disable": "--markov-disable",
    "markov_classic": "--markov-classic",
    "optimized_kernel": "-O",            # 启用优化内核（限制密码长度）
    "stdout_mode": "--stdout",           # 不破解，只打印候选
    "potfile_disable": "--potfile-disable",
    # 设备
    "backend_ignore_cuda": "--backend-ignore-cuda",
    "backend_ignore_hip": "--backend-ignore-hip",
    "backend_ignore_metal": "--backend-ignore-metal",
    "backend_ignore_opencl": "--backend-ignore-opencl",
    "hwmon_disable": "--hwmon-disable",
    # 增量
    "increment": "-i",                   # 启用掩码增量模式
    "increment_inverse": "--increment-inverse",
    # 其它
    "logfile_disable": "--logfile-disable",
    "speed_only": "--speed-only",
    "progress_only": "--progress-only",
    "slow_candidates": "-S",
}

# 带值型参数：勾选后取值，参数名 -> (CLI flag, 类型)
_VALUE_FLAGS: dict[str, tuple[str, type]] = {
    # 核心
    "hash_type": ("-m", int),            # 哈希类型编号（如 0=MD5, 1000=NTLM）
    "attack_mode": ("-a", int),          # 攻击模式（0/1/3/6/7/8/9）
    # 字典/掩码（位置参数由 targets/wordlist 单独处理，这里保留 -r 等可选项）
    "rules_file": ("-r", str),           # 规则文件
    "rule_left": ("-j", str),            # 左字典单条规则
    "rule_right": ("-k", str),           # 右字典单条规则
    "generate_rules": ("-g", int),       # 随机生成 N 条规则
    "custom_charset1": ("-1", str),
    "custom_charset2": ("-2", str),
    "custom_charset3": ("-3", str),
    "custom_charset4": ("-4", str),
    # 性能
    "workload_profile": ("-w", int),     # 负载档位 1-4
    "kernel_accel": ("-n", int),         # 手动调优：外层步长
    "kernel_loops": ("-u", int),         # 手动调优：内层步长
    "kernel_threads": ("-T", int),       # 手动调优：线程数
    "segment_size": ("-c", int),         # 字典缓存大小（MB）
    "opencl_device_types": ("-D", str),  # 设备类型 1=CPU 2=GPU 3=FPGA
    "backend_devices": ("-d", str),      # 指定后端设备
    # 时间/范围
    "runtime": ("--runtime", int),       # 运行 N 秒后中止
    "skip": ("-s", int),
    "limit": ("-l", int),
    "markov_threshold": ("-t", int),     # markov 阈值
    "status_timer": ("--status-timer", int),
    # 增量
    "increment_min": ("--increment-min", int),
    "increment_max": ("--increment-max", int),
    # 会话
    "session": ("--session", str),
    # 输出
    "outfile_format": ("--outfile-format", str),  # 默认 1,2 由服务层固定
    "outfile_check_timer": ("--outfile-check-timer", int),
    "separator": ("-p", str),
    # hash 文件相关
    "hccapx_message_pair": ("--hccapx-message-pair", int),
    # 温度
    "hwmon_temp_abort": ("--hwmon-temp-abort", int),
}


class HashcatScan:
    """封装一次 hashcat 哈希恢复。

    Args:
        hash_file: 目标哈希文件路径（每行一个哈希，或 hash:plain 格式）。
        wordlist: 字典/掩码路径（攻击模式 0/6 需要字典；模式 3 需要掩码如 ?a?a?a?a）。
        options: 前端勾选/填值的参数字典（见模块文档字符串）。
    """

    def __init__(self, hash_file: str, wordlist: str = "",
                 options: dict | None = None):
        self.hash_file = hash_file or ""
        self.wordlist = (wordlist or "").strip()
        self.options = options or {}
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        # 破解结果输出文件（--outfile-format=1,2 → 每行 "<hash>:<plain>"）
        self.outfile = os.path.join(tmp_path, f"hashcat_out_{rand_str}.txt")
        # 独立 potfile，避免污染系统 potfile
        self.potfile = os.path.join(tmp_path, f"hashcat_pot_{rand_str}.pot")
        self._bin_path = HASHCAT_BIN

    # ---------- 探测 ----------
    def check_have_hashcat(self) -> bool:
        """探测 hashcat 是否可用（兼容 systemd 最小化 PATH + 非零退出码）。"""
        ok, abs_path = check_tool_available(HASHCAT_BIN, ["--version"], ["-h"])
        if ok and abs_path and "/" in abs_path:
            self._bin_path = abs_path
        else:
            self._bin_path = HASHCAT_BIN
        return ok

    # ---------- 命令拼装 ----------
    def _build_command(self) -> list[str]:
        """根据 options 拼装 hashcat CLI。

        固定追加：
          --outfile <file>  破解结果写到独立文件
          --outfile-format=1,2  输出格式 = hash + plain（每行 hash:plain）
          --potfile-path <file>  独立 potfile
        位置参数：hash_file [wordlist|mask]
        """
        cmd: list[str] = [
            self._bin_path,
            "--outfile", self.outfile,
            "--outfile-format=1,2",
            "--potfile-path", self.potfile,
        ]

        # 布尔开关
        for key, flag in _BOOL_FLAGS.items():
            if self.options.get(key):
                cmd.append(flag)

        # 带值参数
        # 这些参数 0 是有效值（hash_type=0 即 MD5，attack_mode=0 即字典），不能跳过
        _INT_ZERO_VALID = {"hash_type", "attack_mode", "opencl_device_types"}
        for key, (flag, typ) in _VALUE_FLAGS.items():
            val = self.options.get(key)
            if val is None or val == "":
                continue
            try:
                if typ is int:
                    n = int(val)
                    if n == 0 and key not in _INT_ZERO_VALID:
                        # 多数 int 参数 0 视为「未设置」，跳过让 hashcat 用默认
                        continue
                    val = str(n)
                else:
                    val = str(val).strip()
            except (TypeError, ValueError):
                logger.warning(f"hashcat 参数 {key} 取值非法: {val}，已忽略")
                continue
            if val:
                cmd.append(flag)
                cmd.append(val)

        # 哈希文件（位置参数，必填）
        if self.hash_file:
            cmd.append(self.hash_file)
        # 字典/掩码（位置参数，可选 —— benchmark/show 模式下不需要）
        if self.wordlist:
            cmd.append(self.wordlist)
        return cmd

    # ---------- 执行 ----------
    async def exec_hashcat(self) -> None:
        cmd = self._build_command()
        logger.info("hashcat cmd: " + " ".join(cmd))
        # hashcat GPU 破解可能极长，沿用 24h 上限
        await exec_system(cmd, timeout=24 * 60 * 60)

    # ---------- 结果解析 ----------
    def dump_result(self) -> list[dict]:
        """解析 --outfile-format=1,2 的输出，每行 "<hash>:<plain>"。

        注意：hash 本身可能含冒号（如 NTLM 的 user:hash），但 plain 一定在最后一段。
        因此用 rsplit(":", 1) 从右切一刀，确保 plain 准确。
        破解失败时 outfile 不存在或为空，返回空列表。
        """
        if not os.path.exists(self.outfile):
            return []
        results: list[dict] = []
        try:
            with open(self.outfile, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # hash[:salt] 在左，plain 在右（split 只切最右侧冒号）
                    if ":" in line:
                        hash_part, plain = line.rsplit(":", 1)
                    else:
                        hash_part, plain = line, ""
                    results.append({
                        "hash": hash_part,
                        "plain": plain,
                        "cracked": bool(plain),
                    })
        except OSError as e:
            logger.warning(f"读取 hashcat outfile 失败: {e}")
        return results

    def _delete_file(self) -> None:
        for p in (self.outfile, self.potfile):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # ---------- 主流程 ----------
    async def run(self) -> list[dict]:
        if not self.hash_file or not os.path.exists(self.hash_file):
            logger.warning(f"hashcat hash file not found: {self.hash_file}")
            return []
        if not self.check_have_hashcat():
            logger.warning(f"not found hashcat binary: {HASHCAT_BIN}")
            return []
        try:
            await self.exec_hashcat()
            return self.dump_result()
        finally:
            self._delete_file()


async def run_hashcat(hash_file: str, wordlist: str = "",
                      options: dict | None = None) -> list[dict]:
    """模块级入口：执行一次 hashcat 哈希恢复并返回结构化结果。"""
    logger.info(f"run hashcat, hash_file: {hash_file}, wordlist: {wordlist}")
    results = await HashcatScan(hash_file=hash_file, wordlist=wordlist,
                                options=options or {}).run()
    logger.info(f"hashcat cracked: {len(results)}")
    return results


# 供前端展示的参数元数据（精选高频项，分组 + 说明 + 默认值 + 类型）
PARAM_META: list[dict[str, Any]] = [
    # 核心
    {"group": "核心设置", "key": "hash_type", "flag": "-m", "name": "哈希类型",
     "desc": "哈希算法编号（如 0=MD5, 100=SHA1, 1000=NTLM, 1800=sha512crypt, 留空自动识别）",
     "type": "int", "default": 0},
    {"group": "核心设置", "key": "attack_mode", "flag": "-a", "name": "攻击模式",
     "desc": "0=字典 1=组合 3=掩码(爆破) 6=字典+掩码 7=掩码+字典 8=通用 9=关联（默认 0）",
     "type": "int", "default": 0},
    {"group": "核心设置", "key": "force", "flag": "--force", "name": "忽略警告",
     "desc": "忽略警告（如强制在不完全支持的 GPU 上运行）", "type": "bool", "default": False},
    {"group": "核心设置", "key": "quiet", "flag": "--quiet", "name": "静默模式",
     "desc": "抑制输出", "type": "bool", "default": False},
    {"group": "核心设置", "key": "keep_guessing", "flag": "--keep-guessing", "name": "继续猜测",
     "desc": "破解出一个明文后继续找其它明文", "type": "bool", "default": False},
    {"group": "核心设置", "key": "username", "flag": "--username", "name": "含用户名",
     "desc": "哈希文件含用户名前缀（如 user:hash）时启用，忽略用户名部分", "type": "bool", "default": False},
    # 字典/规则
    {"group": "字典规则", "key": "rules_file", "flag": "-r", "name": "规则文件",
     "desc": "对字典每条词应用规则（如 rules/best66.rule）", "type": "str",
     "default": "", "file": True},
    {"group": "字典规则", "key": "rule_left", "flag": "-j", "name": "左字典规则",
     "desc": "对左字典每条词应用的单条规则", "type": "str", "default": ""},
    {"group": "字典规则", "key": "rule_right", "flag": "-k", "name": "右字典规则",
     "desc": "对右字典每条词应用的单条规则", "type": "str", "default": ""},
    {"group": "字典规则", "key": "generate_rules", "flag": "-g", "name": "随机规则数",
     "desc": "随机生成 N 条规则", "type": "int", "default": 0},
    # 掩码
    {"group": "掩码设置", "key": "custom_charset1", "flag": "-1", "name": "自定义字符集 ?1",
     "desc": "自定义 ?1 字符集（如 ?l?d?u = 小写+数字+大写）", "type": "str", "default": ""},
    {"group": "掩码设置", "key": "custom_charset2", "flag": "-2", "name": "自定义字符集 ?2",
     "desc": "自定义 ?2 字符集", "type": "str", "default": ""},
    {"group": "掩码设置", "key": "increment", "flag": "-i", "name": "增量模式",
     "desc": "启用掩码增量模式（逐长度爆破）", "type": "bool", "default": False},
    {"group": "掩码设置", "key": "increment_min", "flag": "--increment-min", "name": "增量最小长度",
     "desc": "掩码增量起始长度", "type": "int", "default": 0},
    {"group": "掩码设置", "key": "increment_max", "flag": "--increment-max", "name": "增量最大长度",
     "desc": "掩码增量终止长度", "type": "int", "default": 0},
    # 性能
    {"group": "性能设置", "key": "workload_profile", "flag": "-w", "name": "负载档位",
     "desc": "1=低 2=默认 3=高 4=极限（越高越快但桌面越卡）", "type": "int", "default": 0},
    {"group": "性能设置", "key": "optimized_kernel", "flag": "-O", "name": "优化内核",
     "desc": "启用优化内核（限制密码长度，提速）", "type": "bool", "default": False},
    {"group": "性能设置", "key": "kernel_accel", "flag": "-n", "name": "外层步长",
     "desc": "手动调优：外层循环步长", "type": "int", "default": 0},
    {"group": "性能设置", "key": "kernel_loops", "flag": "-u", "name": "内层步长",
     "desc": "手动调优：内层循环步长", "type": "int", "default": 0},
    {"group": "性能设置", "key": "opencl_device_types", "flag": "-D", "name": "设备类型",
     "desc": "1=CPU 2=GPU 3=FPGA/DSP（默认自动）", "type": "str", "default": ""},
    {"group": "性能设置", "key": "backend_devices", "flag": "-d", "name": "指定设备",
     "desc": "使用的后端设备编号，逗号分隔（如 1,2）", "type": "str", "default": ""},
    # 时间/范围
    {"group": "时间范围", "key": "runtime", "flag": "--runtime", "name": "运行时长(秒)",
     "desc": "运行 N 秒后中止会话", "type": "int", "default": 0},
    {"group": "时间范围", "key": "skip", "flag": "-s", "name": "跳过词数",
     "desc": "从开头跳过 X 个候选", "type": "int", "default": 0},
    {"group": "时间范围", "key": "limit", "flag": "-l", "name": "限制词数",
     "desc": "最多尝试 X 个候选（含跳过部分）", "type": "int", "default": 0},
    {"group": "时间范围", "key": "markov_threshold", "flag": "-t", "name": "markov 阈值",
     "desc": "markov 链阈值（默认由 hashcat 决定）", "type": "int", "default": 0},
    # 状态/输出
    {"group": "状态输出", "key": "status", "flag": "--status", "name": "状态屏",
     "desc": "启用状态屏自动刷新", "type": "bool", "default": False},
    {"group": "状态输出", "key": "status_timer", "flag": "--status-timer", "name": "状态刷新间隔",
     "desc": "状态屏刷新间隔（秒）", "type": "int", "default": 0},
    {"group": "状态输出", "key": "status_json", "flag": "--status-json", "name": "状态 JSON",
     "desc": "状态屏用 JSON 格式输出", "type": "bool", "default": False},
    {"group": "状态输出", "key": "machine_readable", "flag": "--machine-readable",
     "name": "机器可读", "desc": "状态屏以机器可读格式输出", "type": "bool", "default": False},
    # 会话
    {"group": "会话管理", "key": "session", "flag": "--session", "name": "会话名",
     "desc": "定义会话名（便于断点续跑 --restore）", "type": "str", "default": ""},
    # potfile
    {"group": "其它", "key": "potfile_disable", "flag": "--potfile-disable",
     "name": "禁用 potfile", "desc": "不写 potfile（本服务默认用独立 potfile）",
     "type": "bool", "default": False},
    {"group": "其它", "key": "self_test_disable", "flag": "--self-test-disable",
     "name": "禁用自检", "desc": "启动时禁用内核自检", "type": "bool", "default": False},
    {"group": "其它", "key": "hwmon_disable", "flag": "--hwmon-disable",
     "name": "禁用温度监控", "desc": "禁用温度/风扇读取", "type": "bool", "default": False},
    {"group": "其它", "key": "hwmon_temp_abort", "flag": "--hwmon-temp-abort",
     "name": "温度中止", "desc": "温度达 X 度时中止（摄氏度）", "type": "int", "default": 0},
    {"group": "其它", "key": "loopback", "flag": "--loopback", "name": "loopback",
     "desc": "将新破解的明文加入归纳目录复用", "type": "bool", "default": False},
    {"group": "其它", "key": "show", "flag": "--show", "name": "显示已破解",
     "desc": "与 potfile 比对，显示已破解的哈希", "type": "bool", "default": False},
    {"group": "其它", "key": "left", "flag": "--left", "name": "显示未破解",
     "desc": "显示尚未破解的哈希", "type": "bool", "default": False},
]
