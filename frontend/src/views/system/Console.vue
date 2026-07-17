<template>
  <div class="page-container">
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span style="font-weight:600">系统信息</span></template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="系统版本">ARL {{ info.version }}</el-descriptions-item>
            <el-descriptions-item label="Python">{{ info.python }}</el-descriptions-item>
            <el-descriptions-item label="MongoDB 库">{{ info.mongo_db }}</el-descriptions-item>
            <el-descriptions-item label="认证状态">
              <el-tag :type="info.auth ? 'success' : 'warning'" size="small">{{ info.auth ? '已开启' : '未开启' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="健康检查">
              <el-tag :type="info.status === 'ok' ? 'success' : 'danger'" size="small">{{ info.status || '-' }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span style="font-weight:600">CPU 使用率</span></template>
          <div style="text-align:center;padding:20px">
            <el-progress type="dashboard" :percentage="cpuPercent" :color="cpuColor" />
            <div style="margin-top:12px;color:#909399">{{ info.data?.cpu_percent || 0 }}%</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span style="font-weight:600">内存使用</span></template>
          <div style="text-align:center;padding:20px">
            <el-progress type="dashboard" :percentage="memPercent" :color="memColor" />
            <div style="margin-top:12px;color:#909399">
              {{ usedMem }} / {{ totalMem }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top:16px">
      <template #header><span style="font-weight:600">数据统计</span></template>
      <div class="stat-cards" style="margin-bottom:0">
        <div class="stat-card" v-for="item in stats" :key="item.label">
          <div class="stat-title">{{ item.label }}</div>
          <div class="stat-value" :style="{color: item.color}">{{ item.value }}</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { consoleApi, healthApi, fetchList } from '@/api'

const info = ref({})
const stats = ref([])

const cpuPercent = computed(() => Math.round(info.value.data?.cpu_percent || 0))
const cpuColor = computed(() => (cpuPercent.value > 80 ? '#f56c6c' : cpuPercent.value > 60 ? '#e6a23c' : '#67c23a'))
const memPercent = computed(() => {
  const m = info.value.data?.memory
  if (!m) return 0
  return Math.round(((m.total - m.available) / m.total) * 100)
})
const memColor = computed(() => (memPercent.value > 80 ? '#f56c6c' : memPercent.value > 60 ? '#e6a23c' : '#67c23a'))
function fmt(bytes) {
  if (!bytes) return '0'
  const gb = bytes / 1024 / 1024 / 1024
  return `${gb.toFixed(1)} GB`
}
const usedMem = computed(() => {
  const m = info.value.data?.memory
  return m ? fmt(m.total - m.available) : '-'
})
const totalMem = computed(() => fmt(info.value.data?.memory?.total))

async function loadInfo() {
  try {
    const [consoleRes, healthRes] = await Promise.all([consoleApi.info(), healthApi.check()])
    info.value = { ...consoleRes.data, ...healthRes }
  } catch (e) {}
}

async function loadStats() {
  // 统计各集合数量
  const cols = [
    { label: '任务', collection: 'task', color: '#409eff' },
    { label: '域名', collection: 'domain', color: '#67c23a' },
    { label: '站点', collection: 'site', color: '#e6a23c' },
    { label: 'IP', collection: 'ip', color: '#f56c6c' },
    { label: '漏洞', collection: 'vuln', color: '#909399' },
    { label: '资产组', collection: 'asset_scope', color: '#9c27b0' },
  ]
  const results = await Promise.all(
    cols.map((c) => fetchList(c.collection, { page: 1, size: 1 }).catch(() => ({ total: 0 })))
  )
  stats.value = cols.map((c, i) => ({ ...c, value: results[i].total || 0 }))
}

onMounted(() => { loadInfo(); loadStats() })
</script>
