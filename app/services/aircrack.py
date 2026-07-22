"""aircrack-ng 离线 WEP/WPA-PSK 密钥破解调用。

外部工具 aircrack-ng（https://github.com/aircrack-ng/aircrack-ng）通过 asyncio 线程池执行。
与 dirsearch/hydra/sqlmap 不同，aircrack-ng 是离线破解工具，输入为：
    - 抓包文件（.cap/.pcap/.ivs/.hccapx，含 WPA 握手或 WEP IV）
    - 字典文件（-w）
破解结果（KEY）写入 -l 指定的 key file，同时解析 stdout 提取破解信息。

与 dirsearch.py / hydra.py / sqlmap.py 保持一致的调用风格：
    拼装命令 -> exec_system 异步执行 -> 解析 stdout/keyfile -> 清理临时文件。

options 字段（前端勾选 / 填值），完整参数清单见 PARAM_META。
"""
from __future__ import annotations

import os
import re
from typing import Any

from ..config import Config, DICTS_DIR
from ..logger import get_logger
from ..utils import check_tool_available, exec_system, random_choices

logger = get_logger()

# aircrack-ng 可执行文件名（按 PATH 解析；如需固定路径可设置环境变量 AIRCRACK_BIN）
AIRCRACK_BIN = os.environ.get("AIRCRACK_BIN", "aircrack-ng")

# 默认密码字典（项目自带）
DEFAULT_WORDLIST = os.path.join(DICTS_DIR, "passwordtop1000.txt")

# 布尔型参数：勾选即追加 flag（值为 aircrack-ng 的开关选项）
_BOOL_FLAGS: dict[str, str] = {
    # Common
    "quiet": "-q",
    # Static WEP
    "alpha_chars": "-c",          # 仅搜索字母数字字符
    "bcd_chars": "-t",            # 仅搜索 BCD 字符
    "fritz_numeric": "-h",        # Fritz!BOX 数字密钥
    "no_brute_last": "-x0",       # 禁用最后密钥字节爆破（等价 -x）
    "brute_last_1": "-x1",        # 最后 1 字节爆破（默认）
    "brute_last_2": "-x2",        # 最后 2 字节爆破
    "single_brute": "-y",         # 实验性单次爆破模式
    "korek_only": "-K",           # 仅用旧 KoreK 攻击（pre-PTW）
    "show_ascii": "-s",           # 破解时显示 ASCII 密钥
    "wep_decloak": "-D",          # WEP decloak，跳过损坏的密钥流
    "ptw_one_try": "-1",          # 仅尝试 1 次 PTW 破解
    "visual_inspection": "-V",    # 可视检查模式
    # WPA-PSK
    "speed_test": "-S",           # WPA 速度测试
    # Other
    "show_cpus": "-u",            # 显示 CPU 数与 SIMD 支持
}

# 带值型参数：勾选后取值，参数名 -> (CLI flag, 类型)
_VALUE_FLAGS: dict[str, tuple[str, type]] = {
    # Common
    "attack_mode": ("-a", str),    # 强制攻击模式：1/WEP, 2/WPA-PSK
    "essid": ("-e", str),          # 目标网络 ESSID
    "bssid": ("-b", str),          # 目标 AP MAC
    "nbcpu": ("-p", int),          # 使用的 CPU 数（默认全部）
    "merge_aps": ("-C", str),      # 合并给定 AP 为虚拟 AP
    "key_file": ("-l", str),       # 将密钥写入文件
    # Static WEP
    "key_mask": ("-d", str),       # 密钥掩码（A1:XX:CF:YY）
    "mac_filter": ("-m", str),     # 过滤可用数据包的 MAC
    "nbits": ("-n", int),          # WEP 密钥长度 64/128/152/256/512
    "key_index": ("-i", int),      # WEP 密钥索引（1-4），默认 any
    "fudge": ("-f", int),          # 爆破 fudge 因子（默认 2）
    "korek_disable": ("-k", int),  # 禁用某 KoreK 攻击方法（1-17）
    "max_ivs": ("-M", int),        # 最大 IV 数量
    "ptw_debug": ("-P", int),      # PTW 调试：1=禁用 Klein，2=PTW
    # WEP/WPA
    "wordlist": ("-w", str),       # 字典文件路径
    "new_session": ("-N", str),    # 新会话文件路径
    "restore_session": ("-R", str),# 恢复会话文件路径
    # WPA-PSK
    "ewsa_project": ("-E", str),   # 创建 EWSA Project 文件 v3
    "pmkid_str": ("-I", str),      # PMKID 字符串（hashcat -m 16800）
    "hashcat_hccapx": ("-j", str), # 创建 Hashcat v3.6+ 文件（HCCAPX）
    "hashcat_hccap": ("-J", str),  # 创建 Hashcat 文件（HCCAP）
    "speed_test_len": ("-Z", int), # WPA 速度测试执行时长（秒）
    "airolib_db": ("-r", str),     # airolib-ng 数据库路径（不能与 -w 同用）
    # SIMD
    "simd": ("--simd", str),       # 指定 SIMD 架构
}


class AircrackScan:
    """封装一次 aircrack-ng 离线破解。

    Args:
        capture_file: 抓包文件路径（.cap/.pcap/.ivs/.hccapx）。
        options: 前端勾选/填值的参数字典（见模块文档字符串）。
    """

    def __init__(self, capture_file: str, options: dict | None = None):
        self.capture_file = capture_file or ""
        self.options = options or {}
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        # -l 输出的 key file
        self.key_file = os.path.join(tmp_path, f"aircrack_key_{rand_str}.txt")
        # stdout 重定向到日志文件，便于解析
        self.stdout_file = os.path.join(tmp_path, f"aircrack_stdout_{rand_str}.log")
        self._bin_path = AIRCRACK_BIN  # 探测成功后更新为绝对路径

    # ---------- 探测 ----------
    def check_have_aircrack(self) -> bool:
        """探测 aircrack-ng 是否可用（兼容 systemd 最小化 PATH + 非零退出码）。"""
        ok, abs_path = check_tool_available(AIRCRACK_BIN, ["--help"], ["--version"])
        if ok and abs_path and "/" in abs_path:
            self._bin_path = abs_path
        else:
            self._bin_path = AIRCRACK_BIN
        return ok

    # ---------- 命令拼装 ----------
    def _build_command(self) -> list[str]:
        """根据 options 拼装 aircrack-ng CLI。

        - 固定追加：-l <keyfile>（破解成功后写入）
        - 抓包文件作为最后一个位置参数
        """
        cmd: list[str] = [self._bin_path, "-l", self.key_file]

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
                if typ is int:
                    n = int(val)
                    if n == 0:
                        # int 参数 0 视为「未设置」，跳过让 aircrack-ng 用默认值
                        continue
                    val = str(n)
                else:
                    val = str(val).strip()
            except (TypeError, ValueError):
                logger.warning(f"aircrack-ng 参数 {key} 取值非法: {val}，已忽略")
                continue
            if val:
                cmd.append(flag)
                cmd.append(val)

        # 抓包文件作为位置参数
        if self.capture_file:
            cmd.append(self.capture_file)
        return cmd

    # ---------- 执行 ----------
    async def exec_aircrack(self) -> None:
        cmd = self._build_command()
        logger.info("aircrack-ng cmd: " + " ".join(cmd))
        # aircrack-ng 字典爆破可能很长，沿用 24h 上限
        await exec_system(cmd, timeout=24 * 60 * 60)

    # ---------- 结果解析 ----------
    def _read_stdout(self) -> str:
        """读取本次执行的 stdout（exec_system 不捕获输出时，可用 keyfile + 重新探测）。

        由于 exec_system 不重定向 stdout，这里通过 keyfile 是否非空判断成功。
        """
        if not os.path.exists(self.key_file):
            return ""
        try:
            with open(self.key_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except OSError as e:
            logger.warning(f"读取 aircrack-ng keyfile 失败: {e}")
            return ""

    def dump_result(self) -> dict:
        """解析 aircrack-ng 结果。

        - 破解成功：keyfile 包含密钥（十六进制或 ASCII）
        - 破解失败：keyfile 为空或不存在

        返回结构：{cracked, key, key_type, attack_mode, essid, bssid}
        """
        key = self._read_stdout()
        result = {
            "cracked": bool(key),
            "key": key,
            "key_type": "",
            "attack_mode": str(self.options.get("attack_mode", "")),
            "essid": str(self.options.get("essid", "")),
            "bssid": str(self.options.get("bssid", "")),
            "capture_file": os.path.basename(self.capture_file),
            "wordlist": os.path.basename(str(self.options.get("wordlist", ""))),
        }
        # 推断密钥类型：纯十六进制 + 冒号 -> WEP；纯 ASCII 可打印 -> WPA
        if key:
            if re.fullmatch(r"([0-9A-Fa-f]{2}:?)+", key):
                result["key_type"] = "WEP"
            else:
                result["key_type"] = "WPA-PSK"
        return result

    # ---------- 主流程 ----------
    async def run(self) -> dict:
        if not self.capture_file or not os.path.exists(self.capture_file):
            logger.warning(f"aircrack-ng capture file not found: {self.capture_file}")
            return {"cracked": False, "key": "", "error": "capture file not found"}
        if not self.check_have_aircrack():
            logger.warning(f"not found aircrack-ng binary: {AIRCRACK_BIN}")
            return {"cracked": False, "key": "", "error": "aircrack-ng not installed"}
        try:
            await self.exec_aircrack()
            return self.dump_result()
        finally:
            # 清理 keyfile（stdout 文件未实际生成）
            for p in (self.key_file, self.stdout_file):
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass


async def run_aircrack(capture_file: str, options: dict | None = None) -> dict:
    """模块级入口：执行一次 aircrack-ng 离线破解并返回结构化结果。"""
    logger.info(f"run aircrack-ng, capture: {capture_file}")
    result = await AircrackScan(capture_file=capture_file, options=options or {}).run()
    logger.info(f"aircrack-ng cracked: {result.get('cracked')}")
    return result


# 供前端展示的参数元数据（精选常用项，分组 + 说明 + 默认值 + 类型）
PARAM_META: list[dict[str, Any]] = [
    # Common
    {"group": "通用设置", "key": "attack_mode", "flag": "-a", "name": "攻击模式",
     "desc": "强制攻击模式：1/WEP 或 2/WPA-PSK（留空自动识别）", "type": "str", "default": ""},
    {"group": "通用设置", "key": "essid", "flag": "-e", "name": "目标 ESSID",
     "desc": "目标网络的 ESSID（网络名）", "type": "str", "default": ""},
    {"group": "通用设置", "key": "bssid", "flag": "-b", "name": "目标 BSSID",
     "desc": "目标 AP 的 MAC 地址（如 00:11:22:33:44:55）", "type": "str", "default": ""},
    {"group": "通用设置", "key": "nbcpu", "flag": "-p", "name": "CPU 数",
     "desc": "使用的 CPU 核心数（默认全部）", "type": "int", "default": 0},
    {"group": "通用设置", "key": "quiet", "flag": "-q", "name": "静默模式",
     "desc": "不输出状态信息", "type": "bool", "default": False},
    {"group": "通用设置", "key": "merge_aps", "flag": "-C", "name": "合并 AP",
     "desc": "合并给定 AP（MAC 列表）为虚拟 AP", "type": "str", "default": ""},
    # 字典
    {"group": "字典设置", "key": "wordlist", "flag": "-w", "name": "密码字典",
     "desc": "字典文件路径（多个用逗号分隔），WPA 破解必填", "type": "str",
     "default": DEFAULT_WORDLIST},
    {"group": "字典设置", "key": "airolib_db", "flag": "-r", "name": "airolib 数据库",
     "desc": "airolib-ng PMK 数据库路径（不能与 -w 同用，加速 WPA 破解）", "type": "str", "default": ""},
    # 会话
    {"group": "会话管理", "key": "new_session", "flag": "-N", "name": "新建会话文件",
     "desc": "将本次破解进度保存为新的会话文件（便于断点续跑）", "type": "str", "default": ""},
    {"group": "会话管理", "key": "restore_session", "flag": "-R", "name": "恢复会话文件",
     "desc": "从已有会话文件恢复破解", "type": "str", "default": ""},
    # Static WEP
    {"group": "WEP 设置", "key": "nbits", "flag": "-n", "name": "WEP 密钥长度",
     "desc": "WEP 密钥长度：64/128/152/256/512", "type": "int", "default": 128},
    {"group": "WEP 设置", "key": "key_index", "flag": "-i", "name": "WEP 密钥索引",
     "desc": "WEP 密钥索引（1-4），默认 any", "type": "int", "default": 0},
    {"group": "WEP 设置", "key": "fudge", "flag": "-f", "name": "fudge 因子",
     "desc": "爆破 fudge 因子（默认 2，越大越慢但越全）", "type": "int", "default": 2},
    {"group": "WEP 设置", "key": "key_mask", "flag": "-d", "name": "密钥掩码",
     "desc": "密钥掩码（如 A1:XX:CF:YY，X 为未知）", "type": "str", "default": ""},
    {"group": "WEP 设置", "key": "mac_filter", "flag": "-m", "name": "MAC 过滤",
     "desc": "按 MAC 地址过滤可用数据包", "type": "str", "default": ""},
    {"group": "WEP 设置", "key": "alpha_chars", "flag": "-c", "name": "仅字母数字",
     "desc": "仅搜索字母数字字符", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "bcd_chars", "flag": "-t", "name": "仅 BCD 字符",
     "desc": "仅搜索 BCD（二进制编码十进制）字符", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "fritz_numeric", "flag": "-h", "name": "Fritz!BOX 数字密钥",
     "desc": "搜索 Fritz!BOX 的数字密钥", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "korek_disable", "flag": "-k", "name": "禁用 Korek 方法",
     "desc": "禁用某个 KoreK 攻击方法（1-17）", "type": "int", "default": 0},
    {"group": "WEP 设置", "key": "brute_last_1", "flag": "-x1", "name": "爆破最后 1 字节",
     "desc": "对最后 1 个密钥字节爆破（默认行为）", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "brute_last_2", "flag": "-x2", "name": "爆破最后 2 字节",
     "desc": "对最后 2 个密钥字节爆破", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "no_brute_last", "flag": "-x0", "name": "禁用最后字节爆破",
     "desc": "禁用最后密钥字节爆破（等价 -x）", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "single_brute", "flag": "-y", "name": "单次爆破模式",
     "desc": "实验性单次爆破模式", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "korek_only", "flag": "-K", "name": "仅 KoreK 攻击",
     "desc": "仅使用旧 KoreK 攻击（pre-PTW）", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "show_ascii", "flag": "-s", "name": "显示 ASCII 密钥",
     "desc": "破解时显示 ASCII 形式的密钥", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "max_ivs", "flag": "-M", "name": "最大 IV 数",
     "desc": "指定使用的最大 IV 数量", "type": "int", "default": 0},
    {"group": "WEP 设置", "key": "wep_decloak", "flag": "-D", "name": "WEP decloak",
     "desc": "WEP decloak，跳过损坏的密钥流", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "ptw_debug", "flag": "-P", "name": "PTW 调试",
     "desc": "PTW 调试：1=禁用 Klein，2=PTW", "type": "int", "default": 0},
    {"group": "WEP 设置", "key": "ptw_one_try", "flag": "-1", "name": "PTW 单次尝试",
     "desc": "仅尝试 1 次 PTW 破解", "type": "bool", "default": False},
    {"group": "WEP 设置", "key": "visual_inspection", "flag": "-V", "name": "可视检查模式",
     "desc": "可视检查模式", "type": "bool", "default": False},
    # WPA-PSK
    {"group": "WPA 设置", "key": "ewsa_project", "flag": "-E", "name": "EWSA 项目文件",
     "desc": "创建 EWSA Project 文件 v3（用于 EWSA GPU 破解）", "type": "str", "default": ""},
    {"group": "WPA 设置", "key": "pmkid_str", "flag": "-I", "name": "PMKID 字符串",
     "desc": "PMKID 字符串（hashcat -m 16800 格式）", "type": "str", "default": ""},
    {"group": "WPA 设置", "key": "hashcat_hccapx", "flag": "-j", "name": "导出 HCCAPX",
     "desc": "创建 Hashcat v3.6+ 文件（HCCAPX 格式，用于 GPU 破解）", "type": "str", "default": ""},
    {"group": "WPA 设置", "key": "hashcat_hccap", "flag": "-J", "name": "导出 HCCAP",
     "desc": "创建 Hashcat 文件（HCCAP 格式，旧版）", "type": "str", "default": ""},
    {"group": "WPA 设置", "key": "speed_test", "flag": "-S", "name": "速度测试",
     "desc": "WPA 破解速度测试", "type": "bool", "default": False},
    {"group": "WPA 设置", "key": "speed_test_len", "flag": "-Z", "name": "速度测试时长",
     "desc": "WPA 速度测试执行时长（秒）", "type": "int", "default": 0},
    # SIMD
    {"group": "性能设置", "key": "simd", "flag": "--simd", "name": "SIMD 架构",
     "desc": "指定 SIMD 架构（generic/avx512/avx2/avx/sse2/altivec/power8/asimd/neon）",
     "type": "str", "default": ""},
    {"group": "性能设置", "key": "show_cpus", "flag": "-u", "name": "显示 CPU/SIMD",
     "desc": "显示 CPU 数与 SIMD 支持后退出", "type": "bool", "default": False},
]
