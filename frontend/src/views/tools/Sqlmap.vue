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
        <div class="stat-title">发现注入</div>
        <div class="stat-value" style="color: #f56c6c">{{ stat.injected }}</div>
      </div>
    </div>

    <!-- 过滤栏 -->
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item label="任务名">
          <el-input v-model="query.name" placeholder="任务名" clearable style="width: 160px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable style="width: 120px">
            <el-option label="等待" value="waiting" />
            <el-option label="运行中" value="running" />
            <el-option label="完成" value="done" />
            <el-option label="错误" value="error" />
            <el-option label="停止" value="stop" />
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
        <el-button type="primary" :icon="Plus" @click="addVisible = true">新建扫描</el-button>
        <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除任务</el-button>
        <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
      </div>

      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="任务名" prop="name" min-width="140" show-overflow-tooltip />
        <el-table-column label="目标数" width="80">
          <template #default="{ row }">{{ (row.targets || []).length }}</template>
        </el-table-column>
        <el-table-column label="目标" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">{{ (row.targets || []).slice(0, 2).join(', ') }}{{ (row.targets || []).length > 2 ? '...' : '' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果数" prop="result_count" width="90" />
        <el-table-column label="创建时间" prop="save_date" width="170" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/sqlmap_result?task_id=${row._id}`)">结果</el-button>
            <el-button link type="primary" :disabled="!canStop(row.status)" @click="onStop(row)">停止</el-button>
            <el-button link type="warning" @click="onViewOptions(row)">参数</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <SqlmapDialog v-model="addVisible" @created="loadData" />

    <el-dialog v-model="optionsVisible" title="任务参数" width="560px">
      <el-descriptions :column="1" border>
        <el-descriptions-item v-for="(v, k) in optionsDetail" :key="k" :label="String(k)">
          {{ String(v) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Search, Refresh, Plus, Delete, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sqlmapApi } from '@/api'
import SqlmapDialog from './SqlmapDialog.vue'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const addVisible = ref(false)
const query = reactive({ page: 1, size: 20, name: '', status: '' })

const optionsVisible = ref(false)
const optionsDetail = ref({})

const stat = computed(() => {
  const s = { running: 0, done: 0, injected: 0 }
  list.value.forEach((t) => {
    if (['waiting', 'running'].includes(t.status)) s.running++
    else if (t.status === 'done') s.done++
    s.injected += t.result_count || 0
  })
  return s
})

async function loadData() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.name) params.name = query.name
    if (query.status) params.status = query.status
    const res = await sqlmapApi.listTask(params)
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}

function onSearch() { query.page = 1; loadData() }
function onReset() { Object.assign(query, { page: 1, name: '', status: '' }); loadData() }
function onSelectionChange(s) { selection.value = s }

function statusType(s) {
  return { waiting: 'warning', running: 'primary', done: 'success', error: 'danger', stop: 'info' }[s] || 'info'
}
function statusText(s) {
  return { waiting: '等待', running: '运行中', done: '完成', error: '错误', stop: '停止' }[s] || s || '-'
}
function canStop(s) { return ['waiting', 'running'].includes(s) }

async function onStop(row) {
  await ElMessageBox.confirm(`确定停止扫描任务 ${row.name}？`, '提示', { type: 'warning' })
  await sqlmapApi.stopTask(row._id)
  ElMessage.success('已发送停止指令')
  loadData()
}

async function onDelete() {
  const ids = selection.value.map((t) => t._id)
  await ElMessageBox.confirm(`确定删除 ${ids.length} 个任务及其结果？此操作不可逆`, '危险操作', { type: 'error' })
  await sqlmapApi.deleteTask(ids)
  ElMessage.success('删除成功')
  loadData()
}

function onViewOptions(row) {
  optionsDetail.value = row.options || {}
  optionsVisible.value = true
}

onMounted(loadData)
</script>
