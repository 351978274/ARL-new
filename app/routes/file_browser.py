"""文件浏览路由：列出服务器上目录的子目录和文件，供前端文件路径选择器使用。

只读，不写入。支持浏览任意绝对路径（用户明确要支持 /usr/share/wordlists/ 等系统路径），
但做基本安全校验：必须是绝对路径、用 realpath 规范化（消除 .. 越界）。
"""
from __future__ import annotations

import os
import platform

from fastapi import APIRouter, Depends, Query

from ..config import Config, ROOT_DIR
from ..deps import require_auth
from ..modules import build_ret, error_map

router = APIRouter(prefix="/file", tags=["文件浏览"], dependencies=[Depends(require_auth)])

# 单次列表最多返回的条目数，防止读超大目录卡死
_MAX_ENTRIES = 2000


@router.get("/roots/")
async def roots():
    """返回可浏览的根目录列表，供前端初始定位。

    返回项目根 + 系统根（Linux: /；Windows: 各盘符）。
    """
    root_list = [
        {"name": "项目根目录", "path": ROOT_DIR},
    ]
    if platform.system() == "Windows":
        # 列出所有可用盘符
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                root_list.append({"name": f"{letter}: 盘", "path": drive})
        root_list.append({"name": "系统根 C:\\", "path": "C:\\"})
    else:
        root_list.append({"name": "系统根 /", "path": "/"})
    return {"code": 200, "message": "success", "data": root_list}


@router.get("/list/")
async def list_dir(path: str = Query("", description="要列出的目录绝对路径，空则用项目根")):
    """列出指定目录的子目录和文件。

    - path 为空或不是绝对路径时，默认返回项目根
    - 用 os.path.realpath 规范化，消除 .. 和符号链接
    - 目录不存在 / 无权限时返回错误
    """
    # 默认项目根
    if not path:
        target = ROOT_DIR
    else:
        target = path

    # 必须是绝对路径
    if not os.path.isabs(target):
        return build_ret(error_map["Error"], {"error": f"路径必须是绝对路径: {target}"})

    # 规范化（消除 ..、多余分隔符、符号链接）
    real = os.path.realpath(target)

    if not os.path.exists(real):
        return build_ret(error_map["Error"], {"error": f"路径不存在: {real}"})
    if not os.path.isdir(real):
        # 如果是文件，返回其所在目录（便于前端选中文件后继续浏览）
        real = os.path.dirname(real)
        if not os.path.isdir(real):
            return build_ret(error_map["Error"], {"error": f"不是有效目录: {target}"})

    dirs: list[dict] = []
    files: list[dict] = []
    try:
        for name in sorted(os.listdir(real)):
            full = os.path.join(real, name)
            try:
                if os.path.isdir(full):
                    dirs.append({"name": name})
                elif os.path.isfile(full):
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    files.append({"name": name, "size": size})
            except OSError:
                # 无权限访问的条目跳过
                continue
            if len(dirs) + len(files) >= _MAX_ENTRIES:
                break
    except PermissionError:
        return build_ret(error_map["Error"], {"error": f"无权限访问目录: {real}"})
    except OSError as e:
        return build_ret(error_map["Error"], {"error": f"读取目录失败: {e}"})

    # 上级目录（便于前端「返回上级」按钮）
    parent = os.path.dirname(real)
    # 到系统根时 parent 与 real 相同，前端据此隐藏「返回上级」
    if parent == real:
        parent = ""

    return {
        "code": 200, "message": "success",
        "data": {
            "path": real,
            "parent": parent,
            "dirs": dirs,
            "files": files,
            "truncated": (len(dirs) + len(files)) >= _MAX_ENTRIES,
        },
    }
