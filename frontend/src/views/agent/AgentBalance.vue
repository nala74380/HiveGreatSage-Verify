<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>我的余额</h2>
        <p class="page-desc">查看代理账号当前点数余额、授信余额、冻结额度与流水记录。</p>
      </div>
      <el-button :icon="Refresh" @click="reloadAll" :loading="loading">刷新</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-row :gutter="16">
      <el-col :span="6">
        <div class="stat-card main">
          <div class="stat-label">可用充值点数</div>
          <div class="stat-value">{{ fmt(balance.recharge_balance) }}</div>
          <div class="stat-sub">优先消耗</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card credit">
          <div class="stat-label">可用授信点数</div>
          <div class="stat-value">{{ fmt(balance.credit_balance) }}</div>
          <div class="stat-sub">管理员授信</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card frozen">
          <div class="stat-label">冻结授信</div>
          <div class="stat-value">{{ fmt(balance.frozen_credit) }}</div>
          <div class="stat-sub">暂不可用</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card total">
          <div class="stat-label">总可用点数</div>
          <div class="stat-value">{{ fmt(totalAvailable) }}</div>
          <div class="stat-sub">充值 + 授信</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">流水记录</span>
          <el-select
            v-model="txType"
            clearable
            placeholder="全部类型"
            size="small"
            style="width: 150px"
            @change="fetchTransactions"
          >
            <el-option label="充值" value="recharge" />
            <el-option label="授信" value="credit" />
            <el-option label="冻结" value="freeze" />
            <el-option label="解冻" value="unfreeze" />
            <el-option label="消费" value="consume" />
          </el-select>
        </div>
      </template>

      <el-table
        v-loading="txLoading"
        :data="transactions"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />

        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag :type="txTagType(row.tx_type)" effect="plain">
              {{ txTypeLabel(row.tx_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="点数" width="120">
          <template #default="{ row }">
            <span :class="Number(row.amount) >= 0 ? 'amount-plus' : 'amount-minus'">
              {{ Number(row.amount) >= 0 ? '+' : '' }}{{ fmt(row.amount) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="说明" min-width="220">
          <template #default="{ row }">
            <span>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="时间" min-width="160">
          <template #default="{ row }">
            {{ formatDatetime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pager-row">
        <span class="total-text">共 {{ total }} 条</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          small
          layout="prev, pager, next, sizes"
          :page-sizes="[20, 50, 100]"
          :total="total"
          @current-change="fetchTransactions"
          @size-change="fetchTransactions"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/agent/AgentBalance.vue
 * 名称: 代理余额与流水页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.1
 * 功能及相关说明:
 *   代理查看自己的余额和流水。
 *   调用：
 *     GET /api/agents/my/balance
 *     GET /api/agents/my/transactions
 *
 * 改进内容:
 *   V1.0.1 - 增加错误提示，不让余额接口异常直接触发退出登录
 *   V1.0.0 - 新增代理侧余额与流水独立页面
 *
 * 调试信息:
 *   Network 应出现 /api/agents/my/balance 和 /api/agents/my/transactions。
 *   若状态不是 200，页面显示错误，不应直接退出登录。
 */

import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { agentBalanceApi } from '@/api/balance'
import { formatDatetime } from '@/utils/format'

const loading = ref(false)
const txLoading = ref(false)
const error = ref('')

const balance = ref({
  recharge_balance: 0,
  credit_balance: 0,
  frozen_credit: 0,
})

const transactions = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const txType = ref('')

const totalAvailable = computed(() => {
  return Number(balance.value.recharge_balance || 0) + Number(balance.value.credit_balance || 0)
})

const fmt = (val) => {
  const n = Number(val || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

const getErrorMessage = (err, actionName) => {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail || err?.response?.data?.message

  if (status === 401) {
    return `${actionName}接口返回 401：当前代理登录态未被后端认可。请确认 Chrome 中仍是代理账号登录，并检查后端代理鉴权。`
  }

  if (status === 403) {
    return `${actionName}接口返回 403：当前账号无权访问该功能。`
  }

  if (status === 404) {
    return `${actionName}接口返回 404：后端尚未注册对应接口，请确认 balance_agent.py 与 main.py 已更新并重启后端。`
  }

  if (status === 500) {
    return `${actionName}接口返回 500：后端内部异常，请查看 PyCharm 后端控制台日志。`
  }

  if (detail) {
    return `${actionName}失败：${detail}`
  }

  return `${actionName}失败：${err?.message || '未知错误'}`
}

const fetchBalance = async () => {
  const res = await agentBalanceApi.myBalance()
  balance.value = {
    recharge_balance: res.data.recharge_balance ?? 0,
    credit_balance: res.data.credit_balance ?? 0,
    frozen_credit: res.data.frozen_credit ?? 0,
  }
}

const fetchTransactions = async () => {
  txLoading.value = true

  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }

    if (txType.value) {
      params.tx_type = txType.value
    }

    const res = await agentBalanceApi.myTransactions(params)
    transactions.value = res.data.transactions ?? []
    total.value = res.data.total ?? 0
  } catch (err) {
    console.error('[AgentBalance] 加载流水失败:', err)
    transactions.value = []
    total.value = 0
    error.value = getErrorMessage(err, '加载流水')
  } finally {
    txLoading.value = false
  }
}

const reloadAll = async () => {
  loading.value = true
  error.value = ''

  try {
    await fetchBalance()
  } catch (err) {
    console.error('[AgentBalance] 加载余额失败:', err)
    error.value = getErrorMessage(err, '加载余额')
  }

  await fetchTransactions()

  loading.value = false
}

const txTypeLabel = (type) => {
  const map = {
    recharge: '充值',
    credit: '授信',
    freeze: '冻结',
    unfreeze: '解冻',
    consume: '消费',
    refund: '退款',
  }
  return map[type] || type || '未知'
}

const txTagType = (type) => {
  const map = {
    recharge: 'success',
    credit: 'primary',
    freeze: 'warning',
    unfreeze: 'info',
    consume: 'danger',
    refund: 'success',
  }
  return map[type] || 'info'
}

onMounted(reloadAll)
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

.tip-alert {
  border-radius: 10px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.07);
  border-top: 4px solid transparent;
}

.stat-card.main {
  border-color: #2563eb;
}

.stat-card.credit {
  border-color: #8b5cf6;
}

.stat-card.frozen {
  border-color: #f59e0b;
}

.stat-card.total {
  border-color: #10b981;
}

.stat-label {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
}

.stat-sub {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 12px;
}

.table-card {
  border-radius: 10px;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.amount-plus {
  color: #10b981;
  font-weight: 600;
}

.amount-minus {
  color: #ef4444;
  font-weight: 600;
}

.pager-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
}

.total-text {
  color: #64748b;
  font-size: 13px;
}
</style>