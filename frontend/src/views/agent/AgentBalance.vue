<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>我的余额</h2>
        <p class="page-desc">
          查看当前点数余额、授信额度、冻结额度，以及用户项目授权扣点 / 删除用户返点明细。
        </p>
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
          <div class="stat-sub">授权扣点时优先消耗</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card credit">
          <div class="stat-label">可用授信点数</div>
          <div class="stat-value">{{ fmt(balance.credit_balance) }}</div>
          <div class="stat-sub">充值不足时消耗</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card frozen">
          <div class="stat-label">冻结授信</div>
          <div class="stat-value">{{ fmt(balance.frozen_credit) }}</div>
          <div class="stat-sub">已冻结，不可用于授权</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card total">
          <div class="stat-label">总可用点数</div>
          <div class="stat-value">{{ fmt(totalAvailable) }}</div>
          <div class="stat-sub">充值 + 可用授信</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="rule-card">
      <template #header>
        <div class="rule-header">
          <span class="card-title">扣点 / 返点规则说明</span>
          <el-tag effect="plain" type="info">按项目授权单独计算</el-tag>
        </div>
      </template>

      <div class="rule-grid">
        <div class="rule-block">
          <div class="rule-title">授权扣点规则</div>
          <div class="rule-line">试用用户：按周计费，1 周 = 168 小时。</div>
          <div class="rule-line">普通 / VIP / SVIP：按月计费，1 月 = 720 小时。</div>
          <div class="formula-box">
            扣点 = 项目等级价格 × 授权设备数 × 授权周期数
          </div>
          <div class="rule-line">
            授权周期数 = 向上取整（授权时长 ÷ 计费周期）。
          </div>
        </div>

        <div class="rule-block">
          <div class="rule-title">删除用户返点规则</div>
          <div class="rule-line">删除用户时，按每个项目授权分别计算剩余未使用点数。</div>
          <div class="rule-line">实际使用时间不足 1 小时，按 1 小时计算。</div>
          <div class="formula-box">
            返点 = 原始扣点 - 每小时成本 × 已使用小时数 - 已返还点数
          </div>
          <div class="rule-line">
            每小时成本 = 原始扣点 ÷ 已购买总小时数。
          </div>
        </div>

        <div class="rule-block">
          <div class="rule-title">返点边界</div>
          <div class="rule-line">已过期授权不返点。</div>
          <div class="rule-line">管理员免费授权不返点。</div>
          <div class="rule-line">只有代理实际扣过点的授权才返点。</div>
          <div class="rule-line">返点会按原扣点来源返还到充值点数 / 授信点数。</div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">流水记录</span>
          <el-select
            v-model="txType"
            clearable
            placeholder="全部类型"
            size="small"
            style="width: 160px"
            @change="fetchTransactions"
          >
            <el-option label="充值" value="recharge" />
            <el-option label="授信" value="credit" />
            <el-option label="冻结" value="freeze" />
            <el-option label="解冻" value="unfreeze" />
            <el-option label="授权扣点" value="consume" />
            <el-option label="删除用户返点" value="refund" />
          </el-select>
        </div>
      </template>

      <el-table
        v-loading="txLoading"
        :data="transactions"
        stripe
        style="width: 100%"
      >
        <el-table-column label="时间" width="165">
          <template #default="{ row }">
            {{ formatDatetime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="txTagType(row.tx_type)" effect="plain">
              {{ txTypeLabel(row) }}
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

        <el-table-column label="余额变化" width="150">
          <template #default="{ row }">
            <span class="balance-change">
              {{ fmt(row.balance_before) }} → {{ fmt(row.balance_after) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="详细说明" min-width="560">
          <template #default="{ row }">
            <div class="business-text">{{ row.business_text || row.description || '—' }}</div>

            <div v-if="row.tx_type === 'consume'" class="detail-line">
              <el-tag size="small" effect="plain" type="info">
                用户：{{ row.related_username || `ID=${row.related_user_id}` }}
              </el-tag>
              <el-tag size="small" effect="plain" type="primary">
                项目：{{ row.related_project_name || `ID=${row.related_project_id}` }}
              </el-tag>
              <el-tag v-if="row.authorization_detail" size="small" effect="plain" type="warning">
                {{ row.authorization_detail.level_name }}
              </el-tag>
              <el-tag v-if="row.authorization_detail" size="small" effect="plain" type="success">
                {{ row.authorization_detail.authorized_devices }} 台
              </el-tag>
              <el-tag
                v-if="row.authorization_detail?.unit_price !== null && row.authorization_detail?.unit_price !== undefined"
                size="small"
                effect="plain"
              >
                {{ fmt(row.authorization_detail.unit_price) }} 点/{{ row.authorization_detail.unit_label }}
              </el-tag>
            </div>

            <div v-if="row.tx_type === 'refund'" class="detail-line refund-line">
              <el-tag size="small" effect="plain" type="success">返点</el-tag>
              <el-tag size="small" effect="plain" type="info">
                用户：{{ row.related_username || `ID=${row.related_user_id}` }}
              </el-tag>
              <el-tag size="small" effect="plain" type="primary">
                项目：{{ row.related_project_name || `ID=${row.related_project_id}` }}
              </el-tag>

              <template v-if="row.refund_detail">
                <el-tag size="small" effect="plain">
                  原扣点：{{ fmt(row.refund_detail.original_cost) }}
                </el-tag>
                <el-tag size="small" effect="plain">
                  已用小时：{{ row.refund_detail.used_hours }}
                </el-tag>
                <el-tag size="small" effect="plain">
                  已用点数：{{ fmt(row.refund_detail.used_cost) }}
                </el-tag>
                <el-tag size="small" effect="plain" type="success">
                  返还：{{ fmt(row.refund_detail.refund_points) }}
                </el-tag>
              </template>

              <template v-else-if="row.authorization_detail">
                <el-tag size="small" effect="plain" type="warning">
                  {{ row.authorization_detail.level_name }}
                </el-tag>
                <el-tag size="small" effect="plain" type="success">
                  {{ row.authorization_detail.authorized_devices }} 台
                </el-tag>
                <el-tag
                  v-if="row.authorization_detail?.unit_price !== null && row.authorization_detail?.unit_price !== undefined"
                  size="small"
                  effect="plain"
                >
                  当前价：{{ fmt(row.authorization_detail.unit_price) }} 点/{{ row.authorization_detail.unit_label }}
                </el-tag>
              </template>
            </div>
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
 * 名称: 代理端我的余额
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.2.0
 * 功能说明:
 *   展示代理余额、授权扣点流水、删除用户返点流水，并解释扣点/返点公式。
 *
 * 已确认规则:
 *   - 授权扣点按项目授权独立计算。
 *   - 删除用户返点按项目授权独立计算。
 *   - 实际使用时间不足 1 小时，按 1 小时计算。
 */

import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { agentBalanceApi } from '@/api/agent/balance'
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

const fmt = (val) => Number(val || 0).toFixed(2)

const getErrorMessage = (err, actionName) => {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail || err?.response?.data?.message

  if (status === 401) return `${actionName}接口返回 401：当前代理登录态未被后端认可。`
  if (status === 403) return `${actionName}接口返回 403：当前账号无权访问该功能。`
  if (status === 404) return `${actionName}接口返回 404：后端尚未注册对应接口。`
  if (status === 500) return `${actionName}接口返回 500：后端内部异常，请查看 PyCharm 后端控制台日志。`
  if (detail) return `${actionName}失败：${detail}`

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
      tx_type: txType.value || undefined,
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

const txTypeLabel = (row) => {
  const map = {
    recharge: '充值',
    credit: '授信',
    freeze: '冻结',
    unfreeze: '解冻',
    consume: '授权扣点',
    refund: '删除用户返点',
    adjust: '调整',
  }

  return map[row.tx_type] || row.tx_type_label || row.tx_type || '未知'
}

const txTagType = (type) => {
  const map = {
    recharge: 'success',
    credit: 'primary',
    freeze: 'warning',
    unfreeze: 'info',
    consume: 'danger',
    refund: 'success',
    adjust: 'info',
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

.rule-card,
.table-card {
  border-radius: 10px;
}

.rule-header,
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

.rule-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.rule-block {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
}

.rule-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 8px;
}

.rule-line {
  font-size: 12px;
  color: #64748b;
  line-height: 1.8;
}

.formula-box {
  margin: 8px 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
  font-family: Consolas, monospace;
}

.amount-plus {
  color: #10b981;
  font-weight: 600;
}

.amount-minus {
  color: #ef4444;
  font-weight: 600;
}

.balance-change {
  font-size: 12px;
  color: #475569;
  font-family: Consolas, monospace;
}

.business-text {
  font-size: 13px;
  color: #1e293b;
  line-height: 1.7;
}

.detail-line {
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.refund-line {
  padding-top: 2px;
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
