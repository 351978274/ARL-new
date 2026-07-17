<template>
  <div class="page-container">
    <!-- 过滤栏 -->
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item v-if="hasTaskId" label="任务ID">
          <el-input v-model="query.task_id" placeholder="task_id" clearable style="width: 240px"
                    @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item v-else-if="hasScopeId" label="资产组ID">
          <el-input v-model="query.scope_id" placeholder="scope_id" clearable style="width: 240px"
                    @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item v-else label="关键字">
          <el-input v-model="query.keyword" placeholder="搜索" clearable style="width: 180px"
                    @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button :icon="Download" @click="onExport">导出</el-button>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card shadow="never">
      <template #header>
        <span style="font-weight: 600">{{ config.title }}</span>
        <span style="color: #909399; margin-left: 12px; font-size: 13px">共 {{ total }} 条</span>
      </template>
      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column type="index" width="50" label="#" />
        <el-table-column
          v-for="col in config.columns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <!-- 截图 -->
            <template v-if="col.type === 'screenshot'">
              <el-image v-if="row.screenshot" :src="row.screenshot" :preview-src-list="[row.screenshot]"
                        fit="cover" style="width: 80px; height: 50px" :preview-teleported="true" />
              <span v-else>-</span>
            </template>
            <!-- 自定义渲染 -->
            <template v-else-if="col.render">{{ col.render(row) || '-' }}</template>
            <!-- 链接 -->
            <template v-else-if="col.link">
              <a :href="row[col.linkKey || col.prop]" target="_blank" rel="noopener"
                 style="color: #409eff; text-decoration: none">{{ row[col.prop] }}</a>
            </template>
            <!-- 普通文本 -->
            <template v-else>{{ row[col.prop] ?? '-' }}</template>
          </template>
        </el-table-column>
        <el-table-column v-if="hasCopyField" label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="copyRow(row)">复制</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[20, 50, 100, 200]"
                       layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search, Download, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchList, exportList } from '@/api'
import { COLLECTION_CONFIG } from './columns'

const route = useRoute()
const collection = computed(() => route.meta.collection)
const config = computed(() => COLLECTION_CONFIG[collection.value] || { title: route.meta.title, columns: [] })

const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, size: 20, task_id: '', scope_id: '', keyword: '' })

const hasTaskId = computed(() => ['domain', 'site', 'ip', 'url', 'cip', 'cert', 'service', 'vuln', 'fileleak', 'poc', 'stat_finger', 'npoc_service', 'nuclei_result', 'wih', 'github_task', 'github_result', 'github_monitor_result'].includes(collection.value))
const hasScopeId = computed(() => ['asset_domain', 'asset_ip', 'asset_site', 'asset_wih'].includes(collection.value))
const hasCopyField = computed(() => config.value.columns.some((c) => c.copyable))

async function loadData() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    // 从路由 query 自动带 task_id / scope_id
    if (route.query.task_id) query.task_id = route.query.task_id
    if (route.query.scope_id) query.scope_id = route.query.scope_id
    if (hasTaskId.value && query.task_id) params.task_id = query.task_id
    if (hasScopeId.value && query.scope_id) params.scope_id = query.scope_id
    if (query.keyword) {
      // 关键字搜索主字段
      const mainField = config.value.columns[0]?.prop
      if (mainField) params[mainField] = query.keyword
    }
    const res = await fetchList(collection.value, params)
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}

function onSearch() { query.page = 1; loadData() }

async function onExport() {
  const params = { page: 1, size: 100000 }
  if (hasTaskId.value && query.task_id) params.task_id = query.task_id
  if (hasScopeId.value && query.scope_id) params.scope_id = query.scope_id
  const resp = await exportList(collection.value, params)
  const blob = new Blob([resp.data], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${collection.value}_${total.value}.txt`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('导出成功')
}

async function copyRow(row) {
  const copyCol = config.value.columns.find((c) => c.copyable)
  if (!copyCol) return
  const val = row[copyCol.prop] || ''
  try {
    await navigator.clipboard.writeText(val)
    ElMessage.success('已复制')
  } catch (e) { ElMessage.warning('复制失败') }
}

// 路由切换或集合变化时重新加载
watch(() => route.path, loadData)
onMounted(loadData)
</script>
