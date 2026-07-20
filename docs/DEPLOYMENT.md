# 部署指南

本版**仅需 MongoDB + 一个 Python 进程**，不再需要 RabbitMQ/Celery/多个 worker。

---

## 1. 系统要求

| 项 | 最低 | 推荐 |
|---|---|---|
| OS | Linux x86_64（CentOS 7+/Ubuntu 20.04+/Rocky/Debian 11+） | Ubuntu 22.04 / Debian 12 |
| Python | 3.11（理论） | **3.13.7** |
| MongoDB | 4.4 | 7.x |
| 内存 | 2 GB | 4 GB+（取决于任务规模） |
| 磁盘 | 10 GB | 50 GB+（截图/日志/数据库） |

外部二进制（按需启用对应功能）：

| 二进制 | 用途 | 安装方式 |
|---|---|---|
| `nmap` | 端口扫描 | `apt install nmap` / `yum install nmap` |
| `massdns` | 域名爆破 | 编译后放到 `tools/massdns` |
| `nuclei` | 漏洞 PoC | https://github.com/projectdiscovery/nuclei/releases，放到 PATH |
| `wih` | WebInfoHunter | 放到 PATH |
| `phantomjs` | 站点截图/web_analyze | 放到 PATH（已停止维护，可选） |

---

## 2. Linux 一键安装

```bash
cd ARL-new
chmod +x misc/setup.sh
./misc/setup.sh
```

`setup.sh` 自动完成：
1. 安装系统依赖（git/wget/nmap/build-essential/libssl-dev/...）
2. 安装并启动 MongoDB 7.x
3. 从源码编译 Python 3.13.7
4. 创建 `.venv` 并安装 `requirements.txt`
5. 复制 `config.yaml.example` 到 `config.yaml`

完成后编辑 `config.yaml` 并运行：

```bash
./misc/run.sh
```

---

## 3. Linux 生产部署（systemd + nginx）

### 3.1 安装为 systemd 服务

```bash
sudo cp misc/arl-web.service /etc/systemd/system/arl-web.service
sudo mkdir -p /var/log/arl
sudo systemctl daemon-reload
sudo systemctl enable --now arl-web
sudo systemctl status arl-web
```

`arl-web.service` 关键字段：

```ini
[Service]
Type=simple
User=root
WorkingDirectory=/opt/ARL
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/ARL/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5018 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/arl/web.log
StandardError=append:/var/log/arl/web.err.log
```

> **注意**：`workers` 必须为 `1`。多 worker 会导致 APScheduler 重复触发、任务执行器状态不一致。如需横向扩展，请改用外部分发器（未内置）。

### 3.2 配置 nginx 反向代理（TLS）

```bash
# 1. 生成自签证书（或替换为正式证书）
sudo openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout /etc/ssl/certs/arl_web.key -out /etc/ssl/certs/arl_web.crt \
  -subj "/CN=arl.example.com"

# 2. 部署 nginx 站点
sudo cp misc/arl.conf /etc/nginx/conf.d/arl.conf
sudo nginx -t && sudo systemctl reload nginx
```

`arl.conf` 监听 `5003` 端口（HTTPS），反代 `/api/`、`/image/` 到 `127.0.0.1:5018`，根路径服务前端 SPA。

访问：`https://IP:5003/`

### 3.3 防火墙

```bash
sudo firewall-cmd --permanent --add-port=5003/tcp   # firewalld
sudo firewall-cmd --reload
# 或 ufw：
sudo ufw allow 5003/tcp
```

---

## 4. Docker 部署

仓库未内置 Dockerfile（保持精简）。以下为参考实现：

### 4.1 Dockerfile

```dockerfile
FROM python:3.13-slim

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap massdns wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 外部二进制
RUN ln -s /usr/bin/nmap /app/tools/nmap && \
    ln -s /usr/bin/massdns /app/tools/massdns

EXPOSE 5003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5003"]
```

### 4.2 docker-compose.yml（含 MongoDB）

```yaml
version: "3.8"
services:
  mongo:
    image: mongo:7
    volumes:
      - mongo-data:/data/db
    restart: unless-stopped

  arl:
    build: .
    depends_on: [mongo]
    ports:
      - "5003:5003"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./tmp:/app/tmp
      - ./logs:/app/logs
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped

volumes:
  mongo-data:
```

`config.yaml` 中 MongoDB URI 改为：

```yaml
MONGO:
  URI: 'mongodb://mongo:27017/'
  DB: 'arl'
```

启动：

```bash
docker compose up -d
docker compose logs -f arl
```

---

## 5. Windows 部署（仅开发/测试）

Windows 不适合运行 `nmap`/`massdns`/`nuclei` 等外部二进制（路径与权限问题）。建议：
- **生产**：Linux
- **开发/测试**：Windows 可运行 Web 与单元测试；外部扫描功能跳过

```powershell
cd ARL-new
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.yaml.example config.yaml
notepad config.yaml   # 修改 MONGO 等

uvicorn app.main:app --host 0.0.0.0 --port 5003 --reload
```

MongoDB 在 Windows 上可下载社区版安装：https://www.mongodb.com/try/download/community

---

## 6. 前端部署（可选）

仓库自带 Vue 前端源码（`frontend/`）。构建后放到 `frontend/dist/`，FastAPI 会自动托管：

```bash
cd frontend
npm install
npm run build
# 产物在 frontend/dist/，重启 uvicorn 后访问根路径即前端
```

若使用原 ARL 官方前端，把构建产物放到 `frontend/dist/` 即可（API 路径完全兼容）。

---

## 7. 日志

- **应用日志**：loguru 输出到 stderr（控制台彩色）+ `logs/arl_*.log`（10MB 轮转，保留 7 天）
- **systemd 日志**：`/var/log/arl/web.log` 与 `/var/log/arl/web.err.log`
- **nginx 日志**：`/var/log/nginx/arl.access.log`
- **MongoDB 日志**：`/var/log/mongodb/mongod.log`

查看实时日志：

```bash
journalctl -u arl-web -f
tail -f logs/arl_*.log
```

---

## 8. 数据库维护

### 8.1 备份

```bash
mongodump --uri="mongodb://127.0.0.1:27017/" --db=arl --out=/backup/arl-$(date +%F)
```

### 8.2 恢复

```bash
mongorestore --uri="mongodb://127.0.0.1:27017/" --db=arl /backup/arl-2025-01-01/arl
```

### 8.3 创建索引（性能优化建议）

```javascript
// mongo shell
use arl
db.task.createIndex({"status": 1, "start_time": -1})
db.domain.createIndex({"task_id": 1, "domain": 1})
db.site.createIndex({"task_id": 1, "site": 1})
db.ip.createIndex({"task_id": 1, "ip": 1})
db.url.createIndex({"task_id": 1})
db.scheduler.createIndex({"scope_id": 1, "next_run_time": 1})
db.asset_site.createIndex({"scope_id": 1, "site": 1})
db.asset_domain.createIndex({"scope_id": 1, "domain": 1})
db.asset_ip.createIndex({"scope_id": 1, "ip": 1})
```

### 8.4 清理旧任务数据

```javascript
// 删除 90 天前的任务及其数据
var cutoff = new Date(Date.now() - 90 * 24 * 3600 * 1000);
var oldIds = db.task.find({"start_time": {$lt: cutoff}}, {_id: 1}).map(t => t._id.toString());
db.task.deleteMany({_id: {$in: oldIds.map(id => new ObjectId(id))}});
["cert","domain","fileleak","ip","service","site","url","vuln","cip","npoc_service","wih","nuclei_result","stat_finger"]
  .forEach(c => db[c].deleteMany({task_id: {$in: oldIds}}));
```

---

## 9. 升级

```bash
cd ARL-new
git pull
source .venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart arl-web
```

数据库结构保持向后兼容；如版本间有 schema 变更会在 release notes 标注。

---

## 10. 安全加固清单

- [ ] `ARL.AUTH=true`（默认）
- [ ] 修改默认密码：`POST /api/user/change_pass`
- [ ] `ARL.API_KEY` 设为高强度随机串，或留空禁用 API key 登录
- [ ] `ARL.BLACK_IPS` 至少包含 RFC1918 与保留段（防 SSRF）
- [ ] `ARL.FORBIDDEN_DOMAINS` 加入禁止目标
- [ ] nginx 启用 TLS 1.2/1.3 + HSTS（`arl.conf` 已含）
- [ ] 防火墙仅开放必要端口（5003）
- [ ] MongoDB 绑定 `127.0.0.1` 或内网，启用 auth
- [ ] 第三方 token（FOFA/GitHub/...）使用最小权限
- [ ] 日志定期轮转与审计
- [ ] 反向代理层收紧 CORS（修改 `app/main.py:_create_cors_middleware`）

---

## 11. 故障排查

| 现象 | 排查 |
|---|---|
| 启动报 `MongoDB 连接失败` | 检查 mongod 是否运行、`MONGO.URI` 正确性、防火墙 |
| `/api/health` 返回 `mongo: false` | 同上；网络/认证问题 |
| 任务一直 `waiting` | 检查日志是否报任务派发异常；task_runner 内存中映射是否被清（多 worker？必须 workers=1） |
| 端口扫描无结果 | 检查 `nmap` 是否在 PATH、`BLACK_IPS` 是否过严 |
| massdns 报错 | `tools/massdns` 二进制存在？`dicts/dnsserver.txt` 有内容？ |
| nuclei 不执行 | `nuclei` 在 PATH？`nuclei -version` 可运行？ |
| 站点截图为默认图 | `phantomjs` 在 PATH？`tools/screenshot.js` 存在？ |
| 调度任务不触发 | `SCHEDULER.POLL_INTERVAL` 过大？job 的 `next_run_time` 是否在未来？ |
| 推送失败 | 检查对应渠道 token/secret；日志会有 `push_xxx error` 警告 |
