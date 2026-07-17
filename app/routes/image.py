"""截图访问路由 + 控制台路由，移植自原 app/routes/image.py + console.py。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..config import Config, ROOT_DIR
from ..deps import require_auth

image_router = APIRouter(prefix="/image", tags=["截图"], dependencies=[Depends(require_auth)])
console_router = APIRouter(prefix="/console", tags=["控制台"], dependencies=[Depends(require_auth)])


@image_router.get("/{task_id}/{filename}")
async def get_image(task_id: str, filename: str):
    """返回任务截图。task_id/filename.jpg。"""
    # 安全：禁止路径穿越
    safe_name = os.path.basename(filename)
    capture_dir = os.path.join(Config.SCREENSHOT_DIR, task_id)
    path = os.path.join(capture_dir, safe_name)
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/jpeg")
    return FileResponse(Config.SCREENSHOT_FAIL_IMG, media_type="image/jpeg")


@console_router.get("/")
async def console_info():
    """系统信息：版本、配置概要。"""
    import psutil
    from .. import __version__
    return {
        "code": 200,
        "data": {
            "version": __version__,
            "python": "3.13.7",
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": psutil.virtual_memory()._asdict(),
            "mongo_db": Config.MONGO_DB,
            "auth": Config.AUTH,
        },
    }
