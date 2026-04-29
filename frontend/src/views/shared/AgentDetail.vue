<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <div class="breadcrumb-line">
          <el-button text size="small" @click="$router.push('/agents')">← 返回代理管理</el-button>
        </div>
        <h2>代理详情</h2>
        <p class="page-desc">
          详情页用于查看代理主体、业务画像、下级代理、直属用户、项目授权、点数余额和最近流水。
        </p>
      </div>

      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <template v-if="agent">
      <el-card shadow="never" class="info-card">
        <div class="agent-head">
          <div class="avatar">{{ agent.username.charAt(0).toUpperCase() }}</div>

          <div class="agent-main">
            <div class="agent-title-row">
              <span class="agent-name">{{ agent.username }}</span>

              <el-tag
                :type="agent.status === 'active' ? 'success' : 'danger'"
                effect="light"
                size="small"
              >
                {{ agent.status === 'active' ? '正常' : '已停用' }}
              </el-tag>

              <el-tag type="info" effect="plain" size="small">
                组织层级 Lv.{{ agent.level }}
              </el-tag>

              <el-tag v-if="profile" type="primary" effect="light" size="small">
                业务等级 Lv.{{ profile.tier_level }} · {{ profile.tier_name }}
              </el-tag>

              <el-tag
                v-if="profile"
                :type="riskStatusType(profile.risk_status)"
                effect="light"
                size="small"
              >
                {{ riskStatusText(profile.risk_status) }}
              </el-tag>
            </div>

            <div class="agent-sub">
              ID: {{ agent.id }}
              <span class="dot">·</span>
              创建时间：{{ formatDatetime(agent.created_at) }}
              <span class="dot">·</span>
              佣金比例：{{ agent.commission_rate === null ? '未设置' : `${agent.commission_rate}%` }}
            </div>
          </div>
        </div>

        <el-divider />

        <el-descriptions :column="3" size="small">
          <el-descriptions-item label="代理 ID">
            <span class="mono">{{ agent.id }}</span>
          </el-descriptions-item>

          <el-descriptions-item label="父代理 ID">
            <span v-if="agent.parent_agent_id" class="mono">{{ agent.parent_agent_id }}</span>
            <span v-else class="muted">顶级代理</span>
          </el-descriptions-item>

          <el-descriptions-item label="创建管理员 ID">
            <span v-if="agent.created_by_admin_id" class="mono">{{ agent.created_by_admin_id }}</span>
            <span v-else class="muted">无</span>
          </el-descriptions-item>

          <el-descriptions-item label="更新时间">
            {{ agent.updated_at ? formatDatetime(agent.updated_at) : '—' }}
          </el-descriptions-item>

          <el-descriptions-item label="业务备注">
            {{ profile?.remark || '—' }}
          </el-descriptions-item>

          <el-descriptions-item label="账号状态">
            {{ agent.status === 'active' ? '正常' : '已停用' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-row :gutter="12">
        <el-col :span="4">
          <div class="stat-card">
            <div class="stat-num">{{ directChildAgentCount }}</div>
            <div class="stat-label">直属下级代理</div>
          </div>
        </el-col>

        <el-col :span="4">
          <div class="stat-card">
            <div class="stat-num">{{ downstreamAgentCount }}</div>
            <div class="stat-label">下级代理总数</div>
          </div>
        </el-col>

        <el-col :span="4">
          <div class="stat-card">
            <div class="stat-num">{{ directUserCount }}</div>
            <div class="stat-label">有效直属用户</div>
          </div>
        </el-col>

        <el-col :span="4">
          <div class="stat-card">
            <div class="stat-num">{{ scopeUserCount }}</div>
            <div class="stat-label">有效范围用户</div>
          </div>
        </el-col>

        <el-col :span="4">
          <div class="stat-card">
            <div class="stat-num">{{ projectAuths.length }}</div>
            <div class="stat-label">已授权项目</div>
          </div>
        </el-col>

        <el-col :span="4">
          <div class="stat-card highlight">
            <div class="stat-num">{{ numberText(balance?.available_total) }}</div>
            <div class="stat-label">可用点数</div>
          </div>
        </el-col>
      </el-row>

      <el-card shadow="never" class="tab-card">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="概览" name="overview">
            <div class="overview-grid">
              <div class="overview-block">
                <div class="block-title">业务画像</div>

                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item label="业务等级">
                    <span v-if="profile">Lv.{{ profile.tier_level }} · {{ profile.tier_name }}</span>
                    <span v-else>—</span>
                  </el-descriptions-item>

                  <el-descriptions-item label="风险状态">
                    <el-tag
                      v-if="profile"
                      :type="riskStatusType(profile.risk_status)"
                      size="small"
                      effect="light"
                    >
                      {{ riskStatusText(profile.risk_status) }}
                    </el-tag>
                    <span v-else>—</span>
                  </el-descriptions-item>

                  <el-descriptions-item label="默认授信">
                    {{ numberText(profile?.credit_limit) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="最高授信">
                    {{ numberText(profile?.max_credit_limit) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="可创建下级">
                    {{ profile?.can_create_sub_agents ? '允许' : '不允许' }}
                  </el-descriptions-item>

                  <el-descriptions-item label="最大下级数">
                    {{ profile?.max_sub_agents ?? 0 }}
                  </el-descriptions-item>

                  <el-descriptions-item label="自动开通项目">
                    {{ profile?.can_auto_open_project ? '允许' : '不允许' }}
                  </el-descriptions-item>

                  <el-descriptions-item label="自动开通上限">
                    {{ profile?.auto_open_project_limit ?? 0 }}
                  </el-descriptions-item>
                </el-descriptions>
              </div>

              <div class="overview-block">
                <div class="block-title">点数余额</div>

                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item label="充值点数">
                    {{ numberText(balance?.charged_points) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="授信点数">
                    {{ numberText(balance?.credit_points) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="冻结授信">
                    {{ numberText(balance?.frozen_credit) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="可用授信">
                    {{ numberText(balance?.available_credit) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="可用总点数">
                    {{ numberText(balance?.available_total) }}
                  </el-descriptions-item>

                  <el-descriptions-item label="累计消耗">
                    {{ numberText(balance?.total_consumed) }}
                  </el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="下级代理" name="children">
            <el-alert
              title="直属下级只包含当前代理直接创建或直接挂载的下一级代理；下级代理总数不包含当前代理本身。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-table :data="childAgentRows" size="small" stripe empty-text="暂无下级代理">
              <el-table-column label="代理名" min-width="160">
                <template #default="{ row }">
                  <button class="link-button" type="button" @click="$router.push(`/agents/${row.id}`)">
                    {{ row.username }}
                  </button>
                  <div class="small-muted">ID: {{ row.id }}</div>
                </template>
              </el-table-column>

              <el-table-column label="组织层级" width="90">
                <template #default="{ row }">Lv.{{ row.level }}</template>
              </el-table-column>

              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small" effect="light">
                    {{ row.status === 'active' ? '正常' : '已停用' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="有效直属用户" width="120" align="center" prop="users_count" />
              <el-table-column label="有效子树用户" width="120" align="center" prop="subtree_user_count" />

              <el-table-column label="下级数量" width="100" align="center">
                <template #default="{ row }">{{ row.children?.length || 0 }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="直属用户" name="direct-users">
            <el-alert
              title="直属用户只统计 created_by_agent_id 等于当前代理 ID 且未软删除的用户；不包含下级代理创建的用户。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-table
              v-loading="directUsersLoading"
              :data="directUsers"
              size="small"
              stripe
              empty-text="暂无直属用户"
            >
              <el-table-column label="用户名" min-width="160">
                <template #default="{ row }">
                  <button
                    class="link-button"
                    type="button"
                    @click="$router.push(`/users/${row.id}`)"
                  >
                    {{ row.username }}
                  </button>
                  <div class="small-muted">ID: {{ row.id }}</div>
                </template>
              </el-table-column>

              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="userStatusType(row.status)" size="small" effect="light">
                    {{ userStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="用户等级" width="100">
                <template #default="{ row }">
                  {{ userLevelText(row.level || row.user_level) }}
                </template>
              </el-table-column>

              <el-table-column label="授权项目" min-width="220">
                <template #default="{ row }">
                  <template v-if="getUserAuths(row).length">
                    <div class="auth-tags">
                      <el-tag
                        v-for="auth in getUserAuths(row).slice(0, 3)"
                        :key="auth.id || auth.authorization_id || auth.project_id"
                        size="small"
                        effect="plain"
                        :type="auth.status === 'active' ? 'success' : 'info'"
                      >
                        {{ auth.project_display_name || auth.project_name || auth.display_name || auth.game_name || '项目' }}
                      </el-tag>
                      <span v-if="getUserAuths(row).length > 3" class="small-muted">
                        +{{ getUserAuths(row).length - 3 }}
                      </span>
                    </div>
                  </template>
                  <span v-else class="muted">暂无授权</span>
                </template>
              </el-table-column>

              <el-table-column label="授权数" width="90" align="center">
                <template #default="{ row }">
                  {{ getUserAuths(row).length }}
                </template>
              </el-table-column>

              <el-table-column label="有效授权" width="90" align="center">
                <template #default="{ row }">
                  {{ getActiveUserAuthCount(row) }}
                </template>
              </el-table-column>

              <el-table-column label="创建时间" width="160">
                <template #default="{ row }">
                  {{ row.created_at ? formatDatetime(row.created_at) : '—' }}
                </template>
              </el-table-column>

              <el-table-column label="操作" width="90" fixed="right">
                <template #default="{ row }">
                  <el-button text size="small" @click="$router.push(`/users/${row.id}`)">
                    详情
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-pagination
              v-model:current-page="directUsersPagination.page"
              v-model:page-size="directUsersPagination.pageSize"
              :total="directUsersPagination.total"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              class="pagination"
              @size-change="loadDirectUsers"
              @current-change="loadDirectUsers"
            />
          </el-tab-pane>

          <el-tab-pane label="项目授权" name="projects">
            <el-table :data="projectAuths" size="small" stripe empty-text="暂无项目授权">
              <el-table-column label="项目名称" min-width="160">
                <template #default="{ row }">
                  {{ row.project_display_name || row.project_name || row.display_name || '—' }}
                </template>
              </el-table-column>

              <el-table-column label="项目代码" width="140">
                <template #default="{ row }">
                  <span class="mono">{{ row.project_code_name || row.project_code || row.code_name || '—' }}</span>
                </template>
              </el-table-column>

              <el-table-column label="类型" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.project_type === 'game' ? 'primary' : 'info'" size="small" effect="plain">
                    {{ row.project_type === 'game' ? '游戏' : '验证' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="到期时间" width="180">
                <template #default="{ row }">
                  {{ row.valid_until ? formatDatetime(row.valid_until) : '永久' }}
                </template>
              </el-table-column>

              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                    {{ row.status === 'active' ? '有效' : '已停用' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="最近流水" name="transactions">
            <el-table :data="transactions" size="small" stripe empty-text="暂无流水记录">
              <el-table-column label="时间" width="160">
                <template #default="{ row }">{{ row.created_at ? formatDatetime(row.created_at) : '—' }}</template>
              </el-table-column>

              <el-table-column label="类型" width="90">
                <template #default="{ row }">
                  <el-tag size="small" effect="light">
                    {{ row.tx_type_label || row.tx_type }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="余额类型" width="100">
                <template #default="{ row }">
                  {{ row.balance_type_label || row.balance_type }}
                </template>
              </el-table-column>

              <el-table-column label="变动" width="110" align="right">
                <template #default="{ row }">
                  <span :class="Number(row.amount || 0) >= 0 ? 'amt-pos' : 'amt-neg'">
                    {{ Number(row.amount || 0) >= 0 ? '+' : '' }}{{ numberText(row.amount) }}
                  </span>
                </template>
              </el-table-column>

              <el-table-column label="变后余额" width="110" align="right">
                <template #default="{ row }">{{ numberText(row.balance_after) }}</template>
              </el-table-column>

              <el-table-column label="业务说明" min-width="260" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.business_text || row.description || '—' }}
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </template>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/AgentDetail.vue
 * 名称: 代理详情页
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.1.0
 * 功能说明:
 *   管理员查看代理详情：
 *     - 代理基础信息
 *     - 业务画像
 *     - 下级代理统计
 *     - 直属用户
 *     - 用户统计
 *     - 项目授权
 *     - 点数余额
 *     - 最近流水
 *
 * 当前边界:
 *   - 本页展示“直属用户”，不混入下级代理用户。
 *   - 权限范围用户只作为统计展示。
 *   - 密码修改、项目授权、点数操作由代理管理统一编辑抽屉承担。
 */

import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '@/api/agent'
import { userApi } from '@/api/user'
import { balanceApi } from '@/api/balance'
import { projectApi } from '@/api/project'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'
import { formatDatetime } from '@/utils/format'

const route = useRoute()

const loading = ref(false)
const directUsersLoading = ref(false)
const activeTab = ref('overview')

const agent = ref(null)
const profile = ref(null)
const subtree = ref(null)
const balance = ref(null)
const projectAuths = ref([])
const transactions = ref([])
const directUsers = ref([])

const directUsersPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const agentId = computed(() => Number(route.params.id))

const numberText = (value) => Number(value || 0).toFixed(2)

const riskStatusText = (status) => {
  const map = {
    normal: '正常',
    watch: '观察',
    restricted: '限制',
    frozen: '冻结',
  }
  return map[status] || '未知'
}

const riskStatusType = (status) => {
  const map = {
    normal: 'success',
    watch: 'warning',
    restricted: 'danger',
    frozen: 'info',
  }
  return map[status] || 'info'
}

const userStatusText = (status) => {
  const map = {
    active: '正常',
    suspended: '停用',
    expired: '过期',
  }
  return map[status] || status || '未知'
}

const userStatusType = (status) => {
  const map = {
    active: 'success',
    suspended: 'danger',
    expired: 'warning',
  }
  return map[status] || 'info'
}

const userLevelText = (level) => {
  const map = {
    trial: '试用',
    normal: '普通',
    vip: 'VIP',
    svip: 'SVIP',
    tester: '测试',
  }
  return map[level] || level || '—'
}

const getUserAuths = (row) => {
  if (Array.isArray(row.authorizations)) return row.authorizations
  if (Array.isArray(row.auths)) return row.auths
  if (Array.isArray(row.projects)) return row.projects
  if (Array.isArray(row.authorized_projects)) return row.authorized_projects
  return []
}

const getActiveUserAuthCount = (row) => {
  return getUserAuths(row).filter(item => item.status === 'active').length
}

const directChildAgentCount = computed(() => {
  return subtree.value?.root?.children?.length || 0
})

const downstreamAgentCount = computed(() => {
  return Math.max(Number(subtree.value?.total_agents || 0) - 1, 0)
})

const directUserCount = computed(() => {
  return subtree.value?.root?.users_count || agent.value?.users_count || 0
})

const scopeUserCount = computed(() => {
  return subtree.value?.total_users || 0
})

const childAgentRows = computed(() => {
  return subtree.value?.root?.children || []
})

const loadDirectUsers = async () => {
  if (!agentId.value) return

  directUsersLoading.value = true

  try {
    const res = await userApi.list({
      creator_agent_id: agentId.value,
      page: directUsersPagination.page,
      page_size: directUsersPagination.pageSize,
    })

    directUsers.value = res.data.users || []
    directUsersPagination.total = res.data.total || 0
  } finally {
    directUsersLoading.value = false
  }
}

const loadAll = async () => {
  if (!agentId.value) return

  loading.value = true

  try {
    const [
      detailRes,
      profileRes,
      subtreeRes,
      balanceRes,
      authRes,
      txRes,
    ] = await Promise.all([
      agentApi.detail(agentId.value),
      adminAgentProfileApi.businessProfile(agentId.value),
      agentApi.subtree(agentId.value),
      balanceApi.getBalance(agentId.value),
      projectApi.listAgentAuths(agentId.value),
      balanceApi.getTransactions(agentId.value, { page: 1, page_size: 20 }),
    ])

    agent.value = detailRes.data
    profile.value = profileRes.data
    subtree.value = subtreeRes.data
    balance.value = balanceRes.data
    projectAuths.value = Array.isArray(authRes.data) ? authRes.data : []
    transactions.value = txRes.data?.transactions || []

    directUsersPagination.page = 1
    await loadDirectUsers()
  } catch (error) {
    ElMessage.error('加载代理详情失败')
    throw error
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

watch(
  () => route.params.id,
  () => {
    activeTab.value = 'overview'
    directUsersPagination.page = 1
    loadAll()
  }
)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.breadcrumb-line {
  margin-bottom: 4px;
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

.header-actions {
  display: flex;
  gap: 8px;
}

.info-card,
.tab-card {
  border-radius: 10px;
}

.agent-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.avatar {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 800;
  flex-shrink: 0;
}

.agent-main {
  flex: 1;
}

.agent-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-name {
  font-size: 20px;
  font-weight: 800;
  color: #1e293b;
}

.agent-sub {
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}

.dot {
  margin: 0 6px;
  color: #cbd5e1;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

.muted,
.small-muted {
  color: #94a3b8;
  font-size: 12px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  border-left: 4px solid #6366f1;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
}

.stat-card.highlight {
  border-left-color: #10b981;
}

.stat-num {
  font-size: 24px;
  font-weight: 800;
  color: #1e293b;
  line-height: 1;
}

.stat-label {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.overview-block {
  min-width: 0;
}

.block-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 10px;
}

.inner-alert {
  margin-bottom: 12px;
  border-radius: 8px;
}

.link-button {
  appearance: none;
  border: none;
  background: transparent;
  color: #2563eb;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
}

.link-button:hover {
  text-decoration: underline;
}

.auth-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.amt-pos {
  color: #10b981;
  font-weight: 700;
}

.amt-neg {
  color: #ef4444;
  font-weight: 700;
}
</style>