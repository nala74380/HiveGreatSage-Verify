<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>项目准入策略</h2>
        <p class="page-desc">
          管理每个项目在代理端的可见性、申请规则、自动开通规则和最低代理等级。
        </p>
      </div>
      <el-button :icon="Refresh" @click="loadPolicies" :loading="loading">刷新</el-button>
    </div>

    <el-alert
      title="项目开通本身不扣点；代理给用户授权项目时才扣点。隐藏项目不会出现在代理项目目录中。"
      type="info"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="policies"
        stripe
        row-key="project_id"
        style="width:100%"
      >
        <el-table-column prop="project_id" label="项目ID" width="80" />

        <el-table-column label="项目" min-width="180">
          <template #default="{ row }">
            <div class="project-name">{{ row.project_name }}</div>
            <div class="project-code">{{ row.project_code }}</div>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag :type="row.project_type === 'game' ? 'primary' : 'info'" effect="plain">
              {{ row.project_type === 'game' ? '游戏项目' : '验证项目' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="可见性" width="130">
          <template #default="{ row }">
            <el-tag :type="visibilityTagType(row.visibility_mode)" effect="light">
              {{ visibilityLabel(row.visibility_mode) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="开通模式" width="145">
          <template #default="{ row }">
            <el-tag :type="openModeTagType(row.open_mode)" effect="plain">
              {{ openModeLabel(row.open_mode) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="等级门槛" min-width="230">
          <template #default="{ row }">
            <div class="rule-line">可见：Lv.{{ row.min_visible_agent_level }}</div>
            <div class="rule-line">申请：Lv.{{ row.min_apply_agent_level }}</div>
            <div class="rule-line">
              自动开通：
              <span v-if="row.min_auto_open_agent_level">Lv.{{ row.min_auto_open_agent_level }}</span>
              <span v-else class="text-muted">未启用</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="余额/开关" min-width="200">
          <template #default="{ row }">
            <div class="rule-line">最低可用点数：{{ fmt(row.min_available_points) }}</div>
            <div class="switch-tags">
              <el-tag size="small" :type="row.allow_apply ? 'success' : 'info'" effect="plain">
                {{ row.allow_apply ? '允许申请' : '禁止申请' }}
              </el-tag>
              <el-tag size="small" :type="row.allow_auto_open ? 'success' : 'info'" effect="plain">
                {{ row.allow_auto_open ? '允许自动开通' : '禁止自动开通' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" effect="light">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager-row">
        <span class="total-text">共 {{ total }} 个项目</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[50, 100, 200]"
          layout="sizes, prev, pager, next"
          :total="total"
          @current-change="loadPolicies"
          @size-change="loadPolicies"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="editDialog.visible"
      title="编辑项目准入策略"
      width="720px"
      destroy-on-close
    >
      <el-form :model="editDialog.form" label-width="150px">
        <el-form-item label="项目">
          <div>
            <div class="project-name">{{ editDialog.row?.project_name }}</div>
            <div class="project-code">{{ editDialog.row?.project_code }}</div>
          </div>
        </el-form-item>

        <el-form-item label="可见性模式">
          <el-select v-model="editDialog.form.visibility_mode" style="width:260px">
            <el-option label="公开可见：所有代理可见" value="public" />
            <el-option label="等级限制：达到等级才可见" value="level_limited" />
            <el-option label="指定代理：仅邀请代理可见" value="invite_only" />
            <el-option label="隐藏：代理端不展示" value="hidden" />
          </el-select>
        </el-form-item>

        <el-form-item label="开通模式">
          <el-select v-model="editDialog.form.open_mode" style="width:260px">
            <el-option label="必须审核" value="manual_review" />
            <el-option label="按等级自动开通" value="auto_by_level" />
            <el-option label="按条件自动开通" value="auto_by_condition" />
            <el-option label="禁止申请" value="disabled" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">等级门槛</el-divider>

        <el-form-item label="最低可见代理等级">
          <el-input-number
            v-model="editDialog.form.min_visible_agent_level"
            :min="1"
            :max="4"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="最低申请代理等级">
          <el-input-number
            v-model="editDialog.form.min_apply_agent_level"
            :min="1"
            :max="4"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="最低自动开通等级">
          <el-select
            v-model="editDialog.form.min_auto_open_agent_level"
            clearable
            placeholder="不启用自动开通"
            style="width:220px"
          >
            <el-option label="Lv.1" :value="1" />
            <el-option label="Lv.2" :value="2" />
            <el-option label="Lv.3" :value="3" />
            <el-option label="Lv.4" :value="4" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">余额与开关</el-divider>

        <el-form-item label="最低可用点数">
          <el-input-number
            v-model="editDialog.form.min_available_points"
            :min="0"
            :precision="2"
            :step="100"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="是否允许申请">
          <el-switch v-model="editDialog.form.allow_apply" />
        </el-form-item>

        <el-form-item label="是否允许自动开通">
          <el-switch v-model="editDialog.form.allow_auto_open" />
        </el-form-item>

        <el-form-item label="申请理由必填">
          <el-switch v-model="editDialog.form.require_request_reason" />
        </el-form-item>

        <el-form-item label="拒绝后冷却小时">
          <el-input-number
            v-model="editDialog.form.cooldown_hours_after_reject"
            :min="0"
            :step="1"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="策略启用">
          <el-switch v-model="editDialog.form.is_active" />
        </el-form-item>

        <el-alert
          v-if="editDialog.form.visibility_mode === 'hidden'"
          title="隐藏项目会自动禁止申请和自动开通；代理项目目录不会展示该项目。"
          type="warning"
          show-icon
          :closable="false"
          class="small-alert"
        />

        <el-alert
          v-if="editDialog.form.open_mode === 'auto_by_condition'"
          title="按条件自动开通会额外校验最低可用点数。"
          type="info"
          show-icon
          :closable="false"
          class="small-alert"
        />
      </el-form>

      <template #footer>
        <el-button @click="editDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="editDialog.loading" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/ProjectAccessPolicies.vue
 * 名称: 管理员项目准入策略页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能说明:
 *   管理员按项目配置代理可见性、申请规则、自动开通规则。
 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { adminProjectAccessApi } from '@/api/admin/projectAccess'

const loading = ref(false)
const policies = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(100)

const editDialog = reactive({
  visible: false,
  loading: false,
  row: null,
  form: {},
})

const fmt = (val) => Number(val || 0).toFixed(2)

const visibilityLabel = (mode) => {
  const map = {
    public: '公开可见',
    level_limited: '等级限制',
    invite_only: '指定代理',
    hidden: '隐藏',
  }
  return map[mode] || mode
}

const visibilityTagType = (mode) => {
  const map = {
    public: 'success',
    level_limited: 'warning',
    invite_only: 'primary',
    hidden: 'info',
  }
  return map[mode] || 'info'
}

const openModeLabel = (mode) => {
  const map = {
    manual_review: '必须审核',
    auto_by_level: '按等级自动',
    auto_by_condition: '按条件自动',
    disabled: '禁止申请',
  }
  return map[mode] || mode
}

const openModeTagType = (mode) => {
  const map = {
    manual_review: 'warning',
    auto_by_level: 'success',
    auto_by_condition: 'success',
    disabled: 'info',
  }
  return map[mode] || 'info'
}

const loadPolicies = async () => {
  loading.value = true

  try {
    const res = await adminProjectAccessApi.policies({
      page: page.value,
      page_size: pageSize.value,
    })

    policies.value = res.data.policies || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

const openEdit = (row) => {
  editDialog.row = row
  editDialog.form = {
    visibility_mode: row.visibility_mode,
    open_mode: row.open_mode,
    min_visible_agent_level: row.min_visible_agent_level,
    min_apply_agent_level: row.min_apply_agent_level,
    min_auto_open_agent_level: row.min_auto_open_agent_level,
    min_available_points: Number(row.min_available_points || 0),
    allow_apply: row.allow_apply,
    allow_auto_open: row.allow_auto_open,
    require_request_reason: row.require_request_reason,
    cooldown_hours_after_reject: row.cooldown_hours_after_reject,
    is_active: row.is_active,
  }
  editDialog.visible = true
}

const validateForm = () => {
  const form = editDialog.form

  if (form.allow_auto_open && !['auto_by_level', 'auto_by_condition'].includes(form.open_mode)) {
    ElMessage.warning('允许自动开通时，开通模式必须选择“按等级自动”或“按条件自动”')
    return false
  }

  if (['auto_by_level', 'auto_by_condition'].includes(form.open_mode) && !form.min_auto_open_agent_level) {
    ElMessage.warning('自动开通模式下必须设置最低自动开通等级')
    return false
  }

  if (form.min_apply_agent_level < form.min_visible_agent_level) {
    ElMessage.warning('最低申请等级不应低于最低可见等级')
    return false
  }

  return true
}

const submitEdit = async () => {
  if (!validateForm()) return

  editDialog.loading = true

  try {
    await adminProjectAccessApi.updatePolicy(editDialog.row.project_id, editDialog.form)
    ElMessage.success('项目准入策略已更新')
    editDialog.visible = false
    await loadPolicies()
  } finally {
    editDialog.loading = false
  }
}

onMounted(loadPolicies)
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

.tip-alert,
.table-card {
  border-radius: 10px;
}

.project-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.project-code {
  margin-top: 3px;
  font-size: 12px;
  color: #64748b;
  font-family: 'Cascadia Code', Consolas, monospace;
}

.rule-line {
  font-size: 12px;
  color: #475569;
  line-height: 1.7;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

.switch-tags {
  margin-top: 5px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
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

.small-alert {
  margin-top: 10px;
  border-radius: 8px;
}
</style>