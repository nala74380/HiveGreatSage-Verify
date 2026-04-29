<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>点数流水</h2>
        <p class="page-desc">
          查看管理员充值/授信/冻结/解冻，以及代理给用户授权项目产生的扣点流水。
        </p>
      </div>
      <el-button :icon="Refresh" @click="loadTransactions" :loading="loading">刷新</el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="类型">
          <el-select v-model="filter.tx_type" clearable placeholder="全部" style="width:130px">
            <el-option label="充值" value="recharge" />
            <el-option label="授信" value="credit" />
            <el-option label="冻结" value="freeze" />
            <el-option label="解冻" value="unfreeze" />
            <el-option label="消费/扣点" value="consume" />
          </el-select>
        </el-form-item>

        <el-form-item label="代理ID">
          <el-input-number
            v-model="filter.agent_id"
            :min="1"
            controls-position="right"
            placeholder="代理ID"
            style="width:130px"
          />
        </el-form-item>

        <el-form-item label="用户ID">
          <el-input-number
            v-model="filter.related_user_id"
            :min="1"
            controls-position="right"
            placeholder="用户ID"
            style="width:130px"
          />
        </el-form-item>

        <el-form-item label="项目ID">
          <el-input-number
            v-model="filter.related_project_id"
            :min="1"
            controls-position="right"
            placeholder="项目ID"
            style="width:130px"
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
        :data="transactions"
        stripe
        row-key="id"
        style="width:100%"
      >
        <el-table-column prop="id" label="ID" width="78" />

        <el-table-column label="时间" width="165">
          <template #default="{ row }">
            {{ formatDatetime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="类型" width="105">
          <template #default="{ row }">
            <el-tag :type="txTagType(row.tx_type)" effect="plain">
              {{ row.tx_type_label }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="代理" width="135">
          <template #default="{ row }">
            <span v-if="row.agent_username">{{ row.agent_username }}</span>
            <span v-else class="text-muted">ID={{ row.agent_id }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作者" width="130">
          <template #default="{ row }">
            <span v-if="row.operated_by_admin_username">{{ row.operated_by_admin_username }}</span>
            <span v-else-if="row.operated_by_admin_id">管理员ID={{ row.operated_by_admin_id }}</span>
            <span v-else class="text-muted">系统/代理</span>
          </template>
        </el-table-column>

        <el-table-column label="金额" width="120">
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

        <el-table-column label="业务说明" min-width="420">
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
              <el-tag v-if="row.authorization_detail?.unit_price !== null && row.authorization_detail?.unit_price !== undefined" size="small" effect="plain">
                {{ fmt(row.authorization_detail.unit_price) }} 点/{{ row.authorization_detail.unit_label }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager-row">
        <span class="total-text">共 {{ total }} 条</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          :total="total"
          @current-change="loadTransactions"
          @size-change="loadTransactions"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/BalanceTransactions.vue
 * 名称: 管理员点数流水页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 */

import { onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { adminBalanceApi } from '@/api/balance'
import { formatDatetime } from '@/utils/format'

const loading = ref(false)
const transactions = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

const filter = reactive({
  tx_type: '',
  agent_id: null,
  related_user_id: null,
  related_project_id: null,
})

const fmt = (val) => Number(val || 0).toFixed(2)

const loadTransactions = async () => {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      tx_type: filter.tx_type || undefined,
      agent_id: filter.agent_id || undefined,
      related_user_id: filter.related_user_id || undefined,
      related_project_id: filter.related_project_id || undefined,
    }

    const res = await adminBalanceApi.globalTransactions(params)
    transactions.value = res.data.transactions || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

const search = () => {
  page.value = 1
  loadTransactions()
}

const resetFilter = () => {
  filter.tx_type = ''
  filter.agent_id = null
  filter.related_user_id = null
  filter.related_project_id = null
  page.value = 1
  loadTransactions()
}

const txTagType = (type) => {
  const map = {
    recharge: 'success',
    credit: 'primary',
    consume: 'danger',
    freeze: 'warning',
    unfreeze: 'info',
    adjust: 'info',
  }
  return map[type] || 'info'
}

onMounted(loadTransactions)
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
}

.filter-card,
.table-card {
  border-radius: 10px;
}

.amount-plus {
  color: #10b981;
  font-weight: 700;
}

.amount-minus {
  color: #ef4444;
  font-weight: 700;
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

.text-muted {
  color: #94a3b8;
  font-size: 12px;
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
</style>