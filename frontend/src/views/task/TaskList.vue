<template>
  <div class="page-container">
    <!-- 指标卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-title">任务总数</div>
        <div class="stat-value">{{ total }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">进行中</div>
        <div class="stat-value" style="color: #409eff">{{ stat.running }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">已完成</div>
        <div class="stat-value" style="color: #67c23a">{{ stat.done }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-title">失败/停止</div>
        <div class="stat-value" style="color: #f56c6c">{{ stat.error }}</div>
      </div>
    </div>

    <!-- 过滤栏 -->
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item label="任务名">
          <el-input v-model="query.name" placeholder="任务名" clearable style="width: 160px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="目标">
          <el-input v-model="query.target" placeholder="目标" clearable style="width: 180px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable style="width: 120px">
            <el-option label="等待" value="waiting" />
            <el-option label="进行中" value="running" />
            <el-option label="完成" value="done" />
            <el-option label="错误" value="error" />
            <el-option label="停止" value="stop" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务标签">
          <el-select v-model="query.task_tag" placeholder="全部" clearable style="width: 120px">
            <el-option label="资产发现" value="task" />
            <el-option label="监控" value="monitor" />
            <el-option label="风险巡航" value="risk_cruising" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button :icon="Refresh" @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 操作栏 + 表格 -->
    <el-card shadow="never">
      <div class="table-toolbar">
        <el-button type="primary" :icon="Plus" @click="addVisible = true">新建任务</el-button>
        <el-button :icon="VideoPause" :disabled="!selection.length" @click="onBatchStop">批量停止</el-button>
        <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除任务</el-button>
        <el-button :icon="Download" :disabled="!selection.length" @click="onBatchExport">批量导出</el-button>
        <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
      </div>

      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="任务名" prop="name" min-width="140" show-overflow-tooltip />
        <el-table-column label="目标" prop="target" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务标签" prop="task_tag" width="100">
          <template #default="{ row }">{{ taskTagText(row.task_tag) }}</template>
        </el-table-column>
        <el-table-column label="进度" width="140">
          <template #default="{ row }">
            <span v-if="row.status === 'waiting'" class="status-waiting">等待中</span>
            <span v-else-if="['done','error','stop'].includes(row.status)">{{ row.status }}</span>
            <span v-else class="status-running">{{ row.status }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" prop="start_time" width="160" />
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ elapsedText(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/site?task_id=${row._id}`)">结果</el-button>
            <el-button link type="primary" :disabled="!canStop(row.status)" @click="onStop(row)">停止</el-button>
            <el-button link type="primary" :disabled="!canRestart(row)" @click="onRestart(row)">重启</el-button>
            <el-button link type="warning" :disabled="row.type !== 'domain' || row.status !== 'done'"
                       @click="onSync(row)">同步</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <!-- 新建任务弹窗 -->
    <AddTaskDialog v-model="addVisible" @created="loadData" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { Search, Refresh, Plus, Delete, Download, RefreshRight, VideoPause } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { taskApi, batchExport } from '@/api'
import AddTaskDialog from './AddTaskDialog.vue'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const addVisible = ref(false)
const query = reactive({ page: 1, size: 20, name: '', target: '', status: '', task_tag: '' })

const stat = computed(() => {
  const s = { running: 0, done: 0, error: 0 }
  list.value.forEach((t) => {
    if (['waiting', 'running'].includes(t.status) || (t.status && !['done', 'error', 'stop'].includes(t.status))) s.running++
    else if (t.status === 'done') s.done++
    else if (['error', 'stop'].includes(t.status)) s.error++
  })
  return s
})

async function loadData() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.name) params.name = query.name
    if (query.target) params.target = query.target
    if (query.status) params.status = query.status
    if (query.task_tag) params.task_tag = query.task_tag
    const res = await taskApi.list(params)
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}

function onSearch() { query.page = 1; loadData() }
function onReset() { Object.assign(query, { page: 1, name: '', target: '', status: '', task_tag: '' }); loadData() }
function onSelectionChange(s) { selection.value = s }

function statusType(s) {
  return { waiting: 'warning', done: 'success', error: 'danger', stop: 'info' }[s] || 'primary'
}
function statusText(s) {
  return { waiting: '等待', done: '完成', error: '错误', stop: '停止' }[s] || (s || '运行中')
}
function taskTagText(t) {
  return { task: '资产发现', monitor: '监控', risk_cruising: '风险巡航' }[t] || t
}
function elapsedText(row) {
  if (!row.service) return '-'
  // service 字段存的是各阶段耗时列表，这里简单显示阶段数
  return row.service.length ? `${row.service.length}阶段` : '-'
}
function canStop(s) { return !['done', 'error', 'stop'].includes(s) }
function canRestart(row) { return ['done', 'error', 'stop'].includes(row.status) && row.task_tag !== 'monitor' }

async function onStop(row) {
  await ElMessageBox.confirm(`确定停止任务 ${row.name}？`, '提示', { type: 'warning' })
  await taskApi.stop(row._id)
  ElMessage.success('已发送停止指令')
  loadData()
}
async function onBatchStop() {
  const ids = selection.value.map((t) => t._id)
  await ElMessageBox.confirm(`确定批量停止 ${ids.length} 个任务？`, '提示', { type: 'warning' })
  await taskApi.batchStop(ids)
  ElMessage.success('已发送停止指令')
  loadData()
}
async function onDelete() {
  const items = selection.value.map((t) => ({ task_id: t._id, del_task_data: true }))
  await ElMessageBox.confirm(`确定删除 ${items.length} 个任务及其数据？此操作不可逆`, '危险操作', { type: 'error' })
  await taskApi.delete(items)
  ElMessage.success('删除成功')
  loadData()
}
async function onRestart(row) {
  await ElMessageBox.confirm(`确定重新运行任务 ${row.name}？`, '提示', { type: 'warning' })
  await taskApi.restart({ task_id: row._id })
  ElMessage.success('已下发重启')
  loadData()
}
async function onSync(row) {
  const { value: scope_id } = await ElMessageBox.prompt('请输入要同步到的资产组 ID', '任务同步', {
    inputPattern: /^[0-9a-fA-F]{24}$/, inputErrorMessage: '请输入 24 位资产组 ID',
  })
  await taskApi.sync({ task_id: row._id, scope_id })
  ElMessage.success('已下发同步任务')
}
async function onBatchExport() {
  const ids = selection.value.map((t) => t._id)
  const res = await batchExport('site', ids)
  downloadBlob(res)
}

function downloadBlob(resp) {
  const blob = new Blob([resp.data], { type: resp.headers['content-type'] })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = decodeURIComponent(resp.headers['content-disposition']?.split('filename=')[1] || 'export.txt')
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadData)
</script>
