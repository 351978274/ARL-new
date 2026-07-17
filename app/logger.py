"""日志模块（loguru + colorlog）。

替代原 app/utils/__init__.py 中的 init_logger / get_logger。
"""
from __future__ import annotations

import logging
import sys

from loguru import logger as loguru_logger

from .config import ROOT_DIR

_CONFIGURED = False


def init_logger():
    """配置 loguru：控制台彩色输出 + 文件轮转。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    loguru_logger.remove()
    # 控制台彩色输出
    loguru_logger.add(
        sys.stderr,
        level="INFO",
        format="<green>[{time:YYYY-MM-DD HH:mm:ss}]</green> "
        "<level>[{level}]</level> "
        "<cyan>[{name}:{line}]</cyan> <level>{message}</level>",
        colorize=True,
    )
    # 文件输出（按 10MB 轮转，保留 7 份）
    loguru_logger.add(
        ROOT_DIR + "/logs/arl_{time}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] [{name}:{line}] {message}",
    )
    # 拦截标准库 logging（让 dnspython / motor 等日志也走 loguru）
    class _InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                loguru_logger.opt(depth=6, exception=record.exc_info).log(
                    record.levelname, record.getMessage()
                )
            except Exception:
                pass

    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.WARNING, force=True)

    _CONFIGURED = True


def get_logger():
    """返回配置好的 loguru logger。"""
    if not _CONFIGURED:
        init_logger()
    return loguru_logger


# 兼容旧用法：from app.utils import get_logger
log = get_logger()
