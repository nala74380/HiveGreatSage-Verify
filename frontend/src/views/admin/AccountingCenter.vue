<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>账务中心</h2>
        <p class="page-desc">
          账务中心用于管理平台内部点数资产：代理钱包、点数账本、授信、授权扣点、删除返点、对账检查与账务风险审计。
        </p>
      </div>

      <el-button :icon="Refresh" :loading="loadingAny" @click="loadAll">
        刷新
      </el-button>
    </div>

    <el-alert
      title="账务中心不处理真实人民币支付、发票、合同或代理提现；这里只管理平台内部点数资产。"
      type="info"
      show-icon
      :closable="false"
      class="top-alert"
    />

    <el-row :gutter="12">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-num">{{ fmtMoney(overview.total_available_balance) }}</div>
          <div class="stat-label">平台可用总点数</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-num">{{ fmtMoney(overview.total_charged_balance) }}</div>
          <div class="stat-label">充值点数余额</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-num">{{ fmtMoney(overview.total_credit_balance) }}</div>
          <div class="stat-label">授信点数余额</div>
        </div>
      </el-col>

      <el-col :span="6">
        <div class="stat-card warn">
          <div class="stat-num">{{ fmtMoney(overview.total_frozen_credit) }}</div>
          <div class="stat-label">冻结授信</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="main-card">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <!-- 账务总览 -->
        <el-tab-pane label="账务总览" name="overview">
          <div class="overview-grid">
            <div class="overview-block">
              <div class="block-title">今日变化</div>

              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="今日充值">
                  {{ fmtMoney(overview.today_recharge) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="今日授信">
                  {{ fmtMoney(overview.today_credit) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="今日冻结">
                  {{ fmtMoney(overview.today_freeze) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="今日解冻">
                  {{ fmtMoney(overview.today_unfreeze) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="今日扣点">
                  {{ fmtMoney(overview.today_consume) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="今日返点">
                  {{ fmtMoney(overview.today_refund) }} 点
                </el-descriptions-item>
              </el-descriptions>
            </div>

            <div class="overview-block">
              <div class="block-title">累计状态</div>

              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="钱包数量">
                  {{ overview.wallet_count || 0 }} 个
                </el-descriptions-item>
                <el-descriptions-item label="累计扣点">
                  {{ fmtMoney(overview.total_consumed) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="累计返点">
                  {{ fmtMoney(overview.total_refunded) }} 点
                </el-descriptions-item>
                <el-descriptions-item label="待返点快照">
                  {{ overview.refundable_snapshot_count || 0 }} 条
                </el-descriptions-item>
              </el-descriptions>
            </div>
          </div>
        </el-tab-pane>

        <!-- 点数账本 -->
        <el-tab-pane label="点数账本" name="ledger">
          <div class="filter-row">
            <el-form inline :model="ledgerFilter">
              <el-form-item label="类型">
                <el-select v-model="ledgerFilter.entry_type" clearable placeholder="全部" style="width:150px">
                  <el-option label="充值" value="recharge" />
                  <el-option label="授信" value="credit" />
                  <el-option label="冻结" value="freeze" />
                  <el-option label="解冻" value="unfreeze" />
                  <el-option label="授权扣点" value="consume" />
                  <el-option label="删除返点" value="refund" />
                  <el-option label="调整" value="adjust" />
                  <el-option label="冲正" value="reversal" />
                </el-select>
              </el-form-item>

              <el-form-item label="代理 ID">
                <el-input-number v-model="ledgerFilter.agent_id" :min="1" controls-position="right" style="width:130px" />
              </el-form-item>

              <el-form-item label="用户 ID">
                <el-input-number v-model="ledgerFilter.related_user_id" :min="1" controls-position="right" style="width:130px" />
              </el-form-item>

              <el-form-item label="项目 ID">
                <el-input-number v-model="ledgerFilter.related_project_id" :min="1" controls-position="right" style="width:130px" />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" @click="searchLedger">查询</el-button>
                <el-button @click="resetLedgerFilter">重置</el-button>
              </el-form-item>
            </el-form>
          </div>

          <el-table v-loading="ledgerLoading" :data="ledgerRows" stripe row-key="id" style="width:100%">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column label="类型" width="110">
              <template #default="{ row }">
                <el-tag :type="entryTypeTag(row.entry_type)" effect="light">
                  {{ row.entry_type_label || row.tx_type_label || row.entry_type }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column label="代理" min-width="130">
              <template #default="{ row }">
                <div class="main-text">{{ row.agent_username || `ID=${row.agent_id}` }}</div>
                <div class="sub-text">ID={{ row.agent_id }}</div>
              </template>
            </el-table-column>

            <el-table-column label="余额类型" width="105">
              <template #default="{ row }">
                {{ row.balance_type_label || row.balance_type }}
              </template>
            </el-table-column>

            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">
                <span :class="Number(row.amount) >= 0 ? 'amount-in' : 'amount-out'">
                  {{ Number(row.amount) >= 0 ? '+' : '' }}{{ fmtMoney(row.amount) }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label="余额变化" width="170">
              <template #default="{ row }">
                {{ fmtMoney(row.balance_before) }} → {{ fmtMoney(row.balance_after) }}
              </template>
            </el-table-column>

            <el-table-column label="关联对象" min-width="190">
              <template #default="{ row }">
                <div v-if="row.related_user_id" class="sub-line">
                  用户：{{ row.related_user_username || `ID=${row.related_user_id}` }}
                </div>
                <div v-if="row.related_project_id" class="sub-line">
                  项目：{{ row.related_project_name || `ID=${row.related_project_id}` }}
                </div>
                <span v-if="!row.related_user_id && !row.related_project_id" class="muted">无</span>
              </template>
            </el-table-column>

            <el-table-column label="说明" min-width="280" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.business_text || row.description || '—' }}
              </template>
            </el-table-column>

            <el-table-column label="时间" width="160">
              <template #default="{ row }">
                {{ formatDatetime(row.posted_at || row.created_at) }}
              </template>
            </el-table-column>
          </el-table>

          <div class="pager-row">
            <span class="total-text">共 {{ ledgerPager.total }} 条</span>
            <el-pagination
              v-model:current-page="ledgerPager.page"
              v-model:page-size="ledgerPager.pageSize"
              :page-sizes="[20, 50, 100, 200]"
              layout="sizes, prev, pager, next"
              :total="ledgerPager.total"
              @size-change="loadLedger"
              @current-change="loadLedger"
            />
          </div>
        </el-tab-pane>

        <!-- 代理钱包 -->
        <el-tab-pane label="代理钱包" name="wallets">
          <div class="filter-row">
            <el-form inline :model="walletFilter">
              <el-form-item label="关键词">
                <el-input v-model="walletFilter.keyword" clearable placeholder="代理账号" style="width:180px" />
              </el-form-item>

              <el-form-item label="代理 ID">
                <el-input-number v-model="walletFilter.agent_id" :min="1" controls-position="right" style="width:130px" />
              </el-form-item>

              <el-form-item label="状态">
                <el-select v-model="walletFilter.status" clearable placeholder="全部" style="width:130px">
                  <el-option label="正常" value="active" />
                  <el-option label="锁定" value="locked" />
                  <el-option label="关闭" value="closed" />
                </el-select>
              </el-form-item>

              <el-form-item label="风险">
                <el-select v-model="walletFilter.risk_status" clearable placeholder="全部" style="width:130px">
                  <el-option label="正常" value="normal" />
                  <el-option label="观察" value="watch" />
                  <el-option label="受限" value="restricted" />
                  <el-option label="冻结" value="frozen" />
                </el-select>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" @click="searchWallets">查询</el-button>
                <el-button @click="resetWalletFilter">重置</el-button>
              </el-form-item>
            </el-form>
          </div>

          <wallet-table
            :rows="walletRows"
            :loading="walletLoading"
            @action="openWalletAction"
          />

          <div class="pager-row">
            <span class="total-text">共 {{ walletPager.total }} 个钱包</span>
            <el-pagination
              v-model:current-page="walletPager.page"
              v-model:page-size="walletPager.pageSize"
              :page-sizes="[20, 50, 100, 200]"
              layout="sizes, prev, pager, next"
              :total="walletPager.total"
              @size-change="loadWallets"
              @current-change="loadWallets"
            />
          </div>
        </el-tab-pane>

        <!-- 授信管理 -->
        <el-tab-pane label="授信管理" name="credit">
          <el-alert
            title="授信管理用于管理代理的先用后补额度。冻结授信用于风控，不会改变授信总额，只会减少可用授信。"
            type="info"
            show-icon
            :closable="false"
            class="inner-alert"
          />

          <wallet-table
            :rows="walletRows"
            :loading="walletLoading"
            mode="credit"
            @action="openWalletAction"
          />
        </el-tab-pane>

        <!-- 扣点与返点 -->
        <el-tab-pane label="扣点与返点" name="charges">
          <el-alert
            title="扣点快照用于解释授权时为什么扣这些点；返点记录用于解释删除用户时为什么返这些点。"
            type="info"
            show-icon
            :closable="false"
            class="inner-alert"
          />

          <el-tabs v-model="chargeSubTab" type="border-card">
            <el-tab-pane label="授权扣点快照" name="charges">
              <div class="filter-row">
                <el-form inline :model="chargeFilter">
                  <el-form-item label="代理 ID">
                    <el-input-number v-model="chargeFilter.agent_id" :min="1" controls-position="right" style="width:130px" />
                  </el-form-item>
                  <el-form-item label="用户 ID">
                    <el-input-number v-model="chargeFilter.user_id" :min="1" controls-position="right" style="width:130px" />
                  </el-form-item>
                  <el-form-item label="项目 ID">
                    <el-input-number v-model="chargeFilter.project_id" :min="1" controls-position="right" style="width:130px" />
                  </el-form-item>
                  <el-form-item label="返点状态">
                    <el-select v-model="chargeFilter.refund_status" clearable placeholder="全部" style="width:130px">
                      <el-option label="未返点" value="none" />
                      <el-option label="部分返点" value="partial" />
                      <el-option label="已返点" value="refunded" />
                      <el-option label="无返点" value="no_refund" />
                    </el-select>
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" @click="searchCharges">查询</el-button>
                    <el-button @click="resetChargeFilter">重置</el-button>
                  </el-form-item>
                </el-form>
              </div>

              <el-table v-loading="chargeLoading" :data="chargeRows" stripe row-key="id">
                <el-table-column prop="id" label="ID" width="70" />
                <el-table-column label="代理 / 用户 / 项目" min-width="220">
                  <template #default="{ row }">
                    <div class="main-text">{{ row.agent_username || `代理ID=${row.agent_id}` }}</div>
                    <div class="sub-text">用户：{{ row.user_username || row.user_id }}</div>
                    <div class="sub-text">项目：{{ row.project_name || row.project_id }}</div>
                  </template>
                </el-table-column>

                <el-table-column label="计费快照" min-width="240">
                  <template #default="{ row }">
                    <div>{{ levelLabel(row.user_level) }} · {{ row.authorized_devices }} 台</div>
                    <div class="sub-text">
                      {{ fmtMoney(row.unit_price) }} 点 × {{ row.period_count }} 期
                    </div>
                    <div class="sub-text">
                      购买 {{ row.paid_hours }} 小时
                    </div>
                  </template>
                </el-table-column>

                <el-table-column label="扣点" width="180">
                  <template #default="{ row }">
                    <div>原扣：{{ fmtMoney(row.original_cost) }}</div>
                    <div class="sub-text">充值：{{ fmtMoney(row.charged_consumed) }}</div>
                    <div class="sub-text">授信：{{ fmtMoney(row.credit_consumed) }}</div>
                  </template>
                </el-table-column>

                <el-table-column label="返点状态" width="130">
                  <template #default="{ row }">
                    <el-tag :type="refundStatusTag(row.refund_status)" effect="light">
                      {{ refundStatusLabel(row.refund_status) }}
                    </el-tag>
                  </template>
                </el-table-column>

                <el-table-column label="有效期" width="240">
                  <template #default="{ row }">
                    <div>{{ formatDatetime(row.valid_from) }}</div>
                    <div class="sub-text">至 {{ formatDatetime(row.valid_until) }}</div>
                  </template>
                </el-table-column>
              </el-table>

              <div class="pager-row">
                <span class="total-text">共 {{ chargePager.total }} 条</span>
                <el-pagination
                  v-model:current-page="chargePager.page"
                  v-model:page-size="chargePager.pageSize"
                  :page-sizes="[20, 50, 100]"
                  layout="sizes, prev, pager, next"
                  :total="chargePager.total"
                  @size-change="loadCharges"
                  @current-change="loadCharges"
                />
              </div>
            </el-tab-pane>

            <el-tab-pane label="删除返点记录" name="refunds">
              <el-table v-loading="refundLoading" :data="refundRows" stripe row-key="id">
                <el-table-column prop="id" label="ID" width="70" />
                <el-table-column label="代理 / 用户 / 项目" min-width="220">
                  <template #default="{ row }">
                    <div class="main-text">{{ row.agent_username || `代理ID=${row.agent_id}` }}</div>
                    <div class="sub-text">用户：{{ row.user_username || row.user_id }}</div>
                    <div class="sub-text">项目：{{ row.project_name || row.project_id }}</div>
                  </template>
                </el-table-column>

                <el-table-column label="原扣点" width="120">
                  <template #default="{ row }">
                    {{ fmtMoney(row.original_cost) }}
                  </template>
                </el-table-column>

                <el-table-column label="返点" width="180">
                  <template #default="{ row }">
                    <div class="amount-in">+{{ fmtMoney(row.refunded_points) }}</div>
                    <div class="sub-text">充值：{{ fmtMoney(row.refunded_charged) }}</div>
                    <div class="sub-text">授信：{{ fmtMoney(row.refunded_credit) }}</div>
                  </template>
                </el-table-column>

                <el-table-column label="使用情况" width="180">
                  <template #default="{ row }">
                    <div>购买 {{ row.last_refund_paid_hours || row.paid_hours || 0 }} 小时</div>
                    <div class="sub-text">已用 {{ row.last_refund_used_hours || 0 }} 小时</div>
                    <div class="sub-text">已用点数 {{ fmtMoney(row.last_refund_used_cost) }}</div>
                  </template>
                </el-table-column>

                <el-table-column label="返点时间" width="160">
                  <template #default="{ row }">
                    {{ formatDatetime(row.refunded_at) }}
                  </template>
                </el-table-column>
              </el-table>

              <div class="pager-row">
                <span class="total-text">共 {{ refundPager.total }} 条</span>
                <el-pagination
                  v-model:current-page="refundPager.page"
                  v-model:page-size="refundPager.pageSize"
                  :page-sizes="[20, 50, 100]"
                  layout="sizes, prev, pager, next"
                  :total="refundPager.total"
                  @size-change="loadRefunds"
                  @current-change="loadRefunds"
                />
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <!-- 对账检查 -->
        <el-tab-pane label="对账检查" name="reconciliation">
          <placeholder-panel
            title="对账检查"
            desc="对账检查用于比对 accounting_wallet 钱包快照与 accounting_ledger_entry 账本累计是否一致。数据库表已预留，后续接入对账运行接口。"
          />
        </el-tab-pane>

        <!-- 代理账单 -->
        <el-tab-pane label="代理账单" name="bills">
          <placeholder-panel
            title="代理账单"
            desc="代理账单用于按月汇总代理的期初余额、本月充值、本月授信、本月扣点、本月返点和期末余额。数据库表已预留，后续接入月账单生成接口。"
          />
        </el-tab-pane>

        <!-- 风险审计 -->
        <el-tab-pane label="风险审计" name="risk">
          <placeholder-panel
            title="风险审计"
            desc="风险审计用于识别短时间大量返点、授信占用过高、扣点异常增长等账务风险。数据库表已预留，后续接入风险事件接口。"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 钱包操作弹窗 -->
    <el-dialog
      v-model="actionDialog.visible"
      :title="actionTitle"
      width="460px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="代理">
          <span class="main-text">
            {{ actionDialog.row?.agent_username || `ID=${actionDialog.row?.agent_id}` }}
          </span>
        </el-form-item>

        <el-form-item label="当前余额">
          <div>
            <div>充值点数：{{ fmtMoney(actionDialog.row?.charged_balance) }}</div>
            <div>授信点数：{{ fmtMoney(actionDialog.row?.credit_balance) }}</div>
            <div>冻结授信：{{ fmtMoney(actionDialog.row?.frozen_credit) }}</div>
            <div>可用总点数：{{ fmtMoney(actionDialog.row?.available_total) }}</div>
          </div>
        </el-form-item>

        <el-form-item label="点数金额">
          <el-input-number
            v-model="actionDialog.form.amount"
            :min="0.01"
            :precision="2"
            :step="10"
            controls-position="right"
            style="width:100%"
          />
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="actionDialog.form.description"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="请输入操作原因或备注"
          />
        </el-form-item>

        <el-alert
          v-if="actionDialog.action === 'freeze'"
          title="冻结授信只减少可用授信，不减少授信总额。"
          type="warning"
          show-icon
          :closable="false"
        />
      </el-form>

      <template #footer>
        <el-button @click="actionDialog.visible = false">
          取消
        </el-button>
        <el-button :type="actionButtonType" :loading="actionDialog.loading" @click="submitWalletAction">
          确认
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/AccountingCenter.vue
 * 名称: 账务中心
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.0.0
 * 功能说明:
 *   平台内部点数资产治理入口。
 *
 * 当前已接入:
 *   - 账务总览
 *   - 点数账本
 *   - 代理钱包
 *   - 授信管理
 *   - 授权扣点快照
 *   - 删除返点记录
 *
 * 后续预留:
 *   - 对账检查
 *   - 代理账单
 *   - 风险审计
 */

import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { accountingApi } from '@/api/accounting'
import { formatDatetime } from '@/utils/format'

const activeTab = ref('overview')
const chargeSubTab = ref('charges')

const overviewLoading = ref(false)
const ledgerLoading = ref(false)
const walletLoading = ref(false)
const chargeLoading = ref(false)
const refundLoading = ref(false)

const loadingAny = computed(() => (
  overviewLoading.value
  || ledgerLoading.value
  || walletLoading.value
  || chargeLoading.value
  || refundLoading.value
))

const overview = reactive({
  wallet_count: 0,
  total_charged_balance: 0,
  total_credit_balance: 0,
  total_frozen_credit: 0,
  total_available_credit: 0,
  total_available_balance: 0,
  total_consumed: 0,
  total_refunded: 0,
  refundable_snapshot_count: 0,
  today_recharge: 0,
  today_credit: 0,
  today_freeze: 0,
  today_unfreeze: 0,
  today_consume: 0,
  today_refund: 0,
  today_adjust: 0,
})

const ledgerRows = ref([])
const walletRows = ref([])
const chargeRows = ref([])
const refundRows = ref([])

const ledgerFilter = reactive({
  entry_type: '',
  agent_id: null,
  related_user_id: null,
  related_project_id: null,
})

const walletFilter = reactive({
  keyword: '',
  status: '',
  risk_status: '',
  agent_id: null,
})

const chargeFilter = reactive({
  agent_id: null,
  user_id: null,
  project_id: null,
  refund_status: '',
})

const ledgerPager = reactive({ page: 1, pageSize: 50, total: 0 })
const walletPager = reactive({ page: 1, pageSize: 50, total: 0 })
const chargePager = reactive({ page: 1, pageSize: 50, total: 0 })
const refundPager = reactive({ page: 1, pageSize: 50, total: 0 })

const actionDialog = reactive({
  visible: false,
  loading: false,
  action: '',
  row: null,
  form: {
    amount: 10,
    description: '',
  },
})

const fmtMoney = (value) => Number(value || 0).toFixed(2)

const levelLabel = (level) => {
  const map = {
    trial: '试用',
    normal: '普通',
    vip: 'VIP',
    svip: 'SVIP',
    tester: '测试',
  }
  return map[level] || level || '—'
}

const refundStatusLabel = (status) => {
  const map = {
    none: '未返点',
    partial: '部分返点',
    refunded: '已返点',
    no_refund: '无返点',
  }
  return map[status] || status || '—'
}

const refundStatusTag = (status) => {
  const map = {
    none: 'info',
    partial: 'warning',
    refunded: 'success',
    no_refund: 'info',
  }
  return map[status] || 'info'
}

const entryTypeTag = (type) => {
  const map = {
    recharge: 'success',
    credit: 'primary',
    freeze: 'warning',
    unfreeze: 'success',
    consume: 'danger',
    refund: 'success',
    adjust: 'warning',
    reversal: 'info',
  }
  return map[type] || 'info'
}

const actionTitle = computed(() => {
  const map = {
    recharge: '代理充值',
    credit: '代理授信',
    freeze: '冻结授信',
    unfreeze: '解冻授信',
  }
  return map[actionDialog.action] || '账务操作'
})

const actionButtonType = computed(() => {
  if (actionDialog.action === 'freeze') return 'warning'
  if (actionDialog.action === 'unfreeze') return 'success'
  if (actionDialog.action === 'credit') return 'primary'
  return 'success'
})

const loadOverview = async () => {
  overviewLoading.value = true
  try {
    const res = await accountingApi.overview()
    Object.assign(overview, res.data || {})
  } finally {
    overviewLoading.value = false
  }
}

const loadLedger = async () => {
  ledgerLoading.value = true
  try {
    const res = await accountingApi.ledger({
      page: ledgerPager.page,
      page_size: ledgerPager.pageSize,
      entry_type: ledgerFilter.entry_type || undefined,
      agent_id: ledgerFilter.agent_id || undefined,
      related_user_id: ledgerFilter.related_user_id || undefined,
      related_project_id: ledgerFilter.related_project_id || undefined,
    })

    ledgerRows.value = res.data.transactions || []
    ledgerPager.total = res.data.total || 0
  } finally {
    ledgerLoading.value = false
  }
}

const loadWallets = async () => {
  walletLoading.value = true
  try {
    const res = await accountingApi.wallets({
      page: walletPager.page,
      page_size: walletPager.pageSize,
      keyword: walletFilter.keyword || undefined,
      status: walletFilter.status || undefined,
      risk_status: walletFilter.risk_status || undefined,
      agent_id: walletFilter.agent_id || undefined,
    })

    walletRows.value = res.data.wallets || []
    walletPager.total = res.data.total || 0
  } finally {
    walletLoading.value = false
  }
}

const loadCharges = async () => {
  chargeLoading.value = true
  try {
    const res = await accountingApi.charges({
      page: chargePager.page,
      page_size: chargePager.pageSize,
      agent_id: chargeFilter.agent_id || undefined,
      user_id: chargeFilter.user_id || undefined,
      project_id: chargeFilter.project_id || undefined,
      refund_status: chargeFilter.refund_status || undefined,
    })

    chargeRows.value = res.data.charges || []
    chargePager.total = res.data.total || 0
  } finally {
    chargeLoading.value = false
  }
}

const loadRefunds = async () => {
  refundLoading.value = true
  try {
    const res = await accountingApi.refunds({
      page: refundPager.page,
      page_size: refundPager.pageSize,
      agent_id: chargeFilter.agent_id || undefined,
      user_id: chargeFilter.user_id || undefined,
      project_id: chargeFilter.project_id || undefined,
    })

    refundRows.value = res.data.refunds || []
    refundPager.total = res.data.total || 0
  } finally {
    refundLoading.value = false
  }
}

const loadAll = async () => {
  await Promise.all([
    loadOverview(),
    loadLedger(),
    loadWallets(),
    loadCharges(),
    loadRefunds(),
  ])
}

const handleTabChange = async (tabName) => {
  if (tabName === 'overview') await loadOverview()
  if (tabName === 'ledger') await loadLedger()
  if (tabName === 'wallets') await loadWallets()
  if (tabName === 'credit') await loadWallets()
  if (tabName === 'charges') {
    await Promise.all([loadCharges(), loadRefunds()])
  }
}

const searchLedger = () => {
  ledgerPager.page = 1
  loadLedger()
}

const resetLedgerFilter = () => {
  ledgerFilter.entry_type = ''
  ledgerFilter.agent_id = null
  ledgerFilter.related_user_id = null
  ledgerFilter.related_project_id = null
  ledgerPager.page = 1
  loadLedger()
}

const searchWallets = () => {
  walletPager.page = 1
  loadWallets()
}

const resetWalletFilter = () => {
  walletFilter.keyword = ''
  walletFilter.status = ''
  walletFilter.risk_status = ''
  walletFilter.agent_id = null
  walletPager.page = 1
  loadWallets()
}

const searchCharges = () => {
  chargePager.page = 1
  refundPager.page = 1
  loadCharges()
  loadRefunds()
}

const resetChargeFilter = () => {
  chargeFilter.agent_id = null
  chargeFilter.user_id = null
  chargeFilter.project_id = null
  chargeFilter.refund_status = ''
  chargePager.page = 1
  refundPager.page = 1
  loadCharges()
  loadRefunds()
}

const openWalletAction = ({ action, row }) => {
  actionDialog.action = action
  actionDialog.row = row
  actionDialog.form = {
    amount: 10,
    description: '',
  }
  actionDialog.visible = true
}

const submitWalletAction = async () => {
  if (!actionDialog.row?.agent_id) return

  actionDialog.loading = true

  try {
    const agentId = actionDialog.row.agent_id
    const data = {
      amount: Number(actionDialog.form.amount),
      description: actionDialog.form.description || null,
    }

    if (actionDialog.action === 'recharge') {
      await accountingApi.recharge(agentId, data)
    } else if (actionDialog.action === 'credit') {
      await accountingApi.credit(agentId, data)
    } else if (actionDialog.action === 'freeze') {
      await accountingApi.freeze(agentId, data)
    } else if (actionDialog.action === 'unfreeze') {
      await accountingApi.unfreeze(agentId, data)
    }

    ElMessage.success('操作成功')
    actionDialog.visible = false

    await Promise.all([
      loadOverview(),
      loadWallets(),
      loadLedger(),
    ])
  } finally {
    actionDialog.loading = false
  }
}

onMounted(loadAll)

/**
 * 局部表格组件：避免代理钱包和授信管理重复写表格。
 */
const WalletTable = defineComponent({
  name: 'WalletTable',
  props: {
    rows: {
      type: Array,
      default: () => [],
    },
    loading: {
      type: Boolean,
      default: false,
    },
    mode: {
      type: String,
      default: 'wallet',
    },
  },
  emits: ['action'],
  setup(props, { emit }) {
    const money = (value) => Number(value || 0).toFixed(2)

    return () => h('div', [
      h(
        resolveElTable(),
        {
          data: props.rows,
          stripe: true,
          rowKey: 'agent_id',
          style: 'width:100%',
          loading: props.loading,
        },
        {
          default: () => [
            h(resolveElTableColumn(), { label: '代理', minWidth: 160 }, {
              default: ({ row }) => h('div', [
                h('div', { class: 'main-text' }, row.agent_username || `ID=${row.agent_id}`),
                h('div', { class: 'sub-text' }, `ID=${row.agent_id} · Lv.${row.agent_level || '-'}`),
              ]),
            }),

            h(resolveElTableColumn(), { label: '充值余额', width: 115, align: 'right' }, {
              default: ({ row }) => money(row.charged_balance),
            }),

            h(resolveElTableColumn(), { label: '授信余额', width: 115, align: 'right' }, {
              default: ({ row }) => money(row.credit_balance),
            }),

            h(resolveElTableColumn(), { label: '冻结授信', width: 115, align: 'right' }, {
              default: ({ row }) => money(row.frozen_credit),
            }),

            h(resolveElTableColumn(), { label: '可用授信', width: 115, align: 'right' }, {
              default: ({ row }) => money(row.available_credit),
            }),

            h(resolveElTableColumn(), { label: '可用总点数', width: 125, align: 'right' }, {
              default: ({ row }) => h('span', { class: 'price-val' }, money(row.available_total)),
            }),

            h(resolveElTableColumn(), { label: '累计扣点', width: 115, align: 'right' }, {
              default: ({ row }) => money(row.total_consumed),
            }),

            h(resolveElTableColumn(), { label: '累计返点', width: 115, align: 'right' }, {
              default: ({ row }) => money(row.total_refunded),
            }),

            h(resolveElTableColumn(), { label: '状态', width: 120 }, {
              default: ({ row }) => h('div', [
                h(resolveElTag(), { size: 'small', type: row.status === 'active' ? 'success' : 'info' }, () => row.status || 'active'),
                h(resolveElTag(), { size: 'small', type: row.risk_status === 'normal' ? 'success' : 'warning', style: 'margin-left:4px' }, () => row.risk_status || 'normal'),
              ]),
            }),

            h(resolveElTableColumn(), { label: '操作', width: props.mode === 'credit' ? 190 : 240, fixed: 'right' }, {
              default: ({ row }) => h('div', [
                props.mode !== 'credit'
                  ? h(resolveElButton(), { text: true, size: 'small', type: 'success', onClick: () => emit('action', { action: 'recharge', row }) }, () => '充值')
                  : null,
                h(resolveElButton(), { text: true, size: 'small', type: 'primary', onClick: () => emit('action', { action: 'credit', row }) }, () => '授信'),
                h(resolveElButton(), { text: true, size: 'small', type: 'warning', onClick: () => emit('action', { action: 'freeze', row }) }, () => '冻结'),
                h(resolveElButton(), { text: true, size: 'small', type: 'success', onClick: () => emit('action', { action: 'unfreeze', row }) }, () => '解冻'),
              ]),
            }),
          ],
        },
      ),
    ])
  },
})

const PlaceholderPanel = defineComponent({
  name: 'PlaceholderPanel',
  props: {
    title: {
      type: String,
      required: true,
    },
    desc: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    return () => h('div', { class: 'placeholder-panel' }, [
      h('div', { class: 'placeholder-title' }, props.title),
      h('div', { class: 'placeholder-desc' }, props.desc),
    ])
  },
})

/**
 * Element Plus 组件在模板里可自动解析。
 * render 函数局部组件里用字符串标签名最稳。
 */
function resolveElTable() { return 'el-table' }
function resolveElTableColumn() { return 'el-table-column' }
function resolveElButton() { return 'el-button' }
function resolveElTag() { return 'el-tag' }
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

.top-alert,
.main-card {
  border-radius: 10px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  border-left: 4px solid #6366f1;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
}

.stat-card.warn {
  border-left-color: #f59e0b;
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

.filter-row {
  margin-bottom: 12px;
}

.inner-alert {
  margin-bottom: 14px;
  border-radius: 8px;
}

.main-text {
  font-size: 13px;
  color: #1e293b;
  font-weight: 600;
}

.sub-text,
.sub-line,
.muted {
  margin-top: 3px;
  font-size: 12px;
  color: #94a3b8;
}

.amount-in {
  color: #059669;
  font-weight: 700;
}

.amount-out {
  color: #dc2626;
  font-weight: 700;
}

.price-val {
  color: #6366f1;
  font-weight: 700;
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

.placeholder-panel {
  border: 1px dashed #cbd5e1;
  background: #f8fafc;
  border-radius: 10px;
  padding: 24px;
}

.placeholder-title {
  font-size: 16px;
  font-weight: 800;
  color: #1e293b;
}

.placeholder-desc {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}
</style>