<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="新建 sqlmap 扫描" width="1000px" top="5vh" :close-on-click-modal="false">
    <el-form :model="form" label-width="110px" label-position="right">
      <el-row :gutter="20">
        <!-- 左侧：目标 -->
        <el-col :span="12">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="目标 URL" required>
            <el-input v-model="form.targetsText" type="textarea" :rows="8"
                      placeholder="每行一个 URL，建议带参数，如&#10;http://example.com/page?id=1" />
            <div style="margin-top: 6px; display: flex; gap: 8px; align-items: center">
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
                  <el-checkbox v-model="enabled[p.key]">
                    <span class="param-name">{{ p.name }}</span>
                    <span class="param-flag">{{ p.flag }}</span>
                  </el-checkbox>
                </el-tooltip>
                <!-- 带值参数：勾选后显示对应控件 -->
                <div v-if="p.type !== 'bool' && enabled[p.key]" class="param-input">
                  <el-input-number v-if="p.type === 'int'" v-model="numValues[p.key]"
                                   :min="0" controls-position="right" size="small" style="width: 200px" />
                  <el-input v-else v-model="values[p.key]" :placeholder="p.desc"
                            size="small" style="width: 200px" />
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
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { sqlmapApi } from '@/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])

const submitting = ref(false)
const paramMeta = ref([])

const defaultForm = () => ({ name: '', targetsText: '' })
const form = reactive(defaultForm())
const enabled = reactive({})
const values = reactive({})
const numValues = reactive({})

const targets = computed(() => {
  const list = form.targetsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  return [...new Set(list)]
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
    const res = await sqlmapApi.paramMeta()
    paramMeta.value = res.data || []
    for (const p of paramMeta.value) {
      if (p.type === 'bool') {
        enabled[p.key] = !!p.default
      } else if (p.type === 'int') {
        // 关键运行参数默认启用，便于直接填值
        const enabledByDefault = ['level', 'risk', 'threads', 'time_sec', 'timeout', 'retries', 'verbose', 'crawl_depth'].includes(p.key)
        enabled[p.key] = enabledByDefault
        numValues[p.key] = Number(p.default) || 0
      } else {
        // 字符串：只有 technique 默认启用
        const enabledByDefault = ['technique'].includes(p.key)
        enabled[p.key] = enabledByDefault
        values[p.key] = p.default !== undefined ? String(p.default) : ''
      }
    }
  } catch (e) {
    // 元数据加载失败时不阻塞
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    Object.assign(form, defaultForm())
    if (paramMeta.value.length === 0) loadParamMeta()
  }
})

function onUploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  sqlmapApi.uploadUrls(fd).then((res) => {
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
  return false
}

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
  if (!targets.value.length) return ElMessage.warning('请输入至少一个目标 URL')
  submitting.value = true
  try {
    const res = await sqlmapApi.addTask({
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
