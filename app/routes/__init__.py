"""routes 包：FastAPI 路由集合，移植自原 app/routes/__init__.py。

每个模块导出一个 router，由 main.py 统一挂载到 /api 前缀。
"""
from __future__ import annotations

from .task import router as task_router
from .user import router as user_router
from .asset_scope import router as asset_scope_router
from .scheduler import router as scheduler_router
from .fingerprint import router as fingerprint_router
from .policy import router as policy_router
from .export import export_router, batch_router
from .task_fofa import router as task_fofa_router
from .github_scheduler import router as github_scheduler_router
from .image import console_router, image_router
from .dirsearch import router as dirsearch_router
from .hydra import router as hydra_router
from .sqlmap import router as sqlmap_router
from .aircrack import router as aircrack_router
from .searchsploit import router as searchsploit_router
from .hashcat import router as hashcat_router
from .file_browser import router as file_router
from .generic import routers as generic_routers

# 所有路由汇总
all_routers: list = [
    task_router, user_router, asset_scope_router, scheduler_router,
    fingerprint_router, policy_router, export_router, batch_router,
    task_fofa_router, github_scheduler_router, image_router, console_router,
    dirsearch_router, hydra_router, sqlmap_router, aircrack_router,
    searchsploit_router, hashcat_router, file_router,
    *generic_routers,
]

__all__ = ["all_routers"]
