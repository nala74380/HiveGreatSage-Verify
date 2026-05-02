<template>
  <div class="dashboard">

    <!-- 顶部统计卡片 -->
    <el-row :gutter="16">
      <el-col :span="auth.isAdmin ? 6 : 12" v-for="card in topCards" :key="card.label">
        <div class="stat-card" :style="{ borderTopColor: card.color }">
          <div class="stat-left">
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-label">{{ card.label }}</div>
            <div v-if="card.sub" class="stat-sub">{{ card.sub }}</div>
          </div>
          <div class="stat-icon" :style="{ background: card.color + '18', color: card.color }">
            <el-icon size="22"><component :is="card.icon" /></el-icon>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第二行：用户级别分布 + 最近注册用户 -->
    <el-row :gutter="16" v-if="auth.isAdmin">
      <!-- 用户级别分布 -->
      <el-col :span="8">
        <el-card shadow="never" class="inner-card">
          <template #header>
            <span class="card-title">用户级别分布</span>
          </template>
          <div v-if="levelLoading" class="chart-loading">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else class="level-bars">
            <div
              v-for="item in levelDistribution"
              :key="item.level"
              class="level-row"
            >
              <div class="level-meta">
                <el-tag
                  effect="dark" size="small"
                  :style="{ backgroundColor: item.color, borderColor: item.color }"
                >{{ item.label }}</el-tag>
                <span class="level-count">{{ item.count }}</span>
              </div>
              <el-progress
                :percentage="item.pct"
                :color="item.color"
                :stroke-width="8"
                :show-text="false"
              />
            </div>
            <div class="level-total">共 {{ totalUsers }} 名用户</div>
          </div>
        </el-card>
      </el-col>

      <!-- 最近注册用户 -->
      <el-col :span="16">
        <el-card shadow="never" class="inner-card">
          <template #header>
            <div class="card-header-row">
              <span class="card-title">最近注册用户</span>
              <router-link to="/users" class="view-all">查看全部 →</router-link>
            </div>
          </template>
          <div v-if="recentLoading">
            <el-skeleton :rows="4" animated />
          </div>
          <el-table
            v-else
            :data="recentUsers"
            size="small"
            :show-header="true"
          >
            <el-table-column prop="username" label="用户名" min-width="130" />
            <el-table-column label="级别" width="75">
              <template #default="{ row }">
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <StatusBadge :status="row.status" type="user" />
              </template>
            </el-table-column>
            <el-table-column label="到期时间" min-width="120">
              <template #default="{ row }">
              </template>
            </el-table-column>
            <el-table-column label="注册时间" min-width="120">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="" width="60" align="right">
              <template #default="{ row }">
                <router-link :to="`/users/${row.id}`" class="detail-link">详情</router-link>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 设备实时状态 -->
    <el-card shadow="never" class="inner-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">设备实时状态</span>
          <el-tag v-if="!notSupported" type="success" effect="plain" size="small">
            每 10 秒自动刷新
          </el-tag>
        </div>
      </template>

      <el-empty
        v-if="notSupported"
        description="设备监控需要终端用户 Token，管理员/代理视角的设备总览将在 Phase 2 开放"
        :image-size="80"
      />
      <div v-else-if="deviceLoading && devices.length === 0">
        <el-skeleton :rows="3" animated />
      </div>
      <div v-else>
        <!-- 在线概览 bar -->
        <div class="device-overview">
          <div class="device-stat-item">
            <span class="dot online"></span>
            <span class="ds-val">{{ deviceSummary.online_count }}</span>
            <span class="ds-lbl">在线</span>
          </div>
          <div class="device-stat-item">
            <span class="dot offline"></span>
            <span class="ds-val">{{ deviceSummary.total - deviceSummary.online_count }}</span>
            <span class="ds-lbl">离线</span>
          </div>
          <div class="device-stat-item">
            <span class="dot running"></span>
            <span class="ds-val">{{ devices.filter(d => d.status === 'running').length }}</span>
            <span class="ds-lbl">运行中</span>
          </div>
          <div class="online-bar-wrap">
            <el-progress
              :percentage="deviceSummary.total ? Math.round(deviceSummary.online_count / deviceSummary.total * 100) : 0"
              :stroke-width="10"
              color="#10b981"
              :show-text="false"
              style="flex:1"
            />
            <span class="online-pct">
              在线率 {{ deviceSummary.total ? Math.round(deviceSummary.online_count / deviceSummary.total * 100) : 0 }}%
            </span>
          </div>
        </div>

        <el-table :data="devices.slice(0, 8)" size="small" style="width:100%">
          <el-table-column width="44" align="center">
            <template #default="{ row }">
              <span :class="['led', row.is_online ? 'on' : 'off']"></span>
            </template>
          </el-table-column>
          <el-table-column prop="device_id" label="设备指纹" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <StatusBadge :status="row.status || 'offline'" type="device" :is-online="row.is_online" />
            </template>
          </el-table-column>
          <el-table-column label="最后心跳" min-width="120">
            <template #default="{ row }">
              <span :class="{ 'text-muted': !row.is_online }">
                {{ formatRelativeTime(row.last_seen) }}
              </span>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="devices.length > 8" class="more-hint">
          仅展示前 8 台，<router-link to="/devices">查看全部 {{ deviceSummary.total }} 台 →</router-link>
        </div>
      </div>
    </el-card>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { User, Share, Monitor, Grid, Key } from '@element-plus/icons-vue'
import { useAuthStore }    from '@/stores/auth'
import { agentApi }        from '@/api/agent'
import { userApi }         from '@/api/user'
import { useDevicePoller } from '@/composables/useDevicePoller'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatRelativeTime, formatDate } from '@/utils/format'
import { USER_LEVEL_MAP } from '@/utils/format'

const auth = useAuthStore()
const { devices, summary: deviceSummary, loading: deviceLoading, notSupported } = useDevicePoller()

// ── 顶部统计 ─────────────────────────────────────────────────
const stats       = ref({ total_users: 0, total_agents: 0, active_projects: 0 })
const statsLoaded = ref(false)

const topCards = computed(() => {
  if (auth.isAdmin) {
    return [
      {
        label: '用户总数',
        value: stats.value.total_users,
        sub:   '所有状态',
        icon:  User,
        color: '#2563eb',
      },
      {
        label: '代理总数',
        value: stats.value.total_agents,
        sub:   '所有层级',
        icon:  Share,
        color: '#f59e0b',
      },
      {
        label: '活跃项目',
        value: stats.value.active_projects,
        sub:   '已启用',
        icon:  Grid,
        color: '#8b5cf6',
      },
      {
        label: '在线设备',
        value: notSupported.value ? '—' : deviceSummary.value.online_count,
        sub:   notSupported.value ? 'Phase 2' : `共 ${deviceSummary.value.total} 台`,
        icon:  Monitor,
        color: '#10b981',
      },
    ]
  }
  return [
    {
      label: '我的用户',
      value: stats.value.total_users,
      icon:  User,
      color: '#2563eb',
    },
    {
      label: '在线设备',
      value: notSupported.value ? '—' : deviceSummary.value.online_count,
      sub:   notSupported.value ? 'Phase 2' : `共 ${deviceSummary.value.total} 台`,
      icon:  Monitor,
      color: '#10b981',
    },
  ]
})

// ── 用户级别分布 ─────────────────────────────────────────────
const levelLoading     = ref(false)
const levelDistribution = ref([])
const totalUsers        = ref(0)

const loadLevelDistribution = async () => {
  if (!auth.isAdmin) return
  levelLoading.value = true
  try {
    // 并发拉取各级别计数
    const levels = ['trial', 'normal', 'vip', 'svip', 'tester']
    const results = await Promise.all(
      levels.map(l => userApi.list({ page: 1, page_size: 1, level: l }))
    )
    const counts = results.map(r => r.data.total)
    const total  = counts.reduce((a, b) => a + b, 0)
    totalUsers.value = total

    levelDistribution.value = levels.map((l, i) => ({
      level:  l,
      label:  USER_LEVEL_MAP[l]?.label ?? l,
      color:  USER_LEVEL_MAP[l]?.color ?? '#909399',
      count:  counts[i],
      pct:    total > 0 ? Math.round(counts[i] / total * 100) : 0,
    }))
  } finally {
    levelLoading.value = false
  }
}

// ── 最近注册用户 ─────────────────────────────────────────────
const recentLoading = ref(false)
const recentUsers   = ref([])

const loadRecentUsers = async () => {
  if (!auth.isAdmin) return
  recentLoading.value = true
  try {
    const res = await userApi.list({ page: 1, page_size: 8 })
    recentUsers.value = res.data.users
  } finally {
    recentLoading.value = false
  }
}

// ── Agent 视角：自己的用户数 ──────────────────────────────────
const loadAgentStats = async () => {
  if (!auth.isAgent) return
  try {
    const res = await userApi.list({ page: 1, page_size: 1 })
    stats.value.total_users = res.data.total
  } catch { /* 静默 */ }
}

onMounted(async () => {
  if (auth.isAdmin) {
    const res = await agentApi.dashboard().catch(() => ({ data: {} }))
    stats.value = { ...stats.value, ...res.data }
    await Promise.all([loadLevelDistribution(), loadRecentUsers()])
  } else {
    await loadAgentStats()
  }
})
</script>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }

/* 顶部统计卡片 */
.stat-card {
  background: #fff; border-radius: 10px; padding: 20px 24px;
  display: flex; align-items: center; justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0,0,0,.07);
  border-top: 3px solid transparent;
}
.stat-left { display: flex; flex-direction: column; gap: 4px; }
.stat-value { font-size: 28px; font-weight: 700; color: #1e293b; line-height: 1; }
.stat-label { font-size: 13px; color: #64748b; }
.stat-sub   { font-size: 11px; color: #94a3b8; }
.stat-icon  {
  width: 48px; height: 48px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

/* 卡片通用 */
.inner-card { border-radius: 10px; }
.card-title { font-size: 14px; font-weight: 600; color: #1e293b; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.view-all { font-size: 12px; color: #2563eb; text-decoration: none; }
.view-all:hover { text-decoration: underline; }
.detail-link { font-size: 12px; color: #2563eb; text-decoration: none; }

/* 级别分布 */
.level-bars { display: flex; flex-direction: column; gap: 14px; padding: 4px 0; }
.level-row  { display: flex; flex-direction: column; gap: 5px; }
.level-meta { display: flex; align-items: center; justify-content: space-between; }
.level-count { font-size: 13px; font-weight: 600; color: #1e293b; }
.level-total { font-size: 12px; color: #94a3b8; text-align: right; margin-top: 4px; }
.chart-loading { padding: 8px 0; }

/* 设备概览 */
.device-overview {
  display: flex; align-items: center; gap: 20px;
  margin-bottom: 14px; padding: 12px 16px;
  background: #f8fafc; border-radius: 8px;
}
.device-stat-item { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.ds-val  { font-size: 18px; font-weight: 700; color: #1e293b; }
.ds-lbl  { font-size: 12px; color: #64748b; }

.dot {
  width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex-shrink: 0;
}
.dot.online  { background: #10b981; box-shadow: 0 0 0 2px rgba(16,185,129,.2); }
.dot.offline { background: #94a3b8; }
.dot.running { background: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,.2); }

.online-bar-wrap {
  flex: 1; display: flex; align-items: center; gap: 10px; min-width: 0;
}
.online-pct { font-size: 12px; color: #64748b; flex-shrink: 0; }

.led {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
}
.led.on  { background: #10b981; box-shadow: 0 0 0 2px rgba(16,185,129,.25); }
.led.off { background: #94a3b8; }

.text-muted  { color: #94a3b8; font-size: 12px; }
.text-danger { color: #ef4444; }

.more-hint { text-align: center; color: #94a3b8; font-size: 12px; margin-top: 10px; }
.more-hint a { color: #2563eb; text-decoration: none; }
.more-hint a:hover { text-decoration: underline; }
</style>
