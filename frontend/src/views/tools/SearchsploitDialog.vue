<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="新建 searchsploit 搜索" width="1000px" top="5vh" :close-on-click-modal="false">
    <el-form :model="form" label-width="110px" label-position="right">
      <el-row :gutter="20">
        <!-- 左侧：搜索词 -->
        <el-col :span="12">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="搜索关键词" required>
            <el-input v-model="form.termsText" type="textarea" :rows="8"
                      placeholder="每行一个关键词，或空格分隔。如&#10;linux kernel 3.2&#10;Apache Struts" />
            <div style="margin-top: 6px; color: #909399; font-size: 12px">
              共 {{ terms.length }} 个关键词（非搜索模式如 -p/-m/--nmap 可留空）
            </div>
          </el-form-item>
          <el-form-item label="Nmap XML">
            <el-upload :show-file-list="false" :before-upload="onUploadNmap" accept=".xml,.nmap">
              <el-button size="small" :icon="Upload">上传 Nmap XML（用于 --nmap）</el-button>
            </el-upload>
            <div v-if="form.nmapFile" class="nmap-info">
              <el-icon><Document /></el-icon>
              <span>{{ form.nmapFilename }}</span>
              <el-button link type="danger" :icon="Close" @click="clearNmap" />
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
                  <el-input v-model="values[p.key]" :placeholder="p.desc"
                            size="small" style="width: 220px" />
                </div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">开始搜索</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Upload, Document, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { searchsploitApi } from '@/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])

const submitting = ref(false)
const paramMeta = ref([])

const defaultForm = () => ({ name: '', termsText: '', nmapFile: '', nmapFilename: '' })
const form = reactive(defaultForm())
const enabled = reactive({})
const values = reactive({})

// 关键词解析：支持换行 + 空格分隔
const terms = computed(() => {
  const tokens = form.termsText
    .split(/\r?\n/)
    .flatMap((line) => line.trim().split(/\s+/))
    .filter(Boolean)
  return [...new Set(tokens)]
})

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
    const res = await searchsploitApi.paramMeta()
    paramMeta.value = res.data || []
    for (const p of paramMeta.value) {
      if (p.type === 'bool') {
        enabled[p.key] = !!p.default
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

// ---------- Nmap XML 上传 ----------
function onUploadNmap(file) {
  const fd = new FormData()
  fd.append('file', file)
  searchsploitApi.uploadNmap(fd).then((res) => {
    const data = res.data || {}
    if (data.nmap_file) {
      form.nmapFile = data.nmap_file
      form.nmapFilename = data.filename || file.name
      // 自动填入 options.nmap
      values.nmap = form.nmapFile
      enabled.nmap = true
      ElMessage.success(`上传成功：${form.nmapFilename}（已自动启用 --nmap 选项）`)
    }
  }).catch(() => {})
  return false
}

function clearNmap() {
  form.nmapFile = ''
  form.nmapFilename = ''
  values.nmap = ''
  enabled.nmap = false
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
      if (v) opts[p.key] = v
    }
  }
  return opts
}

async function onSubmit() {
  if (!form.name.trim()) return ElMessage.warning('请输入任务名称')
  const opts = buildOptions()
  const nonSearch = ['path', 'mirror', 'examine', 'nmap'].some((k) => opts[k])
  if (!terms.value.length && !nonSearch) {
    return ElMessage.warning('请输入搜索关键词（或启用 -p/-m/-x/--nmap 非搜索模式）')
  }
  submitting.value = true
  try {
    const res = await searchsploitApi.addTask({
      name: form.name.trim(),
      terms: terms.value,
      options: opts,
    })
    if (res.code === 200) {
      ElMessage.success('搜索任务已下发')
      emit('update:modelValue', false)
      emit('created')
    }
  } catch (e) {} finally { submitting.value = false }
}
</script>

<style scoped>
.nmap-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 6px 10px;
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
</style>
