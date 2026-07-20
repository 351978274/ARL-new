# ARL 现代化重写版（Asset Reconnaissance Lighthouse）

> 基于 **Python 3.13 / FastAPI / asyncio / APScheduler / MongoDB** 重写
> 替代原版（Flask + Celery + RabbitMQ，Python 3.6）的资产侦察灯塔系统

[![python](https://img.shields.io/badge/python-3.13+-blue)](https://www.python.org/)
[![fastapi](https://img.shields.io/badge/FastAPI-0.115+-009688)](https://fastapi.tiangolo.com/)
[![motor](https://img.shields.io/badge/motor-async-47A248)](https://motor.readthedocs.io/)
[![tests](https://img.shields.io/badge/tests-59%20passed-brightgreen)](tests/)

资产侦察灯塔系统，旨在快速侦察与目标关联的互联网资产，构建基础资产信息库。
本版保持与原 ARL 的 **MongoDB 集合结构、任务选项字段、默认账号** 完全兼容，
但**去除了 RabbitMQ/Celery 依赖**，仅需 **MongoDB + 一个 Python 进程** 即可运行。

---

## 目录

- [1. 与原版的核心差异](#1-与原版的核心差异)
- [2. 功能覆盖](#2-功能覆盖)
- [3. 目录结构](#3-目录结构)
- [4. 安装](#4-安装)
- [5. 配置详解](#5-配置详解)
- [6. 运行](#6-运行)
- [7. API 速查](#7-api-速查)
- [8. 任务选项](#8-任务选项)
- [9. 架构说明](#9-架构说明)
- [10. 测试与开发](#10-测试与开发)
- [11. 已知限制](#11-已知限制)
- [12. 文档导航](#12-文档导航)
- [13. 免责声明](#13-免责声明)

---

## 1. 与原版的核心差异

| 维度 | 原 ARL | 本版（ARL-new） |
|---|---|---|
| Python | 3.6 | **3.13+** |
| Web 框架 | Flask-RESTx | **FastAPI + Uvicorn** |
| 异步任务 | Celery + RabbitMQ（多进程） | **asyncio 后台任务（单进程）** |
| 调度 | 自研 run_forever 循环 | **APScheduler（AsyncIOScheduler）** |
| 并发 | threading.Semaphore + 线程 | **asyncio.Semaphore + asyncio.gather** |
| DB | pymongo（同步） | **motor（异步）** |
| HTTP | requests | **httpx（异步，流式读超时）** |
| DNS | dnspython（同步） | **dnspython async resolver** |
| 指纹 DSL | pyparsing | **纯 Python 递归下降解析器（无依赖）** |
| 认证 | salt + MD5 token | **兼容原方案**（Token header） |
| 配置 | config.yaml | **config.yaml + pydantic-settings** |

**部署简化**：去除 RabbitMQ，仅需 **MongoDB + 一个 Python 进程**。

### 数据兼容性

- MongoDB 集合与文档结构 **与原 ARL 完全一致**：
  `task / domain / ip / site / cert / service / url / vuln / fileleak / cip / stat_finger / npoc_service / wih / nuclei_result / asset_* / github_*/ scheduler / policy / fingerprint / poc / user`
- 任务选项字段（`domain_brute / port_scan_type / dns_query_plugin / ...`）与原 README 第 6 节一一对应。
- 默认账号 `admin / arlpass`（salt-MD5），可与原前端配合使用。

---

## 2. 功能覆盖

| # | 功能 | 实现位置 |
|---|---|---|
| 1 | 域名资产发现和整理 | `app/tasks/domain_task.py`（9 阶段流水线） |
| 2 | IP/IP 段资产整理 | `app/tasks/ip_task.py` |
| 3 | 端口扫描和服务识别 | `app/services/port_scan.py`（nmap） |
| 4 | WEB 站点指纹识别 | `app/core/fingerprint/` + `app/services/fetch_site.py` |
| 5 | 资产分组管理和搜索 | `app/routes/asset_scope.py` + helpers |
| 6 | 任务策略配置 | `app/routes/policy.py` |
| 7 | 计划任务和周期任务 | `app/scheduler/` + `helpers/task_schedule.py` |
| 8 | Github 关键字监控 | `app/tasks/github.py` |
| 9 | 域名/IP 资产监控 | `app/tasks/scheduler_exec.py` |
| 10 | 站点变化监控 | `app/tasks/asset_site.py` + `services/asset_site_monitor.py` |
| 11 | 文件泄漏等风险检测 | `app/services/file_leak.py`（soft-404 检测） |
| 12 | nuclei PoC 调用 | `app/services/nuclei_scan.py` |
| 13 | WebInfoHunter 调用和监控 | `app/services/info_hunter.py` + `app/tasks/asset_wih.py` |
| 14 | 子域名数据源插件 | `app/dns_query_plugin/`（12 源） |
| 15 | Host 碰撞检测 | `app/services/find_vhost.py` |
| 16 | PoC/弱口令/协议识别 | `app/services/npoc.py`（内置 `xing/` ARL-NPoC） |
| 17 | 指纹规则批量导入 | `app/tools/finger_import.py`（ADD-ARL-Finger 等价） |
| 18 | 消息推送（钉钉/飞书/企微/邮件） | `app/utils/push.py` |
| 19 | Webhook 资产推送 | `app/services/webhook.py` |

---

## 3. 目录结构

```
ARL-new/
├── app/
│   ├── main.py                # FastAPI 应用工厂 + APScheduler 生命周期
│   ├── config.py              # pydantic-settings 配置（兼容 config.yaml）
│   ├── database.py            # motor 异步 MongoDB（get_client/conn_db/ping/close_client）
│   ├── deps.py                # 认证 + 分页依赖
│   ├── logger.py              # loguru + colorlog
│   ├── modules/               # 数据模型 + 枚举 + 错误码
│   ├── core/                  # HTTP/DNS/指纹引擎/任务执行器/并发基类
│   │   ├── http_client.py     #   httpx 异步 + 流式读超时
│   │   ├── dns.py             #   dnspython async
│   │   ├── fingerprint/       #   规则 DSL + 本地规则 + DB 缓存
│   │   ├── base_task.py       #   AsyncBaseTask（asyncio.Semaphore）
│   │   └── task_runner.py     #   任务派发/取消（替代 celery）
│   ├── services/              # 扫描服务（fetch_site/port_scan/file_leak/...）
│   ├── dns_query_plugin/      # 12 个子域名数据源插件
│   ├── tasks/                 # 任务流水线（domain/ip/risk_cruising/...）
│   ├── scheduler/             # APScheduler 调度
│   ├── routes/                # FastAPI 路由组（约 35 个）
│   ├── helpers/               # 业务编排（task/scope/policy/...）
│   ├── tools/                 # 辅助工具（finger_import）
│   └── utils/                 # 工具函数 + IPy
├── xing/                      # 内置 ARL-NPoC（PoC/弱口令/协议识别）
├── dicts/                     # 字典/规则文件（域名/黑名单/cdn/wih/webapp）
├── tools/                     # 外部二进制（massdns/screenshot.js/wappalyzer.js）
├── frontend/                  # Vue 前端（dist/ 可被后端 SPA 托管）
├── tests/                     # pytest 单元测试（59 项）
├── misc/                      # 部署配置（systemd/nginx/setup.sh/run.sh）
├── docs/                      # 详细文档
│   ├── CONFIG.md              # 完整配置参考
│   ├── API.md                 # API 端点参考
│   ├── DEPLOYMENT.md          # 部署指南（Linux/Windows/Docker）
│   └── DEVELOPMENT.md         # 开发指南（架构/扩展点）
├── config.yaml.example        # 配置示例
├── pyproject.toml             # 项目元数据 + 依赖
├── requirements.txt           # pip 依赖
├── start.sh                   # 快速启动脚本
└── README.md
```

---

## 4. 安装

### 4.1 快速安装（Linux，root）

```bash
cd ARL-new
chmod +x misc/setup.sh
./misc/setup.sh
```

`setup.sh` 会自动：
1. 安装系统依赖（git/wget/nmap/build-essential 等）
2. 安装并启动 MongoDB 7.x
3. 编译 Python 3.13.7
4. 创建虚拟环境、安装 Python 依赖
5. 复制 `config.yaml.example` 到 `config.yaml`

### 4.2 手动安装

```bash
# 1. 准备 Python 3.13+ 与 MongoDB（见 misc/setup.sh）

# 2. 虚拟环境与依赖
cd ARL-new
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml：MONGO / FOFA / GITHUB / 推送 / 代理 等

# 4. 外部二进制（按需）
#    nmap     -> 系统 yum/apt install nmap
#    nuclei   -> https://github.com/projectdiscovery/nuclei
#    massdns  -> 放到 tools/massdns
#    wih      -> 放到 PATH（WebInfoHunter）
#    phantomjs -> 放到 PATH（站点截图/web_analyze，可选）
```

---

## 5. 配置详解

完整配置说明见 **[docs/CONFIG.md](docs/CONFIG.md)**，以下为快速参考。

`config.yaml` 顶层结构：

| 段 | 作用 |
|---|---|
| `MONGO` | MongoDB 连接（`URI` / `DB`） |
| `QUERY_PLUGIN` | 12 个子域名数据源 token 与开关 |
| `GEOIP` | GeoLite2-City / ASN 数据库路径 |
| `FOFA` | FOFA API key、URL、分页 |
| `DINGDING` / `FEISHU` / `WXWORK` / `EMAIL` | 消息推送 |
| `WEBHOOK` | 资产监控结果 webhook |
| `GITHUB` | GitHub 搜索 token |
| `PROXY` | HTTP 代理（端口扫描不走代理） |
| `ARL` | 认证、黑名单 IP/域名、端口预设、并发数、字典路径 |
| `SCHEDULER` | APScheduler 轮询间隔（秒） |

最小可用配置：

```yaml
MONGO:
  URI: 'mongodb://127.0.0.1:27017/'
  DB: 'arl'

ARL:
  AUTH: true
  API_KEY: ""              # 留空则只允许 Token 登录
  BLACK_IPS:
    - 127.0.0.0/8
    - 0.0.0.0/8
    - 172.16.0.0/12
    - 100.64.0.0/10
  FORBIDDEN_DOMAINS: []    # 不可为空数组以外形式
  DOMAIN_BRUTE_CONCURRENT: 300
  ALT_DNS_CONCURRENT: 1500

SCHEDULER:
  POLL_INTERVAL: 58
```

---

## 6. 运行

### 6.1 开发模式

```bash
cd ARL-new
source .venv/bin/activate          # Windows: .venv\Scripts\activate
./misc/run.sh                      # 或：uvicorn app.main:app --host 0.0.0.0 --port 5003 --reload
./misc/run.sh 5018                 # 指定端口
```

访问：
- **API 文档（Swagger）**：`http://IP:5003/api/doc`
- **OpenAPI Schema**：`http://IP:5003/api/openapi.json`
- **健康检查**：`http://IP:5003/api/health`
- **默认账号**：`admin / arlpass`

### 6.2 生产部署（systemd + nginx）

```bash
sudo cp misc/arl-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arl-web

sudo cp misc/arl.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
# 访问 https://IP:5003/
```

详细部署（含 Docker、Windows、TLS）见 **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**。

### 6.3 启动时发生什么

`app/main.py` 的 `lifespan` 上下文按顺序做：
1. `ping()` MongoDB，成功则调用 `init_admin_user()` 初始化默认管理员
2. 启动 `AsyncIOScheduler`，按 `SCHEDULER.POLL_INTERVAL` 间隔触发 `run_scheduler_tick`
3. 注册路由到 `/api` 前缀
4. 若 `frontend/dist/index.html` 存在，挂载 `/assets` 静态目录并注册 SPA fallback
5. 退出时关闭调度器与 motor 客户端

---

## 7. API 速查

完整端点说明见 **[docs/API.md](docs/API.md)**。所有端点都在 `/api` 前缀下，需 `Token` header（值来自 `/api/user/login`，或 `Config.API_KEY`）。

### 7.1 认证

```bash
# 登录获取 token
curl -k -X POST https://127.0.0.1:5003/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"arlpass"}'
# {"code":200,"data":{"username":"admin","token":"...","type":"login"}}
```

### 7.2 提交任务

```bash
# 提交域名任务
curl -k -X POST https://127.0.0.1:5003/api/task/ \
  -H "Token: <your_token>" -H "Content-Type: application/json" \
  -d '{
    "name":"测试任务",
    "target":"example.com",
    "domain_brute":true,
    "port_scan":true,
    "site_identify":true,
    "dns_query_plugin":true
  }'
```

### 7.3 查询 / 导出

```bash
# 任务列表（分页 + 过滤）
curl -k "https://127.0.0.1:5003/api/task/?size=10&order=-start_time" -H "Token: <token>"

# 站点
curl -k "https://127.0.0.1:5003/api/site/?task_id=<id>&size=10" -H "Token: <token>"

# 域名导出（.txt 附件）
curl -k "https://127.0.0.1:5003/api/domain/export/?task_id=<id>" -H "Token: <token>" -o domains.txt

# 跨任务批量导出
curl -k -X POST "https://127.0.0.1:5003/api/batch_export/domain/" \
  -H "Token: <token>" -H "Content-Type: application/json" \
  -d '["<task_id_1>", "<task_id_2>"]' -o domains.txt
```

### 7.4 资产组 / 调度 / 策略

```bash
# 创建资产组
curl -k -X POST https://127.0.0.1:5003/api/asset_scope/ \
  -H "Token: <token>" -H "Content-Type: application/json" \
  -d '{"name":"测试组","scope":"example.com","scope_type":"domain"}'

# 添加域名监控（周期任务）
curl -k -X POST https://127.0.0.1:5003/api/scheduler/add/ \
  -H "Token: <token>" -H "Content-Type: application/json" \
  -d '{"domain":"example.com","scope_id":"<id>","interval":3600,"name":"每小时监控"}'
```

### 7.5 指纹批量导入

```bash
# 兼容 ADD-ARL-Finger 的 finger.json 格式
python -m app.tools.finger_import https://127.0.0.1:5003/ admin arlpass new finger.json
```

### 7.6 通用查询语法

所有 `GET /<collection>/` 端点支持的 query 参数：

| 参数 | 含义 |
|---|---|
| `page` / `size` / `order` | 分页与排序（`-_id` 默认倒序） |
| `<field>=<value>` | 等值或正则匹配（EQUAL_FIELDS 字段为等值） |
| `<field>__neq=<v>` | `$ne` |
| `<field>__not=<v>` | `$not` 正则 |
| `<field>__gt=<n>` / `__lt=<n>` | 数值比较 |
| `<field>__dgt=<date>` / `__dlt=<date>` | 日期比较（`YYYY-MM-DD HH:MM:SS`） |

---

## 8. 任务选项

提交任务时通过 JSON body 控制（对应原 README 第 6 节）：

| 选项 | 类型 | 说明 |
|---|---|---|
| `domain_brute` | bool | 是否域名爆破 |
| `domain_brute_type` | `test` / `big` | 字典类型 |
| `port_scan` | bool | 是否端口扫描 |
| `port_scan_type` | `test` / `top100` / `top1000` / `all` / `custom` | 端口预设 |
| `port_custom` | str | `custom` 时的端口列表（`80,443,8080-8090`） |
| `service_detection` | bool | nmap `-sV` 服务识别 |
| `os_detection` | bool | nmap `-O` OS 识别 |
| `ssl_cert` | bool | 获取 SSL 证书 |
| `skip_scan_cdn_ip` | bool | 跳过 CDN IP 端口扫描 |
| `site_identify` | bool | 站点指纹识别 |
| `site_capture` | bool | 站点截图 |
| `search_engines` | bool | 搜索引擎子域名收集 |
| `site_spider` | bool | 站点静态爬虫 |
| `file_leak` | bool | 文件泄漏检测 |
| `findvhost` | bool | Host 碰撞检测 |
| `nuclei_scan` | bool | nuclei PoC 扫描 |
| `web_info_hunter` | bool | WebInfoHunter |
| `alt_dns` | bool | DNS 字典智能生成（dnsgen 风格） |
| `arl_search` | bool | 查询 ARL 历史域名 |
| `dns_query_plugin` | bool | 启用 12 个数据源插件 |
| `poc_config` | list | PoC 配置（plugin_name + enable） |
| `brute_config` | list | 弱口令配置 |
| `host_timeout_type` | `default` / `custom` | nmap 主机超时策略 |
| `host_timeout` | int | 自定义主机超时（秒） |
| `port_parallelism` / `port_min_rate` | int | nmap 并发参数 |
| `exclude_ports` | str | nmap 排除端口 |

域名任务 9 阶段流水线（`app/tasks/domain_task.py`）：

```
domain_fetch(爆破/插件/arl/alt_dns)
    → search_engines
    → start_ip_fetch(端口/证书/服务)
    → start_site_fetch(站点识别)
    → start_find_vhost
    → start_poc_run(npoc/PoC/弱口令)
    → start_wih_domain_update
    → common_run(指纹统计/C段统计/任务统计/资产同步)
```

---

## 9. 架构说明

### 任务执行流（替代 Celery）

```
POST /api/task/  →  helpers/task.submit_task_task()
                  →  conn_db('task').insert_one(task_data)
                  →  core/task_runner.submit_task_action(options)
                       └─ asyncio.create_task(_run_with_logging(...))
                            └─ run_task(options)
                                 ├─ DOMAIN_TASK  → tasks/domain_task.domain_task()
                                 ├─ IP_TASK      → tasks/ip_task.ip_task()
                                 └─ ...          → 对应流水线
```

任务状态/进度实时写入 MongoDB（`task` 集合），可通过 `/api/task/` 查询或 `/api/task/stop/{task_id}` 取消。
取消机制：通过 `task_id → run_id → asyncio.Task.cancel()`，同时置 `status=stop`。

### 调度（APScheduler）

`app/main.py` 启动时注册 `run_scheduler_tick`，每 `SCHEDULER.POLL_INTERVAL` 秒执行：
- `asset_monitor_scheduler`：扫描 `scheduler` 集合，到期派发 domain/IP/site_update/wih_update 监控任务
- `github_task_scheduler`：扫描 `github_scheduler` 集合，按 cron 派发 GitHub 监控
- `task_scheduler`：扫描 `task_schedule` 集合，处理周期/定时任务

### 并发模型

- I/O 密集（HTTP/DNS/插件）：`asyncio.Semaphore` + `asyncio.gather`（`AsyncBaseTask`）
- CPU/同步库（nmap/massdns/nuclei/wih/xing）：`asyncio.to_thread` 线程池，不阻塞事件循环
- MongoDB：motor 全异步

---

## 10. 测试与开发

```bash
# 单元测试
pytest tests/ -v
# 59 项：expr DSL / 域名校验 / IP / URL / 端口解析 / 指纹匹配 /
#       DNS 插件加载 / 查询构造 / 任务派发与取消

# 静态检查（需 pip install pyflakes）
python -m pyflakes app/

# 烟雾导入所有模块
python -c "import pkgutil, app; [__import__(m.name) for m in pkgutil.walk_packages(app.__path__, 'app.')]"
```

开发细节（如何加新插件、新路由、新指纹规则）见 **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**。

---

## 11. 已知限制

- **Windows**：核心扫描（nmap/massdns/nuclei）依赖 Linux 二进制，建议在 Linux 部署；开发/测试可在 Windows。
- **xing（NPoC）**：内置的 `xing/` 中 `listener/http_api.py` 需要 Flask（仅监听器模式，默认不启用）。
- **phantomjs**：站点截图与 web_analyze 依赖 phantomjs（已停止维护，可选用 chromium 替代）。
- **GeoIP**：需自行下载 GeoLite2-City/ASN 数据库并配置 `GEOIP` 路径。
- **CORS**：默认 `allow_origins=["*"]`，生产环境建议通过反向代理或代码收紧。

---

## 12. 文档导航

| 文档 | 内容 |
|---|---|
| [docs/CONFIG.md](docs/CONFIG.md) | 完整配置参考（每个字段的含义、默认值、示例） |
| [docs/API.md](docs/API.md) | 所有 REST 端点的请求/响应示例 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 部署指南：systemd / nginx / Docker / Windows / TLS |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 开发指南：架构图、扩展点（新增插件/路由/指纹） |

---

## 13. 免责声明

本项目仅用于授权的安全测试与资产盘点。使用前请务必阅读并同意原 `doc/ARL/Disclaimer.md` 中的条款。
**对未授权目标扫描属违法行为，使用者自行承担后果。**
