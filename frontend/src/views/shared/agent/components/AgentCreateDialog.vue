<template>
  <el-dialog
    :model-value="visible"
    title="新建代理"
    width="620px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="105px"
      autocomplete="off"
    >
      <el-divider content-position="left">账号主体</el-divider>

      <el-form-item label="代理名" prop="username">
        <el-input
          v-model="form.username"
          autocomplete="new-password"
          placeholder="请输入代理名"
          clearable
        />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          autocomplete="new-password"
          placeholder="请输入密码"
        />
      </el-form-item>

      <el-form-item v-if="auth.isAdmin" label="上级代理 ID">
        <el-input-number
          v-model="form.parent_agent_id"
          :min="1"
          controls-position="right"
          style="width: 100%"
        />
        <div class="field-hint">留空则创建为顶级代理（直属管理员）。</div>
      </el-form-item>

      <el-form-item label="佣金比例">
        <el-input-number
          v-model="form.commission_rate"
          :min="0"
          :max="100"
          :precision="2"
          controls-position="right"
          style="width: 100%"
        />
      </el-form-item>

      <template v-if="auth.isAdmin">
        <el-divider content-position="left">业务画像</el-divider>

        <el-form-item label="业务等级" prop="tier_level">
          <el-select v-model="form.tier_level" style="width: 100%">
            <el-option
              v-for="item in levelPolicies"
              :key="item.level"
              :label="item.level_name"
              :value="item.level"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="风险状态" prop="risk_status">
          <el-select v-model="form.risk_status" style="width: 100%">
            <el-option label="正常 normal" value="normal" />
            <el-option label="观察 watch" value="watch" />
            <el-option label="限制 restricted" value="restricted" />
            <el-option label="冻结 frozen" value="frozen" />
          </el-select>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </template>

      <el-alert
        v-if="auth.isAgent"
        title="代理端创建的是直属下级代理。业务等级、风险状态、项目授权、点数由上级治理规则和后续管理流程控制。"
        type="info"
        show-icon
        :closable="false"
        class="inner-alert"
      />
    </el-form>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { agentApi } from '@/api/agent'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['update:visible', 'created'])

const auth = useAuthStore()
const formRef = ref(null)
const loading = ref(false)

const levelPolicies = ref([
  { level: 1, level_name: 'Lv.1 新手代理' },
  { level: 2, level_name: 'Lv.2 标准代理' },
  { level: 3, level_name: 'Lv.3 核心代理' },
  { level: 4, level_name: 'Lv.4 渠道代理' },
])

const form = reactive({
  username: '',
  password: '',
  parent_agent_id: null,
  commission_rate: null,
  tier_level: 1,
  risk_status: 'normal',
  remark: '',
})

const rules = {
  username: [{ required: true, message: '请输入代理名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  tier_level: [{ required: true, message: '请选择业务等级', trigger: 'change' }],
}

const resetForm = () => {
  form.username = ''
  form.password = ''
  form.parent_agent_id = null
  form.commission_rate = null
  form.tier_level = 1
  form.risk_status = 'normal'
  form.remark = ''
}

const loadPolicies = async () => {
  if (!auth.isAdmin) return

  try {
    const res = await adminAgentProfileApi.levelPolicies()
    if (Array.isArray(res.data) && res.data.length) {
      levelPolicies.value = res.data
    }
  } catch {
    // 使用默认等级策略
  }
}

watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      resetForm()
      await loadPolicies()
    }
  },
)

const normalizeNullableText = (value) => {
  const text = String(value ?? '').trim()
  return text ? text : null
}

const submit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true

  try {
    const payload = {
      username: form.username,
      password: form.password,
      commission_rate: form.commission_rate,
    }

    if (auth.isAdmin) {
      payload.parent_agent_id = form.parent_agent_id || null
    }

    const res = await agentApi.create(payload)

    if (auth.isAdmin && res.data?.id) {
      await adminAgentProfileApi.updateBusinessProfile(res.data.id, {
        tier_level: form.tier_level,
        risk_status: form.risk_status,
        remark: normalizeNullableText(form.remark),
      })
    }

    ElMessage.success('代理创建成功')
    emit('update:visible', false)
    emit('created')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.field-hint {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 4px;
}

.inner-alert {
  margin-top: 12px;
}
</style>