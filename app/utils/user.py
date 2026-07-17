"""认证工具，移植自原 app/utils/user.py。

token-based 认证，salt+MD5，保留兼容。提供同步与异步两种 DB 访问入口。
"""
from __future__ import annotations

from ..config import Config
from ..database import conn_db
from .system_util import gen_md5, random_choices

salt = 'arlsalt!@#'


async def user_login(username: str | None = None, password: str | None = None) -> dict | None:
    if not username or not password:
        return None
    query = {"username": username, "password": gen_md5(salt + password)}
    if await conn_db('user').find_one(query):
        token = gen_md5(random_choices(50))
        await conn_db('user').update_one(query, {"$set": {"token": token}})
        return {"username": username, "token": token, "type": "login"}
    return None


async def user_login_by_token(token: str | None) -> bool | dict:
    """校验 token。Config.AUTH 为 False 时直接放行。"""
    if not Config.AUTH:
        return True

    if not token:
        return False

    api_item = {"username": "ARL-API", "token": Config.API_KEY, "type": "api"}
    if Config.API_KEY and token == Config.API_KEY:
        return api_item

    data = await conn_db('user').find_one({"token": token})
    if data:
        return {"username": data.get("username"), "token": token, "type": "login"}
    return False


async def user_logout(token: str) -> None:
    current = await user_login_by_token(token)
    if current:
        await conn_db('user').update_one({"token": token}, {"$set": {"token": None}})


async def change_pass(token: str, old_password: str, new_password: str) -> bool:
    query = {"token": token, "password": gen_md5(salt + old_password)}
    data = await conn_db('user').find_one(query)
    if data:
        await conn_db('user').update_one(
            {"token": token}, {"$set": {"password": gen_md5(salt + new_password)}})
        return True
    return False


async def init_admin_user(default_user: str = "admin", default_pass: str = "arlpass") -> bool:
    """若 user 集合为空，初始化默认管理员（兼容原 admin/arlpass）。返回是否新建。"""
    col = conn_db('user')
    if await col.find_one({}):
        return False
    await col.insert_one({
        "username": default_user,
        "password": gen_md5(salt + default_pass),
        "token": "",
    })
    return True
