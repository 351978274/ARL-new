"""任务资产同步到资产组（asset_* 集合），移植自原 app/services/syncAsset.py。"""
from __future__ import annotations

import copy
import re

from ..database import conn_db
from ..logger import get_logger
from ..utils import curr_date_obj, message_push

logger = get_logger()


class SyncAsset:
    def __init__(self, task_id: str, scope_id: str, update_flag: bool = False,
                 category=None, task_name: str = ""):
        self.available_category = ["site", "domain", "ip", "wih"]
        self.category_list = category or self.available_category
        self.task_id = task_id
        self.scope_id = scope_id
        self.task_name = task_name
        self.update_flag = update_flag
        self.new_asset_map: dict = {"site": [], "domain": [], "ip": [], "task_name": task_name, "wih": []}
        self.new_asset_counter: dict = {"site": 0, "domain": 0, "ip": 0, "wih": 0}
        self.max_record_asset_count = 10

    async def site_in_asset_site(self, site: str) -> bool:
        if "?" not in site and ";" not in site:
            return False
        site_base = site.split("?")[0].split(";")[0]
        query = {"scope_id": self.scope_id, "site": {"$regex": "^" + re.escape(site_base)}}
        return await conn_db("asset_site").find_one(query) is not None

    async def sync_by_category(self, category: str) -> None:
        dist_collection = f'asset_{category}'
        cursor = conn_db(category).find({"task_id": self.task_id})
        async for data in cursor:
            data_content = data.get(category)
            query = {"scope_id": self.scope_id, category: data_content}
            if category == "wih":
                query = {"scope_id": self.scope_id, "fnv_hash": data["fnv_hash"]}
                data_content = data["fnv_hash"]
            del data["_id"]
            data["scope_id"] = self.scope_id

            if category == "site" and await self.site_in_asset_site(data["site"]):
                continue

            old = await conn_db(dist_collection).find_one(query)
            if old is None:
                data["save_date"] = curr_date_obj()
                data["update_date"] = data["save_date"]
                if category in self.new_asset_map:
                    if self.new_asset_counter[category] < self.max_record_asset_count:
                        self.new_asset_map[category].append(copy.deepcopy(data))
                    self.new_asset_counter[category] += 1
                await conn_db(dist_collection).insert_one(data)

            if old and self.update_flag:
                curr_date = curr_date_obj()
                data["save_date"] = old.get("save_date", curr_date)
                data["update_date"] = curr_date
                if category == 'ip':
                    if data.get("domain") and old.get("domain"):
                        old["domain"].extend(data["domain"])
                        data["domain"] = list(set(old["domain"]))
                await conn_db(dist_collection).find_one_and_replace(query, data)

    async def run(self):
        logger.info(f"start sync {self.task_id} -> {self.scope_id}")
        for category in self.category_list:
            if category not in self.available_category:
                logger.warning(f"not found {category} category in {self.available_category}")
                continue
            await self.sync_by_category(category)
        logger.info(f"end sync {self.task_id} -> {self.scope_id}, result: {self.new_asset_counter}")
        return self.new_asset_map, self.new_asset_counter


async def sync_asset(task_id: str, scope_id: str, update_flag: bool = False,
                     category=None, push_flag: bool = False, task_name: str = ""):
    sync = SyncAsset(task_id=task_id, scope_id=scope_id, update_flag=update_flag,
                     category=category, task_name=task_name)
    new_asset_map, new_asset_counter = await sync.run()
    new_asset_map.pop('ip', None)
    new_asset_counter.pop('ip', None)
    if push_flag:
        await message_push(asset_map=new_asset_map, asset_counter=new_asset_counter)
    return new_asset_map, new_asset_counter
