<template>
  <div class="page-container">
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item label="资产组名">
          <el-input v-model="query.name" placeholder="资产组名" clearable style="width: 180px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button type="success" :icon="Plus" @click="addVisible = true">新建资产组</el-button>
          <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除</el-button>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="资产组名" prop="name" min-width="160" />
        <el-table-column label="范围类别" prop="scope_type" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.scope_type === 'ip' ? 'warning' : 'success'">
              {{ row.scope_type === 'ip' ? 'IP' : '域名' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="资产范围" prop="scope" min-width="280" show-overflow-tooltip />
        <el-table-column label="黑名单" prop="black_scope" min-width="160" show-overflow-tooltip />
        <el-table-column label="资产组ID" prop="_id" width="240" />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewAssets(row, 'asset_domain')">域名</el-button>
            <el-button link type="primary" @click="viewAssets(row, 'asset_ip')">IP</el-button>
            <el-button link type="primary" @click="viewAssets(row, 'asset_site')">站点</el-button>
            <el-button link type="primary" @click="viewAssets(row, 'asset_wih')">WIH</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <!-- 新建资产组 -->
    <el-dialog v-model="addVisible" title="新建资产组" width="560px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="资产组名" required>
          <el-input v-model="addForm.name" placeholder="资产组名称" />
        </el-form-item>
        <el-form-item label="范围类别">
          <el-radio-group v-model="addForm.scope_type">
            <el-radio value="domain">域名</el-radio>
            <el-radio value="ip">IP</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="资产范围" required>
          <el-input v-model="addForm.scope" type="textarea" :rows="4"
                    :placeholder="addForm.scope_type === 'domain' ? 'example.com，多个逗号或换行分隔' : '1.2.3.0/24 或 1.2.3.4-10'" />
        </el-form-item>
        <el-form-item label="黑名单范围">
          <el-input v-model="addForm.black_scope" type="textarea" :rows="2" placeholder="可选" />
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
import { useRouter } from 'vue-router'
import { Search, Plus, Delete, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { scopeApi } from '@/api'

const router = useRouter()
const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const query = reactive({ page: 1, size: 20, name: '' })
const addVisible = ref(false)
const addLoading = ref(false)
const addForm = reactive({ name: '', scope: '', black_scope: '', scope_type: 'domain' })

async function loadData() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.name) params.name = query.name
    const res = await scopeApi.list(params)
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}
function onSearch() { query.page = 1; loadData() }
function onSelectionChange(s) { selection.value = s }

async function onAdd() {
  if (!addForm.name || !addForm.scope) return ElMessage.warning('请填写资产组名和范围')
  addLoading.value = true
  try {
    await scopeApi.add({ ...addForm })
    ElMessage.success('新建成功')
    addVisible.value = false
    addForm.name = ''; addForm.scope = ''; addForm.black_scope = ''
    loadData()
  } catch (e) {} finally { addLoading.value = false }
}
async function onDelete() {
  const items = selection.value.map((s) => ({ scope_id: s._id }))
  await ElMessageBox.confirm(`确定删除 ${items.length} 个资产组及其监控任务？`, '危险操作', { type: 'error' })
  await scopeApi.delete(items)
  ElMessage.success('删除成功')
  loadData()
}
function viewAssets(row, path) {
  router.push({ path: `/${path}`, query: { scope_id: row._id } })
}

onMounted(loadData)
</script>
