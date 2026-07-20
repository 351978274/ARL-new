"""WebInfoHunter（wih）调用，移植自原 app/services/infoHunter.py。

外部二进制 wih 从站点 JS 中提取子域名/AK-SK 等信息。
"""
from __future__ import annotations

import json
import os
from typing import List

from ..config import Config
from ..logger import get_logger
from ..modules import WihRecord
from ..utils import check_output, exec_system, random_choices

logger = get_logger()


class InfoHunter:
    def __init__(self, sites: list):
        self.sites = set(sites)
        tmp_path = Config.TMP_PATH
        rand_str = random_choices()
        self.wih_target_path = os.path.join(tmp_path, f"wih_target_{rand_str}.txt")
        self.wih_result_path = os.path.join(tmp_path, f"wih_result_{rand_str}.json")
        self.wih_bin_path = "wih"

    def _get_target_file(self):
        with open(self.wih_target_path, "w") as f:
            for site in self.sites:
                f.write(site + "\n")

    def _delete_file(self):
        for p in (self.wih_target_path, self.wih_result_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning(f"清理 wih 临时文件失败 {p}: {e}")

    async def exec_wih(self):
        command = [self.wih_bin_path, f"-r {Config.WIH_RULE_PATH}", "-J",
                   f"-o {self.wih_result_path}", "--concurrency 3", "--log-level zero",
                   "--concurrency-per-site 1", "--disable-ak-sk-output",
                   f"-t {self.wih_target_path}"]
        if Config.PROXY_URL:
            command.append(f"--proxy {Config.PROXY_URL}")
        logger.info(" ".join(command))
        await exec_system(command, timeout=5 * 24 * 60 * 60)

    async def check_have_wih(self) -> bool:
        try:
            output = await check_output([self.wih_bin_path, "--version"], timeout=2 * 60)
            if "version:" in str(output):
                return True
        except Exception as e:
            logger.debug(str(e))
        return False

    def dump_result(self) -> list[WihRecord]:
        results = []
        if not os.path.exists(self.wih_result_path):
            return results
        with open(self.wih_result_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                site = data["target"]
                for item in data.get("records", []):
                    content = item["content"]
                    if item.get("tag"):
                        content = f"{content} ({item['tag']})"
                    results.append(WihRecord(
                        record_type=item["id"], content=content, source=item["source"],
                        site=site, fnv_hash=item["hash"]))
        return results

    async def run(self) -> list[WihRecord]:
        if not await self.check_have_wih():
            logger.warning("not found webInfoHunter binary")
            return []
        self._get_target_file()
        try:
            await self.exec_wih()
            return self.dump_result()
        finally:
            self._delete_file()


async def run_wih(sites: List[str]) -> List[WihRecord]:
    logger.info(f"run webInfoHunter, sites: {len(sites)}")
    results = await InfoHunter(sites).run()
    logger.info(f"webInfoHunter result: {len(results)}")
    return results
