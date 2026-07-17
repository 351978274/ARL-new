import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import router from '@/router'

const service = axios.create({
  baseURL: '/',
  timeout: 60000,
})

// 请求拦截：带上 Token
service.interceptors.request.use((config) => {
  const userStore = useUserStore()
  if (userStore.token) {
    config.headers['Token'] = userStore.token
  }
  // GET 参数：分页等
  return config
})

// 响应拦截：统一处理错误码
service.interceptors.response.use(
  (response) => {
    const res = response.data
    // 文件下载（二进制）
    if (response.config.responseType === 'blob') {
      return response
    }
    // 后端统一返回 {code, message, data}
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 200) {
        return res
      }
      // 401 未登录
      if (res.code === 401) {
        handleUnauthorized()
        return Promise.reject(new Error(res.message || '未登录'))
      }
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    // 分页结构 {page,size,total,items,code}
    if (res && res.code === 200) {
      return res
    }
    return res
  },
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      handleUnauthorized()
    } else {
      ElMessage.error(error.response?.data?.detail || error.message || '网络错误')
    }
    return Promise.reject(error)
  }
)

function handleUnauthorized() {
  const userStore = useUserStore()
  userStore.logout()
  ElMessage.warning('登录已过期，请重新登录')
  router.push('/login')
}

export default service
