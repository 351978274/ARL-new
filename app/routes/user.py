"""用户认证路由，移植自原 app/routes/user.py。

登录/登出/修改密码。Token-based（兼容原 admin/arlpass）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import Config
from ..deps import require_auth
from ..logger import get_logger
from ..modules import build_ret, error_map
from ..utils.user import change_pass, user_login, user_login_by_token, user_logout

logger = get_logger()
router = APIRouter(prefix="/user", tags=["用户认证"])


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePassBody(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
async def login(body: LoginBody):
    item = await user_login(body.username, body.password)
    if not item:
        return build_ret(error_map["NotLogin"])
    return {"code": 200, "message": "success", "data": item}


@router.post("/logout", dependencies=[Depends(require_auth)])
async def logout(token: str | None = None):
    # token 从依赖中获取更稳妥，这里从请求上下文取
    if token:
        await user_logout(token)
    return build_ret(error_map["Success"])


@router.post("/change_pass", dependencies=[Depends(require_auth)])
async def change_password(body: ChangePassBody, token: str | None = None):
    if not token:
        return build_ret(error_map["NotLogin"])
    ok = await change_pass(token, body.old_password, body.new_password)
    if ok:
        return build_ret(error_map["Success"])
    return build_ret(error_map["Error"], {"message": "旧密码错误"})
