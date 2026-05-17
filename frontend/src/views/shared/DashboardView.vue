<template>
  <div class="dashboard">

    <!-- 行1：Admin 指标卡片 -->
    <div v-if="auth.isAdmin" class="top-cards admin-cards">
      <div class="stat-card" v-for="card in topCards" :key="card.label"
           :style="{ borderTopColor: card.color }"
           @click="card.to && router.push(card.to)">
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-label">{{ card.label }}</div>
        <div v-if="card.sub" class="stat-sub">{{ card.sub }}</div>
      </div>
    </div>

    <!-- 行2：左侧30% + 右侧70% -->
    <el-row :gutter="12" v-if="auth.isAdmin" style="margin-top:12px">
      <!-- 左：用户级别分布 + 系统健康 -->
      <el-col :span="8">
        <el-card shadow="never" class="inner-card">
          <template #header><span class="card-title">用户级别分布</span></template>
          <div v-if="levelLoading"><el-skeleton :rows="3" animated /></div>
          <div v-else class="level-bars">
            <div v-for="item in levelDistribution" :key="item.level" class="level-row">
              <div class="level-meta">
                <el-tag effect="dark" size="small" :style="{ backgroundColor: item.color, borderColor: item.color }">{{ item.label }}</el-tag>
                <span class="level-count">{{ item.count }}</span>
              </div>
              <el-progress :percentage="item.pct" :color="item.color" :stroke-width="8" :show-text="false" />
            </div>
            <div class="level-total">共 {{ totalUsers }} 名用户</div>
          </div>
        </el-card>
        <div class="health-strip">
          <span class="health-dot" :class="systemHealth?.api || 'error'"></span>API
          <span class="health-dot" :class="systemHealth?.database || 'error'"></span>DB
          <span class="health-dot" :class="systemHealth?.redis || 'error'"></span>Redis
          <span class="health-dot" :class="systemHealth?.celery || 'unknown'"></span>Celery
        </div>
      </el-col>

      <!-- 右：今日账务 + 即将到期授权 -->
      <el-col :span="16">
        <!-- 今日账务 -->
        <el-card shadow="never" class="inner-card">
          <template #header>
            <div class="card-header-row">
              <span class="card-title">今日账务</span>
              <span class="card-hint">{{ todayDate }}</span>
            </div>
          </template>
          <div class="accounting-grid">
            <div class="acct-item">
              <div class="acct-value in">+{{ fmtMoney(todayAccounting.recharge || 0) }}</div>
              <div class="acct-label">充值</div>
            </div>
            <div class="acct-item">
              <div class="acct-value in">+{{ fmtMoney(todayAccounting.credit || 0) }}</div>
              <div class="acct-label">授信</div>
            </div>
            <div class="acct-item">
              <div class="acct-value out">-{{ fmtMoney(todayAccounting.consume || 0) }}</div>
              <div class="acct-label">消耗</div>
            </div>
            <div class="acct-item">
              <div class="acct-value in">+{{ fmtMoney(todayAccounting.refund || 0) }}</div>
              <div class="acct-label">返点</div>
            </div>
            <div class="acct-item">
              <div class="acct-value freeze">-{{ fmtMoney(todayAccounting.freeze || 0) }}</div>
              <div class="acct-label">冻结</div>
            </div>
            <div class="acct-item">
              <div class="acct-value in">+{{ fmtMoney(todayAccounting.unfreeze || 0) }}</div>
              <div class="acct-label">解冻</div>
            </div>
          </div>
        </el-card>

        <!-- 即将到期授权 -->
        <el-card shadow="never" class="inner-card" style="margin-top:12px">
          <template #header>
            <div class="card-header-row">
              <span class="card-title">即将到期授权</span>
              <router-link to="/users" class="view-all">查看全部→</router-link>
            </div>
          </template>
          <el-empty v-if="!expiringAuths.length" description="暂无7天内到期授权" :image-size="40" />
          <div v-else class="expiring-list">
            <div v-for="a in expiringAuths" :key="a.auth_id" class="expiring-row">
              <span class="expiring-user">{{ a.username }}</span>
              <LevelTag :level="a.user_level" />
              <span class="expiring-project">{{ a.project }}</span>
              <span class="expiring-date">剩 {{ daysFromNow(a.valid_until) }} 天</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 行3：项目设备概览（全宽） -->
    <el-card shadow="never" class="inner-card" style="margin-top:12px" v-if="auth.isAdmin">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">项目概览</span>
          <el-tag type="success" effect="plain" size="small">在线 {{ onlineDevices }} 台</el-tag>
        </div>
      </template>
      <el-empty v-if="!projectList.length" description="暂无激活项目" :image-size="40" />
      <div v-else class="project-row">
        <div v-for="p in projectList" :key="p.code" class="project-item">
          <span class="project-name">{{ p.display }}</span>
          <span class="project-code">{{ p.code }}</span>
        </div>
      </div>
    </el-card>

    <!-- Agent 视角 -->
    <template v-if="auth.isAgent">
      <!-- 行0：身份卡片（Lv.2+） -->
      <div v-if="agentTier >= 2" class="agent-id-card" :class="'tier-bg-' + agentTier" style="margin-top:12px">
        <div class="id-left">
          <span class="id-name">{{ agentProfile.username }}</span>
          <el-tag effect="dark" size="small" :type="tierTagType">{{ agentProfile.tier_name }}</el-tag>
          <span class="id-dot" :class="agentProfile.risk_status || 'normal'"></span>
          <span class="id-risk">{{ riskLabel }}</span>
        </div>
        <div class="id-right">
          <span>可用 <b>{{ fmtMoney(agentWallet.available_total) }}</b></span>
          <span v-if="agentTier >= 3" class="id-credit">| 授信上限 <b>{{ fmtMoney(agentWallet.max_credit_limit || agentWallet.credit_limit || 0) }}</b></span>
          <span v-if="agentSub.can_create">| 下级 <b>{{ agentSub.list.length }}/{{ agentSub.max || '—' }}</b></span>
        </div>
      </div>

      <!-- 行1：4 指标卡片 -->
      <div class="top-cards admin-cards" :style="{ marginTop: agentTier >= 2 ? '12px' : '0' }">
        <div class="stat-card" v-for="card in agentCards" :key="card.label" :style="{ borderTopColor: card.color }" @click="card.to && router.push(card.to)">
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
          <div v-if="card.sub" class="stat-sub">{{ card.sub }}</div>
        </div>
      </div>

      <!-- 行2：项目一览 + 到期预警 -->
      <el-row :gutter="12" style="margin-top:12px">
        <el-col :span="agentTier >= 2 ? 12 : 16">
          <el-card shadow="never" class="inner-card">
            <template #header><span class="card-title">项目一览</span></template>
            <el-empty v-if="!agentProjects.length" description="暂无已授权项目" :image-size="40" />
            <div v-else class="expiring-list">
              <div v-for="p in agentProjects" :key="p.code" class="expiring-row">
                <span class="expiring-user">{{ p.display }}</span>
                <span class="expiring-project">{{ p.user_count }} 用户</span>
                <span class="expiring-date">{{ p.online }} 在线</span>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="agentTier >= 2 ? 12 : 8">
          <el-card shadow="never" class="inner-card">
            <template #header><div class="card-header-row"><span class="card-title">即将到期</span><router-link to="/users" class="view-all">查看全部→</router-link></div></template>
            <el-empty v-if="!agentExpiring.length" description="暂无7天内到期授权" :image-size="40" />
            <div v-else class="expiring-list">
              <div v-for="a in agentExpiring" :key="a.user" class="expiring-row">
                <span class="expiring-user">{{ a.user }}</span>
                <LevelTag :level="a.level" />
                <span class="expiring-project">{{ a.project }}</span>
                <span class="expiring-date">剩 {{ a.days }} 天</span>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 行3：下级代理子树（Lv.2+ 且 can_create_sub_agents） -->
      <template v-if="agentTier >= 2 && agentSub.can_create">
        <!-- 下级到期预警 -->
        <el-card v-if="agentSubExpiring.length" shadow="never" class="inner-card" style="margin-top:12px">
          <template #header><div class="card-header-row"><span class="card-title">下级到期预警</span><router-link to="/agents" class="view-all">查看全部→</router-link></div></template>
          <div class="expiring-list">
            <div v-for="a in agentSubExpiring" :key="a.user" class="expiring-row">
              <span class="expiring-user">{{ a.user }}</span>
              <LevelTag :level="a.level" />
              <span class="expiring-project">{{ a.project }}</span>
              <span class="expiring-date">剩 {{ a.days }} 天</span>
              <span class="expiring-project">代理: {{ a.agent }}</span>
            </div>
          </div>
        </el-card>

        <!-- 下级列表 -->
        <el-card v-if="agentSub.list.length" shadow="never" class="inner-card" style="margin-top:12px">
          <template #header><div class="card-header-row"><span class="card-title">下级代理（{{ agentSub.list.length }}）</span></div></template>
          <div class="expiring-list">
            <div v-for="s in agentSub.list" :key="s.id" class="expiring-row">
              <span class="expiring-user">{{ s.username }}</span>
              <el-tag size="small" effect="plain">{{ s.tier_name }}</el-tag>
              <span class="expiring-project">{{ s.users }} 用户</span>
              <span class="expiring-date">{{ fmtMoney(s.balance) }} 点</span>
              <span class="expiring-project">{{ s.is_direct ? '直属' : '间接' }}</span>
            </div>
          </div>
        </el-card>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { agentApi } from '@/api/agent'
import LevelTag from '@/components/common/LevelTag.vue'
import { USER_LEVEL_MAP } from '@/utils/format'

const auth = useAuthStore()
const router = useRouter()

const stats = ref({ total_users: 0, total_agents: 0, active_projects: 0 })
const totalPoints = ref(0)
const todayNewUsers = ref(0)
const onlineDevices = ref(0)
const todayAccounting = ref({})
const todayDate = new Date().toLocaleDateString('zh-CN')
const systemHealth = ref({})
const levelDistribution = ref([])
const totalUsers = ref(0)
const levelLoading = ref(false)

// Agent state
const agentProfile = ref({ username: '', tier_level: 1, tier_name: '', risk_status: 'normal' })
const agentWallet = ref({ available_total: 0 })
const agentProjects = ref([])
const agentExpiring = ref([])
const agentSub = ref({ can_create: false, max: 0, list: [] })

const agentTier = computed(() => agentProfile.value.tier_level || 1)
const riskLabel = computed(() => ({ normal: '正常', watch: '观察中', restricted: '已限制', frozen: '已冻结' }[agentProfile.value.risk_status] || ''))
const tierTagType = computed(() => ({ 1: 'info', 2: '', 3: 'warning', 4: 'danger' }[agentTier.value] || ''))
const agentSubExpiring = ref([])
const expiringAuths = ref([])
const projectList = ref([])
const statsLoaded = ref(false)

const fmtMoney = (v) => Number(v || 0).toFixed(2)
const daysFromNow = (iso) => {
  if (!iso) return '—'
  const diff = new Date(iso).getTime() - Date.now()
  return Math.ceil(diff / 86400000)
}

const topCards = computed(() => [
  { label: '用户总数', value: stats.value.total_users, sub: `今日 +${todayNewUsers.value}`, color: '#2563eb', to: '/users' },
  { label: '代理总数', value: stats.value.total_agents, color: '#f59e0b', to: '/agents' },
  { label: '活跃项目', value: stats.value.active_projects, color: '#8b5cf6', to: '/projects' },
  { label: '在线设备', value: onlineDevices.value, color: '#10b981', to: '/devices' },
  { label: '平台点数', value: fmtMoney(totalPoints.value), color: '#f97316', to: '/accounting' },
])

const agentCards = computed(() => [
  { label: '可用点数', value: fmtMoney(agentWallet.value.available_total), color: '#f97316' },
  { label: '直属用户', value: `${agentUsers.value.active}/${agentUsers.value.total}`, color: '#2563eb' },
  { label: '在线设备', value: agentDeviceCount.value, color: '#10b981' },
  { label: '已授权项目', value: agentProjects.value.length, color: '#8b5cf6' },
])
const agentUsers = ref({ total: 0, active: 0 })
const agentDeviceCount = ref(0)

const normalizeAdminDashboard = (payload = {}) => ({
  total_users: payload.total_users || 0,
  total_agents: payload.total_agents || 0,
  active_projects: payload.active_projects || 0,
  today_new_users: payload.today_new_users || 0,
  total_points: payload.total_points || 0,
  online_devices: payload.online_devices || 0,
  today_accounting: payload.today_accounting || {},
  system_health: payload.system_health || {},
  level_distribution: payload.level_distribution || {},
  expiring_auths: payload.expiring_auths || [],
  active_projects_data: payload.active_projects_data || [],
})

const normalizeAgentDashboard = (payload = {}) => ({
  agent: payload.agent || {},
  wallet: payload.wallet || {},
  users: payload.users || { total: 0, active: 0 },
  online_devices: payload.online_devices || 0,
  projects: payload.projects || [],
  expiring_auths: payload.expiring_auths || [],
  sub_agents: payload.sub_agents || { can_create: false, list: [] },
  sub_expiring_auths: payload.sub_expiring_auths || [],
})

const loadAllStats = async () => {
  try {
    if (auth.isAdmin) {
      const res = await agentApi.dashboard()
      const d = normalizeAdminDashboard(res.data)

      stats.value = { total_users: d.total_users, total_agents: d.total_agents, active_projects: d.active_projects }
      statsLoaded.value = true
      todayNewUsers.value = d.today_new_users
      totalPoints.value = d.total_points
      onlineDevices.value = d.online_devices
      todayAccounting.value = d.today_accounting
      systemHealth.value = d.system_health

      levelLoading.value = true
      const dist = d.level_distribution
      const levels = ['trial', 'normal', 'vip', 'svip', 'tester']
      const counts = levels.map(l => dist[l] || 0)
      const total = counts.reduce((a, b) => a + b, 0)
      totalUsers.value = total
      levelDistribution.value = levels.map((l, i) => ({
        level: l, label: USER_LEVEL_MAP[l]?.label ?? l, color: USER_LEVEL_MAP[l]?.color ?? '#909399',
        count: counts[i], pct: total > 0 ? Math.round(counts[i] / total * 100) : 0,
      }))
      levelLoading.value = false

      expiringAuths.value = d.expiring_auths
      projectList.value = d.active_projects_data
    } else {
      try {
        const r = await agentApi.agentDashboard()
        const d = normalizeAgentDashboard(r.data)
        agentProfile.value = d.agent
        agentWallet.value = d.wallet
        agentUsers.value = d.users
        agentDeviceCount.value = d.online_devices
        agentProjects.value = d.projects
        agentExpiring.value = d.expiring_auths
        agentSub.value = d.sub_agents
        agentSubExpiring.value = d.sub_expiring_auths
        statsLoaded.value = true
      } catch {}
    }
  } catch {}
}

onMounted(() => { loadAllStats() })
</script>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 0; }

.top-cards { display: grid; gap: 12px; }
.top-cards.admin-cards { grid-template-columns: repeat(5, 1fr); }
.top-cards:not(.admin-cards) { grid-template-columns: repeat(2, 1fr); }

.health-strip {
  display: flex; align-items: center; gap: 12px; padding: 8px 12px;
  background: #f9fafb; border-radius: 6px; font-size: 12px; color: #6b7280;
}
.health-strip .health-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: #909399; margin-right: 3px;
}
.health-strip .health-dot.ok      { background: #10b981; }
.health-strip .health-dot.error   { background: #ef4444; }
.health-strip .health-dot.unknown { background: #f59e0b; }
.health-strip .health-dot.no_recent_flush { background: #f59e0b; }

.stat-card {
  background: #fff; border-radius: 8px; padding: 16px 18px;
  border-top: 3px solid #e5e7eb; cursor: pointer; transition: box-shadow .15s;
}
.stat-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,.08); }
.stat-value { font-size: 22px; font-weight: 700; color: #1f2937; }
.stat-label { font-size: 13px; color: #6b7280; margin-top: 2px; }
.stat-sub  { font-size: 12px; color: #9ca3af; margin-top: 1px; }

.inner-card { }
.card-title { font-size: 14px; font-weight: 600; color: #374151; }
.card-header-row { display: flex; justify-content: space-between; align-items: center; }
.card-hint { font-size: 12px; color: #9ca3af; }
.view-all { font-size: 12px; color: #2563eb; text-decoration: none; }

.level-bars { display: flex; flex-direction: column; gap: 8px; }
.level-row .level-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.level-count { font-size: 14px; font-weight: 600; color: #374151; margin-left: auto; }
.level-total { font-size: 12px; color: #9ca3af; text-align: right; padding-top: 4px; }

.accounting-grid { display: flex; gap: 20px; flex-wrap: wrap; }
.acct-item { text-align: center; min-width: 60px; }
.acct-value { font-size: 16px; font-weight: 700; }
.acct-value.in { color: #10b981; }
.acct-value.out { color: #ef4444; }
.acct-value.freeze { color: #f59e0b; }
.acct-label { font-size: 12px; color: #6b7280; margin-top: 2px; }

.expiring-list { display: flex; flex-direction: column; gap: 6px; }
.expiring-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.expiring-user { font-weight: 600; color: #1f2937; min-width: 60px; }
.expiring-project { color: #6b7280; margin-left: auto; }
.expiring-date { color: #ef4444; font-weight: 600; white-space: nowrap; }

.project-row { display: flex; gap: 12px; flex-wrap: wrap; }
.project-item { display: flex; gap: 6px; align-items: center; background: #f9fafb; border-radius: 6px; padding: 6px 12px; }
.project-name { font-size: 13px; font-weight: 600; color: #1f2937; }
.project-code { font-size: 11px; color: #9ca3af; }
.stat-big { font-size: 32px; font-weight: 700; color: #1f2937; }
.stat-sub-text { font-size: 13px; color: #6b7280; }

.agent-id-card {
  display: flex; justify-content: space-between; align-items: center;
  background: linear-gradient(135deg, #1e293b, #334155);
  color: #fff; border-radius: 8px; padding: 14px 20px;
}
.agent-id-card .id-left { display: flex; align-items: center; gap: 10px; }
.agent-id-card .id-name { font-size: 16px; font-weight: 700; }
.agent-id-card .id-right { display: flex; gap: 12px; font-size: 13px; opacity: .9; }
.agent-id-card .id-credit { opacity: .75; }
.agent-id-card .id-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin: 0 4px 0 2px; }
.agent-id-card.tier-bg-2 { background: linear-gradient(135deg, #1e3a5f, #2d5a87); }
.agent-id-card.tier-bg-3 { background: linear-gradient(135deg, #5f3a1e, #876a2d); }
.agent-id-card.tier-bg-4 { background: linear-gradient(135deg, #5f1e1e, #872d2d); }
.agent-id-card .id-dot.normal { background: #10b981; }
.agent-id-card .id-dot.watch { background: #f59e0b; }
.agent-id-card .id-dot.restricted { background: #ef4444; }
.agent-id-card .id-dot.frozen { background: #ef4444; }
.agent-id-card .id-risk { font-size: 12px; opacity: .7; }
</style>
