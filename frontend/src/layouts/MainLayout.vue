<template>
  <el-container style="height: 100vh">
    <!-- 侧边导航 -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="layout-aside">
      <div class="logo-bar">
        <el-icon class="logo-icon"><LighthouseSvg /></el-icon>
        <span v-show="!collapsed">资产灯塔</span>
      </div>
      <el-scrollbar style="height: calc(100vh - 60px)">
        <el-menu :default-active="$route.path" :collapse="collapsed" router
                 background-color="#304156" text-color="#bfcbd9" active-text-color="#fff">
          <!-- 任务与资产 -->
          <el-sub-menu index="task-group">
            <template #title>
              <el-icon><List /></el-icon><span>任务</span>
            </template>
            <el-menu-item index="/task">任务</el-menu-item>
            <el-menu-item index="/task_schedule">计划任务</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="asset-group">
            <template #title>
              <el-icon><Files /></el-icon><span>资产</span>
            </template>
            <el-menu-item index="/domain">子域名</el-menu-item>
            <el-menu-item index="/site">站点</el-menu-item>
            <el-menu-item index="/ip">IP</el-menu-item>
            <el-menu-item index="/url">URL</el-menu-item>
            <el-menu-item index="/cip">C段</el-menu-item>
            <el-menu-item index="/cert">证书</el-menu-item>
            <el-menu-item index="/service">系统服务</el-menu-item>
            <el-menu-item index="/vuln">漏洞</el-menu-item>
            <el-menu-item index="/fileleak">文件泄露</el-menu-item>
            <el-menu-item index="/poc">PoC</el-menu-item>
            <el-menu-item index="/stat_finger">指纹统计</el-menu-item>
            <el-menu-item index="/nuclei_result">nuclei 扫描</el-menu-item>
            <el-menu-item index="/wih">WIH</el-menu-item>
          </el-sub-menu>

          <!-- 资产组 -->
          <el-sub-menu index="scope-group">
            <template #title>
              <el-icon><FolderOpened /></el-icon><span>资产组</span>
            </template>
            <el-menu-item index="/asset_scope">资产组</el-menu-item>
            <el-menu-item index="/scheduler">资产监控</el-menu-item>
            <el-menu-item index="/asset_domain">资产组域名</el-menu-item>
            <el-menu-item index="/asset_ip">资产组IP</el-menu-item>
            <el-menu-item index="/asset_site">资产/站点</el-menu-item>
            <el-menu-item index="/asset_wih">资产/WIH</el-menu-item>
          </el-sub-menu>

          <!-- Github -->
          <el-sub-menu index="github-group">
            <template #title>
              <el-icon><Promotion /></el-icon><span>Github</span>
            </template>
            <el-menu-item index="/github_scheduler">Github 监控</el-menu-item>
            <el-menu-item index="/github_task">Github 任务</el-menu-item>
            <el-menu-item index="/github_result">Github 结果</el-menu-item>
            <el-menu-item index="/github_monitor_result">Github 监控结果</el-menu-item>
          </el-sub-menu>

          <!-- 工具 -->
          <el-sub-menu index="tools-group">
            <template #title>
              <el-icon><Tools /></el-icon><span>工具</span>
            </template>
            <el-menu-item index="/dirsearch">dirsearch 扫描</el-menu-item>
            <el-menu-item index="/dirsearch_result">dirsearch 结果</el-menu-item>
            <el-menu-item index="/hydra">hydra 爆破</el-menu-item>
            <el-menu-item index="/hydra_result">hydra 结果</el-menu-item>
            <el-menu-item index="/sqlmap">sqlmap 扫描</el-menu-item>
            <el-menu-item index="/sqlmap_result">sqlmap 结果</el-menu-item>
            <el-menu-item index="/aircrack">aircrack-ng 破解</el-menu-item>
            <el-menu-item index="/aircrack_result">aircrack 结果</el-menu-item>
            <el-menu-item index="/searchsploit">searchsploit 搜索</el-menu-item>
            <el-menu-item index="/searchsploit_result">searchsploit 结果</el-menu-item>
          </el-sub-menu>

          <!-- 系统 -->
          <el-sub-menu index="system-group">
            <template #title>
              <el-icon><Setting /></el-icon><span>系统</span>
            </template>
            <el-menu-item index="/policy">策略管理</el-menu-item>
            <el-menu-item index="/fingerprint">指纹</el-menu-item>
            <el-menu-item index="/console">控制台</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="layout-header">
        <div style="display: flex; align-items: center; gap: 12px">
          <el-icon style="cursor: pointer; font-size: 20px" @click="collapsed = !collapsed">
            <Fold v-if="!collapsed" /><Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>资产灯塔</el-breadcrumb-item>
            <el-breadcrumb-item>{{ $route.meta.title || '页面' }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <el-dropdown>
          <span style="cursor: pointer; display: flex; align-items: center; gap: 6px">
            <el-icon><UserFilled /></el-icon>{{ userStore.username }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="changePassVisible = true">修改密码</el-dropdown-item>
              <el-dropdown-item divided @click="onLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <!-- 主内容 -->
      <el-main style="background: #f0f2f5; padding: 0; overflow: auto">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['GenericList']">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="changePassVisible" title="修改密码" width="420px">
      <el-form ref="passFormRef" :model="passForm" :rules="passRules" label-width="90px">
        <el-form-item label="旧密码" prop="old_password">
          <el-input v-model="passForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passForm.new_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="changePassVisible = false">取消</el-button>
        <el-button type="primary" :loading="passLoading" @click="onChangePass">确定</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '@/api'
import { useUserStore } from '@/stores/user'

const LighthouseSvg = {
  template: `<svg viewBox="0 0 1024 1024" width="1em" height="1em" fill="currentColor">
    <path d="M464 96h96l32 160h-160zM320 416l64-160h256l64 160zm-32 160h448l32 352h-512zM192 928h640v32H192z"/></svg>`,
}
const router = useRouter()
const userStore = useUserStore()
const collapsed = ref(false)

const changePassVisible = ref(false)
const passLoading = ref(false)
const passFormRef = ref()
const passForm = reactive({ old_password: '', new_password: '' })
const passRules = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [{ required: true, message: '请输入新密码', trigger: 'blur' }],
}

async function onChangePass() {
  await passFormRef.value.validate()
  passLoading.value = true
  try {
    const res = await userApi.changePass(passForm)
    if (res.code === 200) {
      ElMessage.success('密码修改成功')
      changePassVisible.value = false
      passForm.old_password = ''
      passForm.new_password = ''
    }
  } catch (e) { /* 拦截器已提示 */ } finally {
    passLoading.value = false
  }
}

async function onLogout() {
  await ElMessageBox.confirm('确定退出登录？', '提示', { type: 'warning' })
  try { await userApi.logout() } catch (e) {}
  userStore.logout()
  router.push('/login')
}
</script>
