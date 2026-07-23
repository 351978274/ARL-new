<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             :title="title || '选择文件'" width="720px" top="8vh" :close-on-click-modal="false">
    <!-- 顶部：路径输入框 + 前往 + 返回上级 + 根目录下拉 -->
    <div class="picker-toolbar">
      <el-select v-model="rootSel" placeholder="根目录" size="small" style="width: 150px"
                 @change="onRootChange">
        <el-option v-for="r in rootList" :key="r.path" :label="r.name" :value="r.path" />
      </el-select>
      <el-input v-model="pathInput" placeholder="输入绝对路径后回车前往" size="small"
                style="flex: 1" @keyup.enter="goPath(pathInput)" />
      <el-button :icon="FolderOpened" size="small" @click="goPath(pathInput)">前往</el-button>
      <el-button :icon="Back" size="small" :disabled="!parentDir" @click="goParent">上级</el-button>
    </div>

    <!-- 当前路径面包屑 -->
    <div class="picker-cwd">
      <el-icon><Folder /></el-icon>
      <span>{{ currentPath }}</span>
    </div>

    <!-- 列表 -->
    <el-table :data="tableData" v-loading="loading" border stripe height="360"
              highlight-current-row @row-dblclick="onRowDblClick" @current-change="onRowSelect">
      <el-table-column label="名称" min-width="280">
        <template #default="{ row }">
          <el-icon v-if="row._isDir" color="#409eff"><Folder /></el-icon>
          <el-icon v-else color="#909399"><Document /></el-icon>
          <span style="margin-left: 6px">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ row._isDir ? '文件夹' : '文件' }}</template>
      </el-table-column>
      <el-table-column label="大小" width="110">
        <template #default="{ row }">{{ row._isDir ? '-' : formatSize(row.size) }}</template>
      </el-table-column>
    </el-table>

    <div v-if="selectedFile" class="picker-selected">
      已选：<el-icon color="#67c23a"><Document /></el-icon>
      <span style="color: #67c23a">{{ selectedFile }}</span>
    </div>
    <div v-else-if="selectedDir" class="picker-selected">
      当前目录：<el-icon color="#409eff"><Folder /></el-icon>
      <span>{{ selectedDir }}</span>
      <span style="color: #909399; margin-left: 8px; font-size: 12px">（也可直接选择当前目录）</span>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!selectedFile && !selectedDir" @click="onConfirm">
        选择
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Folder, FolderOpened, Document, Back } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fileApi } from '@/api'

const props = defineProps({
  modelValue: Boolean,
  title: { type: String, default: '选择文件' },
  // 初始路径（可选）；不传则用项目根
  initialPath: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const loading = ref(false)
const currentPath = ref('')
const parentDir = ref('')
const pathInput = ref('')
const tableData = ref([])
const rootList = ref([])
const rootSel = ref('')
const selectedFile = ref('')   // 选中的文件绝对路径
const selectedDir = ref('')    // 选中的目录绝对路径（或当前所在目录）
const currentRow = ref(null)

// 加载目录
async function loadDir(path) {
  loading.value = true
  try {
    const res = await fileApi.listDir(path)
    if (res.code !== 200) {
      ElMessage.error(res.message || '读取目录失败')
      return
    }
    const d = res.data
    currentPath.value = d.path
    parentDir.value = d.parent || ''
    pathInput.value = d.path
    selectedFile.value = ''
    selectedDir.value = ''
    currentRow.value = null
    // 合并 dirs + files，标记 _isDir
    const dirs = (d.dirs || []).map((x) => ({ ...x, _isDir: true }))
    const files = (d.files || []).map((x) => ({ ...x, _isDir: false }))
    tableData.value = [...dirs, ...files]
  } catch (e) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

// 加载根目录列表
async function loadRoots() {
  try {
    const res = await fileApi.roots()
    if (res.code === 200) {
      rootList.value = res.data || []
      if (!rootSel.value && rootList.value.length) {
        rootSel.value = rootList.value[0].path
      }
    }
  } catch (e) {}
}

function onRootChange(path) {
  loadDir(path)
}

function goPath(p) {
  if (!p) return
  loadDir(p)
}

function goParent() {
  if (parentDir.value) loadDir(parentDir.value)
}

// 行选中（单击）
function onRowSelect(row) {
  currentRow.value = row
  if (!row) return
  const full = joinPath(currentPath.value, row.name)
  if (row._isDir) {
    selectedDir.value = full
    selectedFile.value = ''
  } else {
    selectedFile.value = full
    selectedDir.value = ''
  }
}

// 行双击：目录则进入，文件则直接选定并确认
function onRowDblClick(row) {
  const full = joinPath(currentPath.value, row.name)
  if (row._isDir) {
    loadDir(full)
  } else {
    selectedFile.value = full
    selectedDir.value = ''
    onConfirm()
  }
}

function onConfirm() {
  // 优先文件，其次目录
  const picked = selectedFile.value || selectedDir.value
  if (picked) {
    emit('select', picked)
    emit('update:modelValue', false)
  }
}

// 拼接绝对路径（兼容 / 和 \）
function joinPath(dir, name) {
  if (!dir) return name
  const sep = dir.includes('/') && !dir.includes('\\') ? '/' : '\\'
  if (dir.endsWith(sep) || dir.endsWith('/') || dir.endsWith('\\')) {
    return dir + name
  }
  return dir + sep + name
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

// 打开时初始化
watch(() => props.modelValue, async (v) => {
  if (v) {
    await loadRoots()
    const start = props.initialPath || (rootList.value[0] && rootList.value[0].path) || ''
    loadDir(start)
  }
})
</script>

<style scoped>
.picker-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.picker-cwd {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #606266;
  word-break: break-all;
}
.picker-selected {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  word-break: break-all;
}
</style>
