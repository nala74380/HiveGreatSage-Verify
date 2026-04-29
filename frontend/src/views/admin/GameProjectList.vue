<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>项目管理</h2>
        <p class="page-desc">
          项目是平台业务主实体。列表只保留项目总览与高频操作；项目定价、项目准入进入编辑弹窗；授权申请进入项目详情页。
        </p>
      </div>

      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        新建项目
      </el-button>
    </div>

    <el-alert
      title="说明：项目 UUID 是跨端稳定标识，普通编辑不允许变更或重新生成。"
      type="info"
      show-icon
      :closable="false"
      class="top-alert"
    />

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="项目类型">
          <el-select v-model="filter.project_type" clearable placeholder="全部" style="width:150px">
            <el-option label="游戏项目" value="game" />
            <el-option label="普通验证项目" value="verification" />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="filter.is_active" clearable placeholder="全部" style="width:110px">
            <el-option label="启用" :value="true" />
            <el-option label="停用" :value="false" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button @click="loadProjects">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table v-loading="loading" :data="projects" row-key="id" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="65" />

        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag
              :type="row.project_type === 'game' ? 'primary' : 'info'"
              effect="plain"
              size="small"
            >
              {{ row.project_type === 'game' ? '🎮 游戏项目' : '🔑 普通验证' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="项目名称" min-width="170">
          <template #default="{ row }">
            <button class="project-link" type="button" @click="goProjectDetail(row)">
              {{ row.display_name }}
            </button>
            <div class="project-id">ID: {{ row.id }}</div>
          </template>
        </el-table-column>

        <el-table-column prop="code_name" label="项目代号" width="140" />

        <el-table-column label="项目 UUID" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.project_uuid }}</span>
            <el-button
              text
              size="small"
              :icon="CopyDocument"
              style="margin-left:4px"
              @click="copyUuid(row.project_uuid)"
            />
          </template>
        </el-table-column>

        <el-table-column label="数据库" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.db_name" class="mono db-name">{{ row.db_name }}</span>
            <span v-else class="text-muted">无独立数据库</span>
          </template>
        </el-table-column>

        <el-table-column label="已授权" width="120" align="center">
          <template #default="{ row }">
            <el-tooltip
              :content="`用户 ${row.authorized_user_count} 个，代理 ${row.authorized_agent_count} 个`"
              placement="top"
            >
              <span class="auth-count">
                <el-icon><User /></el-icon> {{ row.authorized_user_count }}
                &nbsp;
                <el-icon><Share /></el-icon> {{ row.authorized_agent_count }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" effect="light" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>

        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="goProjectDetail(row)">
              详情
            </el-button>

            <el-button text size="small" type="primary" @click="openEditDialog(row)">
              编辑
            </el-button>

            <el-button
              text
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>

            <el-popconfirm
              :title="`确认删除项目「${row.display_name}」？该操作为软删除。`"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="deleteProject(row)"
            >
              <template #reference>
                <el-button text size="small" type="danger">
                  删除
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[20, 50]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @size-change="loadProjects"
        @current-change="loadProjects"
      />
    </el-card>

    <!-- 新建项目 -->
    <el-dialog v-model="createDialog.visible" title="新建项目" width="560px" destroy-on-close>
      <el-form
        ref="createFormRef"
        :model="createDialog.form"
        :rules="createRules"
        label-width="120px"
      >
        <el-form-item label="项目类型" prop="project_type">
          <el-radio-group v-model="createDialog.form.project_type" @change="onTypeChange">
            <el-radio-button value="game">
              🎮 游戏项目
            </el-radio-button>
            <el-radio-button value="verification">
              🔑 普通验证项目
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-alert
            v-if="createDialog.form.project_type === 'game'"
            title="游戏项目"
            type="primary"
            :closable="false"
            show-icon
          >
            <template #default>
              需要独立游戏数据库，创建后自动生成数据库名
              <code>hive_{{ createDialog.form.code_name || '项目代号' }}</code>。
            </template>
          </el-alert>

          <el-alert
            v-else
            title="普通验证项目"
            type="info"
            :closable="false"
            show-icon
          >
            <template #default>
              仅提供登录验证和设备绑定服务，无独立数据库。
            </template>
          </el-alert>
        </el-form-item>

        <el-form-item label="项目名称" prop="display_name">
          <el-input v-model="createDialog.form.display_name" placeholder="如：某某手游 2026" />
        </el-form-item>

        <el-form-item label="项目代号" prop="code_name">
          <el-input
            v-model="createDialog.form.code_name"
            placeholder="小写字母/数字/下划线，如：game_001"
          />

          <div class="hint" v-if="createDialog.form.project_type === 'game' && createDialog.form.code_name">
            数据库名将为：<code>hive_{{ createDialog.form.code_name }}</code>
          </div>

          <div class="hint" v-else>
            <el-button size="small" text @click="autoGenCode">自动生成</el-button>
          </div>
        </el-form-item>

        <el-form-item label="创建后继续配置">
          <el-switch v-model="createDialog.continue_config" />
          <div class="field-hint">
            开启后，创建成功会自动打开编辑弹窗，继续配置项目定价和项目准入。
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">
          取消
        </el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑项目：基础信息 + 定价 + 准入 -->
    <el-dialog
      v-model="editDialog.visible"
      :title="editDialog.row ? `编辑项目 — ${editDialog.row.display_name}` : '编辑项目'"
      width="860px"
      destroy-on-close
    >
      <div v-loading="editDialog.loading">
        <el-tabs v-model="editDialog.activeTab">
          <!-- 基础信息 -->
          <el-tab-pane label="基础信息" name="base">
            <el-form
              ref="editFormRef"
              :model="editDialog.form"
              :rules="editRules"
              label-width="110px"
            >
              <el-form-item label="项目类型">
                <el-tag :type="editDialog.row?.project_type === 'game' ? 'primary' : 'info'" effect="plain">
                  {{ editDialog.row?.project_type === 'game' ? '🎮 游戏项目' : '🔑 普通验证项目' }}
                </el-tag>
                <span class="readonly-hint">（创建后不可修改）</span>
              </el-form-item>

              <el-form-item label="项目代号">
                <span class="readonly-val mono">{{ editDialog.row?.code_name }}</span>
                <span class="readonly-hint">（创建后不可修改）</span>
              </el-form-item>

              <el-form-item label="项目 UUID">
                <span class="mono uuid-val">{{ editDialog.row?.project_uuid }}</span>
                <el-button
                  text
                  size="small"
                  :icon="CopyDocument"
                  @click="copyUuid(editDialog.row?.project_uuid)"
                />
                <div class="field-hint">
                  项目 UUID 是跨端稳定标识，普通编辑不允许变更或重新生成。
                </div>
              </el-form-item>

              <el-form-item label="项目名称" prop="display_name">
                <el-input v-model="editDialog.form.display_name" />
              </el-form-item>

              <el-form-item label="项目状态">
                <el-select v-model="editDialog.form.is_active" style="width:100%">
                  <el-option label="启用" :value="true" />
                  <el-option label="停用" :value="false" />
                </el-select>
              </el-form-item>

              <el-form-item v-if="editDialog.row?.db_name" label="数据库名">
                <span class="mono db-name">{{ editDialog.row?.db_name }}</span>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :loading="editDialog.baseSaving" @click="submitEditBase">
                  保存基础信息
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- 项目定价 -->
          <el-tab-pane label="项目定价" name="pricing">
            <el-alert
              title="试用按周计费；普通 / VIP / SVIP 按月计费；点数保留小数点后两位。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-table
              v-loading="editDialog.priceLoading"
              :data="visiblePrices"
              size="small"
              stripe
              empty-text="暂无定价"
            >
              <el-table-column label="用户级别" width="120">
                <template #default="{ row }">
                  <el-tag effect="plain">{{ levelName(row.user_level) }}</el-tag>
                </template>
              </el-table-column>

              <el-table-column label="计费周期" width="120">
                <template #default="{ row }">
                  <el-tag effect="plain" type="info">
                    {{ row.unit_label || unitLabel(row.user_level) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="点数" min-width="260">
                <template #default="{ row }">
                  <div
                    v-if="priceEdit.level === row.user_level"
                    class="edit-cell"
                  >
                    <el-input-number
                      v-model="priceEdit.value"
                      :min="0"
                      :precision="2"
                      :step="0.01"
                      controls-position="right"
                      size="small"
                      style="width:160px"
                      @keyup.enter="savePrice(row.user_level)"
                    />
                    <el-button
                      size="small"
                      type="primary"
                      :loading="priceEdit.saving"
                      @click="savePrice(row.user_level)"
                    >
                      保存
                    </el-button>
                    <el-button size="small" @click="cancelPriceEdit">取消</el-button>
                  </div>

                  <div v-else class="price-display">
                    <span v-if="row.points_per_device !== null" class="price-val">
                      {{ fmtPrice(row.points_per_device) }} 点
                    </span>
                    <span v-else class="no-price">未设置</span>

                    <el-button
                      text
                      size="small"
                      type="primary"
                      @click="startPriceEdit(row.user_level, row.points_per_device)"
                    >
                      {{ row.points_per_device !== null ? '修改' : '设置' }}
                    </el-button>

                    <el-button
                      v-if="row.points_per_device !== null"
                      text
                      size="small"
                      type="danger"
                      @click="removePrice(row.user_level)"
                    >
                      清除
                    </el-button>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="说明" min-width="260">
                <template #default="{ row }">
                  <span v-if="row.points_per_device !== null" class="price-desc">
                    授权 1 台设备{{ periodText(row.user_level) }}扣 {{ fmtPrice(row.points_per_device) }} 点
                  </span>
                  <span v-else class="no-price">
                    未设置价格时，代理不能对此级别进行扣点授权
                  </span>
                </template>
              </el-table-column>
            </el-table>

            <div class="batch-price-row">
              <span class="batch-label">快速设置：</span>
              <el-button size="small" @click="applyPreset('free')">全免费</el-button>
              <el-button size="small" @click="applyPreset('standard')">标准定价</el-button>
              <el-button size="small" type="danger" plain @click="clearAllPrices">
                清除全部
              </el-button>
            </div>
          </el-tab-pane>

          <!-- 项目准入 -->
          <el-tab-pane label="项目准入" name="access">
            <el-alert
              title="项目开通本身不扣点；代理给用户授权项目时才扣点。隐藏项目不会出现在代理项目目录中。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-form :model="editDialog.accessForm" label-width="150px">
              <el-form-item label="可见性模式">
                <el-select v-model="editDialog.accessForm.visibility_mode" style="width:280px">
                  <el-option label="公开可见：所有代理可见" value="public" />
                  <el-option label="等级限制：达到等级才可见" value="level_limited" />
                  <el-option label="指定代理：仅邀请代理可见" value="invite_only" />
                  <el-option label="隐藏：代理端不展示" value="hidden" />
                </el-select>
              </el-form-item>

              <el-form-item label="开通模式">
                <el-select v-model="editDialog.accessForm.open_mode" style="width:280px">
                  <el-option label="必须审核" value="manual_review" />
                  <el-option label="按等级自动开通" value="auto_by_level" />
                  <el-option label="按条件自动开通" value="auto_by_condition" />
                  <el-option label="禁止申请" value="disabled" />
                </el-select>
              </el-form-item>

              <el-divider content-position="left">等级门槛</el-divider>

              <el-form-item label="最低可见业务等级">
                <el-input-number
                  v-model="editDialog.accessForm.min_visible_agent_level"
                  :min="1"
                  :max="4"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="最低申请业务等级">
                <el-input-number
                  v-model="editDialog.accessForm.min_apply_agent_level"
                  :min="1"
                  :max="4"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="最低自动开通等级">
                <el-select
                  v-model="editDialog.accessForm.min_auto_open_agent_level"
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
                  v-model="editDialog.accessForm.min_available_points"
                  :min="0"
                  :precision="2"
                  :step="100"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="是否允许申请">
                <el-switch v-model="editDialog.accessForm.allow_apply" />
              </el-form-item>

              <el-form-item label="是否允许自动开通">
                <el-switch v-model="editDialog.accessForm.allow_auto_open" />
              </el-form-item>

              <el-form-item label="申请理由必填">
                <el-switch v-model="editDialog.accessForm.require_request_reason" />
              </el-form-item>

              <el-form-item label="拒绝后冷却小时">
                <el-input-number
                  v-model="editDialog.accessForm.cooldown_hours_after_reject"
                  :min="0"
                  :step="1"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="策略启用">
                <el-switch v-model="editDialog.accessForm.is_active" />
              </el-form-item>

              <el-alert
                v-if="editDialog.accessForm.visibility_mode === 'hidden'"
                title="隐藏项目会自动禁止申请和自动开通；代理项目目录不会展示该项目。"
                type="warning"
                show-icon
                :closable="false"
                class="small-alert"
              />

              <el-alert
                v-if="editDialog.accessForm.open_mode === 'auto_by_condition'"
                title="按条件自动开通会额外校验最低可用点数。"
                type="info"
                show-icon
                :closable="false"
                class="small-alert"
              />

              <el-form-item class="access-save-row">
                <el-button
                  type="primary"
                  :loading="editDialog.accessSaving"
                  @click="submitAccessPolicy"
                >
                  保存准入策略
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </div>

      <template #footer>
        <el-button @click="editDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/GameProjectList.vue
 * 名称: 项目管理超级列表
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.5.0
 * 功能说明:
 *   项目列表保留详情、编辑、启停、删除。
 *   编辑弹窗融合基础信息、项目定价、项目准入。
 *   授权申请收敛到项目详情页。
 *
 * 当前业务口径:
 *   - 项目 UUID 是跨端稳定标识，普通编辑不允许变更或重新生成。
 *   - 定价属于项目计费能力，放在编辑弹窗的“项目定价”页签。
 *   - 准入属于项目治理能力，放在编辑弹窗的“项目准入”页签。
 *   - 授权申请属于审核流，放在项目详情页。
 */

import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus,
  CopyDocument,
  User,
  Share,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi } from '@/api/project'
import { balanceApi } from '@/api/balance'
import { adminProjectAccessApi } from '@/api/admin/projectAccess'

const router = useRouter()

const LEVELS = ['trial', 'normal', 'vip', 'svip']

const PRESETS = {
  standard: {
    trial: 0.01,
    normal: 2.00,
    vip: 3.50,
    svip: 5.00,
  },
}

function formatDate(iso) {
  if (!iso) return '—'

  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

async function copyUuid(uuid) {
  if (!uuid) return

  await navigator.clipboard.writeText(uuid)
  ElMessage.success('UUID 已复制')
}

const goProjectDetail = (row) => {
  router.push(`/projects/${row.id}`)
}

// ── 列表 ────────────────────────────────────────────────────
const loading = ref(false)
const projects = ref([])
const filter = reactive({ project_type: null, is_active: null })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const loadProjects = async () => {
  loading.value = true

  try {
    const res = await projectApi.list({
      page: pagination.page,
      page_size: pagination.pageSize,
      project_type: filter.project_type || undefined,
      is_active: filter.is_active !== null ? filter.is_active : undefined,
    })

    projects.value = res.data.projects || []
    pagination.total = res.data.total || 0
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filter.project_type = null
  filter.is_active = null
  pagination.page = 1
  loadProjects()
}

onMounted(loadProjects)

const toggleActive = async (row) => {
  await projectApi.update(row.id, { is_active: !row.is_active })
  ElMessage.success('操作成功')
  loadProjects()
}

const deleteProject = async (row) => {
  await projectApi.delete(row.id)
  ElMessage.success('项目已删除')
  loadProjects()
}

// ── 新建项目 ────────────────────────────────────────────────
const createFormRef = ref(null)
const createDialog = reactive({
  visible: false,
  loading: false,
  continue_config: true,
  form: {
    project_type: 'game',
    display_name: '',
    code_name: '',
  },
})

const createRules = {
  project_type: [{ required: true, message: '请选择项目类型', trigger: 'change' }],
  display_name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  code_name: [
    { required: true, message: '请输入项目代号', trigger: 'blur' },
    { pattern: /^[a-z0-9_]+$/, message: '只允许小写字母、数字和下划线', trigger: 'blur' },
  ],
}

const onTypeChange = () => {
  autoGenCode()
}

const autoGenCode = () => {
  const type = createDialog.form.project_type
  const prefix = type === 'game' ? 'game_' : 'verify_'
  const suffix = String(Date.now()).slice(-6)

  createDialog.form.code_name = prefix + suffix
}

const openCreateDialog = () => {
  createDialog.form = {
    project_type: 'game',
    display_name: '',
    code_name: '',
  }
  createDialog.continue_config = true

  autoGenCode()
  createDialog.visible = true
}

const submitCreate = async () => {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  createDialog.loading = true

  const createdCodeName = createDialog.form.code_name
  const shouldContinueConfig = createDialog.continue_config

  try {
    const createRes = await projectApi.create(createDialog.form)

    ElMessage.success('项目创建成功')
    createDialog.visible = false

    await loadProjects()

    if (shouldContinueConfig) {
      const createdProject = createRes.data?.id
        ? createRes.data
        : projects.value.find(item => item.code_name === createdCodeName)

      if (createdProject?.id) {
        await openEditDialog(createdProject, 'pricing')
      } else {
        ElMessage.warning('项目已创建，但未能自动打开配置窗口，请从列表点击编辑继续配置')
      }
    }
  } finally {
    createDialog.loading = false
  }
}

// ── 编辑项目 ────────────────────────────────────────────────
const editFormRef = ref(null)

const editDialog = reactive({
  visible: false,
  loading: false,
  baseSaving: false,
  priceLoading: false,
  accessLoading: false,
  accessSaving: false,
  activeTab: 'base',

  editId: null,
  row: null,

  form: {
    display_name: '',
    is_active: true,
  },

  prices: [],

  accessRow: null,
  accessForm: defaultAccessForm(),
})

const editRules = {
  display_name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

const priceEdit = reactive({
  level: null,
  value: 0,
  saving: false,
})

const visiblePrices = computed(() => {
  return (editDialog.prices || []).filter(row => LEVELS.includes(row.user_level))
})

function defaultAccessForm() {
  return {
    visibility_mode: 'public',
    open_mode: 'manual_review',
    min_visible_agent_level: 1,
    min_apply_agent_level: 1,
    min_auto_open_agent_level: null,
    min_available_points: 0,
    allow_apply: true,
    allow_auto_open: false,
    require_request_reason: false,
    cooldown_hours_after_reject: 24,
    is_active: true,
  }
}

const openEditDialog = async (row, activeTab = 'base') => {
  editDialog.visible = true
  editDialog.loading = true
  editDialog.activeTab = activeTab
  editDialog.editId = row.id
  editDialog.row = row
  editDialog.form = {
    display_name: row.display_name,
    is_active: row.is_active,
  }
  editDialog.prices = []
  editDialog.accessRow = null
  editDialog.accessForm = defaultAccessForm()
  cancelPriceEdit()

  try {
    const detailRes = await projectApi.detail(row.id)
    editDialog.row = detailRes.data
    editDialog.form = {
      display_name: detailRes.data.display_name,
      is_active: detailRes.data.is_active,
    }

    await Promise.all([
      loadEditPrices(row.id),
      loadEditAccessPolicy(row.id),
    ])
  } finally {
    editDialog.loading = false
  }
}

const submitEditBase = async () => {
  const valid = await editFormRef.value?.validate().catch(() => false)
  if (!valid) return

  editDialog.baseSaving = true

  try {
    const res = await projectApi.update(editDialog.editId, {
      display_name: editDialog.form.display_name,
      is_active: editDialog.form.is_active,
    })

    editDialog.row = res.data
    ElMessage.success('基础信息已保存')
    loadProjects()
  } finally {
    editDialog.baseSaving = false
  }
}

// ── 编辑项目：定价 ─────────────────────────────────────────
const loadEditPrices = async (projectId) => {
  editDialog.priceLoading = true

  try {
    const res = await balanceApi.getPrices(projectId)
    editDialog.prices = (res.data || []).filter(row => LEVELS.includes(row.user_level))
  } finally {
    editDialog.priceLoading = false
  }
}

const startPriceEdit = (level, currentValue) => {
  priceEdit.level = level
  priceEdit.value = Number(currentValue ?? 0)
}

const cancelPriceEdit = () => {
  priceEdit.level = null
  priceEdit.value = 0
  priceEdit.saving = false
}

const savePrice = async (level) => {
  priceEdit.saving = true

  try {
    await balanceApi.setPrice(editDialog.editId, level, {
      points_per_device: Number(Number(priceEdit.value).toFixed(2)),
    })

    ElMessage.success('定价已保存')
    cancelPriceEdit()
    await loadEditPrices(editDialog.editId)
  } finally {
    priceEdit.saving = false
  }
}

const removePrice = async (level) => {
  await ElMessageBox.confirm(`确认清除 ${levelName(level)} 的定价？`, '确认', { type: 'warning' })
  await balanceApi.deletePrice(editDialog.editId, level)
  ElMessage.success('已清除')
  await loadEditPrices(editDialog.editId)
}

const applyPreset = async (presetName) => {
  const preset = PRESETS[presetName]

  if (!preset) {
    await Promise.all(
      LEVELS.map(level =>
        balanceApi.setPrice(editDialog.editId, level, { points_per_device: 0.00 }),
      ),
    )
  } else {
    await Promise.all(
      Object.entries(preset).map(([level, pts]) =>
        balanceApi.setPrice(editDialog.editId, level, {
          points_per_device: Number(Number(pts).toFixed(2)),
        }),
      ),
    )
  }

  ElMessage.success('批量设置成功')
  await loadEditPrices(editDialog.editId)
}

const clearAllPrices = async () => {
  await ElMessageBox.confirm('确认清除该项目全部定价？', '确认', { type: 'warning' })

  await Promise.all(
    LEVELS.map(level => balanceApi.deletePrice(editDialog.editId, level).catch(() => {})),
  )

  ElMessage.success('已清除全部定价')
  await loadEditPrices(editDialog.editId)
}

const fmtPrice = (value) => Number(value || 0).toFixed(2)

const levelName = (level) => {
  const map = {
    trial: '试用',
    normal: '普通',
    vip: 'VIP',
    svip: 'SVIP',
  }
  return map[level] || level
}

const unitLabel = (level) => level === 'trial' ? '每周/台' : '每月/台'
const periodText = (level) => level === 'trial' ? '每周' : '每月'

// ── 编辑项目：准入 ─────────────────────────────────────────
const loadEditAccessPolicy = async (projectId) => {
  editDialog.accessLoading = true

  try {
    const res = await adminProjectAccessApi.policies({
      page: 1,
      page_size: 500,
    })

    const rows = res.data.policies || []
    const row = rows.find(item => Number(item.project_id) === Number(projectId))

    editDialog.accessRow = row || null

    if (row) {
      editDialog.accessForm = {
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
    } else {
      editDialog.accessForm = defaultAccessForm()
    }
  } finally {
    editDialog.accessLoading = false
  }
}

const validateAccessForm = () => {
  const form = editDialog.accessForm

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

const submitAccessPolicy = async () => {
  if (!validateAccessForm()) return

  editDialog.accessSaving = true

  try {
    await adminProjectAccessApi.updatePolicy(editDialog.editId, editDialog.accessForm)
    ElMessage.success('项目准入策略已保存')
    await loadEditAccessPolicy(editDialog.editId)
  } finally {
    editDialog.accessSaving = false
  }
}
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
.filter-card,
.table-card {
  border-radius: 10px;
}

.project-link {
  appearance: none;
  border: none;
  background: transparent;
  padding: 0;
  margin: 0;
  color: #2563eb;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.project-link:hover {
  text-decoration: underline;
}

.project-id {
  margin-top: 2px;
  font-size: 11px;
  color: #94a3b8;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

.db-name {
  color: #6366f1;
}

.uuid-val {
  color: #475569;
  word-break: break-all;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

.auth-count {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #475569;
  cursor: default;
}

.hint {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}

.hint code {
  background: #f1f5f9;
  padding: 1px 4px;
  border-radius: 3px;
}

.field-hint {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.5;
}

.readonly-val {
  font-size: 13px;
  color: #1e293b;
}

.readonly-hint {
  font-size: 11px;
  color: #94a3b8;
  margin-left: 6px;
}

.inner-alert {
  margin-bottom: 14px;
  border-radius: 8px;
}

.edit-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.price-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.price-val {
  font-size: 14px;
  font-weight: 600;
  color: #6366f1;
}

.no-price {
  font-size: 12px;
  color: #94a3b8;
}

.price-desc {
  font-size: 12px;
  color: #64748b;
}

.batch-price-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}

.batch-label {
  font-size: 12px;
  color: #64748b;
}

.small-alert {
  margin-top: 10px;
  border-radius: 8px;
}

.access-save-row {
  margin-top: 16px;
}
</style>