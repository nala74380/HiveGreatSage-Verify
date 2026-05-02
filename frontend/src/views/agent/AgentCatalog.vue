<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>项目目录</h2>
        <p class="page-desc">
          查看当前平台项目、代理准入状态、项目授权状态、用户级别价格与功能差异。
        </p>
      </div>
      <el-button :icon="Refresh" @click="fetchCatalog" :loading="loading">刷新</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-alert
      v-else
      title="说明：项目开通本身不扣点；代理给用户授权项目时，才按项目定价、等级、设备数和周期扣点。"
      type="info"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-card shadow="never" class="level-card">
      <template #header>
        <div class="level-card-header">
          <span class="card-title">用户级别功能说明</span>
          <el-tag size="small" effect="plain" type="info">按项目授权等级生效</el-tag>
        </div>
      </template>

      <div class="level-grid">
        <div class="level-block trial">
          <div class="level-title-row">
            <LevelTag level="trial" />
            <span class="level-title">试用用户</span>
          </div>
          <div class="level-desc">等同普通用户，用于短期体验与测试授权。</div>
          <ul class="level-list">
            <li>具备普通用户同等基础功能。</li>
            <li>计费周期按周计算。</li>
          </ul>
        </div>

        <div class="level-block normal">
          <div class="level-title-row">
            <LevelTag level="normal" />
            <span class="level-title">普通用户</span>
          </div>
          <div class="level-desc">基础功能级别。</div>
          <ul class="level-list">
            <li>可使用项目基础验证能力。</li>
            <li>可使用普通用户范围内的基础功能。</li>
          </ul>
        </div>

        <div class="level-block vip">
          <div class="level-title-row">
            <LevelTag level="vip" />
            <span class="level-title">VIP 用户</span>
          </div>
          <div class="level-desc">包含普通用户的所有功能，并增加高级能力。</div>
          <ul class="level-list">
            <li>包含普通用户的所有功能。</li>
            <li>可使用游戏账户数据库。</li>
            <li>可试用组队功能。</li>
            <li>具备物品价格聚合功能。</li>
          </ul>
        </div>

        <div class="level-block svip">
          <div class="level-title-row">
            <LevelTag level="svip" />
            <span class="level-title">SVIP 用户</span>
          </div>
          <div class="level-desc">包含 VIP 用户的所有功能，并增加更高阶配置能力。</div>
          <ul class="level-list">
            <li>包含 VIP 用户的所有功能。</li>
            <li>具备游戏账号不同属性设定功能。</li>
            <li>可扩展其他高级功能。</li>
          </ul>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="projects"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="display_name" label="项目名称" min-width="160" />

        <el-table-column prop="code_name" label="项目代号" min-width="130">
          <template #default="{ row }">
            <span class="mono">{{ row.code_name }}</span>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag :type="row.project_type === 'game' ? 'primary' : 'info'" effect="plain">
              {{ row.project_type === 'game' ? '游戏项目' : '验证项目' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="各级别点数价格" min-width="430">
          <template #default="{ row }">
            <div class="price-list">
              <template v-if="row.prices?.length">
                <span
                  v-for="item in row.prices"
                  :key="item.level"
                  class="price-item"
                >
                  <LevelTag :level="item.level" />
                  <span class="price-num">{{ formatPrice(item) }}</span>
                </span>
              </template>
              <span v-else class="text-muted">暂未定价</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="准入状态" width="145">
          <template #default="{ row }">
            <el-tag :type="statusMeta(row).type" effect="light">
              {{ statusMeta(row).label }}
            </el-tag>

            <div v-if="row.last_request_status === 'rejected' && row.last_review_note" class="reject-note">
              {{ row.last_review_note }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="授权到期" width="155">
          <template #default="{ row }">
            <span v-if="row.auth_valid_until">{{ formatDatetime(row.auth_valid_until) }}</span>
            <span v-else-if="row.is_authorized" class="success-text">永久</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="145" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.action_type === 'auto_open'"
              size="small"
              type="success"
              plain
              :loading="row._actionLoading"
              @click="autoOpenProject(row)"
            >
              立即开通
            </el-button>

            <el-button
              v-else-if="row.action_type === 'apply'"
              size="small"
              type="primary"
              plain
              :loading="row._actionLoading"
              @click="openApplyDialog(row)"
            >
              {{ row.access_status === 'rejected' ? '重新申请' : '申请授权' }}
            </el-button>

            <el-button
              v-else-if="row.action_type === 'view_request'"
              size="small"
              type="warning"
              plain
              disabled
            >
              申请中
            </el-button>

            <el-button
              v-else-if="row.is_authorized"
              size="small"
              type="success"
              plain
              disabled
            >
              已授权
            </el-button>

            <el-button
              v-else
              size="small"
              plain
              disabled
            >
              暂不可申请
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && projects.length === 0"
        description="暂无可展示项目"
        :image-size="80"
      />
    </el-card>

    <el-dialog
      v-model="applyDialog.visible"
      :title="`申请项目授权 — ${applyDialog.project?.display_name || ''}`"
      width="560px"
      destroy-on-close
    >
      <el-form label-width="90px">
        <el-form-item label="项目名称">
          <span class="readonly-val">{{ applyDialog.project?.display_name }}</span>
        </el-form-item>

        <el-form-item label="项目代号">
          <span class="mono">{{ applyDialog.project?.code_name }}</span>
        </el-form-item>

        <el-form-item label="申请说明">
          <el-input
            v-model="applyDialog.reason"
            type="textarea"
            :rows="5"
            maxlength="1000"
            show-word-limit
            placeholder="请说明申请开通该项目的原因、预计用户规模、主要使用场景。"
          />
        </el-form-item>

        <el-alert
          title="申请提交后将进入管理员审核；审核通过后该项目会出现在你的已授权项目中。"
          type="info"
          show-icon
          :closable="false"
          class="small-alert"
        />
      </el-form>

      <template #footer>
        <el-button @click="applyDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="applyDialog.loading" @click="submitApply">
          提交申请
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/agent/AgentCatalog.vue
 * 名称: 代理项目目录页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.2.0
 * 功能说明:
 *   代理查看项目目录、项目准入状态、项目授权状态、项目价格、用户级别功能差异。
 *
 * 本版改进:
 *   - 接入代理项目准入接口。
 *   - 支持“申请授权”。
 *   - 支持“立即开通”。
 *   - 支持“申请中 / 已拒绝 / 暂不可申请 / 已授权”等状态。
 *   - 使用 /api/agents/my/project-access/catalog 单接口返回项目目录。
 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { agentProjectAccessApi } from '@/api/agent/projectAccess'
import LevelTag from '@/components/common/LevelTag.vue'
import { formatDatetime } from '@/utils/format'

const loading = ref(false)
const projects = ref([])
const error = ref('')

const applyDialog = reactive({
  visible: false,
  loading: false,
  project: null,
  reason: '',
})

const statusMap = {
  authorized: { label: '已授权', type: 'success' },
  pending: { label: '申请中', type: 'warning' },
  rejected: { label: '已拒绝', type: 'danger' },
  auto_open_available: { label: '可立即开通', type: 'success' },
  apply_available: { label: '可申请', type: 'primary' },
  unavailable: { label: '暂不可申请', type: 'info' },
}

const statusMeta = (row) => {
  return statusMap[row.access_status] || { label: row.access_status || '未知', type: 'info' }
}

const formatPrice = (item) => {
  if (item.points === null || item.points === undefined) {
    return `未定价 ${item.unit_label || ''}`
  }

  return `${Number(item.points || 0).toFixed(2)} ${item.unit_label || ''}`
}

const getErrorMessage = (err) => {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail || err?.response?.data?.message

  if (status === 401) {
    return '项目目录接口返回 401：当前代理登录态未被后端认可。请确认 Chrome 中仍是代理账号登录。'
  }

  if (status === 403) {
    return '项目目录接口返回 403：当前账号无权访问项目目录。'
  }

  if (status === 404) {
    return '项目目录接口返回 404：后端尚未注册 /api/agents/my/project-access/catalog，请确认后端已更新并重启。'
  }

  if (status === 500) {
    return '项目目录接口返回 500：后端内部异常，请查看 PyCharm 后端控制台日志。'
  }

  if (detail) {
    return `项目目录加载失败：${detail}`
  }

  return `项目目录加载失败：${err?.message || '未知错误'}`
}

const fetchCatalog = async () => {
  loading.value = true
  error.value = ''

  try {
    const res = await agentProjectAccessApi.catalog()
    projects.value = Array.isArray(res.data)
      ? res.data.map(item => ({ ...item, _actionLoading: false }))
      : []
  } catch (err) {
    console.error('[AgentCatalog] 加载项目目录失败:', err)
    projects.value = []
    error.value = getErrorMessage(err)
  } finally {
    loading.value = false
  }
}

const openApplyDialog = (row) => {
  applyDialog.project = row
  applyDialog.reason = ''
  applyDialog.visible = true
}

const submitApply = async () => {
  if (!applyDialog.project) return

  if (!applyDialog.reason.trim()) {
    ElMessage.warning('请填写申请说明')
    return
  }

  applyDialog.loading = true

  try {
    const res = await agentProjectAccessApi.createRequest({
      project_id: applyDialog.project.id,
      request_reason: applyDialog.reason.trim(),
    })

    if (res.data?.status === 'auto_approved') {
      ElMessage.success('项目已自动开通')
    } else {
      ElMessage.success('申请已提交，等待管理员审核')
    }

    applyDialog.visible = false
    await fetchCatalog()
  } finally {
    applyDialog.loading = false
  }
}

const autoOpenProject = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确认立即开通项目「${row.display_name}」？项目开通本身不扣点，后续给用户授权项目时才会按项目价格扣点。`,
      '立即开通确认',
      {
        confirmButtonText: '确认开通',
        cancelButtonText: '取消',
        type: 'success',
      },
    )
  } catch {
    return
  }

  row._actionLoading = true

  try {
    const res = await agentProjectAccessApi.createRequest({
      project_id: row.id,
      request_reason: '',
    })

    if (res.data?.status === 'auto_approved') {
      ElMessage.success('项目已自动开通')
    } else {
      ElMessage.success('申请已提交，等待管理员审核')
    }

    await fetchCatalog()
  } finally {
    row._actionLoading = false
  }
}

onMounted(fetchCatalog)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1e293b;
}

.page-desc {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.tip-alert,
.level-card,
.table-card {
  border-radius: 10px;
}

.level-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.level-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.level-block {
  border-radius: 10px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.level-block.trial {
  background: #f8fafc;
}

.level-block.normal {
  background: #eff6ff;
}

.level-block.vip {
  background: #fff7ed;
}

.level-block.svip {
  background: #fef2f2;
}

.level-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.level-desc {
  margin-top: 8px;
  font-size: 12px;
  color: #475569;
  line-height: 1.7;
}

.level-list {
  margin: 8px 0 0;
  padding-left: 16px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.8;
}

.mono {
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
}

.price-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.price-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  padding: 3px 8px;
}

.price-num {
  font-size: 12px;
  color: #475569;
  font-weight: 600;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

.success-text {
  color: #10b981;
  font-size: 12px;
}

.reject-note {
  margin-top: 4px;
  font-size: 11px;
  color: #ef4444;
  line-height: 1.4;
}

.readonly-val {
  font-size: 13px;
  color: #1e293b;
  font-weight: 600;
}

.small-alert {
  border-radius: 8px;
}
</style>
