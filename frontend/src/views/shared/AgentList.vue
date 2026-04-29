<template>
  <div class="page">
    <div class="page-header">
      <h2>代理管理</h2>
      <el-button v-if="auth.isAdmin" type="primary" :icon="Plus" @click="openCreateDialog">
        新建代理
      </el-button>
    </div>

    <!-- 过滤栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width:120px">
            <el-option label="正常"   value="active" />
            <el-option label="已停用" value="suspended" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadAgents">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 批量操作 -->
    <div v-if="selectedIds.length > 0" class="batch-toolbar">
      <span class="batch-info">已选 {{ selectedIds.length }} 条</span>
      <el-popconfirm :title="`确认批量删除 ${selectedIds.length} 个代理？`"
        confirm-button-text="删除" cancel-button-text="取消" @confirm="batchDelete">
        <template #reference>
          <el-button type="danger" size="small" :loading="batchLoading">批量删除</el-button>
        </template>
      </el-popconfirm>
      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <!-- 代理表格 -->
    <el-card shadow="never" class="table-card">
      <el-table v-loading="loading" :data="agents" row-key="id" stripe style="width:100%"
        @selection-change="onSelectionChange">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="username" label="代理名" min-width="130" />
        <el-table-column label="层级" width="70">
          <template #default="{ row }">
            <el-tag type="info" effect="plain" size="small">Lv.{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <StatusBadge :status="row.status" type="agent" />
          </template>
        </el-table-column>

        <!-- 已授权项目 + 各项目用户数 -->
        <el-table-column label="已授权项目" min-width="260">
          <template #default="{ row }">
            <div v-if="!row.authorized_projects?.length" class="no-data">未授权项目</div>
            <div v-else class="project-list">
              <el-tooltip
                v-for="p in row.authorized_projects" :key="p.project_id"
                :content="`${p.display_name}\u7528户数: ${p.user_count ?? 0} 人${p.valid_until ? '  到期: ' + fmtDate(p.valid_until) : '  永久'}`"
                placement="top"
              >
                <div class="proj-badge">
                  <el-tag size="small" effect="light"
                    :type="p.project_type === 'game' ? 'primary' : 'info'">
                    {{ p.display_name }}
                  </el-tag>
                  <span class="proj-user-count">{{ p.user_count ?? 0 }}人</span>
                </div>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="配额/用户" width="110" align="center">
          <template #default="{ row }">
            <span>{{ row.users_count }} / {{ row.max_users === 0 ? '∞' : row.max_users }}</span>
          </template>
        </el-table-column>

        <!-- 余额 -->
        <el-table-column label="可用点数" width="120" align="right">
          <template #default="{ row }">
            <span :class="row.balance?.available_total > 0 ? 'pts-positive' : 'pts-zero'">
              {{ (row.balance?.available_total ?? 0).toFixed(2) }}
            </span>
            <div class="pts-detail">
              充值 {{ (row.balance?.charged_points ?? 0).toFixed(2) }} +
              授信 {{ ((row.balance?.credit_points ?? 0) - (row.balance?.frozen_credit ?? 0)).toFixed(2) }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDatetime(row.created_at) }}</template>
        </el-table-column>

        <el-table-column v-if="auth.isAdmin" label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button text size="small" :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button>
            <el-button text size="small" type="primary" @click="openAuthDialog(row)">项目授权</el-button>
            <el-button text size="small" type="success" @click="openBalanceDialog(row)">点数</el-button>
            <el-popconfirm title="确认删除该代理？" confirm-button-text="删除"
              cancel-button-text="取消" @confirm="deleteAgent(row)">
              <template #reference>
                <el-button text size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.pageSize"
        :total="pagination.total" :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next" class="pagination"
        @size-change="loadAgents" @current-change="loadAgents" />
    </el-card>

    <!-- ───── 新建 / 编辑 对话框 ───── -->
    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑代理' : '新建代理'"
      width="480px" destroy-on-close>
      <el-form ref="dialogFormRef" :model="dialog.form" :rules="dialogRules"
        label-width="90px" autocomplete="off">
        <template v-if="!dialog.isEdit">
          <!-- 欺骗浏览器 autocomplete 的隐藏诱饵字段（必须放第一位）-->
          <input type="text"     style="display:none" tabindex="-1" aria-hidden="true" />
          <input type="password" style="display:none" tabindex="-1" aria-hidden="true" />
          <el-form-item label="代理名" prop="username">
            <el-input
              v-model="dialog.form.username"
              :name="'agent_name_' + dialog._uid"
              autocomplete="new-password"
              placeholder="请输入代理名"
              clearable
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="dialog.form.password"
              :name="'agent_pwd_' + dialog._uid"
              type="password" show-password
              autocomplete="new-password"
              placeholder="请输入密码"
            />
          </el-form-item>
          <el-form-item label="上级代理 ID">
            <el-input-number v-model="dialog.form.parent_agent_id" :min="1"
              controls-position="right" placeholder="留空=顶级代理" style="width:100%" />
            <div class="field-hint">留空则创建为顶级代理（直属管理员）</div>
          </el-form-item>
        </template>
        <el-form-item label="用户配额">
          <el-input-number v-model="dialog.form.max_users" :min="0"
            controls-position="right" style="width:100%" />
          <div class="field-hint">0 = 无限制</div>
        </el-form-item>
        <el-form-item label="佣金比例">
          <el-input-number v-model="dialog.form.commission_rate" :min="0" :max="100"
            :precision="2" controls-position="right" style="width:100%" />
          <div class="field-hint">单位：%（留空不设置）</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="submitDialog">确定</el-button>
      </template>
    </el-dialog>

    <!-- ───── 项目授权弹窗 ───── -->
    <el-dialog v-model="authDialog.visible" :title="`项目授权 — ${authDialog.agentName}`"
      width="620px" destroy-on-close>
      <div class="auth-section">
        <div class="auth-section-title">
          已授权项目
          <el-button size="small" :icon="Refresh" @click="loadAgentAuths" style="margin-left:8px" />
        </div>
        <el-table v-loading="authDialog.listLoading" :data="authDialog.auths" size="small"
          empty-text="暂无授权项目">
          <el-table-column label="项目名称" min-width="140" prop="project_display_name" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              <el-tag :type="row.project_type === 'game' ? 'primary' : 'info'" effect="plain" size="small">
                {{ row.project_type === 'game' ? '🎮 游戏' : '🔑 验证' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="到期" width="130">
            <template #default="{ row }">{{ row.valid_until ? formatDatetime(row.valid_until) : '永久' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="75">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                {{ row.status === 'active' ? '有效' : '已停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column width="80" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" type="danger" :disabled="row.status !== 'active'"
                @click="revokeAuth(row)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-divider content-position="left">新增项目授权</el-divider>
      <el-form ref="authFormRef" :model="authDialog.form" :rules="authRules" label-width="90px">
        <el-form-item label="选择项目" prop="project_id">
          <el-select v-model="authDialog.form.project_id" placeholder="请选择项目"
            filterable style="width:100%">
            <el-option v-for="p in allProjects" :key="p.id"
              :label="`${p.display_name}（${p.project_type === 'game' ? '游戏' : '验证'}）`"
              :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setAuthExpiry(30)">一个月</el-button>
              <el-button size="small" @click="setAuthExpiry(90)">三个月</el-button>
              <el-button size="small" @click="setAuthExpiry(365)">一年</el-button>
              <el-button size="small" type="info" plain @click="authDialog.form.valid_until = null">永久</el-button>
            </div>
            <el-date-picker v-model="authDialog.form.valid_until" type="datetime"
              placeholder="不填为永久有效" style="width:100%" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="authDialog.grantLoading" @click="grantAuth">授予权限</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>

    <!-- ───── 点数余额弹窗 ───── -->
    <el-dialog v-model="balanceDialog.visible"
      :title="`点数管理 — ${balanceDialog.agentName}`"
      width="600px" destroy-on-close>
      <!-- 当前余额 -->
      <div class="balance-summary" v-loading="balanceDialog.loading">
        <div class="balance-item charged">
          <div class="bal-num">{{ (balanceDialog.info?.charged_points ?? 0).toFixed(2) }}</div>
          <div class="bal-lbl">充值点数</div>
        </div>
        <div class="balance-item credit">
          <div class="bal-num">{{ (balanceDialog.info?.credit_points ?? 0).toFixed(2) }}</div>
          <div class="bal-lbl">授信点数</div>
        </div>
        <div class="balance-item frozen">
          <div class="bal-num">{{ (balanceDialog.info?.frozen_credit ?? 0).toFixed(2) }}</div>
          <div class="bal-lbl">已冻结授信</div>
        </div>
        <div class="balance-item total">
          <div class="bal-num highlight">{{ (balanceDialog.info?.available_total ?? 0).toFixed(2) }}</div>
          <div class="bal-lbl">可用余额</div>
        </div>
      </div>

      <el-divider />

      <!-- 操作区 -->
      <el-tabs v-model="balanceDialog.tab" class="balance-tabs">
        <el-tab-pane label="充值" name="recharge">
          <el-form :model="balanceDialog.rechargeForm" label-width="80px" style="margin-top:12px">
            <el-form-item label="充值点数">
              <el-input-number v-model="balanceDialog.rechargeForm.amount" :min="0.01"
                :precision="2" :step="100" controls-position="right" style="width:200px" />
              <div class="quick-btns" style="margin-top:6px">
                <el-button size="small" @click="balanceDialog.rechargeForm.amount = 100">100</el-button>
                <el-button size="small" @click="balanceDialog.rechargeForm.amount = 500">500</el-button>
                <el-button size="small" @click="balanceDialog.rechargeForm.amount = 1000">1000</el-button>
                <el-button size="small" @click="balanceDialog.rechargeForm.amount = 5000">5000</el-button>
              </div>
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="balanceDialog.rechargeForm.description"
                placeholder="线下付款备注，如：微信转账 ¥100" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="balanceDialog.opLoading"
                @click="doRecharge">确认充值</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="授信" name="credit">
          <el-form :model="balanceDialog.creditForm" label-width="80px" style="margin-top:12px">
            <el-form-item label="授信点数">
              <el-input-number v-model="balanceDialog.creditForm.amount" :min="0.01"
                :precision="2" :step="100" controls-position="right" style="width:200px" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="balanceDialog.creditForm.description" placeholder="授信原因" />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="balanceDialog.opLoading"
                @click="doCredit">确认授信</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="冻结/解冻" name="freeze">
          <el-form :model="balanceDialog.freezeForm" label-width="80px" style="margin-top:12px">
            <el-form-item label="操作金额">
              <el-input-number v-model="balanceDialog.freezeForm.amount" :min="0.01"
                :precision="2" controls-position="right" style="width:200px" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="balanceDialog.freezeForm.description" placeholder="冻结/解冻原因" />
            </el-form-item>
            <el-form-item>
              <el-button type="danger" :loading="balanceDialog.opLoading"
                @click="doFreeze">冻结授信</el-button>
              <el-button :loading="balanceDialog.opLoading"
                @click="doUnfreeze" style="margin-left:12px">解冻授信</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="流水记录" name="txlog">
          <el-table v-loading="balanceDialog.txLoading" :data="balanceDialog.transactions"
            size="small" max-height="280" style="margin-top:8px">
            <el-table-column label="时间" width="140">
              <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="类型" width="75">
              <template #default="{ row }">
                <el-tag size="small"
                  :type="{ recharge:'success', credit:'warning', consume:'danger', freeze:'info', unfreeze:'', adjust:'' }[row.tx_type]">
                  {{ row.tx_type_label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="余额类型" width="90">
              <template #default="{ row }">
                {{ row.balance_type === 'charged' ? '充值' : '授信' }}
              </template>
            </el-table-column>
            <el-table-column label="变动" width="90" align="right">
              <template #default="{ row }">
                <span :class="row.amount >= 0 ? 'amt-pos' : 'amt-neg'">
                  {{ row.amount >= 0 ? '+' : '' }}{{ row.amount.toFixed(2) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="变后余额" width="100" align="right">
              <template #default="{ row }">{{ row.balance_after.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="备注" min-width="120" show-overflow-tooltip prop="description" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { agentApi }   from '@/api/agent'
import { projectApi } from '@/api/project'
import { balanceApi } from '@/api/balance'
import { useAuthStore } from '@/stores/auth'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatDatetime } from '@/utils/format'

const auth = useAuthStore()

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit'
}) : '—'

// ── 列表 ────────────────────────────────────────────────────
const loading     = ref(false)
const agents      = ref([])
const selectedIds = ref([])
const batchLoading = ref(false)
const filter      = reactive({ status: null })
const pagination  = reactive({ page: 1, pageSize: 20, total: 0 })

const loadAgents = async () => {
  loading.value = true
  try {
    const res = await balanceApi.agentsFull({
      page:      pagination.page,
      page_size: pagination.pageSize,
      status:    filter.status || undefined,
    })
    agents.value     = res.data.agents
    pagination.total = res.data.total
  } finally { loading.value = false }
}

const resetFilter = () => {
  filter.status = null; pagination.page = 1; loadAgents()
}
const onSelectionChange = (rows) => { selectedIds.value = rows.map(r => r.id) }
onMounted(loadAgents)

const batchDelete = async () => {
  batchLoading.value = true
  const ids = [...selectedIds.value]
  try {
    const results = await Promise.allSettled(ids.map(id => agentApi.delete(id)))
    const failed  = results.filter(r => r.status === 'rejected').length
    const success = results.filter(r => r.status === 'fulfilled').length
    failed === 0 ? ElMessage.success(`已删除 ${success} 个`) : ElMessage.warning(`成功 ${success}，失败 ${failed}`)
    selectedIds.value = []
    loadAgents()
  } finally { batchLoading.value = false }
}

const toggleStatus = async (row) => {
  await agentApi.update(row.id, { status: row.status === 'active' ? 'suspended' : 'active' })
  ElMessage.success('操作成功'); loadAgents()
}
const deleteAgent = async (row) => {
  await agentApi.delete(row.id); ElMessage.success('已删除代理'); loadAgents()
}

// ── 新建 / 编辑 ─────────────────────────────────────────────
const dialogFormRef = ref(null)
const dialog = reactive({
  visible: false, isEdit: false, loading: false, editId: null,
  form: { username: '', password: '', parent_agent_id: null, max_users: 0, commission_rate: null },
})
const dialogRules = {
  username: [{ required: true, message: '请输入代理名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码',   trigger: 'blur' }],
}
const openCreateDialog = () => {
  dialog.isEdit = false; dialog.editId = null
  dialog.form = { username: '', password: '', parent_agent_id: null, max_users: 0, commission_rate: null }
  dialog._uid  = Date.now()   // 每次开启生成唯一 name，徹底防止浏览器记忆项匹配
  dialog.visible = true
}
const openEditDialog = (row) => {
  dialog.isEdit = true; dialog.editId = row.id
  dialog.form = { max_users: row.max_users, commission_rate: row.commission_rate }
  dialog.visible = true
}
const submitDialog = async () => {
  if (!await dialogFormRef.value?.validate().catch(() => false)) return
  dialog.loading = true
  try {
    if (dialog.isEdit) {
      await agentApi.update(dialog.editId, {
        max_users: dialog.form.max_users, commission_rate: dialog.form.commission_rate,
      })
    } else {
      await agentApi.create({
        username: dialog.form.username, password: dialog.form.password,
        parent_agent_id: dialog.form.parent_agent_id || null,
        max_users: dialog.form.max_users, commission_rate: dialog.form.commission_rate,
      })
    }
    ElMessage.success('操作成功'); dialog.visible = false; loadAgents()
  } finally { dialog.loading = false }
}

// ── 项目授权弹窗 ────────────────────────────────────────────
const authFormRef  = ref(null)
const allProjects  = ref([])
const authDialog   = reactive({
  visible: false, agentId: null, agentName: '',
  auths: [], listLoading: false, grantLoading: false,
  form: { project_id: null, valid_until: null },
})
const authRules = { project_id: [{ required: true, message: '请选择项目', trigger: 'change' }] }

const openAuthDialog = async (row) => {
  authDialog.agentId = row.id; authDialog.agentName = row.username
  authDialog.form = { project_id: null, valid_until: null }
  authDialog.visible = true
  loadAgentAuths()
  if (!allProjects.value.length) {
    const res = await projectApi.list({ page: 1, page_size: 100, is_active: true })
    allProjects.value = res.data.projects
  }
}
const loadAgentAuths = async () => {
  if (!authDialog.agentId) return
  authDialog.listLoading = true
  try {
    const res = await projectApi.listAgentAuths(authDialog.agentId)
    authDialog.auths = res.data
  } finally { authDialog.listLoading = false }
}
const setAuthExpiry = (days) => {
  const d = new Date(); d.setDate(d.getDate() + days); authDialog.form.valid_until = d
}
const grantAuth = async () => {
  if (!await authFormRef.value?.validate().catch(() => false)) return
  authDialog.grantLoading = true
  try {
    await projectApi.grantAgentAuth(authDialog.agentId, {
      project_id: authDialog.form.project_id, valid_until: authDialog.form.valid_until || null,
    })
    ElMessage.success('授权成功')
    authDialog.form = { project_id: null, valid_until: null }
    loadAgentAuths(); loadAgents()
  } finally { authDialog.grantLoading = false }
}
const revokeAuth = async (authRow) => {
  await projectApi.revokeAgentAuth(authDialog.agentId, authRow.id)
  ElMessage.success('已停用授权'); loadAgentAuths(); loadAgents()
}

// ── 点数余额弹窗 ────────────────────────────────────────────
const balanceDialog = reactive({
  visible: false, agentId: null, agentName: '',
  tab: 'recharge', loading: false, opLoading: false, txLoading: false,
  info: null, transactions: [],
  rechargeForm: { amount: 100,  description: '' },
  creditForm:   { amount: 100,  description: '' },
  freezeForm:   { amount: 100,  description: '' },
})

const openBalanceDialog = async (row) => {
  balanceDialog.agentId   = row.id
  balanceDialog.agentName = row.username
  balanceDialog.tab       = 'recharge'
  balanceDialog.visible   = true
  balanceDialog.rechargeForm = { amount: 100, description: '' }
  balanceDialog.creditForm   = { amount: 100, description: '' }
  balanceDialog.freezeForm   = { amount: 100, description: '' }
  await loadBalance()
  loadTransactions()
}

const loadBalance = async () => {
  balanceDialog.loading = true
  try {
    const res = await balanceApi.getBalance(balanceDialog.agentId)
    balanceDialog.info = res.data
  } finally { balanceDialog.loading = false }
}

const loadTransactions = async () => {
  balanceDialog.txLoading = true
  try {
    const res = await balanceApi.getTransactions(balanceDialog.agentId, { page: 1, page_size: 50 })
    balanceDialog.transactions = res.data.transactions
  } finally { balanceDialog.txLoading = false }
}

const doRecharge = async () => {
  balanceDialog.opLoading = true
  try {
    const res = await balanceApi.recharge(balanceDialog.agentId, {
      amount: balanceDialog.rechargeForm.amount,
      description: balanceDialog.rechargeForm.description || undefined,
    })
    balanceDialog.info = res.data
    ElMessage.success(`充值成功，可用余额: ${res.data.available_total.toFixed(2)} 点`)
    balanceDialog.rechargeForm = { amount: 100, description: '' }
    loadTransactions(); loadAgents()
  } finally { balanceDialog.opLoading = false }
}

const doCredit = async () => {
  balanceDialog.opLoading = true
  try {
    const res = await balanceApi.credit(balanceDialog.agentId, {
      amount: balanceDialog.creditForm.amount,
      description: balanceDialog.creditForm.description || undefined,
    })
    balanceDialog.info = res.data
    ElMessage.success(`授信成功`)
    balanceDialog.creditForm = { amount: 100, description: '' }
    loadTransactions(); loadAgents()
  } finally { balanceDialog.opLoading = false }
}

const doFreeze = async () => {
  balanceDialog.opLoading = true
  try {
    const res = await balanceApi.freeze(balanceDialog.agentId, {
      amount: balanceDialog.freezeForm.amount,
      description: balanceDialog.freezeForm.description || undefined,
    })
    balanceDialog.info = res.data
    ElMessage.warning(`已冻结 ${balanceDialog.freezeForm.amount} 点授信`)
    loadTransactions(); loadAgents()
  } finally { balanceDialog.opLoading = false }
}

const doUnfreeze = async () => {
  balanceDialog.opLoading = true
  try {
    const res = await balanceApi.unfreeze(balanceDialog.agentId, {
      amount: balanceDialog.freezeForm.amount,
      description: balanceDialog.freezeForm.description || undefined,
    })
    balanceDialog.info = res.data
    ElMessage.success(`已解冻 ${balanceDialog.freezeForm.amount} 点`)
    loadTransactions(); loadAgents()
  } finally { balanceDialog.opLoading = false }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }
.filter-card, .table-card { border-radius: 10px; }
.pagination { margin-top: 16px; justify-content: flex-end; }

.batch-toolbar {
  background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
  padding: 8px 16px; display: flex; align-items: center; gap: 12px;
}
.batch-info { font-size: 13px; color: #1d4ed8; font-weight: 500; }
.field-hint { font-size: 11px; color: #94a3b8; margin-top: 2px; }

/* 项目列表 */
.no-data    { font-size: 12px; color: #94a3b8; }
.project-list { display: flex; flex-wrap: wrap; gap: 6px; }
.proj-badge {
  display: flex; align-items: center; gap: 3px;
  background: #f8fafc; border-radius: 6px;
  padding: 1px 4px 1px 2px; cursor: default;
}
.proj-user-count { font-size: 11px; color: #6366f1; font-weight: 600; white-space: nowrap; }

/* 点数 */
.pts-positive { color: #10b981; font-weight: 600; font-size: 13px; }
.pts-zero     { color: #94a3b8; font-size: 13px; }
.pts-detail   { font-size: 10px; color: #94a3b8; margin-top: 1px; }

/* 余额弹窗 */
.balance-summary {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 4px;
}
.balance-item {
  background: #f8fafc; border-radius: 8px; padding: 12px 8px; text-align: center;
  border-top: 3px solid transparent;
}
.balance-item.charged { border-color: #6366f1; }
.balance-item.credit  { border-color: #f59e0b; }
.balance-item.frozen  { border-color: #ef4444; }
.balance-item.total   { border-color: #10b981; background: #f0fdf4; }
.bal-num    { font-size: 22px; font-weight: 700; color: #1e293b; line-height: 1; }
.bal-num.highlight { color: #10b981; font-size: 26px; }
.bal-lbl    { font-size: 11px; color: #64748b; margin-top: 4px; }

.balance-tabs { margin-top: 4px; }
.quick-btns { display: flex; gap: 6px; flex-wrap: wrap; }
.expiry-picker-wrap { display: flex; flex-direction: column; gap: 8px; width: 100%; }

/* 流水 */
.amt-pos { color: #10b981; font-weight: 600; }
.amt-neg { color: #ef4444; font-weight: 600; }

/* 授权弹窗 */
.auth-section { margin-bottom: 4px; }
.auth-section-title {
  font-size: 13px; font-weight: 600; color: #475569;
  margin-bottom: 8px; display: flex; align-items: center;
}
</style>
