<template>
  <el-drawer
    :model-value="visible"
    size="820px"
    :title="agent ? `编辑代理 — ${agent.username}` : '编辑代理'"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-loading="loading" class="drawer-body">
      <template v-if="localAgent">
        <div class="drawer-head">
          <div class="drawer-avatar">
            {{ localAgent.username.charAt(0).toUpperCase() }}
          </div>

          <div class="drawer-meta">
            <div class="drawer-name">{{ localAgent.username }}</div>
            <div class="drawer-sub">
              ID: {{ localAgent.id }}
              · 组织层级 Lv.{{ localAgent.hierarchy_depth }}
              · {{ localAgent.status === 'active' ? '正常' : '已停用' }}
            </div>
          </div>
        </div>

        <el-tabs v-model="activeTab" class="drawer-tabs">
          <el-tab-pane label="基础信息" name="base">
            <el-form label-width="120px" :model="baseForm">
              <el-form-item label="账号状态">
                <el-select v-model="baseForm.status" style="width: 100%">
                  <el-option label="正常 active" value="active" />
                  <el-option label="停用 suspended" value="suspended" />
                </el-select>
              </el-form-item>

              <el-form-item label="佣金比例">
                <el-input-number
                  v-model="baseForm.commission_rate"
                  :min="0"
                  :max="100"
                  :precision="2"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :loading="saveLoading" @click="saveBase">
                  保存基础信息
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="业务画像" name="profile">
            <el-form label-width="145px" :model="profileForm">
              <el-form-item label="业务等级">
                <el-select v-model="profileForm.tier_level" style="width: 100%">
                  <el-option
                    v-for="item in levelPolicies"
                    :key="item.level"
                    :label="item.level_name"
                    :value="item.level"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="风险状态">
                <el-select v-model="profileForm.risk_status" style="width: 100%">
                  <el-option label="正常 normal" value="normal" />
                  <el-option label="观察 watch" value="watch" />
                  <el-option label="限制 restricted" value="restricted" />
                  <el-option label="冻结 frozen" value="frozen" />
                </el-select>
              </el-form-item>

              <el-divider content-position="left">能力覆盖</el-divider>

              <el-form-item label="默认授信覆盖">
                <el-input-number
                  v-model="profileForm.credit_limit_override"
                  :min="0"
                  :precision="2"
                  controls-position="right"
                  style="width: 100%"
                />
                <div class="field-hint">
                  当前等级默认授信：{{ numberText(currentPolicy?.default_credit_limit) }} 点；
                  最高授信：{{ numberText(currentPolicy?.max_credit_limit) }} 点。
                </div>
              </el-form-item>

              <el-form-item label="最高授信覆盖">
                <el-input-number
                  v-model="profileForm.max_credit_limit_override"
                  :min="0"
                  :precision="2"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>

              <el-form-item label="下级创建覆盖">
                <el-select
                  v-model="profileForm.can_create_sub_agents_override"
                  clearable
                  placeholder="使用等级策略"
                  style="width: 100%"
                >
                  <el-option label="允许" :value="true" />
                  <el-option label="不允许" :value="false" />
                </el-select>
              </el-form-item>

              <el-form-item label="最大下级覆盖">
                <el-input-number
                  v-model="profileForm.max_sub_agents_override"
                  :min="0"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>

              <el-form-item label="备注">
                <el-input
                  v-model="profileForm.remark"
                  type="textarea"
                  :rows="4"
                  maxlength="2000"
                  show-word-limit
                />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :loading="saveLoading" @click="saveProfile">
                  保存业务画像
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="授权项目" name="projects">
            <div class="section-title-row">
              <span class="section-title">已授权项目</span>
              <el-button size="small" :icon="Refresh" @click="loadProjectAuths">
                刷新
              </el-button>
            </div>

            <el-table
              v-loading="projectLoading"
              :data="projectAuths"
              size="small"
              stripe
              empty-text="暂无授权项目"
            >
              <el-table-column label="项目名称" min-width="150">
                <template #default="{ row }">{{ projectDisplayName(row) }}</template>
              </el-table-column>

              <el-table-column label="类型" width="90">
                <template #default="{ row }">
                  <el-tag
                    :type="row.project_type === 'game' ? 'primary' : 'info'"
                    effect="plain"
                    size="small"
                  >
                    {{ row.project_type === 'game' ? '游戏' : '验证' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="到期" width="150">
                <template #default="{ row }">
                  {{ row.valid_until ? fmtDate(row.valid_until) : '永久' }}
                </template>
              </el-table-column>

              <el-table-column label="状态" width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="row.status === 'active' ? 'success' : 'info'"
                    effect="light"
                    size="small"
                  >
                    {{ row.status === 'active' ? '有效' : '已停用' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column width="80" fixed="right">
                <template #default="{ row }">
                  <el-button
                    text
                    size="small"
                    type="danger"
                    :disabled="row.status !== 'active'"
                    @click="revokeAuth(row)"
                  >
                    停用
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-divider content-position="left">新增项目授权</el-divider>

            <el-form ref="authFormRef" :model="authForm" :rules="authRules" label-width="90px">
              <el-form-item label="选择项目" prop="project_id">
                <el-select
                  v-model="authForm.project_id"
                  placeholder="请选择项目"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="p in projects"
                    :key="projectKey(p)"
                    :label="`${projectDisplayName(p)}（${p.project_type === 'game' ? '游戏' : '验证'}）`"
                    :value="Number(p.id || p.project_id)"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="到期时间">
                <div class="quick-btns">
                  <el-button size="small" @click="setAuthExpiry(30)">一个月</el-button>
                  <el-button size="small" @click="setAuthExpiry(90)">三个月</el-button>
                  <el-button size="small" @click="setAuthExpiry(365)">一年</el-button>
                  <el-button
                    v-if="auth.isAdmin"
                    size="small"
                    type="info"
                    plain
                    @click="authForm.valid_until = null"
                  >
                    永久
                  </el-button>
                </div>

                <el-date-picker
                  v-model="authForm.valid_until"
                  type="datetime"
                  :placeholder="auth.isAdmin ? '不填为永久有效' : '代理端请不要超过自身项目到期时间'"
                  style="width: 100%; margin-top: 8px"
                />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :loading="grantLoading" @click="grantAuth">
                  授予权限
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="点数管理" name="balance">
            <div class="balance-summary" v-loading="balanceLoading">
              <div class="balance-item charged">
                <div class="bal-num">{{ numberText(balanceValue('charged')) }}</div>
                <div class="bal-lbl">充值点数</div>
              </div>

              <div class="balance-item credit">
                <div class="bal-num">{{ numberText(balanceValue('credit')) }}</div>
                <div class="bal-lbl">授信点数</div>
              </div>

              <div class="balance-item frozen">
                <div class="bal-num">{{ numberText(balance?.frozen_credit) }}</div>
                <div class="bal-lbl">已冻结授信</div>
              </div>

              <div class="balance-item total">
                <div class="bal-num highlight">{{ numberText(balance?.available_total) }}</div>
                <div class="bal-lbl">可用余额</div>
              </div>
            </div>

            <el-alert
              title="授信默认值会根据业务画像中的业务等级显示；代理端授信会从当前代理自身授信点数中划拨给下级。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-tabs v-model="balanceTab" class="balance-tabs">
              <el-tab-pane label="充值" name="recharge">
                <el-form :model="rechargeForm" label-width="80px" style="margin-top: 12px">
                  <el-form-item label="充值点数">
                    <el-input-number
                      v-model="rechargeForm.amount"
                      :min="0.01"
                      :precision="2"
                      :step="100"
                      controls-position="right"
                      style="width: 220px"
                    />
                  </el-form-item>

                  <el-form-item label="备注">
                    <el-input v-model="rechargeForm.description" placeholder="充值备注" />
                  </el-form-item>

                  <el-form-item>
                    <el-button
                      type="primary"
                      :loading="balanceOpLoading"
                      @click="doRecharge"
                    >
                      确认充值
                    </el-button>
                  </el-form-item>
                </el-form>
              </el-tab-pane>

              <el-tab-pane label="授信" name="credit">
                <el-form :model="creditForm" label-width="80px" style="margin-top: 12px">
                  <el-form-item label="授信点数">
                    <el-input-number
                      v-model="creditForm.amount"
                      :min="0.01"
                      :precision="2"
                      :step="100"
                      controls-position="right"
                      style="width: 220px"
                    />

                    <el-button
                      size="small"
                      type="primary"
                      plain
                      style="margin-left: 8px"
                      @click="useCurrentDefaultCredit"
                    >
                      填入默认授信
                    </el-button>

                    <div class="field-hint credit-policy-hint">
                      {{ currentDefaultCreditText }}
                    </div>
                  </el-form-item>

                  <el-form-item label="备注">
                    <el-input v-model="creditForm.description" placeholder="授信原因" />
                  </el-form-item>

                  <el-form-item>
                    <el-button
                      type="warning"
                      :loading="balanceOpLoading"
                      @click="doCredit"
                    >
                      确认授信
                    </el-button>
                  </el-form-item>
                </el-form>
              </el-tab-pane>

              <el-tab-pane label="冻结/解冻" name="freeze">
                <el-form :model="freezeForm" label-width="80px" style="margin-top: 12px">
                  <el-form-item label="操作金额">
                    <el-input-number
                      v-model="freezeForm.amount"
                      :min="0.01"
                      :precision="2"
                      controls-position="right"
                      style="width: 220px"
                    />
                  </el-form-item>

                  <el-form-item label="备注">
                    <el-input v-model="freezeForm.description" placeholder="冻结/解冻原因" />
                  </el-form-item>

                  <el-form-item>
                    <el-button
                      type="danger"
                      :loading="balanceOpLoading"
                      @click="doFreeze"
                    >
                      冻结授信
                    </el-button>

                    <el-button
                      :loading="balanceOpLoading"
                      style="margin-left: 12px"
                      @click="doUnfreeze"
                    >
                      解冻授信
                    </el-button>
                  </el-form-item>
                </el-form>
              </el-tab-pane>

              <el-tab-pane label="流水记录" name="txlog">
                <el-table
                  v-loading="txLoading"
                  :data="transactions"
                  size="small"
                  max-height="320"
                  stripe
                  empty-text="暂无流水"
                  style="margin-top: 8px"
                >
                  <el-table-column label="时间" width="150">
                    <template #default="{ row }">
                      {{ fmtDate(row.created_at || row.posted_at) }}
                    </template>
                  </el-table-column>

                  <el-table-column label="类型" width="90">
                    <template #default="{ row }">
                      <el-tag size="small" effect="light">
                        {{ row.entry_type_label || row.entry_type }}
                      </el-tag>
                    </template>
                  </el-table-column>

                  <el-table-column label="余额类型" width="100">
                    <template #default="{ row }">
                      {{ row.balance_type_label || row.balance_type || '—' }}
                    </template>
                  </el-table-column>

                  <el-table-column label="变动" width="100" align="right">
                    <template #default="{ row }">
                      <span :class="Number(row.amount || 0) >= 0 ? 'amt-pos' : 'amt-neg'">
                        {{ Number(row.amount || 0) >= 0 ? '+' : '' }}{{ numberText(row.amount) }}
                      </span>
                    </template>
                  </el-table-column>

                  <el-table-column label="变后余额" width="110" align="right">
                    <template #default="{ row }">
                      {{ numberText(row.balance_after) }}
                    </template>
                  </el-table-column>

                  <el-table-column label="说明" min-width="180" show-overflow-tooltip>
                    <template #default="{ row }">
                      {{ row.business_text || row.description || '—' }}
                    </template>
                  </el-table-column>
                </el-table>

                <div class="tx-actions">
                  <el-button
                    size="small"
                    :icon="Refresh"
                    :loading="txLoading"
                    @click="loadTransactions"
                  >
                    刷新流水
                  </el-button>
                </div>
              </el-tab-pane>
            </el-tabs>
          </el-tab-pane>

          <el-tab-pane label="修改密码" name="password">
            <el-alert
              title="自动生成密码时，明文只会在本次响应中返回，请复制后妥善保存。"
              type="warning"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-form label-width="120px" :model="passwordForm">
              <el-form-item label="重置方式">
                <el-radio-group v-model="passwordForm.auto_generate">
                  <el-radio :label="true">自动生成</el-radio>
                  <el-radio :label="false">手动设置</el-radio>
                </el-radio-group>
              </el-form-item>

              <el-form-item v-if="!passwordForm.auto_generate" label="新密码">
                <el-input
                  v-model="passwordForm.new_password"
                  type="password"
                  show-password
                  autocomplete="new-password"
                  placeholder="请输入新密码"
                />
              </el-form-item>

              <el-form-item>
                <el-button type="danger" :loading="passwordLoading" @click="resetPassword">
                  重置密码
                </el-button>
              </el-form-item>

              <el-form-item v-if="generatedPassword" label="生成密码">
                <el-input :model-value="generatedPassword" readonly>
                  <template #append>
                    <el-button @click="copyGeneratedPassword">复制</el-button>
                  </template>
                </el-input>
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { agentApi } from '@/api/agent'
import { agentScopeApi } from '@/api/agentScope'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { adminBalanceApi as balanceApi } from '@/api/admin/balance'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  agent: {
    type: Object,
    default: null,
  },
  projects: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:visible', 'saved'])

const auth = useAuthStore()

const loading = ref(false)
const saveLoading = ref(false)
const activeTab = ref('base')
const balanceTab = ref('recharge')

const localAgent = ref(null)
const levelPolicies = ref([])
const projectAuths = ref([])
const balance = ref(null)
const transactions = ref([])

const projectLoading = ref(false)
const grantLoading = ref(false)
const balanceLoading = ref(false)
const balanceOpLoading = ref(false)
const txLoading = ref(false)
const passwordLoading = ref(false)
const generatedPassword = ref('')

const baseForm = reactive({
  status: 'active',
  commission_rate: null,
})

const profileForm = reactive({
  tier_level: 1,
  risk_status: 'normal',
  remark: '',
  credit_limit_override: null,
  max_credit_limit_override: null,
  can_create_sub_agents_override: null,
  max_sub_agents_override: null,
})

const authFormRef = ref(null)
const authForm = reactive({
  project_id: null,
  valid_until: null,
})

const authRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
}

const rechargeForm = reactive({
  amount: 100,
  description: '',
})

const creditForm = reactive({
  amount: 100,
  description: '',
})

const freezeForm = reactive({
  amount: 100,
  description: '',
})

const passwordForm = reactive({
  auto_generate: true,
  new_password: '',
})

const numberText = (value) => Number(value || 0).toFixed(2)

const fmtDate = (iso) => {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const projectDisplayName = (project) =>
  project?.display_name ||
  project?.project_display_name ||
  project?.project_name ||
  project?.game_project_name ||
  project?.code_name ||
  project?.project_code ||
  project?.game_project_code ||
  '未命名项目'

const projectKey = (project) =>
  project?.project_id ||
  project?.id ||
  project?.game_project_id ||
  project?.code_name ||
  project?.project_code ||
  project?.game_project_code ||
  projectDisplayName(project)

const selectableLevelPolicies = computed(() => {
  if (auth.isAdmin) {
    return levelPolicies.value
  }

  return levelPolicies.value.filter((item) => {
    return Number(item.level) < Number(auth.user?.tier_level || 999)
  })
})

const currentPolicy = computed(() => {
  return levelPolicies.value.find((p) => Number(p.level) === Number(profileForm.tier_level))
})

const currentDefaultCreditText = computed(() => {
  const policy = currentPolicy.value
  if (!policy) return '未加载业务等级策略'
  return `当前业务等级默认授信：${numberText(policy.default_credit_limit)} 点，最高授信：${numberText(policy.max_credit_limit)} 点`
})

const resetState = () => {
  activeTab.value = 'base'
  balanceTab.value = 'recharge'
  localAgent.value = null
  projectAuths.value = []
  balance.value = null
  transactions.value = []
  generatedPassword.value = ''

  baseForm.status = 'active'
  baseForm.commission_rate = null

  profileForm.tier_level = 1
  profileForm.risk_status = 'normal'
  profileForm.remark = ''
  profileForm.credit_limit_override = null
  profileForm.max_credit_limit_override = null
  profileForm.can_create_sub_agents_override = null
  profileForm.max_sub_agents_override = null

  authForm.project_id = null
  authForm.valid_until = null

  rechargeForm.amount = 100
  rechargeForm.description = ''
  creditForm.amount = 100
  creditForm.description = ''
  freezeForm.amount = 100
  freezeForm.description = ''

  passwordForm.auto_generate = true
  passwordForm.new_password = ''
}

const loadLevelPolicies = async () => {
  const res = auth.isAdmin
    ? await adminAgentProfileApi.levelPolicies()
    : await agentScopeApi.levelPolicies()

  levelPolicies.value = Array.isArray(res.data) ? res.data : []
}

const loadDetail = async () => {
  if (!props.agent?.id) return

  loading.value = true

  try {
    resetState()
    await loadLevelPolicies()

    const detailRes = await agentApi.detail(props.agent.id)
    localAgent.value = detailRes.data

    baseForm.status = detailRes.data.status
    baseForm.commission_rate = detailRes.data.commission_rate

    await Promise.all([
      loadProfile(),
      loadProjectAuths(),
      loadBalance(),
      loadTransactions(),
    ])
  } finally {
    loading.value = false
  }
}

const loadProfile = async () => {
  if (!props.agent?.id) return

  const res = auth.isAdmin
    ? await adminAgentProfileApi.businessProfile(props.agent.id)
    : await agentScopeApi.businessProfile(props.agent.id)

  const data = res.data || {}

  profileForm.tier_level = data.tier_level || 1
  profileForm.risk_status = data.risk_status || 'normal'
  profileForm.remark = data.remark || ''
  profileForm.credit_limit_override = data.credit_limit_override ?? data.credit_limit ?? null
  profileForm.max_credit_limit_override = data.max_credit_limit_override ?? data.max_credit_limit ?? null
  profileForm.can_create_sub_agents_override = data.can_create_sub_agents_override ?? null
  profileForm.max_sub_agents_override = data.max_sub_agents_override ?? null
}

const loadProjectAuths = async () => {
  if (!props.agent?.id) return

  projectLoading.value = true

  try {
    const res = auth.isAdmin
      ? await projectApi.listAgentAuths(props.agent.id)
      : await agentScopeApi.projectAuths(props.agent.id)

    projectAuths.value = Array.isArray(res.data) ? res.data : []
  } finally {
    projectLoading.value = false
  }
}

const loadBalance = async () => {
  if (!props.agent?.id) return

  balanceLoading.value = true

  try {
    const res = auth.isAdmin
      ? await balanceApi.getBalance(props.agent.id)
      : await agentScopeApi.balance(props.agent.id)

    balance.value = res.data
  } finally {
    balanceLoading.value = false
  }
}

const loadTransactions = async () => {
  if (!props.agent?.id) return

  txLoading.value = true

  try {
    const res = auth.isAdmin
      ? await balanceApi.getTransactions(props.agent.id, { page: 1, page_size: 50 })
      : await agentScopeApi.transactions(props.agent.id, { page: 1, page_size: 50 })

    transactions.value = res.data?.transactions || []
  } finally {
    txLoading.value = false
  }
}

const saveBase = async () => {
  if (!localAgent.value) return

  saveLoading.value = true

  try {
    await agentApi.update(localAgent.value.id, {
      status: baseForm.status,
      commission_rate: baseForm.commission_rate,
    })

    ElMessage.success('基础信息已保存')
    emit('saved')
    await loadDetail()
  } finally {
    saveLoading.value = false
  }
}

const saveProfile = async () => {
  if (!localAgent.value) return

  saveLoading.value = true

  try {
    const payload = {
      tier_level: profileForm.tier_level,
      risk_status: profileForm.risk_status,
      remark: profileForm.remark || null,
      credit_limit_override: profileForm.credit_limit_override,
      max_credit_limit_override: profileForm.max_credit_limit_override,
      can_create_sub_agents_override: profileForm.can_create_sub_agents_override,
      max_sub_agents_override: profileForm.max_sub_agents_override,
    }

    if (auth.isAdmin) {
      await adminAgentProfileApi.updateBusinessProfile(localAgent.value.id, payload)
    } else {
      await agentScopeApi.updateBusinessProfile(localAgent.value.id, payload)
    }

    ElMessage.success('业务画像已保存')
    emit('saved')
    await loadProfile()
  } finally {
    saveLoading.value = false
  }
}

const setAuthExpiry = (days) => {
  const d = new Date()
  d.setDate(d.getDate() + days)
  authForm.valid_until = d
}

const grantAuth = async () => {
  if (!localAgent.value) return

  const valid = await authFormRef.value?.validate().catch(() => false)
  if (!valid) return

  grantLoading.value = true

  try {
    const payload = {
      project_id: authForm.project_id,
      valid_until: authForm.valid_until || null,
    }

    if (auth.isAdmin) {
      await projectApi.grantAgentAuth(localAgent.value.id, payload)
    } else {
      await agentScopeApi.grantProjectAuth(localAgent.value.id, payload)
    }

    ElMessage.success('项目授权成功')

    authForm.project_id = null
    authForm.valid_until = null

    emit('saved')
    await loadProjectAuths()
  } finally {
    grantLoading.value = false
  }
}

const revokeAuth = async (row) => {
  if (!localAgent.value) return

  if (auth.isAdmin) {
    await projectApi.revokeAgentAuth(localAgent.value.id, row.id || row.project_auth_id)
  } else {
    await agentScopeApi.revokeProjectAuth(localAgent.value.id, row.id || row.project_auth_id)
  }

  ElMessage.success('已停用项目授权')
  emit('saved')
  await loadProjectAuths()
}

const balanceValue = (type) => {
  if (type === 'charged') {
    return balance.value?.charged_balance
  }
  if (type === 'credit') {
    return balance.value?.credit_balance
  }
  return 0
}

const useCurrentDefaultCredit = () => {
  const policy = currentPolicy.value
  if (policy) {
    creditForm.amount = Number(policy.default_credit_limit || 0)
  }
}

const doRecharge = async () => {
  if (!localAgent.value) return

  balanceOpLoading.value = true

  try {
    const payload = {
      amount: rechargeForm.amount,
      description: rechargeForm.description || undefined,
    }

    if (auth.isAdmin) {
      await balanceApi.recharge(localAgent.value.id, payload)
    } else {
      await agentScopeApi.recharge(localAgent.value.id, payload)
    }

    ElMessage.success('充值成功')
    rechargeForm.amount = 100
    rechargeForm.description = ''
    emit('saved')
    await Promise.all([loadBalance(), loadTransactions()])
  } finally {
    balanceOpLoading.value = false
  }
}

const doCredit = async () => {
  if (!localAgent.value) return

  balanceOpLoading.value = true

  try {
    const payload = {
      amount: creditForm.amount,
      description: creditForm.description || undefined,
    }

    if (auth.isAdmin) {
      await balanceApi.credit(localAgent.value.id, payload)
    } else {
      await agentScopeApi.credit(localAgent.value.id, payload)
    }

    ElMessage.success('授信成功')
    creditForm.amount = 100
    creditForm.description = ''
    emit('saved')
    await Promise.all([loadBalance(), loadTransactions()])
  } finally {
    balanceOpLoading.value = false
  }
}

const doFreeze = async () => {
  if (!localAgent.value) return

  balanceOpLoading.value = true

  try {
    const payload = {
      amount: freezeForm.amount,
      description: freezeForm.description || undefined,
    }

    if (auth.isAdmin) {
      await balanceApi.freeze(localAgent.value.id, payload)
    } else {
      await agentScopeApi.freeze(localAgent.value.id, payload)
    }

    ElMessage.success('冻结成功')
    emit('saved')
    await Promise.all([loadBalance(), loadTransactions()])
  } finally {
    balanceOpLoading.value = false
  }
}

const doUnfreeze = async () => {
  if (!localAgent.value) return

  balanceOpLoading.value = true

  try {
    const payload = {
      amount: freezeForm.amount,
      description: freezeForm.description || undefined,
    }

    if (auth.isAdmin) {
      await balanceApi.unfreeze(localAgent.value.id, payload)
    } else {
      await agentScopeApi.unfreeze(localAgent.value.id, payload)
    }

    ElMessage.success('解冻成功')
    emit('saved')
    await Promise.all([loadBalance(), loadTransactions()])
  } finally {
    balanceOpLoading.value = false
  }
}

const resetPassword = async () => {
  if (!localAgent.value) return

  if (!passwordForm.auto_generate && !passwordForm.new_password) {
    ElMessage.warning('请输入新密码')
    return
  }

  passwordLoading.value = true
  generatedPassword.value = ''

  try {
    const payload = {
      auto_generate: passwordForm.auto_generate,
      new_password: passwordForm.auto_generate ? null : passwordForm.new_password,
    }

    const res = auth.isAdmin
      ? await adminAgentProfileApi.resetPassword(localAgent.value.id, payload)
      : await agentScopeApi.resetPassword(localAgent.value.id, payload)

    generatedPassword.value = res.data?.generated_password || ''
    passwordForm.new_password = ''

    ElMessage.success(
      generatedPassword.value
        ? '密码已重置，请复制生成密码'
        : '密码已重置',
    )
  } finally {
    passwordLoading.value = false
  }
}

const copyGeneratedPassword = async () => {
  if (!generatedPassword.value) return
  await navigator.clipboard.writeText(generatedPassword.value)
  ElMessage.success('已复制')
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      loadDetail()
    }
  },
)

watch(
  () => profileForm.tier_level,
  (newLevel, oldLevel) => {
    if (!newLevel || newLevel === oldLevel) return

    const policy = currentPolicy.value
    if (!policy) return

    profileForm.credit_limit_override = Number(policy.default_credit_limit || 0)
    profileForm.max_credit_limit_override = Number(policy.max_credit_limit || 0)
    profileForm.can_create_sub_agents_override = !!policy.can_create_sub_agents
    profileForm.max_sub_agents_override = Number(policy.max_sub_agents || 0)
  },
)
</script>

<style scoped>
.drawer-body {
  padding: 0 4px;
}

.drawer-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}

.drawer-avatar {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.drawer-name {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
}

.drawer-sub,
.field-hint {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 4px;
}

.drawer-tabs {
  margin-top: 8px;
}

.section-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-title {
  font-weight: 600;
  color: #1e293b;
}

.quick-btns {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.balance-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.balance-item {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px;
  background: #fff;
}

.bal-num {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}

.bal-num.highlight {
  color: #2563eb;
}

.bal-lbl {
  color: #64748b;
  font-size: 12px;
  margin-top: 4px;
}

.amt-pos {
  color: #059669;
}

.amt-neg {
  color: #dc2626;
}

.credit-policy-hint {
  width: 100%;
  margin-top: 6px;
}

.inner-alert {
  margin-bottom: 12px;
}

.tx-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .balance-summary {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>