# API 参考

所有端点都在 **`/api`** 前缀下。除 `/api/user/login`、`/api/health`、`/` 外，均需认证：

- `ARL.AUTH=true`（默认）：请求头需带 `Token: <token>`
  - `<token>` 来自 `/api/user/login` 的返回，或配置文件中的 `ARL.API_KEY`
- `ARL.AUTH=false`：所有端点放行（仅建议本地开发）

返回结构统一为：

```json
{ "code": 200, "message": "success", "data": {...} }
```

错误码与消息见 `app/modules/error_map.py`。

---

## 1. 认证

### POST `/api/user/login`

请求体：

```json
{ "username": "admin", "password": "arlpass" }
```

响应（成功）：

```json
{
  "code": 200,
  "message": "success",
  "data": { "username": "admin", "token": "abcd1234...", "type": "login" }
}
```

### POST `/api/user/logout`

请求头 `Token: <token>`。返回 `{"code":200,"message":"success"}`。

### POST `/api/user/change_pass`

请求头 `Token: <token>`，请求体：

```json
{ "old_password": "arlpass", "new_password": "newpass" }
```

---

## 2. 任务（task）

### GET `/api/task/` —— 任务列表（分页 + 过滤）

```
GET /api/task/?page=1&size=10&order=-start_time&status=done
```

### POST `/api/task/` —— 提交任务

```json
{
  "name": "测试任务",
  "target": "example.com",
  "domain_brute": true,
  "domain_brute_type": "test",
  "port_scan": true,
  "port_scan_type": "test",
  "service_detection": false,
  "os_detection": false,
  "site_identify": true,
  "site_capture": false,
  "file_leak": false,
  "search_engines": false,
  "site_spider": false,
  "arl_search": false,
  "alt_dns": false,
  "ssl_cert": false,
  "dns_query_plugin": true,
  "skip_scan_cdn_ip": false,
  "nuclei_scan": false,
  "findvhost": false,
  "web_info_hunter": false
}
```

`target` 支持空格/逗号分隔的多个目标；自动拆分为 IP / 域名两组，分别下发。

### POST `/api/task/batch_stop/` —— 批量停止

请求体：`["<task_id_1>", "<task_id_2>"]`

### GET `/api/task/stop/{task_id}` —— 停止单任务

### POST `/api/task/delete/` —— 删除任务

```json
[
  { "task_id": "<id>", "del_task_data": true }
]
```

`del_task_data=true` 时连同 task 关联的 `cert/domain/fileleak/ip/service/site/url/vuln/cip/npoc_service/wih/nuclei_result/stat_finger` 一并删除。

### POST `/api/task/sync/` —— 同步任务资产到资产组

```json
{ "task_id": "<id>", "scope_id": "<scope_id>" }
```

### POST `/api/task/policy/` —— 按策略 ID 提交

```json
{ "policy_id": "<id>", "target": "example.com", "name": "策略任务" }
```

### POST `/api/task/restart/` —— 重新运行已完成任务

```json
{ "task_id": "<id>" }
```

---

## 3. FOFA 任务

### POST `/api/task_fofa/`

用 FOFA 语法查询目标并下发 IP 任务，详见 `app/routes/task_fofa.py`。

---

## 4. 资产组（asset_scope）

### GET `/api/asset_scope/` —— 资产组列表

### POST `/api/asset_scope/` —— 创建资产组

```json
{
  "name": "外网资产",
  "scope": "example.com,*.example.com",
  "black_scope": "test.example.com",
  "scope_type": "domain"
}
```

`scope_type`：`domain` / `ip`。IP 类型 scope 支持 `1.2.3.0/24`、`1.2.3.4-50`。

### POST `/api/asset_scope/delete/`

```json
[{ "scope_id": "<id>" }]
```

删除资产组同时会清理关联的 `scheduler` 监控任务。

---

## 5. 调度（scheduler）

### GET `/api/scheduler/` —— 监控任务列表

### POST `/api/scheduler/add/` —— 添加域名/IP 监控

```json
{
  "domain": "example.com",
  "scope_id": "<scope_id>",
  "interval": 3600,
  "name": "每小时监控",
  "scope_type": "domain"
}
```

### POST `/api/scheduler/add_site_monitor/` —— 添加站点变化监控

```json
{ "scope_id": "<id>", "name": "站点监控", "interval": 3600 }
```

### POST `/api/scheduler/add_wih_monitor/` —— 添加 WIH 监控

### POST `/api/scheduler/stop/`、`/recover/`、`/delete/`

请求体均为 `[{ "job_id": "<id>" }]`。

---

## 6. GitHub 监控（github_scheduler）

### GET `/api/github_scheduler/` —— 监控任务列表

### POST `/api/github_scheduler/` —— 创建关键字监控

```json
{
  "name": "敏感词监控",
  "keyword": "password,secret",
  "cron": "0 */6 * * *",
  "scope_id": "<可选>"
}
```

### POST `/api/github_scheduler/stop/`、`/recover/`、`/delete/`

---

## 7. 策略（policy）

任务选项预设，便于复用。

### GET `/api/policy/`、POST `/api/policy/`、POST `/api/policy/save/`、POST `/api/policy/delete/`

---

## 8. 指纹（fingerprint）

### GET `/api/fingerprint/` —— 指纹规则列表

### POST `/api/fingerprint/` —— 新增规则

```json
{
  "name": "Apache-HTTP",
  "human_rule": "header=\"Server: Apache\" || header=\"Server: Apache/\"",
  "category": "应用"
}
```

### POST `/api/fingerprint/upload/` —— 批量导入（finger.json）

### POST `/api/fingerprint/delete/`

---

## 9. 只读资产集合（通用路由）

以下集合都提供相同的两个端点（`app/routes/generic.py`）：

| 集合 | 路径前缀 | tag |
|---|---|---|
| `domain` | `/api/domain/` | 域名 |
| `site` | `/api/site/` | 站点 |
| `ip` | `/api/ip/` | IP |
| `url` | `/api/url/` | URL |
| `cert` | `/api/cert/` | 证书 |
| `service` | `/api/service/` | 系统服务 |
| `fileleak` | `/api/fileleak/` | 文件泄漏 |
| `vuln` | `/api/vuln/` | 漏洞 |
| `poc` | `/api/poc/` | PoC |
| `cip` | `/api/cip/` | C段统计 |
| `stat_finger` | `/api/stat_finger/` | 指纹统计 |
| `npoc_service` | `/api/npoc_service/` | 系统服务(python) |
| `nuclei_result` | `/api/nuclei_result/` | nuclei结果 |
| `wih` | `/api/wih/` | WIH |
| `asset_domain` | `/api/asset_domain/` | 资产组域名 |
| `asset_ip` | `/api/asset_ip/` | 资产组IP |
| `asset_site` | `/api/asset_site/` | 资产组站点 |
| `asset_wih` | `/api/asset_wih/` | 资产组WIH |
| `github_task` | `/api/github_task/` | Github任务 |
| `github_result` | `/api/github_result/` | Github结果 |
| `github_monitor_result` | `/api/github_monitor_result/` | Github监控结果 |
| `task_schedule` | `/api/task_schedule/` | 计划任务 |

### GET `/<collection>/` —— 分页查询

支持的 query 参数：

| 参数 | 示例 | 说明 |
|---|---|---|
| `page` | `1` | 页码，≥1 |
| `size` | `10` | 每页数量，1-100000 |
| `order` | `-start_time` | 排序字段，逗号分隔多字段；`-` 前缀降序 |
| `<field>=<value>` | `task_id=abc` | 等值或正则匹配（不区分大小写） |
| `<f>__neq=<v>` | `status__neq=done` | 不等于 |
| `<f>__not=<v>` | `title__not=test` | 正则 NOT |
| `<f>__gt=<n>` / `__lt=<n>` | `port__gt=80` | 数值比较 |
| `<f>__dgt=<date>` / `__dlt=<date>` | `save_date__dgt=2025-01-01 00:00:00` | 日期比较 |

**等值字段**（`EQUAL_FIELDS`）：`task_id`、`task_tag`、`ip_type`、`scope_id`、`type` —— 这些字段精确匹配而非正则。

### GET `/<collection>/export/` —— 导出主字段为 .txt

返回 `application/octet-stream` 附件，每行一个值。

---

## 10. 跨任务/跨资产组批量导出

### POST `/api/batch_export/<type>/` —— 按任务 ID 批量导出

请求体：`["<task_id_1>", "<task_id_2>"]`

支持的 `<type>`：`site`、`domain`、`ip`、`url`、`cert`、`fileleak`、`vuln`、`service` 等。

### POST `/api/scope_batch_export/<type>/` —— 按资产组批量导出

请求体：`["<scope_id_1>", "<scope_id_2>"]`

支持的 `<type>`：`asset_site`、`asset_domain`、`asset_ip`、`asset_wih`。

---

## 11. 截图与控制台

### GET `/api/image/{task_id}/{filename}` —— 获取站点截图

### GET `/api/console/` —— 控制台信息（用于前端展示版本/MongoDB 状态等）

---

## 12. 系统

### GET `/` —— 根信息

```json
{ "name": "ARL", "version": "3.0.0", "doc": "/api/doc" }
```

### GET `/api/health` —— 健康检查

```json
{ "status": "ok", "mongo": true, "version": "3.0.0" }
```

### GET `/api/doc` —— Swagger UI

### GET `/api/openapi.json` —— OpenAPI Schema

---

## 13. curl 速查

```bash
BASE="https://127.0.0.1:5003"
TOKEN="<your_token>"

# 登录
curl -k -X POST $BASE/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"arlpass"}'

# 提交任务
curl -k -X POST $BASE/api/task/ -H "Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"demo","target":"example.com","port_scan":true,"site_identify":true}'

# 查询任务结果
curl -k "$BASE/api/site/?task_id=<id>&size=20" -H "Token: $TOKEN"

# 导出
curl -k "$BASE/api/domain/export/?task_id=<id>" -H "Token: $TOKEN" -o domains.txt

# 停止任务
curl -k "$BASE/api/task/stop/<task_id>" -H "Token: $TOKEN"

# 创建资产组
curl -k -X POST $BASE/api/asset_scope/ -H "Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"demo","scope":"example.com","scope_type":"domain"}'

# 添加监控
curl -k -X POST $BASE/api/scheduler/add/ -H "Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"domain":"example.com","scope_id":"<id>","interval":3600,"name":"h"}'
```
