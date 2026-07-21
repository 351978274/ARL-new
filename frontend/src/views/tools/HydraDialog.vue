<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="新建 hydra 爆破" width="1000px" top="5vh" :close-on-click-modal="false">
    <el-form :model="form" label-width="110px" label-position="right">
      <el-row :gutter="20">
        <!-- 左侧：目标 -->
        <el-col :span="12">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="目标" required>
            <el-input v-model="form.targetsText" type="textarea" :rows="8"
                      placeholder="每行一个目标，如&#10;192.168.1.1&#10;ssh://192.168.1.1:22&#10;10.0.0.0/24" />
            <div style="margin-top: 6px; display: flex; gap: 8px; align-items: center">
              <el-upload :show-file-list="false" :before-upload="onUploadFile" accept=".txt">
                <el-button size="small" :icon="Upload">上传目标文件</el-button>
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
                  <!-- 服务类型：下拉选择 -->
                  <el-select v-if="p.type === 'select'" v-model="values[p.key]"
                             filterable allow-create placeholder="选择服务" size="small" style="width: 200px">
                    <el-option v-for="s in (p.options || [])" :key="s" :label="s" :value="s" />
                  </el-select>
                  <!-- 整数 -->
                  <el-input-number v-else-if="p.type === 'int'" v-model="numValues[p.key]"
                                   :min="0" controls-position="right" size="small" style="width: 200px" />
                  <!-- 字符串 -->
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
      <el-button type="primary" :loading="submitting" @click="onSubmit">开始爆破</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { hydraApi } from '@/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])

const submitting = ref(false)
const paramMeta = ref([])

const defaultForm = () => ({ name: '', targetsText: '' })
const form = reactive(defaultForm())
// 参数启用状态：{ key: bool }
const enabled = reactive({})
// 字符串/选择型参数值
const values = reactive({})
// 整数型参数值（el-input-number 绑定数字）
const numValues = reactive({})

// 目标解析（去空、去重）
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
    const res = await hydraApi.paramMeta()
    paramMeta.value = res.data || []
    for (const p of paramMeta.value) {
      if (p.type === 'bool') {
        enabled[p.key] = !!p.default
      } else if (p.type === 'int') {
        // 关键凭据参数默认不启用（用户按需勾选），
        // 但 service/port/tasks 等目标设置类参数默认启用以便直接填值
        const enabledByDefault = ['service', 'port', 'tasks', 'tasks_total'].includes(p.key)
        enabled[p.key] = enabledByDefault
        numValues[p.key] = Number(p.default) || 0
      } else {
        // str / select
        const enabledByDefault = ['service'].includes(p.key) ||
          (p.key === 'pass_file' && p.default)  // 默认密码字典预填
        enabled[p.key] = enabledByDefault
        values[p.key] = p.default !== undefined ? String(p.default) : ''
      }
    }
  } catch (e) {
    // 元数据加载失败时不阻塞，使用空表单
  }
}

// 弹窗打开时加载元数据
watch(() => props.modelValue, (v) => {
  if (v) {
    Object.assign(form, defaultForm())
    if (paramMeta.value.length === 0) loadParamMeta()
  }
})

// ---------- 上传目标文件 ----------
function onUploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  hydraApi.uploadTargets(fd).then((res) => {
    const list = res.data || []
    if (!list.length) {
      ElMessage.warning('文件中未解析到有效目标')
      return
    }
    const existing = form.targetsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    const merged = [...new Set([...existing, ...list])]
    form.targetsText = merged.join('\n')
    ElMessage.success(`已导入 ${list.length} 个目标`)
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

function validate() {
  if (!form.name.trim()) return '请输入任务名称'
  if (!targets.value.length) return '请输入至少一个目标'
  if (!enabled.service) return '请勾选并选择目标服务（service）'
  if (!values.service) return '请选择目标服务'
  // 至少提供一种凭据来源
  const hasCredential =
    (enabled.login && values.login) ||
    (enabled.login_file && values.login_file) ||
    (enabled.colon_file && values.colon_file) ||
    enabled.extra_check || enabled.brute_gen
  if (!hasCredential) return '请至少提供一种凭据来源（-l/-L/-C/-e/-x）'
  return ''
}

async function onSubmit() {
  const err = validate()
  if (err) return ElMessage.warning(err)
  submitting.value = true
  try {
    const res = await hydraApi.addTask({
      name: form.name.trim(),
      targets: targets.value,
      options: buildOptions(),
    })
    if (res.code === 200) {
      ElMessage.success('爆破任务已下发')
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
