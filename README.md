# ARL 现代化重写版（Asset Reconnaissance Lighthouse）

> 基于 **Python 3.13.7 / FastAPI / asyncio / APScheduler / MongoDB** 重写
> 参考实现：`doc/ARL`（原 Flask + Celery + RabbitMQ，Python 3.6）

资产侦察灯塔系统，旨在快速侦察与目标关联的互联网资产，构建基础资产信息库。

---

## 1. 与原版的核心差异

| 维度 | 原 ARL（doc/ARL） | 本版（yang/） |
|---|---|---|
| Python | 3.6 | **3.13.7** |
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
- MongoDB 集合与文档结构 **与原 ARL 完全一致**（task/domain/ip/site/cert/service/url/vuln/fileleak/cip/stat_finger/npoc_service/wih/nuclei_result/asset_*/github_*/scheduler/policy/fingerprint/poc/user）。
- 任务选项字段（domain_brute/port_scan_type/dns_query_plugin/...）与原 README 第 6 节一一对应。
- 默认账号 `admin / arlpass`（salt-MD5），可与原前端配合使用。

---

## 2. 功能覆盖（对应原 ARL 特性）

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
| 9 | 域名/IP 资产监控 | `app/tasks/scheduler_exec.py`（DomainExecutor/IPExecutor） |
| 10 | 站点变化监控 | `app/tasks/asset_site.py` + `services/asset_site_monitor.py` |
| 11 | 文件泄漏等风险检测 | `app/services/file_leak.py`（soft-404 检测） |
| 12 | nuclei PoC 调用 | `app/services/nuclei_scan.py` |
| 13 | WebInfoHunter 调用和监控 | `app/services/info_hunter.py` + `app/tasks/asset_wih.py` |
| 14 | 13 个子域名数据源插件 | `app/dns_query_plugin/` |
| 15 | Host 碰撞检测 | `app/services/find_vhost.py` |
| 16 | PoC/弱口令/协议识别 | `app/services/npoc.py`（内置 xing/ARL-NPoC） |
| 17 | 指纹规则批量导入 | `app/tools/finger_import.py`（ADD-ARL-Finger 等价） |
| 18 | 消息推送（钉钉/飞书/企微/邮件） | `app/utils/push.py` |
| 19 | Webhook 资产推送 | `app/services/webhook.py` |

---

## 3. 目录结构

```
yang/
├── app/
│   ├── main.py                # FastAPI 应用工厂 + APScheduler
│   ├── config.py              # pydantic-settings 配置（兼容 config.yaml）
│   ├── database.py            # motor 异步 MongoDB
│   ├── deps.py                # 认证 + 分页依赖
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
│   ├── routes/                # 34 个 FastAPI 路由组（80 个端点）
│   ├── helpers/               # 业务编排（task/scope/policy/...）
│   ├── tools/                 # 辅助工具（finger_import）
│   └── utils/                 # 工具函数 + IPy
├── xing/                      # 内置 ARL-NPoC（PoC/弱口令/协议识别）
├── dicts/                     # 字典/规则文件（域名/黑名单/cdn/wih/webapp）
├── tests/                     # pytest 单元测试（59 项）
├── misc/                      # 部署配置（systemd/nginx/setup.sh）
├── config.yaml.example
├── pyproject.toml / requirements.txt
└── README.md
```

---

## 4. 安装

### 4.1 快速安装（Linux，root）
```bash
cd yang
chmod +x misc/setup.sh
./misc/setup.sh
```

### 4.2 手动安装
```bash
# 1. Python 3.13.7 + MongoDB（见 misc/setup.sh）

# 2. 虚拟环境与依赖
cd yang
python3.13 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml：MONGO / FOFA / GITHUB / 推送 / 代理 等

# 4. 外部二进制（按需）
#    nmap    -> 系统 yum/apt install nmap
#    nuclei  -> https://github.com/projectdiscovery/nuclei
#    massdns -> 放到 tools/massdns
#    wih     -> 放到 PATH（WebInfoHunter）
#    phantomjs -> 放到 PATH（站点截图/识别，可选）
```

---

## 5. 运行

### 5.1 开发模式
```bash
cd yang
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 5003 --reload
# 或：./misc/run.sh
```

访问：
- API 文档（Swagger）：`http://IP:5003/api/doc`
- 健康检查：`http://IP:5003/api/health`
- 默认账号：`admin / arlpass`

### 5.2 生产部署（systemd + nginx）
```bash
sudo cp misc/arl-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arl-web

sudo cp misc/arl.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
# 访问 https://IP:5003/
```

### 5.3 验证测试
```bash
cd yang
source .venv/bin/activate
pytest tests/ -v
```

---

## 6. API 使用示例

### 6.1 登录获取 Token
```bash
curl -k -X POST https://127.0.0.1:5003/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"arlpass"}'
# {"code":200,"data":{"username":"admin","token":"...","type":"login"}}
```

### 6.2 提交域名任务
```bash
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

### 6.3 查询任务结果
```bash
# 站点
curl -k "https://127.0.0.1:5003/api/site/?task_id=<id>&size=10" -H "Token: <token>"
# 域名导出
curl -k "https://127.0.0.1:5003/api/export/domain/?task_id=<id>" -H "Token: <token>" -o domains.txt
```

### 6.4 批量导入指纹
```bash
# 兼容 ADD-ARL-Finger 的 finger.json 格式
python -m app.tools.finger_import https://127.0.0.1:5003/ admin arlpass new finger.json
```

---

## 7. 配置参数说明

详见 `config.yaml.example`，关键项：

| 配置 | 说明 |
|---|---|
| `MONGO.URI/DB` | MongoDB 连接 |
| `QUERY_PLUGIN.*` | 13 个子域名数据源 token（crtsh/fofa/hunter/quake/...） |
| `FOFA.KEY` | FOFA API key |
| `GITHUB.TOKEN` | GitHub 搜索 token |
| `ARL.AUTH` | 是否开启认证（建议 true） |
| `ARL.API_KEY` | 后端 API 调用 key |
| `ARL.BLACK_IPS` | 禁扫 IP 段（防 SSRF） |
| `ARL.FORBIDDEN_DOMAINS` | 禁止域名 |
| `ARL.PORT_TOP_10` | 前端端口测试选项 |
| `ARL.DOMAIN_BRUTE_CONCURRENT` | 域名爆破并发 |
| `PROXY.HTTP_URL` | HTTP 代理 |
| `DINGDING/FEISHU/WXWORK/EMAIL` | 消息推送 |
| `WEBHOOK.URL/TOKEN` | 资产监控 webhook |
| `SCHEDULER.POLL_INTERVAL` | 调度轮询间隔（秒） |

---

## 8. 任务选项说明（对应原 README 第 6 节）

| 选项 | 说明 |
|---|---|
| `domain_brute` / `domain_brute_type` | 域名爆破（test/big） |
| `port_scan` / `port_scan_type` | 端口扫描（test/top100/top1000/all） |
| `service_detection` / `os_detection` | 服务/OS 识别 |
| `ssl_cert` | SSL 证书获取 |
| `skip_scan_cdn_ip` | 跳过 CDN IP |
| `site_identify` / `site_capture` | 站点识别/截图 |
| `search_engines` / `site_spider` | 搜索引擎/站点爬虫 |
| `file_leak` | 文件泄露检测 |
| `findvhost` | Host 碰撞 |
| `nuclei_scan` | nuclei PoC |
| `web_info_hunter` | WebInfoHunter |
| `alt_dns` | DNS 字典智能生成 |
| `arl_search` | ARL 历史查询 |
| `dns_query_plugin` | 域名查询插件（13 源） |
| `poc_config` / `brute_config` | PoC/弱口令配置 |

---

## 9. 架构说明

### 任务执行流（替代 Celery）
```
POST /api/task/  →  helpers/task.submit_task()
                  →  conn_db('task').insert_one(task_data)
                  →  core/task_runner.submit_task_action(options)
                       └─ asyncio.create_task(run_task(options))
                            └─ action_map[action](data)
                                 ├─ DOMAIN_TASK  → tasks/domain_task.domain_task()
                                 ├─ IP_TASK      → tasks/ip_task.ip_task()
                                 └─ ...          → 对应流水线
```
任务状态/进度实时写入 MongoDB（task 集合），可通过 `/api/task/` 查询或 `/api/task/stop/` 取消。

### 调度（APScheduler）
`app/main.py` 启动时注册 `run_scheduler_tick`，每 `SCHEDULER.POLL_INTERVAL` 秒执行：
- `asset_monitor_scheduler`：扫描 `scheduler` 集合，到期派发 domain/IP/site_update/wih_update 监控任务
- `github_task_scheduler`：扫描 `github_scheduler` 集合，按 cron 派发 GitHub 监控
- `task_scheduler`：扫描 `task_schedule` 集合，处理周期/定时任务

---

## 10. 测试

```bash
pytest tests/ -v
# 59 项测试：expr DSL / 域名校验 / IP / URL / 端口解析 / 指纹匹配 /
#          DNS 插件加载 / 查询构造 / 任务派发与取消
```

---

## 11. 已知限制

- **Windows**：核心扫描（nmap/massdns/nuclei）依赖 Linux 二进制，建议在 Linux 部署；开发/测试可在 Windows。
- **xing（NPoC）**：内置的 `xing/` 中 `listener/http_api.py` 需要 Flask（仅监听器模式，默认不启用）。
- **phantomjs**：站点截图与 web_analyze 依赖 phantomjs（已停止维护，可选用 chromium 替代）。
- **GeoIP**：需自行下载 GeoLite2-City/ASN 数据库并配置 `GEOIP` 路径。

---

## 12. 免责声明

本项目仅用于授权的安全测试与资产盘点。使用前请务必阅读并同意 `doc/ARL/Disclaimer.md` 中的条款。对未授权目标扫描属违法行为，使用者自行承担后果。
