<template>
  <div class="page">
    <div class="page-header">
      <div class="header-left">
        <div>
          <h2>设备监控</h2>
          <p class="page-desc">
            查看平台设备绑定、在线状态、心跳时间、运行状态、项目归属与实时运行数据。
          </p>
        </div>

        <template v-if="filterUserId">
          <el-divider direction="vertical" />
          <span class="filter-label">
            <el-icon><User /></el-icon>
            用户：{{ filterUsername || filterUserId }}
          </span>
          <el-button text size="small" @click="clearUserFilter">
            查看全部
          </el-button>
        </template>
      </div>

      <div class="header-right">
        <el-switch
          v-model="autoRefresh"
          inline-prompt
          active-text="自动"
          inactive-text="手动"
        />
        <el-tag v-if="autoRefresh" type="success" effect="plain">
          每 10 秒自动刷新
        </el-tag>
        <el-button :icon="Refresh" @click="loadDevices" :loading="loading">
          立即刷新
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="error"
      :title="String(error)"
      type="error"
      show-icon
      :closable="false"
      class="top-alert"
    />

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
          <div class="stat-lbl">在线设备</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card offline">
          <div class="stat-num">{{ summary.offline_count }}</div>
          <div class="stat-lbl">离线设备</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card running">
          <div class="stat-num">{{ summary.running_count }}</div>
          <div class="stat-lbl">运行中</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="关键词">
          <el-input
            v-model="filter.keyword"
            clearable
            placeholder="用户 / 设备指纹 / IMSI"
            style="width:220px"
            @keyup.enter="search"
          />
        </el-form-item>

        <el-form-item label="用户 ID">
          <el-input-number
            v-model="filter.user_id"
            :min="1"
            controls-position="right"
            style="width:130px"
          />
        </el-form-item>

        <el-form-item label="项目 Code">
          <el-input
            v-model="filter.project_code"
            clearable
            placeholder="项目 code_name"
            style="width:170px"
            @keyup.enter="search"
          />
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width:130px">
            <el-option label="运行中" value="running" />
            <el-option label="空闲" value="idle" />
            <el-option label="异常" value="error" />
            <el-option label="离线" value="offline" />
          </el-select>
        </el-form-item>

        <el-form-item label="在线">
          <el-switch
            v-model="filter.online_only"
            inline-prompt
            active-text="仅在线"
            inactive-text="全部"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="devices"
        row-key="binding_id"
        stripe
        style="width:100%"
        empty-text="暂无设备记录"
        @row-click="openDetail"
      >
        <el-table-column width="50" align="center">
          <template #default="{ row }">
            <span :class="['indicator', row.is_online ? 'on' : 'off']"></span>
          </template>
        </el-table-column>

        <el-table-column label="设备指纹" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="mono">{{ row.device_id || row.device_fingerprint }}</div>
            <div v-if="row.imsi" class="sub-text">IMSI：{{ row.imsi }}</div>
          </template>
        </el-table-column>

        <el-table-column label="用户" width="150">
          <template #default="{ row }">
            <router-link
              v-if="row.user_id"
              :to="`/users/${row.user_id}`"
              class="link"
              @click.stop
            >
              {{ row.username || `ID=${row.user_id}` }}
            </router-link>
            <span v-else class="text-muted">未知</span>
            <div class="sub-text">ID={{ row.user_id || '—' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <div>{{ row.project_name || '—' }}</div>
            <div class="sub-text">{{ row.project_code || '—' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="运行状态" width="110">
          <template #default="{ row }">
            <StatusBadge
              :status="row.status || 'offline'"
              type="device"
              :is-online="row.is_online"
            />
          </template>
        </el-table-column>

        <el-table-column label="在线状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="row.is_online ? 'success' : 'info'"
              effect="plain"
              size="small"
            >
              {{ row.is_online ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="最后心跳" width="160">
          <template #default="{ row }">
            <div :class="{ 'text-muted': !row.is_online }">
              {{ formatRelativeTime(row.last_seen || row.last_seen_at) }}
            </div>
            <div class="sub-text">
              {{ formatDatetime(row.last_seen || row.last_seen_at) }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="来源" width="90">
          <template #default="{ row }">
            <el-tag
              :type="row.source === 'redis' ? 'success' : 'info'"
              effect="plain"
              size="small"
            >
              {{ sourceLabel(row.source) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="运行数据" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="game-data">
              {{ row.game_data ? JSON.stringify(row.game_data) : '—' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click.stop="openDetail(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager-row">
        <span class="total-text">共 {{ pagination.total }} 台设备</span>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100, 200]"
          layout="sizes, prev, pager, next"
          @size-change="loadDevices"
          @current-change="loadDevices"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="drawer.visible"
      title="设备详情"
      size="460px"
      destroy-on-close
    >
      <div v-if="drawer.data" class="drawer-body">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="设备指纹">
            <span class="mono">{{ drawer.data.device_id || drawer.data.device_fingerprint }}</span>
          </el-descriptions-item>

          <el-descriptions-item label="用户">
            {{ drawer.data.username || '—' }}
            <span class="text-muted">ID={{ drawer.data.user_id || '—' }}</span>
          </el-descriptions-item>

          <el-descriptions-item label="项目">
            {{ drawer.data.project_name || '—' }}
            <span class="text-muted">{{ drawer.data.project_code || '' }}</span>
          </el-descriptions-item>

          <el-descriptions-item label="运行状态">
            <StatusBadge
              :status="drawer.data.status || 'offline'"
              type="device"
              :is-online="drawer.data.is_online"
            />
          </el-descriptions-item>

          <el-descriptions-item label="在线状态">
            {{ drawer.data.is_online ? '在线' : '离线' }}
          </el-descriptions-item>

          <el-descriptions-item label="最后心跳">
            {{ formatDatetime(drawer.data.last_seen || drawer.data.last_seen_at) }}
          </el-descriptions-item>

          <el-descriptions-item label="绑定时间">
            {{ formatDatetime(drawer.data.bound_at) }}
          </el-descriptions-item>

          <el-descriptions-item label="IMSI">
            <span class="mono">{{ drawer.data.imsi || '—' }}</span>
          </el-descriptions-item>

          <el-descriptions-item label="数据来源">
            {{ sourceLabel(drawer.data.source) }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">运行数据 game_data</div>
        <pre class="game-data-json">{{ JSON.stringify(drawer.data.game_data || {}, null, 2) }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/DeviceList.vue
 * 名称: 设备监控
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V2.0.0
 * 功能说明:
 *   管理后台设备监控页面。
 *
 * 本版改进:
 *   1. 不再依赖 useDevicePoller，页面直接调用 adminDeviceApi。
 *   2. 页面始终展示统计卡、过滤栏、表格，避免主体空白。
 *   3. 支持关键词、用户 ID、项目 code、状态、仅在线过滤。
 *   4. 展示项目归属、用户、IMSI、来源、最后心跳。
 *   5. 支持 10 秒自动刷新。
 */

import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adminDeviceApi } from '@/api/admin/device'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatRelativeTime, formatDatetime } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const filterUserId = ref(route.query.user_id ? Number(route.query.user_id) : null)
const filterUsername = ref(route.query.username ?? '')

const loading = ref(false)
const error = ref(null)
const autoRefresh = ref(true)
let timer = null

const devices = ref([])

const summary = reactive({
  total: 0,
  online_count: 0,
  offline_count: 0,
  running_count: 0,
})

const pagination = reactive({
  page: 1,
  pageSize: 50,
  total: 0,
})

const filter = reactive({
  keyword: '',
  user_id: filterUserId.value,
  project_code: '',
  status: '',
  online_only: false,
})

const drawer = reactive({
  visible: false,
  data: null,
})

const buildParams = () => {
  const params = {
    page: pagination.page,
    page_size: pagination.pageSize,
  }

  if (filter.keyword) {
    params.keyword = filter.keyword
  }

  if (filter.user_id) {
    params.user_id = filter.user_id
  }

  if (filter.project_code) {
    params.project_code = filter.project_code
  }

  if (filter.status) {
    params.status = filter.status
  }

  if (filter.online_only) {
    params.online_only = true
  }

  return params
}

const sourceLabel = (source) => {
  const map = {
    redis: 'Redis',
    database: 'DB',
    not_found: '无数据',
  }

  return map[source] || source || '—'
}

const loadDevices = async () => {
  loading.value = true
  error.value = null

  try {
    const res = await adminDeviceApi.listAll(buildParams())
    const data = res.data || {}

    devices.value = data.devices || []

    summary.total = data.total || 0
    summary.online_count = data.online_count || 0
    summary.offline_count = data.offline_count ?? Math.max(0, summary.total - summary.online_count)
    summary.running_count = data.running_count ?? devices.value.filter((item) => item.status === 'running').length

    pagination.total = data.total || 0
  } catch (err) {
    console.error(err)
    devices.value = []
    pagination.total = 0
    summary.total = 0
    summary.online_count = 0
    summary.offline_count = 0
    summary.running_count = 0
    error.value = err.response?.data?.detail || err.message || '设备数据加载失败'
    ElMessage.error('设备数据加载失败')
  } finally {
    loading.value = false
  }
}

const search = () => {
  pagination.page = 1
  loadDevices()
}

const resetFilter = () => {
  filter.keyword = ''
  filter.user_id = filterUserId.value || null
  filter.project_code = ''
  filter.status = ''
  filter.online_only = false
  pagination.page = 1
  loadDevices()
}

const clearUserFilter = () => {
  router.push('/devices')
}

const openDetail = (row) => {
  drawer.visible = true
  drawer.data = { ...row }
}

const startTimer = () => {
  stopTimer()

  if (autoRefresh.value) {
    timer = setInterval(loadDevices, 10_000)
  }
}

const stopTimer = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

watch(
  () => route.query,
  (q) => {
    filterUserId.value = q.user_id ? Number(q.user_id) : null
    filterUsername.value = q.username ?? ''
    filter.user_id = filterUserId.value
    pagination.page = 1
    loadDevices()
  },
)

watch(autoRefresh, () => {
  startTimer()
})

onMounted(() => {
  loadDevices()
  startTimer()
})

onUnmounted(() => {
  stopTimer()
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
  align-items: flex-start;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.header-left h2 {
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

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-label {
  font-size: 13px;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 4px;
  padding-top: 3px;
}

.top-alert,
.filter-card,
.table-card {
  border-radius: 10px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .07);
  border-left: 4px solid transparent;
}

.stat-card.total {
  border-color: #6366f1;
}

.stat-card.online {
  border-color: #10b981;
}

.stat-card.offline {
  border-color: #94a3b8;
}

.stat-card.running {
  border-color: #f59e0b;
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1;
}

.stat-lbl {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

.indicator {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.indicator.on {
  background: #10b981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, .2);
}

.indicator.off {
  background: #94a3b8;
}

.sub-text {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 12px;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
  word-break: break-all;
}

.link {
  color: #2563eb;
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
}

.link:hover {
  text-decoration: underline;
}

.game-data {
  font-size: 12px;
  color: #64748b;
  font-family: 'Cascadia Code', monospace;
}

.pager-row {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.total-text {
  color: #64748b;
  font-size: 13px;
}

.drawer-body {
  padding: 0 4px;
}

.section-title {
  margin: 20px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.game-data-json {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  color: #334155;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
