"""FastAPI 应用工厂。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 5003
或：
    python -m app.main

启动时：初始化管理员账号（兼容 admin/arlpass）、启动 APScheduler。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import Config, ROOT_DIR
from .database import ping
from .logger import get_logger
from .routes import all_routers
from .utils.user import init_admin_user

logger = get_logger()

# APScheduler 实例（在 lifespan 中管理）
_scheduler = None


async def _start_scheduler():
    """启动 APScheduler，定期运行 run_scheduler_tick。"""
    global _scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _scheduler = AsyncIOScheduler()
    interval = max(10, Config.SCHEDULER_POLL_INTERVAL)

    async def _tick():
        from .scheduler.jobs import run_scheduler_tick
        try:
            await run_scheduler_tick()
        except Exception as e:
            logger.error(f"scheduler tick error: {e}")

    _scheduler.add_job(_tick, "interval", seconds=interval, id="arl_scheduler")
    _scheduler.start()
    logger.info(f"APScheduler started, interval={interval}s")


async def _stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化。"""
    # 检查 MongoDB
    if await ping():
        logger.info(f"MongoDB 连接成功: {Config.MONGO_URL} / {Config.MONGO_DB}")
        new_admin = await init_admin_user()
        if new_admin:
            logger.info("已初始化默认管理员 admin/arlpass")
    else:
        logger.warning(f"MongoDB 连接失败: {Config.MONGO_URL}（API 可启动，但功能不可用）")
    # 启动调度器
    await _start_scheduler()
    logger.info(f"ARL v{__version__} 启动完成")
    yield
    await _stop_scheduler()
    logger.info("ARL 已停止")


def create_app() -> FastAPI:
    """构造 FastAPI 应用。"""
    app = FastAPI(
        title="ARL（Asset Reconnaissance Lighthouse）资产侦察灯塔系统",
        description="基于 Python 3.13.7 / FastAPI / asyncio 现代化重写",
        version=__version__,
        docs_url="/api/doc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    # 所有路由挂载在 /api 前缀
    for router in all_routers:
        app.include_router(router, prefix="/api")

    # 静态托管前端（若 frontend/dist 存在）
    import os
    from fastapi.staticfiles import StaticFiles
    dist_dir = os.path.join(ROOT_DIR, "frontend", "dist")
    if os.path.isdir(dist_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

        # SPA fallback：非 /api、非 /image 路径返回 index.html
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            from fastapi.responses import FileResponse
            if full_path.startswith(("api", "image")):
                return {"detail": "Not Found"}
            index = os.path.join(dist_dir, "index.html")
            if os.path.isfile(index):
                return FileResponse(index)
            return {"detail": "Not Found"}
    return app


app = create_app()


@app.get("/")
async def root():
    return {"name": "ARL", "version": __version__, "doc": "/api/doc"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "mongo": await ping(), "version": __version__}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5003)
