<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>代理管理</h2>
        <p class="page-desc">
          代理是项目售卖与用户授权主体；组织层级用于代理树关系，业务等级用于项目准入、授信建议、自动开通能力和代理治理。
        </p>
      </div>

      <el-button type="primary" :icon="Plus" @click="createDialogVisible = true">
        新建代理
      </el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
          </el-select>
        </el-form-item>

        <el-form-item label="项目">
          <el-select
            v-model="filter.project_id"
            clearable
            filterable
            placeholder="全部项目"
            style="width: 180px"
            :loading="projectLoading"
          >
            <el-option
              v-for="p in allProjects"
              :key="projectKey(p)"
              :label="projectDisplayName(p)"
              :value="Number(p.id || p.project_id)"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="searchAgents">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
          <el-button :icon="Refresh" :loading="loading" @click="loadAgents">
            刷新
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="agents"
        row-key="id"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="username" label="代理名" min-width="145">
          <template #default="{ row }">
            <button class="agent-link" type="button" @click="goDetail(row)">
              {{ row.username }}
            </button>
            <div class="agent-id">ID: {{ row.id }}</div>
          </template>
        </el-table-column>

        <el-table-column label="组织层级" width="90">
          <template #default="{ row }">
            <el-tag type="info" effect="plain" size="small">
              Lv.{{ row.hierarchy_depth }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="业务等级" width="135">
          <template #default="{ row }">
            <el-tag v-if="row.business_profile" type="primary" effect="light" size="small">
              {{ businessLevelText(row.business_profile) }}
            </el-tag>
            <el-tag v-else type="info" effect="plain" size="small">未加载</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="风险状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="riskStatusType(row.business_profile?.risk_status)"
              effect="light"
              size="small"
            >
              {{ riskStatusText(row.business_profile?.risk_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <StatusBadge :status="row.status" type="agent" />
          </template>
        </el-table-column>

        <el-table-column label="已授权项目" min-width="280">
          <template #default="{ row }">
            <div v-if="!row.authorized_projects?.length" class="no-data">
              未授权项目
            </div>

            <div v-else class="project-list">
              <el-tooltip
                v-for="p in row.authorized_projects"
                :key="projectKey(p)"
                :content="`${projectDisplayName(p)} 直属授权用户数: ${p.user_count ?? 0} 人${p.valid_until || p.auth_valid_until ? '  到期: ' + fmtDate(p.valid_until || p.auth_valid_until) : '  永久'}`"
                placement="top"
              >
                <div class="proj-badge">
                  <el-tag
                    size="small"
                    effect="light"
                    :type="p.project_type === 'game' ? 'primary' : 'info'"
                  >
                    {{ projectDisplayName(p) }}
                  </el-tag>
                  <span class="proj-user-count">{{ p.user_count ?? 0 }}人</span>
                </div>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="用户数" width="90" align="center">
          <template #default="{ row }">
            <span class="user-count">{{ row.users_count ?? 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column label="可用点数" width="150" align="right">
          <template #default="{ row }">
            <span :class="Number(row.balance?.available_total || 0) > 0 ? 'pts-positive' : 'pts-zero'">
              {{ numberText(row.balance?.available_total) }}
            </span>
            <div class="pts-detail">
              充值 {{ numberText(row.balance?.charged_balance) }} +
              授信 {{ numberText((row.balance?.credit_balance ?? 0) - (row.balance?.frozen_credit ?? 0)) }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">
            {{ row.created_at ? formatDatetime(row.created_at) : '—' }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="goDetail(row)">详情</el-button>
            <el-button text size="small" type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button
              text
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>

            <el-popconfirm
              v-if="auth.isAdmin"
              title="确认硬删除该代理？只有无下级、无直属用户、无账务历史的代理才能删除。"
              confirm-button-text="硬删除"
              cancel-button-text="取消"
              @confirm="hardDeleteAgent(row)"
            >
              <template #reference>
                <el-button text size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @size-change="loadAgents"
        @current-change="loadAgents"
      />
    </el-card>

    <AgentCreateDialog
      v-model:visible="createDialogVisible"
      :projects="allProjects"
      @created="loadAgents"
    />

    <AgentEditDrawer
      v-model:visible="editDrawerVisible"
      :agent="editingAgent"
      :projects="allProjects"
      @saved="loadAgents"
    />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import http from '@/api/http'
import { agentApi } from '@/api/agent'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { adminBalanceApi as balanceApi } from '@/api/admin/balance'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'
import { useAuthStore } from '@/stores/auth'

import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatDatetime } from '@/utils/format'
import AgentCreateDialog from './components/AgentCreateDialog.vue'
import AgentEditDrawer from './components/AgentEditDrawer.vue'

const auth = useAuthStore()
const router = useRouter()

const loading = ref(false)
const projectLoading = ref(false)
const agents = ref([])
const allProjects = ref([])
const createDialogVisible = ref(false)
const editDrawerVisible = ref(false)
const editingAgent = ref(null)

const filter = reactive({
  status: null,
  project_id: null,
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const numberText = (value) => Number(value || 0).toFixed(2)

const fmtDate = (iso) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const projectDisplayName = (project) =>
  project?.display_name ||
  project?.project_display_name ||
  project?.project_name ||
  project?.game_project_name ||
  project?.code_name ||
  project?.project_code ||
  project?.game_project_code ||
  '未命名项目'

const projectKey = (project) =>
  project?.project_id ||
  project?.id ||
  project?.game_project_id ||
  project?.code_name ||
  project?.project_code ||
  project?.game_project_code ||
  projectDisplayName(project)

const normalizeProjectList = (projects = []) =>
  projects.map((p) => ({
    ...p,
    display_name: projectDisplayName(p),
  }))

const riskStatusText = (status) => ({
  normal: '正常',
  watch: '观察',
  restricted: '限制',
  frozen: '冻结',
}[status] || '未知')

const riskStatusType = (status) => ({
  normal: 'success',
  watch: 'warning',
  restricted: 'danger',
  frozen: 'info',
}[status] || 'info')

const businessLevelText = (item) => {
  if (!item) return '—'
  const level = Number(item.tier_level)
  const levelText = Number.isFinite(level) && level > 0 ? `Lv.${level}` : ''
  const tierName = String(item.tier_name || item.level_name || '').trim()

  if (!tierName) return levelText || '—'
  if (levelText && tierName.toLowerCase().startsWith(levelText.toLowerCase())) return tierName
  return levelText ? `${levelText} · ${tierName}` : tierName
}

const loadAllProjects = async () => {
  projectLoading.value = true

  try {
    if (auth.isAdmin) {
      const res = await projectApi.list({
        page: 1,
        page_size: 100,
        is_active: true,
      })
      allProjects.value = normalizeProjectList(res.data.projects || [])
      return
    }

    const res = await agentApi.myProjects()
    allProjects.value = normalizeProjectList(Array.isArray(res.data) ? res.data : [])
  } catch {
    allProjects.value = []
  } finally {
    projectLoading.value = false
  }
}

const enrichAgentsWithProfiles = async (rows) => {
  return Promise.all(
    rows.map(async (agent) => {
      let profile = agent.business_profile || null

      if (!profile && auth.isAdmin) {
        try {
          profile = (await adminAgentProfileApi.businessProfile(agent.id)).data
        } catch {
          profile = null
        }
      }

      return {
        ...agent,
        business_profile: profile,
        authorized_projects: normalizeProjectList(
          agent.authorized_projects || agent.project_auths || []
        ),
      }
    }),
  )
}

const loadAgents = async () => {
  loading.value = true
  try {
    let rows = []

    if (auth.isAdmin) {
      const res = await balanceApi.agentsFull({
        page: pagination.page,
        page_size: pagination.pageSize,
        status: filter.status || undefined,
      })

      rows = res.data.agents || []
      pagination.total = res.data.total || 0

      if (filter.project_id) {
        rows = rows.filter((ag) =>
          (ag.project_auths || ag.authorized_projects || []).some(
            (p) => Number(projectKey(p)) === Number(filter.project_id),
          ),
        )
      }

      agents.value = await enrichAgentsWithProfiles(rows)
    } else {
      const res = await agentApi.scopeList({
        page: pagination.page,
        page_size: pagination.pageSize,
        status: filter.status || undefined,
      })

      rows = res.data.agents || []
      pagination.total = res.data.total || 0

      if (filter.project_id) {
        rows = rows.filter((ag) =>
          (ag.authorized_projects || ag.project_auths || []).some(
            (p) => Number(projectKey(p)) === Number(filter.project_id),
          ),
        )
      }

      agents.value = rows.map((row) => ({
        ...row,
        authorized_projects: normalizeProjectList(
          row.authorized_projects || row.project_auths || [],
        ),
      }))
    }
  } finally {
    loading.value = false
  }
}

const searchAgents = () => {
  pagination.page = 1
  loadAgents()
}

const resetFilter = () => {
  filter.status = null
  filter.project_id = null
  pagination.page = 1
  loadAgents()
}

const goDetail = (row) => {
  router.push(`/agents/${row.id}`)
}

const openEdit = (row) => {
  editingAgent.value = row
  editDrawerVisible.value = true
}

const toggleStatus = async (row) => {
  await agentApi.update(row.id, {
    status: row.status === 'active' ? 'suspended' : 'active',
  })
  ElMessage.success('操作成功')
  await loadAgents()
}

const formatDeleteBlockers = (detail) => {
  const blockers = detail?.blockers
  if (!blockers || typeof blockers !== 'object') {
    return typeof detail?.message === 'string'
      ? detail.message
      : '该代理存在业务关联，不能硬删除。'
  }

  const nameMap = {
    child_agents: '下级代理',
    direct_users: '直属用户',
    accounting_documents: '账务单据',
    ledger_entries: '账本流水',
    authorization_charge_snapshots: '授权扣点快照',
    reconciliation_items: '对账明细',
    adjustment_requests: '调账申请',
    monthly_bills: '月账单',
  }

  const parts = Object.entries(blockers).map(([key, value]) => {
    return `${nameMap[key] || key} ${value} 条`
  })

  return `${detail.message || '该代理存在业务关联，不能硬删除。'}阻断项：${parts.join('，')}`
}

const hardDeleteAgent = async (row) => {
  try {
    await http.delete(`/api/agents/${row.id}`)
    ElMessage.success(`代理 ${row.username} 已硬删除`)
    await loadAgents()
  } catch (error) {
    const statusCode = error.response?.status
    const detail = error.response?.data?.detail

    if (statusCode === 409) {
      ElMessage.error(formatDeleteBlockers(detail))
      return
    }

    if (typeof detail === 'string') {
      ElMessage.error(detail)
      return
    }

    ElMessage.error('删除代理失败')
  }
}

onMounted(async () => {
  await Promise.all([
    loadAllProjects(),
    loadAgents(),
  ])
})
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
  align-items: flex-start;
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
  line-height: 1.6;
}

.filter-card,
.table-card {
  border-radius: 10px;
}

.agent-link {
  border: 0;
  background: transparent;
  padding: 0;
  color: #2563eb;
  cursor: pointer;
  font-weight: 600;
}

.agent-link:hover {
  text-decoration: underline;
}

.agent-id,
.pts-detail {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 4px;
}

.no-data {
  color: #94a3b8;
  font-size: 12px;
}

.project-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.proj-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.proj-user-count {
  color: #2563eb;
  font-size: 12px;
}

.user-count {
  font-weight: 600;
}

.pts-positive {
  color: #059669;
  font-weight: 600;
}

.pts-zero {
  color: #94a3b8;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>