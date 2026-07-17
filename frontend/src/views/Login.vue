<template>
  <div class="login-bg">
    <div class="login-card">
      <div class="login-logo">
        <el-icon :size="32" style="vertical-align: middle"><LighthouseSvg /></el-icon>
        资产灯塔
        <span class="logo-sub">资产侦察灯塔系统</span>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="onLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large"
                    :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="onLogin">
          登 录
        </el-button>
      </el-form>
      <div style="text-align: center; color: #909399; font-size: 12px; margin-top: 20px">
        默认账号 admin / arlpass
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api'
import { useUserStore } from '@/stores/user'

// 用一个内置 SVG 作为灯塔图标（ElementPlus 无此图标）
const LighthouseSvg = {
  template: `<svg viewBox="0 0 1024 1024" width="1em" height="1em" fill="currentColor">
    <path d="M464 96h96l32 160h-160zM320 416l64-160h256l64 160zm-32 160h448l32 352h-512zM192 928h640v32H192z"/>
  </svg>`,
}

const router = useRouter()
const userStore = useUserStore()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onLogin() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await userApi.login(form)
    if (res.code === 200 && res.data?.token) {
      userStore.setLogin(res.data)
      ElMessage.success('登录成功')
      router.push('/')
    } else {
      ElMessage.error(res.message || '登录失败')
    }
  } catch (e) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}
</script>
