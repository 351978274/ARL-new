"""指纹导入工具，移植自 doc/ADD-ARL-Finger/ADD-ARL-finger.py。

提供两种导入方式：
- new: 直接上传 finger.json（含 name + human_rule）到 /api/fingerprint/upload/
- old: 从旧格式 {fingerprint:[{cms,method,location,keyword}]} 转换后逐条添加

用法（已集成进本项目，无需单独脚本）：
    from app.tools.finger_import import import_fingers
    await import_fingers(base_url, username, password, 'new', file_path)
"""
from __future__ import annotations

import json
import sys

import httpx


async def login(base_url: str, username: str, password: str) -> str | None:
    """登录获取 token。"""
    login_url = f"{base_url}/api/user/login"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json; charset=UTF-8",
    }
    data = {"username": username, "password": password}
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(login_url, json=data, headers=headers, timeout=20)
    if resp.status_code == 200:
        token = resp.json().get("data", {}).get("token")
        if token:
            print("[+] Login Success!!")
            return token
    print("[-] Login Failure!")
    return None


async def add_finger(name: str, rule: str, base_url: str, token: str) -> None:
    """添加单条指纹到 /api/fingerprint/。"""
    add_url = f"{base_url}/api/fingerprint/"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0",
        "token": token,
        "Content-Type": "application/json; charset=UTF-8",
    }
    data = {"name": name, "human_rule": rule}
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(add_url, json=data, headers=headers, timeout=20)
    if resp.status_code == 200:
        print(f"Add: [+] {json.dumps(data, ensure_ascii=False)}\nRsp: [+] {resp.text}")
    else:
        print(f"[-] Failed to add fingerprint for {name}")


async def upload_finger_file(file_path: str, base_url: str, token: str) -> None:
    """上传指纹文件到 /api/fingerprint/upload/。"""
    upload_url = f"{base_url}/api/fingerprint/upload/"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0",
        "token": token,
    }
    with open(file_path, "rb") as f:
        files = {"file": ("finger.json", f, "application/json")}
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(upload_url, files=files, headers=headers, timeout=60)
    if resp.status_code == 200:
        print(f"[+] File upload success: {file_path}\nRsp: [+] {resp.text}")
    else:
        print(f"[-] Failed to upload file: {file_path}\nStatus: {resp.status_code}\n{resp.text}")


async def import_fingers(base_url: str, token: str, method: str, file_path: str | None = None) -> None:
    """主入口。method 为 'new'（上传）或 'old'（转换逐条添加）。"""
    if method == "new":
        await upload_finger_file(file_path or "./finger.json", base_url, token)
    elif method == "old":
        path = file_path or "./finger.json"
        with open(path, "r", encoding="utf-8") as f:
            load_dict = json.loads(f.read())
        body_template = 'body="{}"'
        title_template = 'title="{}"'
        hash_template = 'icon_hash="{}"'
        for i in load_dict.get("fingerprint", []):
            name = i["cms"]
            location = i.get("location", "")
            if i.get("method") == "keyword":
                if "body" in location:
                    template = body_template
                elif "title" in location:
                    template = title_template
                else:
                    template = hash_template
                keywords = i.get("keyword", [])
                if keywords:
                    for rule in keywords:
                        await add_finger(name, template.format(rule), base_url, token)
                else:
                    await add_finger(name, template.format(""), base_url, token)
    else:
        print("[-] Invalid method. Use 'new' or 'old'.")


def main():
    if len(sys.argv) in (5, 6):
        login_url = sys.argv[1]
        login_name = sys.argv[2]
        login_password = sys.argv[3]
        method = sys.argv[4]
        file_path = sys.argv[5] if len(sys.argv) == 6 else None
        import asyncio
        token = asyncio.run(login(login_url, login_name, login_password))
        if token:
            asyncio.run(import_fingers(login_url, token, method, file_path))
    else:
        print('''
usage:
    python -m app.tools.finger_import https://127.0.0.1:5003/ admin password old [file_path]
    python -m app.tools.finger_import https://127.0.0.1:5003/ admin password new [file_path]
''')


if __name__ == "__main__":
    main()
