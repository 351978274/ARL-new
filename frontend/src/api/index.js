import request from '@/utils/request'

// ============ 通用：资产集合分页查询 + 导出 ============
// collection: domain/site/ip/url/cert/service/fileleak/vuln/poc/cip/stat_finger/npoc_service/nuclei_result/wih
//             asset_domain/asset_ip/asset_site/asset_wih/github_task/github_result/github_monitor_result/task_schedule
export function fetchList(collection, params) {
  return request.get(`/api/${collection}/`, { params })
}
export function exportList(collection, params) {
  return request.get(`/api/export/${collection}/`, { params, responseType: 'blob' })
}
export function batchExport(type, task_id_list) {
  return request.post(`/api/batch_export/${type}/`, { task_id_list }, { responseType: 'blob' })
}

// ============ 用户认证 ============
export const userApi = {
  login: (data) => request.post('/api/user/login', data),
  logout: () => request.post('/api/user/logout'),
  changePass: (data) => request.post('/api/user/change_pass', data),
}

// ============ 任务 ============
export const taskApi = {
  list: (params) => request.get('/api/task/', { params }),
  add: (data) => request.post('/api/task/', data),
  batchStop: (task_ids) => request.post('/api/task/batch_stop/', task_ids),
  stop: (task_id) => request.get(`/api/task/stop/${task_id}`),
  delete: (items) => request.post('/api/task/delete/', items),
  sync: (data) => request.post('/api/task/sync/', data),
  addByPolicy: (data) => request.post('/api/task/policy/', data),
  restart: (data) => request.post('/api/task/restart/', data),
}

// ============ 资产组（scope） ============
export const scopeApi = {
  list: (params) => request.get('/api/asset_scope/', { params }),
  add: (data) => request.post('/api/asset_scope/', data),
  delete: (items) => request.post('/api/asset_scope/delete/', items),
}

// ============ 资产监控任务（scheduler） ============
export const schedulerApi = {
  list: (params) => request.get('/api/scheduler/', { params }),
  add: (data) => request.post('/api/scheduler/add/', data),
  addSiteMonitor: (data) => request.post('/api/scheduler/add_site_monitor/', data),
  addWihMonitor: (data) => request.post('/api/scheduler/add_wih_monitor/', data),
  stop: (data) => request.post('/api/scheduler/stop/', data),
  recover: (data) => request.post('/api/scheduler/recover/', data),
  delete: (items) => request.post('/api/scheduler/delete/', items),
}

// ============ Github 监控调度 ============
export const githubSchedulerApi = {
  list: (params) => request.get('/api/github_scheduler/', { params }),
  add: (data) => request.post('/api/github_scheduler/', data),
  stop: (items) => request.post('/api/github_scheduler/stop/', items),
  recover: (items) => request.post('/api/github_scheduler/recover/', items),
  delete: (items) => request.post('/api/github_scheduler/delete/', items),
}

// ============ 指纹 ============
export const fingerApi = {
  list: (params) => request.get('/api/fingerprint/', { params }),
  add: (data) => request.post('/api/fingerprint/', data),
  upload: (formData) =>
    request.post('/api/fingerprint/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  delete: (items) => request.post('/api/fingerprint/delete/', items),
}

// ============ 策略 ============
export const policyApi = {
  list: (params) => request.get('/api/policy/', { params }),
  add: (data) => request.post('/api/policy/', data),
  save: (data) => request.post('/api/policy/save/', data),
  delete: (items) => request.post('/api/policy/delete/', items),
}

// ============ FOFA 任务 ============
export const fofaApi = {
  add: (data) => request.post('/api/task_fofa/', data),
}

// ============ 控制台 ============
export const consoleApi = {
  info: () => request.get('/api/console/'),
}

// ============ 健康检查 ============
export const healthApi = {
  check: () => request.get('/api/health'),
}

// ============ dirsearch 目录爆破 ============
export const dirsearchApi = {
  // 任务
  listTask: (params) => request.get('/api/dirsearch/task/', { params }),
  addTask: (data) => request.post('/api/dirsearch/task/', data),
  stopTask: (task_id) => request.get(`/api/dirsearch/task/stop/${task_id}`),
  deleteTask: (task_ids) => request.post('/api/dirsearch/task/delete/', { task_ids }),
  // 结果
  listResult: (params) => request.get('/api/dirsearch/result/', { params }),
  exportResult: (params) => request.get('/api/dirsearch/result/export/', { params, responseType: 'blob' }),
  // 辅助
  paramMeta: () => request.get('/api/dirsearch/param_meta/'),
  siteList: (data) => request.post('/api/dirsearch/site_list/', data),
  uploadUrls: (formData) =>
    request.post('/api/dirsearch/upload_urls/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ============ hydra 网络登录爆破 ============
export const hydraApi = {
  // 任务
  listTask: (params) => request.get('/api/hydra/task/', { params }),
  addTask: (data) => request.post('/api/hydra/task/', data),
  stopTask: (task_id) => request.get(`/api/hydra/task/stop/${task_id}`),
  deleteTask: (task_ids) => request.post('/api/hydra/task/delete/', { task_ids }),
  // 结果
  listResult: (params) => request.get('/api/hydra/result/', { params }),
  exportResult: (params) => request.get('/api/hydra/result/export/', { params, responseType: 'blob' }),
  // 辅助
  paramMeta: () => request.get('/api/hydra/param_meta/'),
  services: () => request.get('/api/hydra/services/'),
  uploadTargets: (formData) =>
    request.post('/api/hydra/upload_targets/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ============ sqlmap SQL 注入检测 ============
export const sqlmapApi = {
  // 任务
  listTask: (params) => request.get('/api/sqlmap/task/', { params }),
  addTask: (data) => request.post('/api/sqlmap/task/', data),
  stopTask: (task_id) => request.get(`/api/sqlmap/task/stop/${task_id}`),
  deleteTask: (task_ids) => request.post('/api/sqlmap/task/delete/', { task_ids }),
  // 结果
  listResult: (params) => request.get('/api/sqlmap/result/', { params }),
  exportResult: (params) => request.get('/api/sqlmap/result/export/', { params, responseType: 'blob' }),
  // 辅助
  paramMeta: () => request.get('/api/sqlmap/param_meta/'),
  uploadUrls: (formData) =>
    request.post('/api/sqlmap/upload_urls/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ============ aircrack-ng 无线密钥破解 ============
export const aircrackApi = {
  // 任务
  listTask: (params) => request.get('/api/aircrack/task/', { params }),
  addTask: (data) => request.post('/api/aircrack/task/', data),
  stopTask: (task_id) => request.get(`/api/aircrack/task/stop/${task_id}`),
  deleteTask: (task_ids) => request.post('/api/aircrack/task/delete/', { task_ids }),
  // 结果
  listResult: (params) => request.get('/api/aircrack/result/', { params }),
  exportResult: (params) => request.get('/api/aircrack/result/export/', { params, responseType: 'blob' }),
  // 辅助
  paramMeta: () => request.get('/api/aircrack/param_meta/'),
  uploadCapture: (formData) =>
    request.post('/api/aircrack/upload_capture/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  listCaptures: (params) => request.get('/api/aircrack/captures/', { params }),
}

// ============ searchsploit Exploit-DB 搜索 ============
export const searchsploitApi = {
  // 任务
  listTask: (params) => request.get('/api/searchsploit/task/', { params }),
  addTask: (data) => request.post('/api/searchsploit/task/', data),
  stopTask: (task_id) => request.get(`/api/searchsploit/task/stop/${task_id}`),
  deleteTask: (task_ids) => request.post('/api/searchsploit/task/delete/', { task_ids }),
  // 结果
  listResult: (params) => request.get('/api/searchsploit/result/', { params }),
  exportResult: (params) => request.get('/api/searchsploit/result/export/', { params, responseType: 'blob' }),
  // 辅助
  paramMeta: () => request.get('/api/searchsploit/param_meta/'),
  uploadNmap: (formData) =>
    request.post('/api/searchsploit/upload_nmap/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ============ hashcat 密码哈希恢复 ============
export const hashcatApi = {
  // 任务
  listTask: (params) => request.get('/api/hashcat/task/', { params }),
  addTask: (data) => request.post('/api/hashcat/task/', data),
  stopTask: (task_id) => request.get(`/api/hashcat/task/stop/${task_id}`),
  deleteTask: (task_ids) => request.post('/api/hashcat/task/delete/', { task_ids }),
  // 结果
  listResult: (params) => request.get('/api/hashcat/result/', { params }),
  exportResult: (params) => request.get('/api/hashcat/result/export/', { params, responseType: 'blob' }),
  // 辅助
  paramMeta: () => request.get('/api/hashcat/param_meta/'),
  uploadHash: (formData) =>
    request.post('/api/hashcat/upload_hash/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  listHashes: (params) => request.get('/api/hashcat/hashes/', { params }),
}

// ============ 文件浏览（工具参数文件路径选择器） ============
export const fileApi = {
  // 列出目录内容
  listDir: (path) => request.get('/api/file/list/', { params: { path } }),
  // 可浏览根目录列表（项目根 + 系统盘符/根）
  roots: () => request.get('/api/file/roots/'),
}
