<template>
  <div class="page-container">
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item>
          <el-button type="success" :icon="Plus" @click="addVisible = true">新建监控任务</el-button>
          <el-button type="success" :icon="Plus" @click="siteMonitorVisible = true">站点更新监控</el-button>
          <el-button type="success" :icon="Plus" @click="wihMonitorVisible = true">WIH 更新监控</el-button>
          <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除</el-button>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="监控名" prop="name" min-width="140" />
        <el-table-column label="监控目标" prop="domain" min-width="180" />
        <el-table-column label="范围类型" prop="scope_type" width="130">
          <template #default="{ row }">{{ scopeTypeText(row.scope_type) }}</template>
        </el-table-column>
        <el-table-column label="监控间隔(秒)" prop="interval" width="120" />
        <el-table-column label="运行次数" prop="run_number" width="90" />
        <el-table-column label="下次运行" prop="next_run_date" width="160" />
        <el-table-column label="上次运行" prop="last_run_date" width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'running' ? 'success' : 'info'" size="small">
              {{ row.status === 'running' ? '运行中' : '已停止' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'running'" link type="warning" @click="onStop(row)">停止</el-button>
            <el-button v-else link type="success" @click="onRecover(row)">恢复</el-button>
            <el-button link type="primary" @click="onEditOptions(row)">选项</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <!-- 新建监控任务 -->
    <el-dialog v-model="addVisible" title="新建资产监控任务" width="520px">
      <el-form :model="addForm" label-width="110px">
        <el-form-item label="资产组" required>
          <el-input v-model="addForm.scope_id" placeholder="资产组 ID（24位）" />
        </el-form-item>
        <el-form-item label="监控名">
          <el-input v-model="addForm.name" placeholder="监控任务名" />
        </el-form-item>
        <el-form-item label="范围类别">
          <el-radio-group v-model="addForm.scope_type">
            <el-radio value="domain">域名</el-radio>
            <el-radio value="ip">IP</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="监控间隔(秒)">
          <el-input-number v-model="addForm.interval" :min="3600" :step="3600" />
          <span style="color:#909399;margin-left:8px">最小 1 小时</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="onAdd">新建</el-button>
      </template>
    </el-dialog>

    <!-- 站点/WIH 监控 -->
    <el-dialog v-model="siteMonitorVisible" title="新建站点更新监控" width="460px">
      <el-form :model="siteForm" label-width="100px">
        <el-form-item label="资产组" required><el-input v-model="siteForm.scope_id" placeholder="资产组 ID" /></el-form-item>
        <el-form-item label="监控名"><el-input v-model="siteForm.name" /></el-form-item>
        <el-form-item label="间隔(秒)"><el-input-number v-model="siteForm.interval" :min="3600" :step="3600" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="siteMonitorVisible = false">取消</el-button>
        <el-button type="primary" @click="onAddSite">新建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="wihMonitorVisible" title="新建 WIH 更新监控" width="460px">
      <el-form :model="wihForm" label-width="100px">
        <el-form-item label="资产组" required><el-input v-model="wihForm.scope_id" placeholder="资产组 ID" /></el-form-item>
        <el-form-item label="监控名"><el-input v-model="wihForm.name" /></el-form-item>
        <el-form-item label="间隔(秒)"><el-input-number v-model="wihForm.interval" :min="3600" :step="3600" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wihMonitorVisible = false">取消</el-button>
        <el-button type="primary" @click="onAddWih">新建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus, Delete, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { schedulerApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const query = reactive({ page: 1, size: 20 })

const addVisible = ref(false); const addLoading = ref(false)
const addForm = reactive({ scope_id: '', name: '', interval: 21600, scope_type: 'domain' })
const siteMonitorVisible = ref(false); const siteForm = reactive({ scope_id: '', name: '', interval: 21600 })
const wihMonitorVisible = ref(false); const wihForm = reactive({ scope_id: '', name: '', interval: 21600 })

async function loadData() {
  loading.value = true
  try {
    const res = await schedulerApi.list({ page: query.page, size: query.size })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}
function onSelectionChange(s) { selection.value = s }
function scopeTypeText(t) {
  return { domain: '域名监控', ip: 'IP监控', site_update_monitor: '站点更新', wih_update_monitor: 'WIH更新' }[t] || t
}

async function onAdd() {
  if (!addForm.scope_id) return ElMessage.warning('请输入资产组 ID')
  addLoading.value = true
  try {
    await schedulerApi.add({ ...addForm })
    ElMessage.success('已创建监控任务')
    addVisible.value = false
    loadData()
  } catch (e) {} finally { addLoading.value = false }
}
async function onAddSite() {
  await schedulerApi.addSiteMonitor({ ...siteForm })
  ElMessage.success('已创建站点更新监控')
  siteMonitorVisible.value = false
  loadData()
}
async function onAddWih() {
  await schedulerApi.addWihMonitor({ ...wihForm })
  ElMessage.success('已创建 WIH 更新监控')
  wihMonitorVisible.value = false
  loadData()
}
async function onStop(row) {
  await schedulerApi.stop({ job_id: row._id })
  ElMessage.success('已停止')
  loadData()
}
async function onRecover(row) {
  await schedulerApi.recover({ job_id: row._id })
  ElMessage.success('已恢复')
  loadData()
}
async function onDelete() {
  const items = selection.value.map((s) => ({ job_id: s._id }))
  await ElMessageBox.confirm(`确定删除 ${items.length} 个监控任务？`, '提示', { type: 'warning' })
  await schedulerApi.delete(items)
  ElMessage.success('删除成功')
  loadData()
}
function onEditOptions(row) {
  ElMessageBox.alert(`监控选项：${JSON.stringify(row.monitor_options || {}, null, 2)}`, '监控选项', { type: 'info' })
}

onMounted(loadData)
</script>
