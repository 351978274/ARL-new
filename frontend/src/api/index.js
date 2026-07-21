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
