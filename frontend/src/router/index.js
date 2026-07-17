import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/task',
    children: [
      // 任务与资产
      { path: 'task', name: 'Task', component: () => import('@/views/task/TaskList.vue'), meta: { title: '任务' } },
      { path: 'domain', name: 'Domain', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '子域名', collection: 'domain' } },
      { path: 'site', name: 'Site', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '站点', collection: 'site' } },
      { path: 'ip', name: 'Ip', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'IP', collection: 'ip' } },
      { path: 'url', name: 'Url', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'URL', collection: 'url' } },
      { path: 'cip', name: 'Cip', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'C段', collection: 'cip' } },
      { path: 'cert', name: 'Cert', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '证书', collection: 'cert' } },
      { path: 'service', name: 'Service', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '系统服务', collection: 'service' } },
      { path: 'vuln', name: 'Vuln', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '漏洞', collection: 'vuln' } },
      { path: 'fileleak', name: 'Fileleak', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '文件泄露', collection: 'fileleak' } },
      { path: 'poc', name: 'Poc', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'PoC', collection: 'poc' } },
      { path: 'stat_finger', name: 'StatFinger', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '指纹统计', collection: 'stat_finger' } },
      { path: 'nuclei_result', name: 'Nuclei', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'nuclei 扫描', collection: 'nuclei_result' } },
      { path: 'wih', name: 'Wih', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'WIH', collection: 'wih' } },
      { path: 'task_schedule', name: 'TaskSchedule', component: () => import('@/views/task/TaskSchedule.vue'), meta: { title: '计划任务' } },

      // 资产组
      { path: 'asset_scope', name: 'AssetScope', component: () => import('@/views/scope/ScopeList.vue'), meta: { title: '资产组' } },
      { path: 'scheduler', name: 'Scheduler', component: () => import('@/views/scope/SchedulerList.vue'), meta: { title: '资产监控' } },
      { path: 'asset_domain', name: 'AssetDomain', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '资产组域名', collection: 'asset_domain' } },
      { path: 'asset_ip', name: 'AssetIp', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '资产组IP', collection: 'asset_ip' } },
      { path: 'asset_site', name: 'AssetSite', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '资产/站点', collection: 'asset_site' } },
      { path: 'asset_wih', name: 'AssetWih', component: () => import('@/views/asset/GenericList.vue'), meta: { title: '资产/WIH', collection: 'asset_wih' } },

      // Github
      { path: 'github_scheduler', name: 'GithubScheduler', component: () => import('@/views/github/GithubScheduler.vue'), meta: { title: 'Github 监控' } },
      { path: 'github_task', name: 'GithubTask', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'Github 任务', collection: 'github_task' } },
      { path: 'github_result', name: 'GithubResult', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'Github 结果', collection: 'github_result' } },
      { path: 'github_monitor_result', name: 'GithubMonitorResult', component: () => import('@/views/asset/GenericList.vue'), meta: { title: 'Github 监控结果', collection: 'github_monitor_result' } },

      // 系统配置
      { path: 'policy', name: 'Policy', component: () => import('@/views/system/Policy.vue'), meta: { title: '策略管理' } },
      { path: 'fingerprint', name: 'Fingerprint', component: () => import('@/views/system/Fingerprint.vue'), meta: { title: '指纹' } },
      { path: 'console', name: 'Console', component: () => import('@/views/system/Console.vue'), meta: { title: '控制台' } },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫：未登录跳转
router.beforeEach((to) => {
  const userStore = useUserStore()
  if (!to.meta.public && !userStore.token) {
    return '/login'
  }
})

export default router
