<template>
  <div class="page-container">
    <el-card class="filter-bar" shadow="never">
      <el-form inline>
        <el-form-item label="策略名">
          <el-input v-model="query.name" placeholder="策略名" clearable style="width: 180px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button type="success" :icon="Plus" @click="onNew">新建策略</el-button>
          <el-button :icon="Delete" :disabled="!selection.length" @click="onDelete">删除</el-button>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column label="策略名" prop="name" min-width="180" />
        <el-table-column label="策略ID" prop="_id" width="240" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="onRunByPolicy(row)">下发</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-bar">
        <el-pagination v-model:current-page="query.page" v-model:page-size="query.size"
                       :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper"
                       @size-change="loadData" @current-change="loadData" />
      </div>
    </el-card>

    <!-- 策略编辑弹窗 -->
    <el-dialog v-model="editVisible" :title="editForm._id ? '编辑策略' : '新建策略'" width="820px" top="5vh">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="策略名" required><el-input v-model="editForm.name" /></el-form-item>

        <el-divider content-position="left">域名配置</el-divider>
        <el-form-item label="域名选项">
          <div class="check-grid">
            <el-checkbox v-model="domain.domain_brute">域名爆破</el-checkbox>
            <el-checkbox v-model="domain.alt_dns">DNS智能生成</el-checkbox>
            <el-checkbox v-model="domain.arl_search">ARL历史查询</el-checkbox>
            <el-checkbox v-model="domain.dns_query_plugin">域名查询插件</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item label="爆破类型">
          <el-radio-group v-model="domain.domain_brute_type">
            <el-radio value="test">测试</el-radio>
            <el-radio value="big">大字典</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-divider content-position="left">端口配置</el-divider>
        <el-form-item label="端口选项">
          <div class="check-grid">
            <el-checkbox v-model="ipConf.port_scan">端口扫描</el-checkbox>
            <el-checkbox v-model="ipConf.service_detection">服务识别</el-checkbox>
            <el-checkbox v-model="ipConf.os_detection">操作系统识别</el-checkbox>
            <el-checkbox v-model="ipConf.ssl_cert">SSL证书</el-checkbox>
            <el-checkbox v-model="ipConf.skip_scan_cdn_ip">跳过CDN</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item label="扫描类型">
          <el-radio-group v-model="ipConf.port_scan_type">
            <el-radio value="test">TEST</el-radio>
            <el-radio value="top100">TOP100</el-radio>
            <el-radio value="top1000">TOP1000</el-radio>
            <el-radio value="all">ALL</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-divider content-position="left">站点配置</el-divider>
        <el-form-item label="站点选项">
          <div class="check-grid">
            <el-checkbox v-model="site.site_identify">站点识别</el-checkbox>
            <el-checkbox v-model="site.site_capture">站点截图</el-checkbox>
            <el-checkbox v-model="site.site_spider">站点爬虫</el-checkbox>
            <el-checkbox v-model="site.file_leak">文件泄露</el-checkbox>
            <el-checkbox v-model="site.search_engines">搜索引擎</el-checkbox>
            <el-checkbox v-model="site.findvhost">Host碰撞</el-checkbox>
            <el-checkbox v-model="site.nuclei_scan">nuclei扫描</el-checkbox>
            <el-checkbox v-model="site.web_info_hunter">WIH调用</el-checkbox>
          </div>
        </el-form-item>

        <el-divider content-position="left">资产组配置（可选）</el-divider>
        <el-form-item label="关联资产组">
          <el-input v-model="scopeId" placeholder="资产组 ID（24位），填写后任务结果会自动同步到该资产组" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveLoading" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 按策略下发任务 -->
    <el-dialog v-model="runVisible" title="按策略下发任务" width="500px">
      <el-form :model="runForm" label-width="90px">
        <el-form-item label="任务名"><el-input v-model="runForm.name" /></el-form-item>
        <el-form-item label="目标" required><el-input v-model="runForm.target" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="任务类型">
          <el-radio-group v-model="runForm.task_tag">
            <el-radio value="task">资产发现</el-radio>
            <el-radio value="risk_cruising">风险巡航</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runVisible = false">取消</el-button>
        <el-button type="primary" :loading="runLoading" @click="onRunSubmit">下发</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Search, Plus, Delete, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { policyApi, taskApi } from '@/api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const query = reactive({ page: 1, size: 20, name: '' })

const editVisible = ref(false); const saveLoading = ref(false)
const editForm = reactive({ _id: '', name: '', policy: {} })
const domain = reactive({ domain_brute: false, alt_dns: false, arl_search: false, dns_query_plugin: false, domain_brute_type: 'test' })
const ipConf = reactive({ port_scan: false, service_detection: false, os_detection: false, ssl_cert: false, skip_scan_cdn_ip: false, port_scan_type: 'test' })
const site = reactive({ site_identify: false, site_capture: false, site_spider: false, file_leak: false, search_engines: false, findvhost: false, nuclei_scan: false, web_info_hunter: false })
const scopeId = ref('')

const runVisible = ref(false); const runLoading = ref(false)
const runForm = reactive({ policy_id: '', name: '', target: '', task_tag: 'task' })

async function loadData() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.name) params.name = query.name
    const res = await policyApi.list(params)
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {} finally { loading.value = false }
}
function onSearch() { query.page = 1; loadData() }
function onSelectionChange(s) { selection.value = s }

function onNew() {
  editForm._id = ''; editForm.name = ''
  Object.assign(domain, { domain_brute: false, alt_dns: false, arl_search: false, dns_query_plugin: false, domain_brute_type: 'test' })
  Object.assign(ipConf, { port_scan: false, service_detection: false, os_detection: false, ssl_cert: false, skip_scan_cdn_ip: false, port_scan_type: 'test' })
  Object.assign(site, { site_identify: false, site_capture: false, site_spider: false, file_leak: false, search_engines: false, findvhost: false, nuclei_scan: false, web_info_hunter: false })
  scopeId.value = ''
  editVisible.value = true
}

function onEdit(row) {
  editForm._id = row._id; editForm.name = row.name
  const p = row.policy || {}
  Object.assign(domain, p.domain_config || {}, { domain_brute_type: p.domain_config?.domain_brute_type || 'test' })
  Object.assign(ipConf, p.ip_config || {}, { port_scan_type: p.ip_config?.port_scan_type || 'test' })
  Object.assign(site, p.site_config || {})
  scopeId.value = p.scope_config?.scope_id || ''
  editVisible.value = true
}

async function onSave() {
  if (!editForm.name) return ElMessage.warning('请输入策略名')
  saveLoading.value = true
  try {
    const policy = {
      domain_config: { ...domain },
      ip_config: { ...ipConf },
      site_config: { ...site },
    }
    if (scopeId.value) policy.scope_config = { scope_id: scopeId.value }
    if (editForm._id) {
      await policyApi.save({ policy_id: editForm._id, name: editForm.name, policy })
    } else {
      await policyApi.add({ name: editForm.name, policy })
    }
    ElMessage.success('保存成功')
    editVisible.value = false
    loadData()
  } catch (e) {} finally { saveLoading.value = false }
}

async function onDelete() {
  const items = selection.value.map((s) => ({ policy_id: s._id }))
  await ElMessageBox.confirm(`确定删除 ${items.length} 个策略？`, '提示', { type: 'warning' })
  await policyApi.delete(items)
  ElMessage.success('删除成功')
  loadData()
}

function onRunByPolicy(row) {
  runForm.policy_id = row._id
  runForm.name = row.name
  runForm.target = ''
  runForm.task_tag = 'task'
  runVisible.value = true
}

async function onRunSubmit() {
  if (!runForm.target) return ElMessage.warning('请输入目标')
  runLoading.value = true
  try {
    await taskApi.addByPolicy({ ...runForm })
    ElMessage.success('任务已下发')
    runVisible.value = false
  } catch (e) {} finally { runLoading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.check-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; }
</style>
