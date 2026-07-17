#!/bin/bash
# ARL 现代化版 源码安装脚本
# 适用：CentOS 7/8、Rocky 8、Ubuntu 20.04+（需 root）
#
# 与原版 setup-arl.sh 的区别：
#   - 仅需 MongoDB（无需 RabbitMQ / Celery worker）
#   - Python 3.13.7（从源码编译）
#   - 外部二进制：nmap / nuclei / massdns / wih / phantomjs
set -e

ARL_DIR="/opt/ARL"
PY_VERSION="3.13.7"

echo "[*] ARL 现代化版安装脚本"

# 1. 系统依赖
echo "[*] 安装系统依赖..."
if command -v apt-get &>/dev/null; then
    apt-get update -y
    apt-get install -y git wget curl build-essential libssl-dev zlib1g-dev \
        libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev \
        libgdbm-dev libdb5.3-dev libbz2-dev libexpat1-dev liblzma-dev \
        libffi-dev uuid-dev nmap
elif command -v yum &>/dev/null; then
    yum groupinstall -y "Development Tools"
    yum install -y git wget curl openssl-devel zlib-devel \
        ncurses-devel sqlite-devel gdbm-devel bzip2-devel expat-devel \
        libffi-devel xz-devel nmap
fi

# 2. MongoDB
if ! command -v mongod &>/dev/null; then
    echo "[*] 安装 MongoDB 7.x..."
    if command -v apt-get &>/dev/null; then
        wget -qO - https://www.mongodb.org/static/pgp/server-7.0.asc | apt-key add -
        echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/7.0 multiverse" \
            | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
        apt-get update -y
        apt-get install -y mongodb-org
    else
        cat > /etc/yum.repos.d/mongodb-org-7.0.repo <<'EOF'
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/$releasever/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-7.0.asc
EOF
        yum install -y mongodb-org
    fi
    systemctl enable --now mongod
fi

# 3. Python 3.13.7
if ! python3.13 -V &>/dev/null 2>&1; then
    echo "[*] 编译安装 Python ${PY_VERSION}..."
    cd /tmp
    wget -q https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tgz
    tar xzf Python-${PY_VERSION}.tgz
    cd Python-${PY_VERSION}
    ./configure --enable-optimizations --with-ensurepip=install
    make -j"$(nproc)"
    make altinstall
    ln -sf /usr/local/bin/python3.13 /usr/local/bin/python3.13
fi

# 4. 项目代码
echo "[*] 部署项目到 ${ARL_DIR}..."
mkdir -p "$(dirname "$ARL_DIR")"
if [ -d "$ARL_DIR/.git" ]; then
    cd "$ARL_DIR" && git pull
else
    # 将当前目录代码复制过去（或 git clone）
    cp -r "$(dirname "$0")/.." "$ARL_DIR" 2>/dev/null || true
    cd "$ARL_DIR"
fi

# 5. venv + 依赖
echo "[*] 创建虚拟环境并安装依赖..."
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. 配置文件
if [ ! -f config.yaml ]; then
    cp config.yaml.example config.yaml
    echo "[*] 已生成 config.yaml，请编辑其中的 FOFA/GITHUB/推送 等 key"
fi

# 7. 外部二进制（提示用户手动安装）
echo ""
echo "[!] 请手动安装外部扫描工具（放到 PATH 或 yang/tools/）："
echo "    - nmap    (端口扫描)        yum/apt install nmap"
echo "    - nuclei  (漏洞扫描)        https://github.com/projectdiscovery/nuclei"
echo "    - massdns (域名爆破)        放到 tools/massdns"
echo "    - wih     (WebInfoHunter)   放到 PATH"
echo "    - phantomjs(站点截图/识别)  放到 PATH"

# 8. 启动
echo ""
echo "[*] 启动方式："
echo "    cd ${ARL_DIR} && source .venv/bin/activate"
echo "    uvicorn app.main:app --host 0.0.0.0 --port 5003"
echo ""
echo "[*] 或用 systemd："
echo "    cp misc/arl-web.service /etc/systemd/system/"
echo "    systemctl enable --now arl-web"
echo ""
echo "[+] 安装完成。默认账号 admin / arlpass"
