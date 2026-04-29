<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>代理等级策略</h2>
        <p class="page-desc">
          配置 Lv.1 - Lv.4 代理业务等级的授信额度、自动开通能力、下级代理能力和审核优先级。
        </p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadPolicies">刷新</el-button>
    </div>

    <el-alert
      title="说明：Agent.level 表示代理组织层级；本页面配置的是代理业务等级 tier_level。用户数量只作统计，不再作为代理配额限制。"
      type="info"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="policies"
        row-key="level"
        stripe
        style="width:100%"
      >
        <el-table-column label="等级" width="90">
          <template #default="{ row }">
            <el-tag type="primary" effect="light">Lv.{{ row.level }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="名称" min-width="140">
          <template #default="{ row }">
            <div class="main-text">{{ row.level_name }}</div>
            <div v-if="row.description" class="sub-text">{{ row.description }}</div>
          </template>
        </el-table-column>

        <el-table-column label="授信额度" min-width="170">
          <template #default="{ row }">
            <div class="rule-line">默认：{{ fmt(row.default_credit_limit) }}</div>
            <div class="rule-line">最高：{{ fmt(row.max_credit_limit) }}</div>
          </template>
        </el-table-column>

        <el-table-column label="下级代理" min-width="170">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.can_create_sub_agents ? 'success' : 'info'"
              effect="plain"
            >
              {{ row.can_create_sub_agents ? '允许创建' : '禁止创建' }}
            </el-tag>
            <div class="rule-line">
              最大下级：{{ row.max_sub_agents === 0 ? '不限/未限制' : row.max_sub_agents }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="自动开通" min-width="180">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.can_auto_open_project ? 'success' : 'info'"
              effect="plain"
            >
              {{ row.can_auto_open_project ? '允许自动开通' : '禁止自动开通' }}
            </el-tag>
            <div class="rule-line">自动开通上限：{{ row.auto_open_project_limit }}</div>
          </template>
        </el-table-column>

        <el-table-column label="审核优先级" width="110">
          <template #default="{ row }">
            {{ row.review_priority }}
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
    </el-card>

    <el-dialog
      v-model="editDialog.visible"
      title="编辑代理等级策略"
      width="720px"
      destroy-on-close
    >
      <el-form :model="editDialog.form" label-width="145px">
        <el-form-item label="等级">
          <el-tag type="primary" effect="light">Lv.{{ editDialog.row?.level }}</el-tag>
        </el-form-item>

        <el-form-item label="等级名称">
          <el-input v-model="editDialog.form.level_name" maxlength="64" />
        </el-form-item>

        <el-form-item label="说明">
          <el-input
            v-model="editDialog.form.description"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>

        <el-divider content-position="left">授信额度</el-divider>

        <el-form-item label="默认授信额度">
          <el-input-number
            v-model="editDialog.form.default_credit_limit"
            :min="0"
            :precision="2"
            :step="100"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="最高授信额度">
          <el-input-number
            v-model="editDialog.form.max_credit_limit"
            :min="0"
            :precision="2"
            :step="100"
            controls-position="right"
          />
        </el-form-item>

        <el-divider content-position="left">下级代理能力</el-divider>

        <el-form-item label="允许创建下级代理">
          <el-switch v-model="editDialog.form.can_create_sub_agents" />
        </el-form-item>

        <el-form-item label="最大下级代理数">
          <el-input-number
            v-model="editDialog.form.max_sub_agents"
            :min="0"
            :step="1"
            controls-position="right"
          />
          <span class="hint-text">0 表示暂不限制或未启用硬限制。</span>
        </el-form-item>

        <el-divider content-position="left">项目自动开通能力</el-divider>

        <el-form-item label="允许自动开通项目">
          <el-switch v-model="editDialog.form.can_auto_open_project" />
        </el-form-item>

        <el-form-item label="自动开通项目上限">
          <el-input-number
            v-model="editDialog.form.auto_open_project_limit"
            :min="0"
            :step="1"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="审核优先级">
          <el-input-number
            v-model="editDialog.form.review_priority"
            :min="0"
            :step="1"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="启用状态">
          <el-switch v-model="editDialog.form.is_active" />
        </el-form-item>

        <el-alert
          title="最高授信额度不能低于默认授信额度。用户数量只作统计，不再作为代理等级策略中的配额项。"
          type="warning"
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
 * 文件位置: src/views/admin/AgentLevelPolicies.vue
 * 名称: 代理等级策略页面
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能说明:
 *   管理员配置代理业务等级策略。
 *
 * 当前业务口径:
 *   - 等级策略只表达授信、下级代理、自动开通和审核优先级。
 *   - 用户数量只作统计展示。
 *   - 代理等级策略只表达授信、下级代理、自动开通、审核优先级等业务能力。
 *
 * 注意:
 *   当前独立路由入口已从 router 中移除。
 *   后续如需使用，可将本页面内容抽成弹窗组件嵌入代理管理页。
 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'

const loading = ref(false)
const policies = ref([])

const editDialog = reactive({
  visible: false,
  loading: false,
  row: null,
  form: {},
})

const fmt = (value) => Number(value || 0).toFixed(2)

const loadPolicies = async () => {
  loading.value = true

  try {
    const res = await adminAgentProfileApi.levelPolicies()
    policies.value = Array.isArray(res.data) ? res.data : []
  } finally {
    loading.value = false
  }
}

const openEdit = (row) => {
  editDialog.row = row
  editDialog.form = {
    level_name: row.level_name,
    description: row.description || '',
    default_credit_limit: Number(row.default_credit_limit || 0),
    max_credit_limit: Number(row.max_credit_limit || 0),
    can_create_sub_agents: !!row.can_create_sub_agents,
    max_sub_agents: Number(row.max_sub_agents || 0),
    can_auto_open_project: !!row.can_auto_open_project,
    auto_open_project_limit: Number(row.auto_open_project_limit || 0),
    review_priority: Number(row.review_priority || 0),
    is_active: !!row.is_active,
  }
  editDialog.visible = true
}

const validateForm = () => {
  if (!editDialog.form.level_name?.trim()) {
    ElMessage.warning('请输入等级名称')
    return false
  }

  if (Number(editDialog.form.max_credit_limit || 0) < Number(editDialog.form.default_credit_limit || 0)) {
    ElMessage.warning('最高授信额度不能低于默认授信额度')
    return false
  }

  return true
}

const submitEdit = async () => {
  if (!validateForm()) return

  editDialog.loading = true

  try {
    await adminAgentProfileApi.updateLevelPolicy(editDialog.row.level, {
      ...editDialog.form,
      level_name: editDialog.form.level_name.trim(),
      description: editDialog.form.description || null,
    })

    ElMessage.success('代理等级策略已更新')
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

.main-text {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.sub-text {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.rule-line {
  font-size: 12px;
  color: #475569;
  line-height: 1.8;
}

.hint-text {
  margin-left: 8px;
  font-size: 12px;
  color: #94a3b8;
}

.small-alert {
  border-radius: 8px;
}
</style>