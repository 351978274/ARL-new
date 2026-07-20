"""MongoDB 异步连接层（motor）。

替代原 app/utils/conn.py 中的 ConnMongo / conn_db（同步 pymongo）。
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from .config import Config

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """获取全局 AsyncIOMotorClient 单例。

    首次创建时从 Config.MONGO_URL 读取连接串。可通过 close_client() 显式关闭。
    """
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(Config.MONGO_URL)
    return _client


def get_db(db_name: str | None = None) -> AsyncIOMotorDatabase:
    """获取数据库对象，默认使用 Config.MONGO_DB。"""
    return get_client()[db_name or Config.MONGO_DB]


def conn_db(collection: str, db_name: str | None = None) -> AsyncIOMotorCollection:
    """获取集合对象，等价于原 conn_db(collection)。

    用法（异步）：
        col = conn_db('task')
        await col.find_one({...})
    """
    return get_db(db_name)[collection]


async def ping() -> bool:
    """检测 MongoDB 是否可连（serverInfo 默认 1s 超时）。"""
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:
        return False


async def close_client() -> None:
    """关闭全局 motor 客户端（应用退出时调用）。"""
    global _client
    if _client is not None:
        _client.close()
        _client = None
