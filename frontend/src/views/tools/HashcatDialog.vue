<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="新建 hashcat 恢复" width="1000px" top="5vh" :close-on-click-modal="false">
    <el-form :model="form" label-width="110px" label-position="right">
      <el-row :gutter="20">
        <!-- 左侧：任务名 + 哈希文件 + 字典/掩码 -->
        <el-col :span="12">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="哈希文件" required>
            <el-upload
              :show-file-list="false"
              :before-upload="onUploadHash"
              accept=".txt,.hash,.hashes,.lst,.list,.hccapx,.hccap"
              drag
              style="width: 100%"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">
                拖拽哈希文件到此处，或<em>点击上传</em>
              </div>
              <template #tip>
                <div style="font-size: 12px; color: #909399; padding: 0 12px">
                  每行一个哈希（支持 hash:salt / user:hash 格式）
                </div>
              </template>
            </el-upload>
            <div v-if="form.hashFile" class="file-info">
              <el-icon><Document /></el-icon>
              <span>{{ form.hashFilename }}</span>
              <span style="color: #909399; margin-left: 8px">{{ formatSize(form.hashSize) }}</span>
              <el-button link type="danger" :icon="Close" @click="clearHash" />
            </div>
            <div style="margin-top: 6px">
              <el-button size="small" :icon="Files" @click="hashPickerVisible = true">从已上传选择</el-button>
            </div>
          </el-form-item>
          <el-form-item label="字典/掩码">
            <el-input v-model="form.wordlist" placeholder="字典路径或掩码，如 /tmp/rockyou.txt 或 ?a?a?a?a?a?a" />
            <div style="margin-top: 4px; color: #909399; font-size: 12px">
              字典模式(-a 0)填路径；掩码模式(-a 3)填掩码
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
                  <el-checkbox v-model="enabled[p.key]">
                    <span class="param-name">{{ p.name }}</span>
                    <span class="param-flag">{{ p.flag }}</span>
                  </el-checkbox>
                </el-tooltip>
                <div v-if="p.type !== 'bool' && enabled[p.key]" class="param-input">
                  <el-input-number v-if="p.type === 'int'" v-model="numValues[p.key]"
                                   :min="0" controls-position="right" size="small" style="width: 200px" />
                  <div v-else class="param-value-row">
                    <el-input v-model="values[p.key]" :placeholder="p.desc"
                              size="small" style="width: 200px" />
                    <el-button v-if="p.file" :icon="Folder" size="small"
                               @click="openPicker(p.key)" title="选择文件" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">开始恢复</el-button>
    </template>

    <!-- 已上传哈希文件选择抽屉 -->
    <el-drawer v-model="hashPickerVisible" title="从已上传哈希文件选择" size="600px" direction="rtl">
      <el-table :data="hashes" v-loading="hashesLoading" border stripe height="400"
                @current-change="onHashPick">
        <el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="line_count" label="哈希数" width="80" />
        <el-table-column label="大小" width="90">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="save_date" label="上传时间" width="160" />
      </el-table>
      <div style="margin-top: 10px; text-align: right">
        <el-button type="primary" :disabled="!pickedHash" @click="confirmHashPick">使用该文件</el-button>
      </div>
    </el-drawer>

    <!-- 文件路径选择器 -->
    <FilePicker v-model="filePickerVisible" :title="filePickerTitle"
                @select="onFilePicked" />
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { UploadFilled, Document, Close, Files, Folder } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { hashcatApi } from '@/api'
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
  name: '', hashFile: '', hashFilename: '', hashSize: 0, wordlist: '',
})
const form = reactive(defaultForm())
const enabled = reactive({})
const values = reactive({})
const numValues = reactive({})

const groupedMeta = computed(() => {
  const map = new Map()
  for (const p of paramMeta.value) {
    if (!map.has(p.group)) map.set(p.group, [])
    map.get(p.group).push(p)
  }
  return [...map.entries()].map(([name, items]) => ({ name, items }))
})

async function loadParamMeta() {
  try {
    const res = await hashcatApi.paramMeta()
    paramMeta.value = res.data || []
    for (const p of paramMeta.value) {
      if (p.type === 'bool') {
        enabled[p.key] = !!p.default
      } else if (p.type === 'int') {
        // 核心参数默认启用
        const enabledByDefault = ['hash_type', 'attack_mode', 'workload_profile'].includes(p.key)
        enabled[p.key] = enabledByDefault
        numValues[p.key] = Number(p.default) || 0
      } else {
        enabled[p.key] = false
        values[p.key] = p.default !== undefined ? String(p.default) : ''
      }
    }
  } catch (e) {}
}

watch(() => props.modelValue, (v) => {
  if (v) {
    Object.assign(form, defaultForm())
    if (paramMeta.value.length === 0) loadParamMeta()
  }
})

// ---------- 哈希文件上传 ----------
function onUploadHash(file) {
  const fd = new FormData()
  fd.append('file', file)
  hashcatApi.uploadHash(fd).then((res) => {
    const data = res.data || {}
    if (data.hash_file) {
      form.hashFile = data.hash_file
      form.hashFilename = data.filename || file.name
      form.hashSize = data.size || file.size
      ElMessage.success(`上传成功：${form.hashFilename}（${data.line_count || 0} 个哈希）`)
    }
  }).catch(() => {})
  return false
}

function clearHash() {
  form.hashFile = ''
  form.hashFilename = ''
  form.hashSize = 0
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

// ---------- 已上传哈希文件选择 ----------
const hashPickerVisible = ref(false)
const hashesLoading = ref(false)
const hashes = ref([])
const pickedHash = ref(null)

watch(hashPickerVisible, async (v) => {
  if (v) {
    hashesLoading.value = true
    try {
      const res = await hashcatApi.listHashes({ size: 100 })
      hashes.value = res.items || []
    } catch (e) {} finally { hashesLoading.value = false }
  }
})

function onHashPick(row) { pickedHash.value = row }

function confirmHashPick() {
  if (!pickedHash.value) return
  form.hashFile = pickedHash.value.stored_path
  form.hashFilename = pickedHash.value.filename
  form.hashSize = pickedHash.value.size || 0
  hashPickerVisible.value = false
  ElMessage.success(`已选择：${form.hashFilename}`)
}

// ---------- 提交 ----------
function buildOptions() {
  const opts = {}
  for (const p of paramMeta.value) {
    if (!enabled[p.key]) continue
    if (p.type === 'bool') {
      opts[p.key] = true
    } else if (p.type === 'int') {
      const n = Number(numValues[p.key])
      if (!Number.isNaN(n)) opts[p.key] = n
    } else {
      const v = (values[p.key] || '').toString().trim()
      if (v) opts[p.key] = v
    }
  }
  return opts
}

async function onSubmit() {
  if (!form.name.trim()) return ElMessage.warning('请输入任务名称')
  if (!form.hashFile) return ElMessage.warning('请上传或选择哈希文件')
  submitting.value = true
  try {
    const res = await hashcatApi.addTask({
      name: form.name.trim(),
      hash_file: form.hashFile,
      wordlist: form.wordlist.trim(),
      options: buildOptions(),
    })
    if (res.code === 200) {
      ElMessage.success('恢复任务已下发')
      emit('update:modelValue', false)
      emit('created')
    }
  } catch (e) {} finally { submitting.value = false }
}
</script>

<style scoped>
.file-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  color: #67c23a;
  font-size: 13px;
}
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
.param-input {
  margin-left: 8px;
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
}
</style>
