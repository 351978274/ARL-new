// 各资产集合的表格列配置（标题/字段/渲染）
// 字段名与后端 MongoDB 文档结构一致
export const COLLECTION_CONFIG = {
  domain: {
    title: '子域名',
    columns: [
      { prop: 'domain', label: '域名', minWidth: 220, copyable: true },
      { prop: 'type', label: '类型', width: 90 },
      { prop: 'record', label: '记录值', minWidth: 180, render: (row) => (row.record || []).join(', ') },
      { prop: 'ips', label: 'IP', minWidth: 160, render: (row) => (row.ips || []).join(', ') },
      { prop: 'source', label: '来源', width: 110 },
      { prop: 'fld', label: '主域', width: 160 },
    ],
  },
  site: {
    title: '站点',
    columns: [
      { prop: 'screenshot', label: '截图', width: 100, type: 'screenshot' },
      { prop: 'site', label: '站点', minWidth: 200, copyable: true, link: true },
      { prop: 'title', label: '标题', minWidth: 160 },
      { prop: 'http_server', label: 'Server', width: 130 },
      { prop: 'status', label: '状态码', width: 80 },
      { prop: 'body_length', label: '长度', width: 90 },
      { prop: 'ip', label: 'IP', width: 130 },
      { prop: 'finger', label: '指纹', minWidth: 200, render: (row) => fingerText(row.finger) },
      { prop: 'tag', label: '标签', width: 90, render: (row) => tagHtml(row.tag) },
    ],
  },
  ip: {
    title: 'IP',
    columns: [
      { prop: 'ip', label: 'IP', minWidth: 140, copyable: true },
      { prop: 'port_info', label: '端口/服务', minWidth: 280, render: (row) => portText(row.port_info) },
      { prop: 'ip_type', label: '类型', width: 90 },
      { prop: 'cdn_name', label: 'CDN', width: 110 },
      { prop: 'geo_city.country_name', label: '国家', width: 100, render: (row) => row.geo_city?.country_name },
      { prop: 'geo_city.city', label: '城市', width: 100, render: (row) => row.geo_city?.city },
      { prop: 'geo_asn.organization', label: '组织', minWidth: 160, render: (row) => row.geo_asn?.organization },
      { prop: 'domain', label: '关联域名', minWidth: 180, render: (row) => (row.domain || []).join(', ') },
    ],
  },
  url: {
    title: 'URL',
    columns: [
      { prop: 'url', label: 'URL', minWidth: 320, copyable: true, link: true },
      { prop: 'title', label: '标题', minWidth: 160 },
      { prop: 'content_length', label: '长度', width: 80 },
      { prop: 'status_code', label: '状态码', width: 80 },
      { prop: 'source', label: '来源', width: 110 },
      { prop: 'fld', label: '主域', width: 160 },
    ],
  },
  cip: {
    title: 'C段',
    columns: [
      { prop: 'cidr_ip', label: 'C段', minWidth: 160, copyable: true },
      { prop: 'ip_count', label: 'IP数', width: 90 },
      { prop: 'ip_list', label: 'IP列表', minWidth: 220, render: (row) => (row.ip_list || []).join(', ') },
      { prop: 'domain_count', label: '域名数', width: 90 },
      { prop: 'domain_list', label: '域名列表', minWidth: 280, render: (row) => (row.domain_list || []).join(', ') },
    ],
  },
  cert: {
    title: '证书',
    columns: [
      { prop: 'ip', label: 'IP', width: 140 },
      { prop: 'port', label: '端口', width: 80 },
      { prop: 'cert.subject_dn', label: '主体', minWidth: 220, render: (row) => row.cert?.subject_dn },
      { prop: 'cert.issuer_dn', label: '颁发者', minWidth: 220, render: (row) => row.cert?.issuer_dn },
      { prop: 'cert.validity.end', label: '过期时间', width: 170, render: (row) => row.cert?.validity?.end },
    ],
  },
  service: {
    title: '系统服务',
    columns: [
      { prop: 'service_name', label: '服务名', width: 140 },
      { prop: 'service_info', label: '服务详情', minWidth: 400, render: (row) => serviceText(row.service_info) },
    ],
  },
  vuln: {
    title: '漏洞',
    columns: [
      { prop: 'vul_name', label: '漏洞名', minWidth: 180 },
      { prop: 'app_name', label: '应用', width: 120 },
      { prop: 'target', label: '目标', minWidth: 220, copyable: true },
      { prop: 'plg_name', label: '插件', width: 130 },
      { prop: 'plg_type', label: '类型', width: 100 },
      { prop: 'verify_data', label: '验证数据', minWidth: 200 },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  fileleak: {
    title: '文件泄露',
    columns: [
      { prop: 'url', label: 'URL', minWidth: 320, copyable: true, link: true },
      { prop: 'title', label: '标题', minWidth: 160 },
      { prop: 'status_code', label: '状态码', width: 80 },
      { prop: 'content_length', label: '长度', width: 90 },
      { prop: 'site', label: '站点', width: 200 },
    ],
  },
  poc: {
    title: 'PoC',
    columns: [
      { prop: 'plugin_name', label: '插件名', minWidth: 160 },
      { prop: 'app_name', label: '应用', width: 140 },
      { prop: 'scheme', label: '协议', width: 120 },
      { prop: 'vul_name', label: '漏洞名', minWidth: 200 },
      { prop: 'category', label: '类别', width: 110 },
      { prop: 'plugin_type', label: '类型', width: 90 },
    ],
  },
  stat_finger: {
    title: '指纹统计',
    columns: [
      { prop: 'name', label: '指纹名', minWidth: 200 },
      { prop: 'cnt', label: '数量', width: 120 },
    ],
  },
  npoc_service: {
    title: '系统服务(python)',
    columns: [
      { prop: 'scheme', label: '协议', width: 110 },
      { prop: 'host', label: '主机', width: 150 },
      { prop: 'port', label: '端口', width: 90 },
      { prop: 'target', label: '目标', minWidth: 220, copyable: true },
    ],
  },
  nuclei_result: {
    title: 'nuclei 扫描结果',
    columns: [
      { prop: 'vuln_name', label: '漏洞名', minWidth: 180 },
      { prop: 'vuln_severity', label: '级别', width: 90, render: (row) => severityTag(row.vuln_severity) },
      { prop: 'vuln_url', label: 'URL', minWidth: 260, copyable: true, link: true },
      { prop: 'template_id', label: '模板ID', width: 160 },
      { prop: 'target', label: '目标', width: 200 },
      { prop: 'save_date', label: '时间', width: 160 },
    ],
  },
  wih: {
    title: 'WebInfoHunter',
    columns: [
      { prop: 'record_type', label: '类型', width: 100 },
      { prop: 'content', label: '内容', minWidth: 300, copyable: true },
      { prop: 'source', label: '来源', width: 130 },
      { prop: 'site', label: '站点', width: 200 },
      { prop: 'fnv_hash', label: 'hash', width: 140 },
    ],
  },
  asset_domain: {
    title: '资产组域名',
    columns: [
      { prop: 'domain', label: '域名', minWidth: 220, copyable: true },
      { prop: 'type', label: '类型', width: 90 },
      { prop: 'record', label: '记录值', minWidth: 180, render: (row) => (row.record || []).join(', ') },
      { prop: 'ips', label: 'IP', minWidth: 160, render: (row) => (row.ips || []).join(', ') },
      { prop: 'update_date', label: '更新时间', width: 170 },
    ],
  },
  asset_ip: {
    title: '资产组IP',
    columns: [
      { prop: 'ip', label: 'IP', minWidth: 140, copyable: true },
      { prop: 'port_info', label: '端口/服务', minWidth: 280, render: (row) => portText(row.port_info) },
      { prop: 'ip_type', label: '类型', width: 90 },
      { prop: 'cdn_name', label: 'CDN', width: 110 },
      { prop: 'update_date', label: '更新时间', width: 170 },
    ],
  },
  asset_site: {
    title: '资产组站点',
    columns: [
      { prop: 'site', label: '站点', minWidth: 220, copyable: true, link: true },
      { prop: 'title', label: '标题', minWidth: 160 },
      { prop: 'status', label: '状态码', width: 80 },
      { prop: 'http_server', label: 'Server', width: 130 },
      { prop: 'finger', label: '指纹', minWidth: 200, render: (row) => fingerText(row.finger) },
      { prop: 'update_date', label: '更新时间', width: 170 },
    ],
  },
  asset_wih: {
    title: '资产组 WIH',
    columns: [
      { prop: 'record_type', label: '类型', width: 100 },
      { prop: 'content', label: '内容', minWidth: 320, copyable: true },
      { prop: 'source', label: '来源', width: 130 },
      { prop: 'update_date', label: '更新时间', width: 170 },
    ],
  },
  github_task: {
    title: 'Github 任务',
    columns: [
      { prop: 'name', label: '任务名', minWidth: 180 },
      { prop: 'keyword', label: '关键字', minWidth: 180 },
      { prop: 'status', label: '状态', width: 100, render: (row) => statusText(row.status) },
      { prop: 'statistic.github_result_cnt', label: '结果数', width: 90, render: (row) => row.statistic?.github_result_cnt },
      { prop: 'start_time', label: '开始时间', width: 160 },
      { prop: 'end_time', label: '结束时间', width: 160 },
    ],
  },
  github_result: {
    title: 'Github 结果',
    columns: [
      { prop: 'repo_full_name', label: '仓库', minWidth: 200, link: true, linkKey: 'html_url' },
      { prop: 'path', label: '文件路径', minWidth: 240 },
      { prop: 'keyword', label: '关键字', width: 130 },
      { prop: 'commit_date', label: 'Commit时间', width: 170 },
      { prop: 'human_content', label: '代码片段', minWidth: 300, render: (row) => (row.human_content || '').slice(0, 200) },
    ],
  },
  github_monitor_result: {
    title: 'Github 监控结果',
    columns: [
      { prop: 'repo_full_name', label: '仓库', minWidth: 200, link: true, linkKey: 'html_url' },
      { prop: 'path', label: '文件路径', minWidth: 240 },
      { prop: 'keyword', label: '关键字', width: 130 },
      { prop: 'human_content', label: '代码片段', minWidth: 300, render: (row) => (row.human_content || '').slice(0, 200) },
      { prop: 'update_date', label: '更新时间', width: 170 },
    ],
  },
  dirsearch_result: {
    title: 'dirsearch 结果',
    columns: [
      { prop: 'url', label: 'URL', minWidth: 320, copyable: true, link: true },
      { prop: 'path', label: '路径', minWidth: 200 },
      { prop: 'status_code', label: '状态码', width: 90 },
      { prop: 'content_length', label: '长度', width: 100 },
      { prop: 'redirect', label: '跳转', minWidth: 200 },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  hydra_result: {
    title: 'hydra 破解结果',
    columns: [
      { prop: 'host', label: '主机', minWidth: 180, copyable: true },
      { prop: 'port', label: '端口', width: 80 },
      { prop: 'service', label: '服务', width: 120 },
      { prop: 'login', label: '用户名', minWidth: 140, copyable: true },
      { prop: 'password', label: '密码', minWidth: 160, copyable: true },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  sqlmap_result: {
    title: 'sqlmap 注入结果',
    columns: [
      { prop: 'target', label: '目标', minWidth: 220, copyable: true },
      {
        prop: 'vulnerable', label: '可注入', width: 90,
        render: (row) => row.vulnerable ? '是' : '否',
      },
      { prop: 'parameter', label: '注入点', minWidth: 140 },
      { prop: 'dbms', label: '数据库', minWidth: 140 },
      { prop: 'current_db', label: '当前库', width: 130 },
      { prop: 'current_user', label: '当前用户', minWidth: 140 },
      { prop: 'techniques', label: '注入技术', minWidth: 200 },
      { prop: 'payloads', label: 'Payload 示例', minWidth: 240 },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  aircrack_result: {
    title: 'aircrack-ng 破解结果',
    columns: [
      {
        prop: 'cracked', label: '破解', width: 80,
        render: (row) => row.cracked ? '是' : '否',
      },
      { prop: 'key', label: '密钥', minWidth: 220, copyable: true },
      { prop: 'key_type', label: '密钥类型', width: 100 },
      { prop: 'attack_mode', label: '攻击模式', width: 100, render: (row) => ({ '1': 'WEP', '2': 'WPA-PSK' }[row.attack_mode] || row.attack_mode || '-') },
      { prop: 'essid', label: 'ESSID', minWidth: 140 },
      { prop: 'bssid', label: 'BSSID', width: 160 },
      { prop: 'capture_file', label: '抓包文件', minWidth: 180 },
      { prop: 'wordlist', label: '字典', minWidth: 160 },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  searchsploit_result: {
    title: 'searchsploit 搜索结果',
    columns: [
      { prop: 'edb_id', label: 'EDB-ID', width: 90, copyable: true },
      { prop: 'title', label: '标题', minWidth: 320, copyable: true, link: true, linkKey: 'url' },
      { prop: 'source', label: '类型', width: 90, render: (row) => ({ exploit: 'exploit', shellcode: 'shellcode', paper: 'paper' }[row.source] || row.source) },
      { prop: 'type', label: '分类', width: 100 },
      { prop: 'platform', label: '平台', width: 110 },
      { prop: 'codes', label: 'CVE/编码', minWidth: 160 },
      { prop: 'date', label: '发布日期', width: 110 },
      { prop: 'author', label: '作者', minWidth: 140 },
      {
        prop: 'verified', label: '已验证', width: 80,
        render: (row) => row.verified ? '是' : '否',
      },
      { prop: 'path', label: '本地路径', minWidth: 240 },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  hashcat_result: {
    title: 'hashcat 破解结果',
    columns: [
      {
        prop: 'cracked', label: '破解', width: 80,
        render: (row) => row.cracked ? '是' : '否',
      },
      { prop: 'hash', label: '哈希', minWidth: 320, copyable: true },
      { prop: 'plain', label: '明文', minWidth: 180, copyable: true },
      { prop: 'save_date', label: '发现时间', width: 160 },
    ],
  },
  task_schedule: {
    title: '计划任务',
    columns: [
      { prop: 'name', label: '任务名', minWidth: 160 },
      { prop: 'target', label: '目标', minWidth: 200 },
      { prop: 'schedule_type', label: '类型', width: 120, render: (row) => row.schedule_type === 'recurrent_scan' ? '周期' : '定时' },
      { prop: 'cron', label: 'Cron', width: 150 },
      { prop: 'next_run_date', label: '下次运行', width: 170 },
      { prop: 'status', label: '状态', width: 100 },
      { prop: 'run_number', label: '运行次数', width: 90 },
    ],
  },
}

// 工具函数
export function fingerText(finger) {
  if (!Array.isArray(finger)) return ''
  return finger.map((f) => f.name).join(', ')
}
export function portText(ports) {
  if (!Array.isArray(ports)) return ''
  return ports.map((p) => `${p.port_id}/${p.service_name || 'tcp'}`).join(' ')
}
export function serviceText(infos) {
  if (!Array.isArray(infos)) return ''
  return infos.map((i) => `${i.ip}:${i.port_id}(${i.product || ''})`).join(' ')
}
export function statusText(s) {
  return { waiting: '等待', done: '完成', error: '错误', stop: '停止', scheduled: '已计划', running: '运行中' }[s] || s
}
export function severityTag(s) {
  const map = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' }
  return map[s] || s
}
export function tagHtml(tags) {
  if (!Array.isArray(tags)) return ''
  return tags.join('/')
}
