#!/bin/bash
# ARL 现代化版 运行脚本（开发/快速启动）
# 用法：
#   ./misc/run.sh          # 启动 Web（默认 5003）
#   ./misc/run.sh 5018     # 指定端口
set -e
cd "$(dirname "$0")/.."

PORT="${1:-5003}"

# 激活 venv
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
elif [ -f .venv/Scripts/activate ]; then
    source .venv/Scripts/activate
fi

echo "[*] 启动 ARL Web (端口 ${PORT})..."
echo "[*] 文档：http://127.0.0.1:${PORT}/api/doc"
echo "[*] 健康检查：http://127.0.0.1:${PORT}/api/health"

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
