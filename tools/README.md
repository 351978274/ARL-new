# tools 目录：外部二进制占位

本项目调用以下外部工具，请按需安装并放置：

| 工具 | 用途 | 路径要求 | 安装方式 |
|---|---|---|---|
| **massdns** | 域名爆破 | `tools/massdns` | https://github.com/ablukacz/massdns |
| **nmap** | 端口扫描 | 系统 PATH | `yum/apt install nmap` |
| **nuclei** | 漏洞扫描（CVE） | 系统 PATH | https://github.com/projectdiscovery/nuclei |
| **wih** | WebInfoHunter（JS 信息提取） | 系统 PATH | https://github.com/TophantTechnology/WebInfoHunter |
| **phantomjs** | 站点截图/识别（可选） | 系统 PATH | https://phantomjs.org/ |

## 配套文件
- `screenshot.js` —— phantomjs 截图脚本（原 ARL 提供）
- `driver.js` —— phantomjs 站点识别脚本（原 ARL 提供，配合 wappalyzer）

如使用原 ARL 的 phantomjs 脚本，请从 `doc/ARL/app/tools/` 复制 `screenshot.js`、`driver.js`、`wappalyzer.js`、`apps.json` 到本目录。

## 代码已做存在性检测
- nuclei/wih：`check_have_nuclei()` / `check_have_wih()` 探测，缺失时降级为空结果
- massdns/phantomjs：缺失时对应服务报错（日志可见）
