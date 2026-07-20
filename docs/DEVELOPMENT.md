# 开发指南

面向希望理解架构、扩展功能或贡献代码的开发者。前置阅读：[README](../README.md) 与 [CONFIG.md](CONFIG.md)。

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI app (单进程)                       │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  routes/     │ →  │  helpers/    │ →  │  core/task_runner│  │
│  │  (~35 组)    │    │  业务编排    │    │  asyncio 后台    │  │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘  │
│           ↑              ↑                      │              │
│           │          ┌───┴────┐         ┌────────▼─────────┐    │
│      ┌────┴────┐     │ DB层  │         │   tasks/         │    │
│      │ deps.py │     │ motor │         │ domain/ip/...    │    │
│      │ 认证+分页│     │异步   │         └────────┬─────────┘    │
│      └─────────┘     └───┬───┘                  │              │
│                          │              ┌───────▼────────┐     │
│                  ┌───────┴────────┐     │  services/     │     │
│                  │ MongoDB        │     │ fetch_site/    │     │
│                  │ arl db         │     │ port_scan/...  │     │
│                  └────────────────┘     └───────┬────────┘     │
│                                                 │              │
│                                  ┌──────────────┴──────────┐   │
│                                  │  core/                  │   │
│                                  │  http_client (httpx)    │   │
│                                  │  dns (dnspython async)  │   │
│                                  │  base_task (Semaphore)  │   │
│                                  │  fingerprint (DSL)      │   │
│                                  └─────────────────────────┘   │
│                                                                 │
│  APScheduler (AsyncIOScheduler) → run_scheduler_tick            │
│    ├ asset_monitor_scheduler (scheduler 集合)                   │
│    ├ github_task_scheduler (github_scheduler 集合)              │
│    └ task_scheduler (task_schedule 集合)                        │
└─────────────────────────────────────────────────────────────────┘
```

### 关键设计原则

1. **单进程 asyncio**：Web、任务执行、调度都在一个事件循环里
2. **同步库用 `asyncio.to_thread`**：nmap/massdns/nuclei/wih/xing 等不阻塞 loop
3. **I/O 全异步**：httpx/motor/dnspython 都是 async
4. **DB 优先**：所有任务状态/进度/结果落 MongoDB，进程重启可恢复（除运行中任务的内存映射）

---

## 2. 代码分层

| 层 | 职责 | 例子 |
|---|---|---|
| `routes/` | HTTP 入参/出参、调用 helpers | `routes/task.py` |
| `helpers/` | 业务编排（拆目标、build task_data、调 task_runner） | `helpers/task.py` |
| `core/` | 通用基础设施（HTTP/DNS/并发/任务派发） | `core/task_runner.py` |
| `services/` | 单一扫描服务（无业务状态） | `services/port_scan.py` |
| `tasks/` | 任务流水线（组合多个 services） | `tasks/domain_task.py` |
| `modules/` | 数据模型、枚举、错误码 | `modules/enums.py` |
| `utils/` | 纯工具函数 | `utils/url_util.py` |
| `scheduler/` | APScheduler 任务 CRUD 与 tick | `scheduler/jobs.py` |

依赖方向：`routes → helpers → core/services → utils`，`tasks → services + core`。

---

## 3. 任务执行机制

### 提交流程

```
POST /api/task/
  ↓
routes/task.py:add_task
  ↓
helpers/task.submit_task_task(target, name, options)
  ↓ get_ip_domain_list() 拆分 + 黑名单校验
  ↓ build_task_data() 构造 task 文档
  ↓ submit_task(task_data)
      ├ conn_db('task').insert_one(task_data)    # 落库，状态=waiting
      ├ task_runner.submit_task_action(options)  # 派发
      │     ├ asyncio.create_task(_run_with_logging(run_id, options))
      │     ├ _running_tasks[run_id] = task
      │     ├ _task_id_to_run_id[task_id] = run_id
      │     └ _run_id_to_task_id[run_id] = task_id
      └ conn_db('task').update_one(celery_id=run_id)
  ↓
返回 task_data_list
```

### 执行流程

```
_run_with_logging(run_id, options)
  ↓ run_task(options)
      根据 options.celery_action 分发：
      ├ DOMAIN_TASK   → tasks/domain_task.domain_task(target, task_id, options)
      ├ IP_TASK       → tasks/ip_task.ip_task(...)
      ├ RUN_RISK_CRUISING → tasks/risk_cruising.run_risk_cruising_task(...)
      ├ FOFA_TASK     → ...
      ├ ASSET_SITE_UPDATE → ...
      └ ...
  ↓ 异常时 _mark_task_status(task_id, ERROR)
  ↓ 取消时 _mark_task_status(task_id, STOP)
  ↓ 完成 _on_done(run_id, task) 清理内存映射
```

### 取消机制

```
GET /api/task/stop/{task_id}
  ↓
task_runner.cancel_task_by_task_id(task_id)
  ├ run_id = _task_id_to_run_id.get(task_id)
  ├ task = _running_tasks.get(run_id)
  └ task.cancel()   # 触发 CancelledError，被 _run_with_logging 捕获
```

注意：`asyncio.Task.cancel()` 只能取消 await 中的协程；如果任务正在 `asyncio.to_thread` 跑 nmap，需等当前同步调用返回后才能生效。

---

## 4. 扩展点

### 4.1 新增子域名数据源插件

1. 在 `app/dns_query_plugin/` 新建 `<source>.py`：

```python
from .base import DNSQueryBase

class MySourcePlugin(DNSQueryBase):
    def __init__(self):
        super().__init__()
        self.source_name = "mysource"
        self.api_key = ""

    def init_key(self, api_key=""):
        self.api_key = api_key

    async def sub_domains(self, target: str) -> list[str]:
        # 调用你的 API，返回原始子域名列表（无需过滤，base.query 会统一过滤）
        resp = await http_req(f"https://api.mysource.com/domains/{target}",
                              headers={"Authorization": f"Bearer {self.api_key}"})
        return resp.json().get("subdomains", [])
```

2. 在 `app/utils/query_loader.py` 注册（如果它使用动态加载则无需）：

```python
# query_loader 通常自动扫描 dns_query_plugin 目录
# 若需显式注册：
from .mysource import MySourcePlugin
```

3. 在 `config.yaml` 添加配置：

```yaml
QUERY_PLUGIN:
  mysource:
    api_key: "xxxx"
    enable: true
```

### 4.2 新增 REST 端点

1. 在 `app/routes/` 新建 `<feature>.py`：

```python
from __future__ import annotations
from fastapi import APIRouter, Depends
from ..deps import require_auth
from ..modules import build_ret, error_map

router = APIRouter(prefix="/myfeature", tags=["我的功能"],
                   dependencies=[Depends(require_auth)])

@router.get("/")
async def list_items():
    return build_ret(error_map["Success"], {"items": []})
```

2. 在 `app/routes/__init__.py` 注册：

```python
from .myfeature import router as myfeature_router
all_routers: list = [
    # ... existing
    myfeature_router,
]
```

3. 重启服务，访问 `/api/myfeature/` 与 `/api/doc`。

### 4.3 新增任务类型（action）

1. 在 `app/modules/enums.py:TaskAction` 添加常量：

```python
class TaskAction:
    # ... existing
    MY_TASK = "my_task"
```

2. 在 `app/core/task_runner.py:run_task` 的 `action_map` 注册处理函数：

```python
action_map = {
    # ... existing
    TaskAction.MY_TASK: _my_task,
}

async def _my_task(data: dict):
    from ..tasks.my_task import my_task
    await my_task(task_id=data["task_id"], **data)
```

3. 在 `app/helpers/task.py:submit_task` 的 `type_map_action` 添加映射（若走标准 task 提交路径）。

4. 实现 `app/tasks/my_task.py`。

### 4.4 新增指纹规则

**方式 A：通过 API 添加单条**

```bash
curl -k -X POST https://127.0.0.1:5003/api/fingerprint/ \
  -H "Token: <token>" -H "Content-Type: application/json" \
  -d '{"name":"MyApp","human_rule":"header=\"X-Powered-By: MyApp\"","category":"应用"}'
```

**方式 B：批量导入（finger.json 格式，兼容 ADD-ARL-Finger）**

```bash
python -m app.tools.finger_import https://127.0.0.1:5003/ admin arlpass new finger.json
```

**方式 C：本地规则（webapp.json）**

编辑 `dicts/webapp.json`，按现有格式添加。本地规则在 `load_fingerprint()` 时加载。

### 指纹 DSL 语法

```
expression := or_expr
or_expr    := and_expr ( "||" and_expr )*
and_expr   := not_expr ( "&&" not_expr )*
not_expr   := "!" not_expr | primary
primary    := "(" expression ")" | atom
atom       := variable op value | variable
op         := "==" | "!=" | "="
value      := "quoted_string" | integer
variable   := body | header | title | icon_hash
```

- `=` 包含（`value in variable`）
- `==` 完全相等
- `!=` 不包含

示例：

```
header="Server: nginx" && body="Welcome"
title=="Login Page"
icon_hash=="1234567890"
```

---

## 5. 测试

```bash
# 全部
pytest tests/ -v

# 单个文件
pytest tests/test_expr.py -v

# 匹配名称
pytest tests/ -k "domain or ip" -v

# 覆盖率
pytest tests/ --cov=app --cov-report=term-missing
```

测试约定：
- 异步测试用 `pytest-asyncio`（`pyproject.toml` 中 `asyncio_mode = "auto"`）
- DB 测试需要可连 MongoDB（当前 59 项测试均为纯函数，不依赖 DB）
- 新增功能建议补单测到 `tests/test_<feature>.py`

---

## 6. 代码风格

- Python 3.13+，使用 `from __future__ import annotations` + PEP 604 类型（`int | None`）
- 异步优先：所有 I/O 用 async/await
- 同步库（subprocess/nmap/...）用 `asyncio.to_thread` 包裹
- 类型注解必填（pydantic 模型 / `dict[str, Any]`）
- 日志用 `from .logger import get_logger`（loguru）
- 错误返回用 `build_ret(error_map["XXX"], {...})`
- 临时文件用 `try/finally` + `os.unlink` 清理（参见 `services/nuclei_scan.py`）
- 模块顶部 docstring 注明对应原 ARL 文件（便于追溯）

静态检查：

```bash
pip install pyflakes
python -m pyflakes app/
```

---

## 7. 调试技巧

### 7.1 查看运行中的任务

```python
from app.core.task_runner import list_running_tasks
print(list_running_tasks())   # {run_id: task_name}
```

### 7.2 手动触发调度 tick

```python
import asyncio
from app.scheduler.jobs import run_scheduler_tick
asyncio.run(run_scheduler_tick())
```

### 7.3 单独测试某个服务

```python
import asyncio
from app.services.fetch_site import fetch_site

async def main():
    sites = await fetch_site(["https://example.com"])
    print(sites)

asyncio.run(main())
```

### 7.4 开启 DEBUG 日志

修改 `app/logger.py`，把控制台 handler 的 `level="INFO"` 改为 `"DEBUG"`。

### 7.5 禁用认证便于调试

```yaml
ARL:
  AUTH: false
```

重启后所有端点免 Token。

---

## 8. 常见开发任务

### 8.1 添加新的端口扫描预设

编辑 `app/config.py:ScanPortPresets`，添加常量；在 `app/modules/enums.py:ScanPortType` 引用；
在 `app/tasks/domain_task.py:DomainTask.__init__` 的 `scan_port_map` 添加映射。

### 8.2 添加新的消息推送渠道

1. 在 `app/utils/push.py` 实现 `async def xxx_send(markdown: str)` 与 `Push.push_xxx()`
2. 在 `message_push()` 中调用
3. 在 `app/config.py:Settings` 添加配置字段
4. 在 `config.yaml.example` 添加段

### 8.3 修改默认账号

- 启动后调用 `POST /api/user/change_pass`
- 或直接在 MongoDB 中修改 `user` 集合的 `password` 字段（`gen_md5("arlsalt!@#" + new_pass)`）
- `init_admin_user` 仅在 `user` 集合为空时创建 admin

---

## 9. 性能调优

| 场景 | 调优参数 |
|---|---|
| 大规模域名爆破 | `ARL.DOMAIN_BRUTE_CONCURRENT`（默认 300，massdns `-s` 参数） |
| AltDNS 慢 | `ARL.ALT_DNS_CONCURRENT`（默认 1500） |
| 端口扫描慢 | 任务选项 `port_parallelism`（默认 32）、`port_min_rate`（默认 64） |
| 站点抓取慢 | `fetch_site` 的 `concurrency`（默认 15，代码内常量） |
| 调度延迟高 | `SCHEDULER.POLL_INTERVAL`（默认 58s） |
| MongoDB 压力大 | 见 [DEPLOYMENT.md#83-创建索引](DEPLOYMENT.md#83-创建索引) |

**禁忌**：
- 不要开多 worker（`uvicorn --workers 4`）—— APScheduler 会重复触发，task_runner 内存映射会丢失
- 不要在事件循环中直接调用同步阻塞函数（用 `asyncio.to_thread`）

---

## 10. 贡献流程

1. Fork → 新建分支 `feature/<name>`
2. 改动 + 补测试（`tests/`）
3. `pytest tests/ -v` 全绿
4. `python -m pyflakes app/` 无新增警告
5. 更新对应文档（`docs/` 或 `README.md`）
6. 提交 PR，说明动机、改动点、测试方式

PR 模板：

```
## 改动
- xxx

## 测试
- pytest tests/ -v  (XX passed)
- 手动验证：xxx

## 文档
- 已更新 docs/CONFIG.md
```
