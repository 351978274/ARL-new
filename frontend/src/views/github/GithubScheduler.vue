<template>
  <div class="page-container">
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item>
          <el-button type="success" :icon="Plus" @click="addVisible = true">新建 Github 监控</el-button>
          <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除</el-button>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="监控名" prop="name" min-width="140" />
        <el-table-column label="关键字" prop="keyword" min-width="180" />
        <el-table-column label="Cron 表达式" prop="cron" width="140" />
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
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'running'" link type="warning" @click="onStop(row)">停止</el-button>
            <el-button v-else link type="success" @click="onRecover(row)">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <el-dialog v-model="addVisible" title="新建 Github 监控" width="480px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="监控名" required><el-input v-model="addForm.name" /></el-form-item>
        <el-form-item label="关键字" required><el-input v-model="addForm.keyword" placeholder="如 公司域名、内部邮箱后缀" /></el-form-item>
        <el-form-item label="Cron 表达式" required>
          <el-input v-model="addForm.cron" placeholder="如 0 2 * * *（每天凌晨2点）" />
          <span style="color:#909399;font-size:12px">五段式：分 时 日 月 周</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="onAdd">新建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus, Delete, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { githubSchedulerApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const query = reactive({ page: 1, size: 20 })
const addVisible = ref(false); const addLoading = ref(false)
const addForm = reactive({ name: '', keyword: '', cron: '0 2 * * *' })

async function loadData() {
  loading.value = true
  try {
    const res = await githubSchedulerApi.list({ page: query.page, size: query.size })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}
function onSelectionChange(s) { selection.value = s }

async function onAdd() {
  if (!addForm.name || !addForm.keyword || !addForm.cron) return ElMessage.warning('请填写完整')
  addLoading.value = true
  try {
    await githubSchedulerApi.add({ ...addForm })
    ElMessage.success('已创建 Github 监控')
    addVisible.value = false
    addForm.name = ''; addForm.keyword = ''
    loadData()
  } catch (e) {} finally { addLoading.value = false }
}
async function onStop(row) {
  await githubSchedulerApi.stop([{ github_scheduler_id: row._id }])
  ElMessage.success('已停止')
  loadData()
}
async function onRecover(row) {
  await githubSchedulerApi.recover([{ github_scheduler_id: row._id }])
  ElMessage.success('已恢复')
  loadData()
}
async function onDelete() {
  const items = selection.value.map((s) => ({ github_scheduler_id: s._id }))
  await ElMessageBox.confirm(`确定删除 ${items.length} 个 Github 监控及结果？`, '危险操作', { type: 'error' })
  await githubSchedulerApi.delete(items)
  ElMessage.success('删除成功')
  loadData()
}

onMounted(loadData)
</script>
