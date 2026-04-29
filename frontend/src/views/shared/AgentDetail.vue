<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <div class="breadcrumb-line">
          <el-button text size="small" @click="$router.push('/agents')">← 返回代理管理</el-button>
        </div>
        <h2>代理详情</h2>
        <p class="page-desc">
          详情页用于查看代理主体、业务画像、下级代理、用户统计、项目授权、点数余额和最近流水。
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
            <div class="stat-label">直属用户数</div>
          </div>
        </el-col>

        <el-col :span="4">
          <div class="stat-card">
            <div class="stat-num">{{ scopeUserCount }}</div>
            <div class="stat-label">权限范围用户</div>
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

              <el-table-column label="直属用户" width="100" align="center" prop="users_count" />
              <el-table-column label="子树用户" width="100" align="center" prop="subtree_user_count" />

              <el-table-column label="下级数量" width="100" align="center">
                <template #default="{ row }">{{ row.children?.length || 0 }}</template>
              </el-table-column>
            </el-table>
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
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能说明:
 *   管理员查看代理详情：
 *     - 代理基础信息
 *     - 业务画像
 *     - 下级代理统计
 *     - 用户统计
 *     - 项目授权
 *     - 点数余额
 *     - 最近流水
 *
 * 当前边界:
 *   - 本页先做详情展示。
 *   - 密码修改、项目授权、点数操作后续统一进入代理编辑抽屉。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '@/api/agent'
import { balanceApi } from '@/api/balance'
import { projectApi } from '@/api/project'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'
import { formatDatetime } from '@/utils/format'

const route = useRoute()

const loading = ref(false)
const activeTab = ref('overview')

const agent = ref(null)
const profile = ref(null)
const subtree = ref(null)
const balance = ref(null)
const projectAuths = ref([])
const transactions = ref([])

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

.amt-pos {
  color: #10b981;
  font-weight: 700;
}

.amt-neg {
  color: #ef4444;
  font-weight: 700;
}
</style>