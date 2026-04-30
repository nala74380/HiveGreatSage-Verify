<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>登录日志</h2>
        <p class="page-desc">
          登录日志用于查看用户端登录记录、客户端来源、IP 地址、设备指纹和失败原因。该页面只读，不允许删除。
        </p>
      </div>
      <el-tag type="info" effect="plain" size="small">只读 · 不可删除</el-tag>
    </div>

    <!-- 过滤栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="结果">
          <el-select v-model="filter.success" clearable placeholder="全部" style="width:110px">
            <el-option label="成功" :value="true" />
            <el-option label="失败" :value="false" />
          </el-select>
        </el-form-item>

        <el-form-item label="客户端">
          <el-select v-model="filter.client_type" clearable placeholder="全部" style="width:140px">
            <el-option label="PC 中控" value="pc" />
            <el-option label="安卓脚本" value="android" />
          </el-select>
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filter.dateRange"
            type="daterange"
            range-separator="—"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width:240px"
            :shortcuts="dateShortcuts"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadLogs">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 当前页统计摘要 -->
    <el-row :gutter="12" v-if="pageSummary.pageTotal > 0">
      <el-col :span="6">
        <div class="summary-card">
          <div class="sum-val">{{ pageSummary.pageTotal }}</div>
          <div class="sum-lbl">当前页记录</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="summary-card success">
          <div class="sum-val">{{ pageSummary.success }}</div>
          <div class="sum-lbl">当前页成功</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="summary-card fail">
          <div class="sum-val">{{ pageSummary.fail }}</div>
          <div class="sum-lbl">当前页失败</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="summary-card rate">
          <div class="sum-val">{{ pageSummary.successRate }}%</div>
          <div class="sum-lbl">当前页成功率</div>
        </div>
      </el-col>
    </el-row>

    <!-- 日志表格 -->
    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="logs"
        stripe
        style="width:100%"
        empty-text="暂无登录日志"
      >
        <el-table-column label="结果" width="70" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.success ? 'success' : 'danger'"
              effect="dark"
              size="small"
            >
              {{ row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="用户" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.username">
              <router-link
                v-if="row.user_id"
                :to="`/users/${row.user_id}`"
                class="user-link"
              >
                {{ row.username }}
              </router-link>
              <span v-else>{{ row.username }}</span>
            </span>
            <span v-else class="text-muted">ID: {{ row.user_id ?? '未知' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="客户端" width="145">
          <template #default="{ row }">
            <el-tag
              :type="clientTypeMeta(row.client_type).tagType"
              effect="plain"
              size="small"
            >
              {{ clientTypeMeta(row.client_type).label }}
            </el-tag>

            <div class="raw-client" v-if="row.client_type">
              {{ row.client_type }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="IP 地址" width="140">
          <template #default="{ row }">
            <span class="mono">{{ row.ip_address ?? '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="设备指纹" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono text-muted">{{ row.device_fingerprint ?? '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="失败原因" width="150">
          <template #default="{ row }">
            <el-tag
              v-if="row.fail_reason"
              type="danger"
              effect="plain"
              size="small"
            >
              {{ failReasonLabel(row.fail_reason) }}
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>

        <el-table-column label="登录时间" width="170">
          <template #default="{ row }">
            {{ formatDatetime(row.login_at) }}
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
        @size-change="loadLogs"
        @current-change="loadLogs"
      />
    </el-card>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/LoginLogView.vue
 * 名称: 登录日志
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.1.0
 * 功能说明:
 *   查看用户端登录记录。
 *
 * 修复说明:
 *   1. 修复 PC 中控显示成安卓脚本的问题。
 *      后端 client_type 合法值是 pc / android，不是 pc_control。
 *   2. pc 和历史兼容值 pc_control 都显示为 PC 中控。
 *   3. android 显示为安卓脚本。
 *   4. 未知客户端显示原始值，避免误判。
 *   5. 失败原因兼容当前后端 fail_xxx 口径。
 */

import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { formatDatetime } from '@/utils/format'

// 失败原因中文映射：兼容新旧口径
const failReasonMap = {
  // 当前后端 auth_service.py 使用的 fail_xxx 口径
  fail_auth: '用户名或密码错误',
  fail_suspended: '账号已停用',
  fail_expired: '账号已过期',
  fail_project: '项目不存在或已下线',
  fail_no_auth: '未授权项目',
  fail_auth_expired: '项目授权已过期',
  fail_device_limit: '设备已达上限',
  fail_unknown: '未知错误',

  // 旧页面 / 旧文档口径兼容
  wrong_password: '密码错误',
  user_not_found: '用户不存在',
  user_suspended: '账号已停用',
  user_expired: '账号已过期',
  project_not_found: '项目不存在',
  auth_not_found: '未授权项目',
  auth_expired: '授权已过期',
  auth_suspended: '授权已停用',
  device_limit: '设备已达上限',
  device_unbound: '设备未绑定',
}

const clientTypeMap = {
  pc: {
    label: '🖥 PC 中控',
    tagType: 'primary',
  },
  pc_control: {
    label: '🖥 PC 中控',
    tagType: 'primary',
  },
  android: {
    label: '📱 安卓脚本',
    tagType: 'warning',
  },
}

const clientTypeMeta = (clientType) => {
  if (!clientType) {
    return {
      label: '未知客户端',
      tagType: 'info',
    }
  }

  return clientTypeMap[clientType] || {
    label: `未知：${clientType}`,
    tagType: 'info',
  }
}

const failReasonLabel = (reason) => {
  return failReasonMap[reason] || reason || '—'
}

// ── 日期快捷选项 ─────────────────────────────────────────────
const dateShortcuts = [
  {
    text: '今天',
    value: () => {
      const d = new Date()
      return [d, d]
    },
  },
  {
    text: '最近7天',
    value: () => {
      const e = new Date()
      const s = new Date()
      s.setDate(s.getDate() - 6)
      return [s, e]
    },
  },
  {
    text: '最近30天',
    value: () => {
      const e = new Date()
      const s = new Date()
      s.setDate(s.getDate() - 29)
      return [s, e]
    },
  },
]

// ── 过滤 ─────────────────────────────────────────────────────
const filter = reactive({
  success: null,
  client_type: null,
  dateRange: null,
})

// ── 分页 & 数据 ──────────────────────────────────────────────
const loading = ref(false)
const logs = ref([])

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const pageSummary = computed(() => {
  const pageTotal = logs.value.length
  const success = logs.value.filter((item) => item.success).length
  const fail = pageTotal - success
  const successRate = pageTotal > 0 ? Math.round((success / pageTotal) * 100) : 0

  return {
    pageTotal,
    success,
    fail,
    successRate,
  }
})

const buildParams = () => {
  const params = {
    page: pagination.page,
    page_size: pagination.pageSize,
  }

  if (filter.success !== null) {
    params.success = filter.success
  }

  if (filter.client_type) {
    params.client_type = filter.client_type
  }

  if (filter.dateRange?.[0]) {
    params.date_from = filter.dateRange[0].toISOString().split('T')[0]
  }

  if (filter.dateRange?.[1]) {
    params.date_to = filter.dateRange[1].toISOString().split('T')[0]
  }

  return params
}

const loadLogs = async () => {
  loading.value = true

  try {
    const res = await http.get('/admin/api/login-logs/', {
      params: buildParams(),
    })

    logs.value = res.data.logs ?? []
    pagination.total = res.data.total ?? 0
  } catch (error) {
    logs.value = []
    pagination.total = 0
    console.error(error)
    ElMessage.error('登录日志加载失败')
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filter.success = null
  filter.client_type = null
  filter.dateRange = null
  pagination.page = 1
  loadLogs()
}

onMounted(loadLogs)
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

/* 统计摘要 */
.summary-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .06);
  text-align: center;
}

.summary-card.success .sum-val {
  color: #10b981;
}

.summary-card.fail .sum-val {
  color: #ef4444;
}

.summary-card.rate .sum-val {
  color: #2563eb;
}

.sum-val {
  font-size: 26px;
  font-weight: 700;
  color: #1e293b;
}

.sum-lbl {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

.user-link {
  color: #2563eb;
  text-decoration: none;
  font-size: 13px;
}

.user-link:hover {
  text-decoration: underline;
}

.raw-client {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 11px;
  font-family: 'Cascadia Code', monospace;
}
</style>