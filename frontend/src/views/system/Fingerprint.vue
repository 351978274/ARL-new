<template>
  <div class="page-container">
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item label="应用名">
          <el-input v-model="query.name" placeholder="应用名" clearable style="width: 160px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button type="success" :icon="Plus" @click="addVisible = true">添加指纹</el-button>
          <el-button type="warning" :icon="Upload" @click="triggerUpload">批量导入</el-button>
          <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onUploadFile" />
          <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除</el-button>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="应用名" prop="name" min-width="160" />
        <el-table-column label="规则" prop="human_rule" min-width="400" show-overflow-tooltip />
        <el-table-column label="更新时间" prop="update_date" width="160" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onTest(row)">测试</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <!-- 添加指纹 -->
    <el-dialog v-model="addVisible" title="添加指纹规则" width="560px">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="应用名" required><el-input v-model="addForm.name" /></el-form-item>
        <el-form-item label="规则" required>
          <el-input v-model="addForm.human_rule" type="textarea" :rows="3"
                    placeholder='如 body="phpMyAdmin" && title="phpMyAdmin"' />
          <span style="color:#909399;font-size:12px">
            支持 body/title/header/icon_hash 与 ==/!=/=/&amp;&amp;/||/! 组合
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="onAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Search, Plus, Delete, RefreshRight, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fingerApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const query = reactive({ page: 1, size: 20, name: '' })
const addVisible = ref(false); const addLoading = ref(false)
const addForm = reactive({ name: '', human_rule: '' })
const fileInput = ref()

async function loadData() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.name) params.name = query.name
    const res = await fingerApi.list(params)
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}
function onSearch() { query.page = 1; loadData() }
function onSelectionChange(s) { selection.value = s }

async function onAdd() {
  if (!addForm.name || !addForm.human_rule) return ElMessage.warning('请填写应用名和规则')
  addLoading.value = true
  try {
    await fingerApi.add({ ...addForm })
    ElMessage.success('添加成功')
    addVisible.value = false
    addForm.name = ''; addForm.human_rule = ''
    loadData()
  } catch (e) {} finally { addLoading.value = false }
}

function triggerUpload() { fileInput.value.click() }
async function onUploadFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fingerApi.upload(formData)
    ElMessage.success(`导入成功：${res.data?.count || 0} 条`)
    loadData()
  } catch (err) {} finally {
    fileInput.value.value = ''
  }
}

async function onDelete() {
  const items = selection.value.map((s) => ({ fingerprint_id: s._id }))
  await ElMessageBox.confirm(`确定删除 ${items.length} 条指纹？`, '提示', { type: 'warning' })
  await fingerApi.delete(items)
  ElMessage.success('删除成功')
  loadData()
}

function onTest(row) {
  ElMessageBox.alert(`规则：${row.human_rule}`, '指纹规则', { type: 'info' })
}

onMounted(loadData)
</script>
