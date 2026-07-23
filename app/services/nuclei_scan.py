"""nuclei 漏洞扫描，移植自原 app/services/nuclei_scan.py。

外部二进制 nuclei 通过 asyncio 线程池执行。自动探测 -json/-jsonl 参数（兼容 nuclei 2.9.1+）。
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess

from ..config import Config
from ..logger import get_logger
from ..utils import exec_system, random_choices

logger = get_logger()


class NucleiScan:
    def __init__(self, targets: list):
        self.targets = targets
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        self.nuclei_target_path = os.path.join(tmp_path, f"nuclei_target_{rand_str}.txt")
        self.nuclei_result_path = os.path.join(tmp_path, f"nuclei_result_{rand_str}.json")
        self.nuclei_bin_path = "nuclei"
        self.nuclei_json_flag: str | None = None

    def _check_json_flag(self):
        for x in ["-json", "-jsonl"]:
            command = [self.nuclei_bin_path, "-duc", x, "-version"]
            pro = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if pro.returncode == 0:
                self.nuclei_json_flag = x
                return
        assert self.nuclei_json_flag

    def _delete_file(self):
        for p in (self.nuclei_target_path, self.nuclei_result_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning(f"清理 nuclei 临时文件失败 {p}: {e}")

    def check_have_nuclei(self) -> bool:
        try:
            pro = subprocess.run([self.nuclei_bin_path, "-version"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return pro.returncode == 0
        except Exception as e:
            logger.debug(str(e))
            return False

    def _gen_target_file(self):
        with open(self.nuclei_target_path, "w") as f:
            for domain in self.targets:
                domain = domain.strip()
                if domain:
                    f.write(domain + "\n")

    def dump_result(self) -> list[dict]:
        results = []
        if not os.path.exists(self.nuclei_result_path):
            return results
        with open(self.nuclei_result_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                results.append({
                    "template_url": data.get("template-url", ""),
                    "template_id": data.get("template-id", ""),
                    "vuln_name": data.get("info", {}).get("name", ""),
                    "vuln_severity": data.get("info", {}).get("severity", ""),
                    "vuln_url": data.get("matched-at", ""),
                    "curl_command": data.get("curl-command", ""),
                    "target": data.get("host", ""),
                })
        return results

    async def exec_nuclei(self):
        self._gen_target_file()
        # 注意：exec_system 走 subprocess.run(list) 不做 shell 分词，
        # flag 与值必须拆成独立的 argv 元素，否则 nuclei 报 unknown flag 且不产出结果。
        command = [self.nuclei_bin_path, "-duc", "-tags", "cve",
                   "-severity", "low,medium,high,critical", "-type", "http",
                   "-l", self.nuclei_target_path, self.nuclei_json_flag,
                   "-stats", "-stats-interval", "60", "-o", self.nuclei_result_path]
        logger.info(" ".join(command))
        await exec_system(command, timeout=96 * 60 * 60)

    async def run(self) -> list[dict]:
        if not self.check_have_nuclei():
            logger.warning("not found nuclei")
            return []
        # _check_json_flag 使用 subprocess 同步，放线程池
        await asyncio.to_thread(self._check_json_flag)
        try:
            await self.exec_nuclei()
            return self.dump_result()
        finally:
            self._delete_file()


async def nuclei_scan(targets: list) -> list[dict]:
    if not targets:
        return []
    return await NucleiScan(targets=targets).run()
