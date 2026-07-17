<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="新建任务" width="900px" top="5vh" :close-on-click-modal="false">
    <el-form :model="form" label-width="120px" label-position="right">
      <!-- 左侧：基础输入 -->
      <el-row :gutter="20">
        <el-col :span="14">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="请输入任务名称" />
          </el-form-item>
          <el-form-item label="任务目标" required>
            <el-input v-model="form.target" type="textarea" :rows="5"
                      placeholder="支持 IP、IP段和域名，可一次性下发多个目标，逗号或换行分隔" />
          </el-form-item>
          <el-form-item label="域名爆破类型">
            <el-radio-group v-model="form.domain_brute_type">
              <el-radio value="test">测试</el-radio>
              <el-radio value="big">大字典</el-radio>
            </el-radio-group>
            <el-checkbox v-model="form.domain_brute" style="margin-left: 16px">启用域名爆破</el-checkbox>
          </el-form-item>
          <el-form-item label="端口扫描类型">
            <el-radio-group v-model="form.port_scan_type">
              <el-radio value="test">TEST</el-radio>
              <el-radio value="top100">TOP100</el-radio>
              <el-radio value="top1000">TOP1000</el-radio>
              <el-radio value="all">ALL</el-radio>
            </el-radio-group>
            <el-checkbox v-model="form.port_scan" style="margin-left: 16px">启用端口扫描</el-checkbox>
          </el-form-item>
        </el-col>

        <!-- 右侧：功能勾选 -->
        <el-col :span="10">
          <div style="font-weight: 600; margin-bottom: 8px; color: #606266">功能选项</div>
          <div class="check-grid">
            <el-checkbox v-model="form.service_detection">服务识别</el-checkbox>
            <el-checkbox v-model="form.os_detection">操作系统识别</el-checkbox>
            <el-checkbox v-model="form.ssl_cert">SSL 证书获取</el-checkbox>
            <el-checkbox v-model="form.skip_scan_cdn_ip">跳过 CDN</el-checkbox>
            <el-checkbox v-model="form.site_identify">站点识别</el-checkbox>
            <el-checkbox v-model="form.search_engines">搜索引擎调用</el-checkbox>
            <el-checkbox v-model="form.site_spider">站点爬虫</el-checkbox>
            <el-checkbox v-model="form.site_capture">站点截图</el-checkbox>
            <el-checkbox v-model="form.file_leak">文件泄露</el-checkbox>
            <el-checkbox v-model="form.findvhost">Host 碰撞</el-checkbox>
            <el-checkbox v-model="form.nuclei_scan">nuclei 调用</el-checkbox>
            <el-checkbox v-model="form.web_info_hunter">WIH 调用</el-checkbox>
            <el-checkbox v-model="form.alt_dns">DNS 字典智能生成</el-checkbox>
            <el-checkbox v-model="form.arl_search">ARL 历史查询</el-checkbox>
            <el-checkbox v-model="form.dns_query_plugin">域名查询插件</el-checkbox>
          </div>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">新建任务</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { taskApi } from '@/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'created'])

const submitting = ref(false)
const defaultForm = () => ({
  name: '', target: '',
  domain_brute: false, domain_brute_type: 'test',
  port_scan: false, port_scan_type: 'test',
  service_detection: false, os_detection: false, ssl_cert: false, skip_scan_cdn_ip: false,
  site_identify: false, search_engines: false, site_spider: false, site_capture: false,
  file_leak: false, findvhost: false, nuclei_scan: false, web_info_hunter: false,
  alt_dns: false, arl_search: false, dns_query_plugin: false,
})
const form = reactive(defaultForm())

// 每次打开重置
watch(() => props.modelValue, (v) => { if (v) Object.assign(form, defaultForm()) })

async function onSubmit() {
  if (!form.name.trim()) return ElMessage.warning('请输入任务名称')
  if (!form.target.trim()) return ElMessage.warning('请输入任务目标')
  submitting.value = true
  try {
    const res = await taskApi.add({ ...form })
    if (res.code === 200) {
      ElMessage.success('任务已下发')
      emit('update:modelValue', false)
      emit('created')
    }
  } catch (e) {} finally { submitting.value = false }
}
</script>

<style scoped>
.check-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 8px;
  padding: 12px;
  background: #f7f8fa;
  border-radius: 6px;
}
</style>
