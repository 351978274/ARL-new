# 配置参考（config.yaml）

ARL 读取项目根目录下的 `config.yaml`（缺失时使用默认值并打印警告，不退出）。
所有字段对应 `app/config.py` 的 `Settings` 类，可用 `reload_config()` 热加载。

字段映射保持与原 ARL 的 `config.py` 一致；新增字段在表格中标注 **(新增)**。

---

## 1. MONGO —— MongoDB 连接

```yaml
MONGO:
  URI: 'mongodb://127.0.0.1:27017/'
  DB: 'arl'
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `URI` | `mongodb://127.0.0.1:27017/` | MongoDB 连接串，可带账号/副本集：`mongodb://user:pass@host:27017/?replicaSet=rs0` |
| `DB` | `arl` | 数据库名 |

`app/database.py` 用 motor 创建全局 `AsyncIOMotorClient` 单例；应用退出时通过 `close_client()` 关闭。

---

## 2. QUERY_PLUGIN —— 子域名数据源插件（12 源）

每个插件独立配置 `enable` 与各自的 token。`enable: true` 但 token 未填写时，插件会被跳过（参见 `app/dns_query_plugin/base.py`）。

```yaml
QUERY_PLUGIN:
  alienvault:        { enable: true }                # https://otx.alienvault.com
  certspotter:                                      # https://www.certspotter.com/
    after_id: 1
    max_page: 3
    enable: true
  crtsh:             { enable: true }                # https://crt.sh
  fofa:              { enable: true }                # key 复用下方 FOFA 段
  hunter_qax:                                        # https://hunter.qianxin.com/
    api_key: ""
    page_size: 100
    max_page: 5
    enable: false
  passivetotal:                                      # https://community.riskiq.com/
    auth_email: ""
    auth_key: ""
    enable: false
  quake_360:                                         # https://quake.360.cn/
    quake_token: ""
    max_size: 500
    enable: false
  rapiddns:          { enable: true }                # https://rapiddns.io
  securitytrails:                                    # https://securitytrails.com/
    api_key: ""
    enable: false
  virustotal:                                        # https://www.virustotal.com/
    api_key: ""
    enable: false
  zoomeye:                                           # https://www.zoomeye.org/
    api_key: ""
    max_page: 20
    enable: false
  chaos:                                             # https://chaos.projectdiscovery.io/
    api_key: ""
    enable: false
```

测试数据源加载：

```bash
pytest tests/test_dns_plugins.py -v
```

单独调用某插件（Python REPL）：

```python
import asyncio
from app.dns_query_plugin.base import run_query_plugin
asyncio.run(run_query_plugin("example.com", sources=["crtsh", "fofa"]))
```

---

## 3. GEOIP —— GeoIP 数据库

```yaml
GEOIP:
  CITY: '/data/GeoLite2/GeoLite2-City.mmdb'
  ASN:  '/data/GeoLite2/GeoLite2-ASN.mmdb'
```

- 任一为空时，对应的 `get_ip_city` / `get_ip_asn` 返回空字典（不影响其他功能）。
- 数据库需从 MaxMind 下载（需注册免费账号）：https://www.maxmind.com/

---

## 4. FOFA —— FOFA 资产搜索引擎

```yaml
FOFA:
  URL: "https://fofa.info"
  KEY: ""
  MAX_PAGE: 5
  PAGE_SIZE: 2000
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `URL` | `https://fofa.info` | FOFA API 域名 |
| `KEY` | `""` | Personal API Key（在 FOFA 个人中心获取） |
| `MAX_PAGE` | 5 | 单次任务最大翻页 |
| `PAGE_SIZE` | 2000 | 每页大小（普通会员上限 100，VIP 上限 2000） |

---

## 5. DINGDING / FEISHU / WXWORK / EMAIL —— 消息推送

仅当资产监控任务发现新资产/站点变化时推送（参见 `app/utils/push.py` 的 `message_push`）。

### 钉钉（自定义机器人 + 加签）

```yaml
DINGDING:
  SECRET: "SECxxxx"
  ACCESS_TOKEN: "xxxx"
```

### 飞书（自定义机器人 + 签名校验）

```yaml
FEISHU:
  WEBHOOK_URL: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
  SECRET: "xxxx"
```

### 企业微信群机器人

```yaml
WXWORK:
  WEBHOOK_URL: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx"
```

### 邮件（SMTP）

```yaml
EMAIL:
  HOST: "smtp.example.com"
  PORT: 465                 # 465 走 SMTP_SSL；其他端口走明文 SMTP
  USERNAME: "arl@example.com"
  PASSWORD: "smtp-password-or-app-password"
  TO: "sec-team@example.com,leader@example.com"
```

---

## 6. WEBHOOK —— 资产监控结果外发

监控任务（domain/ip/site）结束后，向 `URL` POST JSON，Header 带 `Token: <TOKEN>`。
请求体结构见 `app/services/webhook.py` 的 `DomainAssetWebHook.build_data()` 等。

```yaml
WEBHOOK:
  URL: "https://your-soc.example.com/api/arl ingest"
  TOKEN: "shared-secret"
```

`URL` 为空时跳过推送。

---

## 7. GITHUB —— GitHub 代码搜索

```yaml
GITHUB:
  TOKEN: "ghp_xxxx"
```

- 需要 `public_repo` 或经典 PAT；用于 `app/services/github_search.py` 调用 Code Search API。
- 触发关键字监控（`/api/github_scheduler/`）时使用。

---

## 8. PROXY —— HTTP 代理

```yaml
PROXY:
  HTTP_URL: "http://127.0.0.1:8080"
```

- 仅作用于 `httpx` 发起的请求（站点抓取、数据源插件、webhook、消息推送）。
- **端口扫描、massdns、nuclei、wih、nmap 不走代理**（这些是外部二进制）。

---

## 9. ARL —— 核心运行参数

```yaml
ARL:
  AUTH: true
  API_KEY: ""
  BLACK_IPS:
    - 127.0.0.0/8
    - 0.0.0.0/8
    - 172.16.0.0/12
    - 100.64.0.0/10
  FORBIDDEN_DOMAINS: []
  PORT_TOP_10: "80,443,8443,8080,8081,8888,8089,5000,5001,8085,800,81,9000,88,8001,8090"
  DOMAIN_DICT: ""
  FILE_LEAK_DICT: ""
  DOMAIN_BRUTE_CONCURRENT: 300
  ALT_DNS_CONCURRENT: 1500
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `AUTH` | `true` | 是否开启 Token 认证；`false` 时所有端点放行（仅本地开发建议） |
| `API_KEY` | `""` | 后端 API 调用 key；非空时可代替 user token，请求头 `Token: <API_KEY>` |
| `BLACK_IPS` | 内网/保留段 | 禁扫 IP CIDR 列表，防 SSRF；`not_in_black_ips` 校验 |
| `FORBIDDEN_DOMAINS` | `[]` | 禁止下发的域名后缀列表；**不可为非 list 类型** |
| `PORT_TOP_10` | 16 个常见 WEB 端口 | 前端"测试"选项对应的端口 |
| `DOMAIN_DICT` | `""` | 自定义大字典路径（覆盖默认 `dicts/domain_2w.txt`）；空则用默认 |
| `FILE_LEAK_DICT` | `""` | 自定义文件泄漏字典（覆盖 `dicts/file_top_2000.txt`） |
| `DOMAIN_BRUTE_CONCURRENT` | 300 | massdns 域名爆破并发 |
| `ALT_DNS_CONCURRENT` | 1500 | AltDNS 组合生成并发 |

预设端口常量见 `app/config.py:ScanPortPresets`：
- `TOP_10` ≈ 16 端口（WEB）
- `TOP_100` ≈ 250 端口
- `TOP_1000` = nmap TOP 1000
- `ALL` = `0-65535`

---

## 10. SCHEDULER —— APScheduler 调度

```yaml
SCHEDULER:
  POLL_INTERVAL: 58
```

- 单位：秒；最小值会被钳制到 `10`。
- 每次 tick 执行 `run_scheduler_tick`（资产监控 + GitHub 监控 + 计划任务）。
- 调度过密会增加 MongoDB 读压力；建议保持默认 `58`。

---

## 11. 路径相关常量（不可配置，自动派生）

`app/config.py` 中以下路径基于项目根目录自动派生：

| 常量 | 路径 |
|---|---|
| `TMP_PATH` | `<root>/tmp/` |
| `MASSDNS_BIN` | `<root>/tools/massdns` |
| `SCREENSHOT_JS` | `<root>/tools/screenshot.js` |
| `DRIVER_JS` | `<root>/tools/driver.js` |
| `SCREENSHOT_DIR` | `<root>/tmp_screenshot/` |
| `DOMAIN_DICT_TEST` | `<root>/dicts/domain_dict_test.txt` |
| `DOMAIN_DICT_2W` | `<root>/dicts/domain_2w.txt` |
| `DNS_SERVER` | `<root>/dicts/dnsserver.txt` |
| `CDN_JSON_PATH` | `<root>/dicts/cdn_info.json` |
| `WIH_RULE_PATH` | `<root>/dicts/wih_rules.yml` |
| `FILE_LEAK_TOP_2k` | `<root>/dicts/file_top_2000.txt` |

---

## 12. 配置加载机制

1. `app/config.py` 在 import 时执行 `_build_settings()`，读取 `config.yaml`
2. 解析失败/缺失时返回默认 `Settings()` 并打印警告，**不会退出**
3. 全局单例 `Config`（`Settings` 实例），所有模块通过 `from .config import Config` 引用
4. 测试或运维场景可通过 `reload_config()` 强制重新读取

---

## 13. 完整示例（最小可用）

```yaml
MONGO:
  URI: 'mongodb://127.0.0.1:27017/'
  DB: 'arl'

QUERY_PLUGIN:
  crtsh:    { enable: true }
  rapiddns: { enable: true }

ARL:
  AUTH: true
  API_KEY: ""
  BLACK_IPS:
    - 127.0.0.0/8
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
  FORBIDDEN_DOMAINS: []
  DOMAIN_BRUTE_CONCURRENT: 300
  ALT_DNS_CONCURRENT: 1500

SCHEDULER:
  POLL_INTERVAL: 58
```

完整字段示例见仓库根目录的 `config.yaml.example`。
