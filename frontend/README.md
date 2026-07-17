# ARL 前端（Vue 3 + Element Plus）

> 基于 `doc/ARL/image/` 设计图实现，与 `yang/app/` FastAPI 后端接口对接。

## 技术栈
- **Vue 3**（Composition API + `<script setup>`）
- **Vue Router 4**（hash 模式）
- **Pinia**（用户态管理）
- **Element Plus 2.8**（按需自动导入，中文 locale）
- **Axios**（统一 Token 拦截 + 错误处理）
- **Vite 5**（开发/构建）

## 功能页面（对应设计图）

| 设计图 | 页面 | 路由 |
|---|---|---|
| login.png | 登录 | `/login` |
| task.png | 任务列表 | `/task` |
| scan.png | 新建任务弹窗 | （弹窗） |
| domain.png | 子域名 | `/domain` |
| site.png | 站点 | `/site` |
| monitor.png | 资产监控 | `/scheduler` |
| policy.png | 策略管理 | `/policy` |
| task_scheduler.png | 计划任务 | `/task_schedule` |
| github_monitor.png | Github 监控 | `/github_scheduler` |

## 已实现的全部页面（27 个路由）
- **任务**：任务（列表/新建/停止/重启/同步/删除/批量导出）、计划任务
- **资产**：子域名、站点、IP、URL、C段、证书、系统服务、漏洞、文件泄露、PoC、指纹统计、nuclei、WIH（共 14 个，复用 GenericList）
- **资产组**：资产组、资产监控、资产组域名/IP/站点/WIH
- **Github**：Github 监控、Github 任务/结果/监控结果
- **系统**：策略管理、指纹管理、控制台

## 新建任务弹窗的全部勾选项（对应 scan.png）
- 任务名称、任务目标、域名爆破类型（测试/大字典）、端口扫描类型（TEST/TOP100/TOP1000/ALL）
- **15 个中文勾选**：域名爆破、服务识别、操作系统识别、SSL证书获取、跳过CDN、站点识别、搜索引擎调用、站点爬虫、站点截图、文件泄露、Host碰撞、nuclei调用、WIH调用、DNS字典智能生成、ARL历史查询、域名查询插件

## 策略编辑弹窗的配置组（对应 policy.png）
- 域名配置（域名爆破/DNS智能生成/ARL历史查询/域名查询插件 + 爆破类型）
- 端口配置（端口扫描/服务识别/操作系统识别/SSL证书/跳过CDN + 扫描类型）
- 站点配置（站点识别/截图/爬虫/文件泄露/搜索引擎/Host碰撞/nuclei/WIH）
- 资产组配置（关联资产组ID，自动同步）

## 开发

```bash
cd frontend
npm install        # 安装依赖
npm run dev        # 开发服务器 http://localhost:8080（代理 /api 到 5003）
npm run build      # 生产构建到 dist/
```

开发模式下 `/api` 与 `/image` 自动代理到 `http://127.0.0.1:5003`（vite.config.js）。

## 生产部署

构建后将 `dist/` 托管在 nginx，或交给后端 FastAPI 静态托管：

```bash
npm run build
# 方式1：nginx 托管（参考 misc/arl.conf）
#   root /opt/ARL/frontend/dist;
# 方式2：FastAPI 托管（在 app/main.py 挂载 StaticFiles）
```

## 接口对接

所有 API 调用集中在 `src/api/index.js`，对应后端 34 个路由组：
- 资产集合分页查询：`GET /api/{collection}/?page=&size=&task_id=`
- 资产导出：`GET /api/export/{collection}/`
- 任务 CRUD：`/api/task/*`
- 资产组/监控/指纹/策略/Github：各自路由组

认证：登录返回 `token`，存 localStorage，每次请求自动带 `Token` header。401 自动跳登录。
