<template>
  <div class="page">
    <div class="page-header">
      <div class="header-left">
        <h2>设备监控</h2>
        <!-- 当按用户过滤时显示面包屑 -->
        <template v-if="filterUserId">
          <el-divider direction="vertical" />
          <span class="filter-label">
            <el-icon><User /></el-icon>
            用户：{{ filterUsername }}
          </span>
          <el-button text size="small" @click="clearUserFilter">查看全部</el-button>
        </template>
      </div>
      <div class="header-right" v-if="!notSupported">
        <el-tag type="success" effect="plain">每 10 秒自动刷新</el-tag>
        <el-button :icon="Refresh" @click="refresh" :loading="loading">立即刷新</el-button>
      </div>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-if="error"
      :title="String(error)"
      type="error"
      show-icon
      :closable="false"
      style="border-radius:8px"
    />

    <!-- 设备表格 -->
    <template>
      <!-- 统计行 -->
      <el-row :gutter="12">
        <el-col :span="6">
          <div class="stat-card total">
            <div class="stat-num">{{ summary.total }}</div>
            <div class="stat-lbl">总设备数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card online">
            <div class="stat-num">{{ summary.online_count }}</div>
            <div class="stat-lbl">在线</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card offline">
            <div class="stat-num">{{ summary.total - summary.online_count }}</div>
            <div class="stat-lbl">离线</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card running">
            <div class="stat-num">{{ runningCount }}</div>
            <div class="stat-lbl">运行中</div>
          </div>
        </el-col>
      </el-row>

      <!-- 过滤 + 表格 -->
      <el-card shadow="never" class="table-card">
        <div class="table-toolbar">
          <el-radio-group v-model="statusFilter" size="small">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button label="online">在线</el-radio-button>
            <el-radio-button label="offline">离线</el-radio-button>
            <el-radio-button label="running">运行中</el-radio-button>
            <el-radio-button label="error">异常</el-radio-button>
          </el-radio-group>
        </div>

        <el-table
          v-loading="loading"
          :data="filteredDevices"
          row-key="device_id"
          stripe
          style="width:100%"
          @row-click="openDetail"
        >
          <el-table-column width="50" align="center">
            <template #default="{ row }">
              <span :class="['indicator', row.is_online ? 'on' : 'off']"></span>
            </template>
          </el-table-column>
          <el-table-column prop="device_id" label="设备指纹" min-width="200" show-overflow-tooltip />
          <el-table-column label="运行状态" width="100">
            <template #default="{ row }">
              <StatusBadge :status="row.status || 'offline'" type="device" :is-online="row.is_online" />
            </template>
          </el-table-column>
          <el-table-column label="最后心跳" width="130">
            <template #default="{ row }">
              <span :class="{ 'text-muted': !row.is_online }">
                {{ formatRelativeTime(row.last_seen) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_online ? 'success' : 'info'" effect="plain" size="small">
                {{ row.is_online ? 'Redis' : 'DB' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="自定义数据" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="game-data">{{ row.game_data ? JSON.stringify(row.game_data) : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click.stop="openDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawer.visible" title="设备详情" size="420px" destroy-on-close>
      <div v-if="drawer.loading" style="padding:16px">
        <el-skeleton :rows="6" animated />
      </div>
      <div v-else-if="drawer.data" style="padding:0 4px">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="设备指纹">
            <span class="mono">{{ drawer.data.device_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="运行状态">
            <StatusBadge :status="drawer.data.status || 'offline'" type="device" :is-online="drawer.data.is_online" />
          </el-descriptions-item>
          <el-descriptions-item label="最后心跳">{{ formatDatetime(drawer.data.last_seen) }}</el-descriptions-item>
          <el-descriptions-item label="数据来源">{{ drawer.data.source }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:20px">
          <div class="section-title">游戏自定义数据 (game_data)</div>
          <pre class="game-data-json">{{ JSON.stringify(drawer.data.game_data, null, 2) }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh, User } from '@element-plus/icons-vue'
import { useDevicePoller } from '@/composables/useDevicePoller'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatRelativeTime, formatDatetime } from '@/utils/format'

const route  = useRoute()
const router = useRouter()

// ── 用户过滤参数（从路由 query 读取）─────────────────────────
const filterUserId   = ref(route.query.user_id ? Number(route.query.user_id) : null)
const filterUsername = ref(route.query.username ?? '')

// query 参数变化时同步更新（同一组件路由复用时触发）
watch(() => route.query, (q) => {
  filterUserId.value   = q.user_id ? Number(q.user_id) : null
  filterUsername.value = q.username ?? ''
})

const clearUserFilter = () => {
  router.push('/devices')
}

const { devices, summary, loading, error, notSupported, refresh } = useDevicePoller(filterUserId)

// ── 状态过滤 ─────────────────────────────────────────────────
const statusFilter = ref('')

const filteredDevices = computed(() => {
  if (!statusFilter.value) return devices.value
  if (statusFilter.value === 'online')  return devices.value.filter(d => d.is_online)
  if (statusFilter.value === 'offline') return devices.value.filter(d => !d.is_online)
  return devices.value.filter(d => d.status === statusFilter.value)
})

const runningCount = computed(() => devices.value.filter(d => d.status === 'running').length)

// ── 详情抽屉 ─────────────────────────────────────────────────
// 后台设备列表本身已经返回详情所需字段，不再调用 /api/device/data。
// /api/device/data 是 User Token 终端接口，Admin / Agent 后台直接调用会 401。
const drawer = ref({ visible: false, loading: false, data: null })

const openDetail = async (row) => {
  drawer.value = {
    visible: true,
    loading: false,
    data: { ...row },
  }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 10px; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }
.header-right { display: flex; align-items: center; gap: 12px; }
.filter-label { font-size: 13px; color: #475569; display: flex; align-items: center; gap: 4px; }

.not-supported-card { border-radius: 10px; min-height: 280px; }
.ns-title { font-size: 15px; font-weight: 600; color: #1e293b; margin: 8px 0 6px; }
.ns-desc  { font-size: 13px; color: #64748b; line-height: 1.8; }
.ns-desc code { background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 12px; }

.stat-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.07); border-left: 4px solid transparent;
}
.stat-card.total   { border-color: #6366f1; }
.stat-card.online  { border-color: #10b981; }
.stat-card.offline { border-color: #94a3b8; }
.stat-card.running { border-color: #f59e0b; }
.stat-num { font-size: 28px; font-weight: 700; color: #1e293b; line-height: 1; }
.stat-lbl { font-size: 12px; color: #64748b; margin-top: 4px; }

.table-card { border-radius: 10px; }
.table-toolbar { margin-bottom: 14px; }

.indicator { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
.indicator.on  { background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,.2); }
.indicator.off { background: #94a3b8; }

.text-muted { color: #94a3b8; }
.game-data  { font-size: 12px; color: #64748b; font-family: monospace; }
.mono       { font-family: monospace; font-size: 12px; word-break: break-all; }
.section-title { font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 8px; }
.game-data-json {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 12px; font-size: 12px; color: #334155;
  overflow-x: auto; white-space: pre-wrap; word-break: break-all;
  max-height: 400px; overflow-y: auto;
}
:deep(.el-table__row) { cursor: pointer; }
</style>