"""FastAPI 依赖：认证、分页参数。

认证逻辑移植自原 app/utils/user.py 的 user_login_header + auth 装饰器。
通过 Header Token 或 query token 校验；Config.AUTH=False 时放行。
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Query, Request

from .config import Config
from .utils.user import user_login_by_token


async def require_auth(request: Request, token: str | None = Header(default=None, alias="Token")) -> dict | bool:
    """认证依赖。Config.AUTH=False 时放行；否则校验 Token header / query token / API_KEY。

    返回用户身份 dict（或 True），失败抛 401。
    """
    if not Config.AUTH:
        return True
    if not token:
        token = request.query_params.get("token")
    identity = await user_login_by_token(token)
    if not identity:
        raise HTTPException(status_code=401, detail="not login")
    return identity


# 别名，便于在路由中按需引用
auth = require_auth


class Pagination:
    """通用分页参数。"""

    def __init__(self, page: int = Query(1, ge=1, description="页码"),
                 size: int = Query(10, ge=1, le=100000, description="每页数量"),
                 order: str = Query("-_id", description="排序字段")):
        self.page = page
        self.size = size
        self.order = order
