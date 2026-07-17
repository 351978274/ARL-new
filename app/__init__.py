"""ARL 现代化重写版 - 基于 Python 3.13.7 / FastAPI / asyncio。

顶层包：导入本包时即初始化日志。
"""
from __future__ import annotations

from .logger import get_logger, init_logger

init_logger()

__version__ = "3.0.0"
__all__ = ["get_logger", "init_logger", "__version__"]
