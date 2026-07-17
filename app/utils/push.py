"""消息推送（钉钉/飞书/企业微信/邮件），移植自原 app/utils/push.py。

发送部分改为异步（http_req → httpx）。各渠道凭证从 Config 读取。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import smtplib
import ssl
import time
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import Config
from ..core.http_client import http_req
from ..logger import get_logger

logger = get_logger()


def dict2dingding_mark(info_list: list[dict]) -> str:
    """列表字典转 markdown 表格（钉钉/飞书/企微）。"""
    if not info_list:
        return ""
    keys = list(info_list[0].keys())
    lines = ["| " + " | ".join(keys) + " |"]
    lines.append("| " + " | ".join(["---"] * len(keys)) + " |")
    for idx, item in enumerate(info_list, 1):
        row = [str(idx)] + [str(item.get(k, "")) for k in keys]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def dict2table(info_list: list[dict]) -> str:
    """列表字典转 HTML 表格（邮件）。"""
    if not info_list:
        return "<p>无数据</p>"
    keys = list(info_list[0].keys())
    html = ['<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">']
    head = "".join(f"<th>{k}</th>" for k in ["序号"] + keys)
    html.append(f"<tr>{head}</tr>")
    for idx, item in enumerate(info_list, 1):
        cells = "".join(
            f"<td>{str(item.get(k, '')).replace('<', '&lt;').replace('>', '&gt;')}</td>"
            for k in keys)
        html.append(f"<tr><td>{idx}</td>{cells}</tr>")
    html.append("</table>")
    return "".join(html)


class Push:
    """根据 asset_map / asset_counter 构造各渠道消息体。"""

    def __init__(self, asset_map: dict, asset_counter: dict):
        self.asset_map = asset_map
        self.asset_counter = asset_counter
        self.domain_len = asset_counter.get("domain", 0)
        self.ip_len = asset_counter.get("ip", 0)
        self.site_len = asset_counter.get("site", 0)
        self.task_name = asset_map.get("task_name", "")

    def build_domain_info_list(self) -> list[dict]:
        out = []
        for old in self.asset_map.get("domain", []):
            out.append({"域名": old["domain"], "解析类型": old["type"], "记录值": old["record"][0] if old.get("record") else ""})
        return out

    def build_ip_info_list(self) -> list[dict]:
        out = []
        for old in self.asset_map.get("ip", []):
            port_list = [str(p["port_id"]) for p in old.get("port_info", [])]
            out.append({
                "IP": old["ip"],
                "端口数目": len(port_list),
                "开放端口": ",".join(port_list[:10]),
                "组织": old.get("geo_asn", {}).get("organization"),
            })
        return out

    def build_site_info_list(self) -> list[dict]:
        out = []
        for old in self.asset_map.get("site", []):
            out.append({
                "站点": old["site"],
                "标题": old.get("title", "")[:30],
                "状态码": old.get("status", ""),
                "favicon": old.get("favicon", {}).get("hash", ""),
            })
        return out

    def _markdown(self) -> str:
        parts = [f"### {self.task_name} 资产监控报告",
                 f"- 域名: {self.domain_len}", f"- IP: {self.ip_len}", f"- 站点: {self.site_len}"]
        for title, rows in [("域名", self.build_domain_info_list()),
                            ("IP", self.build_ip_info_list()),
                            ("站点", self.build_site_info_list())]:
            if rows:
                parts.append(f"\n**{title}**\n" + dict2dingding_mark(rows))
        return "\n".join(parts)

    def _html(self) -> str:
        parts = [f"<h3>{self.task_name} 资产监控报告</h3>",
                 f"<p>域名 {self.domain_len} / IP {self.ip_len} / 站点 {self.site_len}</p>"]
        for title, rows in [("域名", self.build_domain_info_list()),
                            ("IP", self.build_ip_info_list()),
                            ("站点", self.build_site_info_list())]:
            if rows:
                parts.append(f"<h4>{title}</h4>" + dict2table(rows))
        return "".join(parts)

    async def push_dingding(self):
        if not (Config.DINGDING_ACCESS_TOKEN and Config.DINGDING_SECRET):
            return
        try:
            await dingding_send(self._markdown())
        except Exception as e:
            logger.warning(f"push_dingding error: {e}")

    async def push_feishu(self):
        if not (Config.FEISHU_WEBHOOK and Config.FEISHU_SECRET):
            return
        try:
            await feishu_send(self._markdown())
        except Exception as e:
            logger.warning(f"push_feishu error: {e}")

    async def push_wx_work(self):
        if not Config.WX_WORK_WEBHOOK:
            return
        try:
            await wx_work_send(self._markdown())
        except Exception as e:
            logger.warning(f"push_wx_work error: {e}")

    async def push_email(self):
        if not (Config.EMAIL_HOST and Config.EMAIL_USERNAME and Config.EMAIL_TO):
            return
        try:
            await send_email(self.task_name + " 资产监控报告", self._html())
        except Exception as e:
            logger.warning(f"push_email error: {e}")


async def message_push(asset_map: dict, asset_counter: dict) -> None:
    """统一消息推送入口。"""
    p = Push(asset_map, asset_counter)
    await p.push_dingding()
    await p.push_feishu()
    await p.push_wx_work()
    await p.push_email()


# ---- 各渠道发送 ----

async def dingding_send(markdown: str) -> None:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{Config.DINGDING_SECRET}"
    hmac_code = hmac.new(Config.DINGDING_SECRET.encode("utf-8"),
                         string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    url = (f"https://oapi.dingtalk.com/robot/send?access_token={Config.DINGDING_ACCESS_TOKEN}"
           f"&timestamp={timestamp}&sign={sign}")
    payload = {"msgtype": "markdown", "markdown": {"title": "ARL监控", "text": markdown}}
    await http_req(url, method='post', json=payload)


async def feishu_send(markdown: str) -> None:
    timestamp = str(round(time.time()))
    string_to_sign = f"{timestamp}\n{Config.FEISHU_SECRET}"
    sign = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode()
    payload = {
        "timestamp": timestamp, "sign": sign,
        "msg_type": "text", "content": {"text": markdown},
    }
    await http_req(Config.FEISHU_WEBHOOK, method='post', json=payload)


async def wx_work_send(markdown: str) -> None:
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
    await http_req(Config.WX_WORK_WEBHOOK, method='post', json=payload)


async def send_email(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = Config.EMAIL_USERNAME
    msg["To"] = Config.EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))

    def _send():
        port = int(Config.EMAIL_PORT) if Config.EMAIL_PORT else 465
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(Config.EMAIL_HOST, port, context=context, timeout=20) as s:
                s.login(Config.EMAIL_USERNAME, Config.EMAIL_PASSWORD)
                s.sendmail(Config.EMAIL_USERNAME, Config.EMAIL_TO.split(","), msg.as_string())
        else:
            with smtplib.SMTP(Config.EMAIL_HOST, port, timeout=20) as s:
                s.login(Config.EMAIL_USERNAME, Config.EMAIL_PASSWORD)
                s.sendmail(Config.EMAIL_USERNAME, Config.EMAIL_TO.split(","), msg.as_string())

    import asyncio
    await asyncio.to_thread(_send)
