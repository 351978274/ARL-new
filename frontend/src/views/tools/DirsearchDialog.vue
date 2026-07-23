<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="新建 dirsearch 扫描" width="1000px" top="5vh" :close-on-click-modal="false">
    <el-form :model="form" label-width="110px" label-position="right">
      <el-row :gutter="20">
        <!-- 左侧：目标 -->
        <el-col :span="12">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="目标 URL" required>
            <el-input v-model="form.targetsText" type="textarea" :rows="8"
                      placeholder="每行一个 URL，如 https://example.com" />
            <div style="margin-top: 6px; display: flex; gap: 8px; align-items: center">
              <el-button size="small" :icon="Search" @click="openSitePicker">从站点选择</el-button>
              <el-upload :show-file-list="false" :before-upload="onUploadFile" accept=".txt">
                <el-button size="small" :icon="Upload">上传 URL 文件</el-button>
              </el-upload>
              <span style="color: #909399; font-size: 12px">共 {{ targets.length }} 个</span>
            </div>
          </el-form-item>
        </el-col>

        <!-- 右侧：参数勾选（按分组） -->
        <el-col :span="12">
          <div style="max-height: 480px; overflow-y: auto; padding-right: 4px">
            <div v-for="group in groupedMeta" :key="group.name" class="param-group">
              <div class="param-group-title">{{ group.name }}</div>
              <div v-for="p in group.items" :key="p.key" class="param-row">
                <el-tooltip :content="p.desc" placement="top" :show-after="300">
                  <el-checkbox v-model="enabled[p.key]" @change="onToggle(p)">
                    <span class="param-name">{{ p.name }}</span>
                    <span class="param-flag">{{ p.flag }}</span>
                  </el-checkbox>
                </el-tooltip>
                <!-- 带值参数：勾选后显示输入框 -->
                <div v-if="p.type !== 'bool' && enabled[p.key]" class="param-value-row">
                  <el-input v-model="values[p.key]"
                            :placeholder="p.desc"
                            size="small"
                            :type="p.type === 'int' || p.type === 'float' ? 'number' : 'text'"
                            style="width: 200px" />
                  <el-button v-if="p.file" :icon="Folder" size="small"
                             @click="openPicker(p.key)" title="选择文件" />
                </div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">开始扫描</el-button>
    </template>

    <!-- 站点选择抽屉 -->
    <el-drawer v-model="sitePickerVisible" title="从站点集合选择" size="600px" direction="rtl">
      <div style="margin-bottom: 10px; display: flex; gap: 8px">
        <el-input v-model="siteSearch" placeholder="搜索站点" clearable @keyup.enter="loadSites" />
        <el-button :icon="Search" @click="loadSites">搜索</el-button>
      </div>
      <el-table :data="siteOptions" v-loading="siteLoading" border stripe height="400"
                @selection-change="onSiteSelection">
        <el-table-column type="selection" width="45" />
        <el-table-column prop="site" label="站点" show-overflow-tooltip />
      </el-table>
      <div style="margin-top: 10px; text-align: right">
        <el-button type="primary" @click="confirmSitePicker">加入目标 ({{ selectedSites.length }})</el-button>
      </div>
    </el-drawer>

    <!-- 文件路径选择器 -->
    <FilePicker v-model="filePickerVisible" :title="filePickerTitle"
                @select="onFilePicked" />
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Search, Upload, Folder } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { dirsearchApi } from '@/api'
import FilePicker from '@/components/FilePicker.vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])

const submitting = ref(false)
const paramMeta = ref([])

// 文件路径选择器
const filePickerVisible = ref(false)
const filePickerTitle = ref('选择文件')
const filePickerTargetKey = ref('')
function openPicker(key) {
  filePickerTargetKey.value = key
  const meta = paramMeta.value.find((p) => p.key === key)
  filePickerTitle.value = `选择文件 - ${meta ? meta.name : key}`
  filePickerVisible.value = true
}
function onFilePicked(path) {
  if (filePickerTargetKey.value) {
    values[filePickerTargetKey.value] = path
  }
}

const defaultForm = () => ({
  name: '',
  targetsText: '',
})

const form = reactive(defaultForm())
// 参数启用状态：{ key: bool }
const enabled = reactive({})
// 参数值：{ key: string }
const values = reactive({})

// 目标 URL 解析（去空、去重）
const targets = computed(() => {
  const list = form.targetsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  return [...new Set(list)]
})

// 按分组聚合参数元数据
const groupedMeta = computed(() => {
  const map = new Map()
  for (const p of paramMeta.value) {
    if (!map.has(p.group)) map.set(p.group, [])
    map.get(p.group).push(p)
  }
  return [...map.entries()].map(([name, items]) => ({ name, items }))
})

// 加载参数元数据并初始化默认值
async function loadParamMeta() {
  try {
    const res = await dirsearchApi.paramMeta()
    paramMeta.value = res.data || []
    // 初始化：bool 类型默认值取 default；带值类型默认 enabled=false
    for (const p of paramMeta.value) {
      if (p.type === 'bool') {
        enabled[p.key] = !!p.default
      } else {
        enabled[p.key] = false
        values[p.key] = p.default !== undefined && p.default !== '' ? String(p.default) : ''
      }
    }
  } catch (e) {
    // 元数据加载失败时使用空表单，不阻塞
  }
}

function onToggle(p) {
  // 取消勾选带值参数时清空（保留默认值便于再次勾选）
}

// 弹窗打开时加载元数据
watch(() => props.modelValue, (v) => {
  if (v) {
    Object.assign(form, defaultForm())
    if (paramMeta.value.length === 0) loadParamMeta()
  }
})

// ---------- 站点选择 ----------
const sitePickerVisible = ref(false)
const siteLoading = ref(false)
const siteOptions = ref([])
const siteSearch = ref('')
const selectedSites = ref([])

async function openSitePicker() {
  sitePickerVisible.value = true
  await loadSites()
}

async function loadSites() {
  siteLoading.value = true
  try {
    const res = await dirsearchApi.siteList({ search: siteSearch.value, size: 500 })
    siteOptions.value = (res.data || []).map((s) => ({ site: s }))
  } catch (e) {} finally { siteLoading.value = false }
}

function onSiteSelection(rows) { selectedSites.value = rows }

function confirmSitePicker() {
  if (!selectedSites.value.length) {
    ElMessage.warning('请先勾选站点')
    return
  }
  const existing = form.targetsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  const merged = [...new Set([...existing, ...selectedSites.value.map((r) => r.site)])]
  form.targetsText = merged.join('\n')
  sitePickerVisible.value = false
  ElMessage.success(`已加入 ${selectedSites.value.length} 个站点`)
}

// ---------- 上传 URL 文件 ----------
function onUploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  dirsearchApi.uploadUrls(fd).then((res) => {
    const urls = res.data || []
    if (!urls.length) {
      ElMessage.warning('文件中未解析到有效 URL')
      return
    }
    const existing = form.targetsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    const merged = [...new Set([...existing, ...urls])]
    form.targetsText = merged.join('\n')
    ElMessage.success(`已导入 ${urls.length} 个 URL`)
  }).catch(() => {})
  return false // 阻止 el-upload 自动上传
}

// ---------- 提交 ----------
function buildOptions() {
  const opts = {}
  for (const p of paramMeta.value) {
    if (!enabled[p.key]) continue
    if (p.type === 'bool') {
      opts[p.key] = true
    } else {
      const v = (values[p.key] || '').toString().trim()
      if (!v) continue
      if (p.type === 'int') opts[p.key] = parseInt(v, 10)
      else if (p.type === 'float') opts[p.key] = parseFloat(v)
      else opts[p.key] = v
    }
  }
  return opts
}

async function onSubmit() {
  if (!form.name.trim()) return ElMessage.warning('请输入任务名称')
  if (!targets.value.length) return ElMessage.warning('请输入至少一个目标 URL')
  submitting.value = true
  try {
    const res = await dirsearchApi.addTask({
      name: form.name.trim(),
      targets: targets.value,
      options: buildOptions(),
    })
    if (res.code === 200) {
      ElMessage.success('扫描任务已下发')
      emit('update:modelValue', false)
      emit('created')
    }
  } catch (e) {} finally { submitting.value = false }
}
</script>

<style scoped>
.param-group {
  margin-bottom: 14px;
  padding: 10px 12px;
  background: #f7f8fa;
  border-radius: 6px;
}
.param-group-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  font-size: 13px;
}
.param-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.param-name {
  font-size: 13px;
}
.param-flag {
  margin-left: 6px;
  color: #909399;
  font-family: monospace;
  font-size: 12px;
}
.param-value-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
}
</style>
