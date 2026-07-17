<template>
  <div class="page-container">
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span style="font-weight:600">计划任务</span>
        <span style="color:#909399;margin-left:12px;font-size:13px">
          周期任务（cron）与一次性定时任务，在控制台「策略」中创建后由调度器自动派发
        </span>
      </template>
      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column label="任务名" prop="name" min-width="160" />
        <el-table-column label="目标" prop="target" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.schedule_type === 'recurrent_scan' ? 'success' : 'warning'">
              {{ row.schedule_type === 'recurrent_scan' ? '周期扫描' : '定时扫描' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Cron / 执行时间" width="180">
          <template #default="{ row }">{{ row.cron || formatDate(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="下次运行" prop="next_run_date" width="160" />
        <el-table-column label="上次运行" prop="last_run_date" width="160" />
        <el-table-column label="运行次数" prop="run_number" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'
import { fetchList } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, size: 20 })

async function loadData() {
  loading.value = true
  try {
    const res = await fetchList('task_schedule', { page: query.page, size: query.size })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}
function statusType(s) {
  return { scheduled: 'primary', done: 'success', stop: 'info', error: 'danger' }[s] || ''
}
function statusText(s) {
  return { scheduled: '已计划', done: '已完成', stop: '已停止', error: '错误' }[s] || s
}
function formatDate(t) {
  if (!t) return '-'
  return new Date(t * 1000).toLocaleString('zh-CN')
}

onMounted(loadData)
</script>
