"""消息通知辅助，移植自原 app/helpers/message_notify.py。

复用 app.utils.push 的发送函数（钉钉/邮件）。
"""
from __future__ import annotations

from ..config import Config
from ..logger import get_logger
from ..utils.push import dingding_send, send_email

logger = get_logger()


async def push_email(title: str, html_report: str) -> bool:
    try:
        if Config.EMAIL_HOST and Config.EMAIL_USERNAME and Config.EMAIL_PASSWORD:
            import asyncio
            await asyncio.to_thread(
                send_email, subject=title, html=html_report,
            )
            logger.info("send email succ")
            return True
    except Exception as e:
        logger.info(f"error on send email {title}")
        logger.warning(e)
    return False


async def push_dingding(markdown_report: str) -> bool:
    try:
        if Config.DINGDING_ACCESS_TOKEN and Config.DINGDING_SECRET:
            await dingding_send(markdown_report)
            logger.info("push dingding succ")
            return True
    except Exception as e:
        logger.info(f"error on send dingding {markdown_report[:15]}")
        logger.warning(e)
    return False
