<template>
  <div class="page">
    <div class="page-header">
      <h2>项目管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建项目</el-button>
    </div>

    <!-- 过滤栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="项目类型">
          <el-select v-model="filter.project_type" clearable placeholder="全部" style="width:150px">
            <el-option label="游戏项目"     value="game" />
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

    <!-- 项目表格 -->
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

        <el-table-column prop="display_name" label="项目名称" min-width="150" />
        <el-table-column prop="code_name"    label="项目代号" width="140" />

        <el-table-column label="项目 UUID" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.project_uuid }}</span>
            <el-button
              text size="small" :icon="CopyDocument"
              @click="copyUuid(row.project_uuid)"
              style="margin-left:4px"
            />
          </template>
        </el-table-column>

        <el-table-column label="数据库" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.db_name" class="mono db-name">{{ row.db_name }}</span>
            <span v-else class="text-muted">无独立数据库</span>
          </template>
        </el-table-column>

        <el-table-column label="已授权" width="110" align="center">
          <template #default="{ row }">
            <el-tooltip :content="`用户 ${row.authorized_user_count} 个，代理 ${row.authorized_agent_count} 个`" placement="top">
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

        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button
              text size="small"
              :type="row.is_active ? 'warning' : 'success'"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm
              title="确认删除该项目？（软删除）"
              confirm-button-text="删除" cancel-button-text="取消"
              @confirm="deleteProject(row)"
            >
              <template #reference>
                <el-button text size="small" type="danger">删除</el-button>
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

    <!-- ───── 新建项目对话框 ───── -->
    <el-dialog v-model="createDialog.visible" title="新建项目" width="520px" destroy-on-close>
      <el-form
        ref="createFormRef"
        :model="createDialog.form"
        :rules="createRules"
        label-width="100px"
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

        <!-- 类型说明 -->
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
              <code>hive_{代号}</code>。
              适用于需要设备数据上报、脚本参数下发的场景。
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
              适用于简单授权场景（如软件激活码）。
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
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- ───── 编辑项目对话框 ───── -->
    <el-dialog v-model="editDialog.visible" title="编辑项目" width="480px" destroy-on-close>
      <el-form
        ref="editFormRef"
        :model="editDialog.form"
        :rules="editRules"
        label-width="100px"
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

        <el-form-item label="项目名称" prop="display_name">
          <el-input v-model="editDialog.form.display_name" />
        </el-form-item>

        <el-form-item label="项目 UUID">
          <span class="mono uuid-val">{{ editDialog.row?.project_uuid }}</span>
          <el-button text size="small" :icon="CopyDocument" @click="copyUuid(editDialog.row?.project_uuid)" />
        </el-form-item>

        <el-form-item v-if="editDialog.row?.db_name" label="数据库名">
          <span class="mono db-name">{{ editDialog.row?.db_name }}</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="editDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="editDialog.loading" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus, CopyDocument, User, Share } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { projectApi } from '@/api/project'
// ── 工具 ────────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
}

async function copyUuid(uuid) {
  if (!uuid) return
  await navigator.clipboard.writeText(uuid)
  ElMessage.success('UUID 已复制')
}

// ── 列表 ────────────────────────────────────────────────────
const loading  = ref(false)
const projects = ref([])
const filter   = reactive({ project_type: null, is_active: null })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const loadProjects = async () => {
  loading.value = true
  try {
    const res = await projectApi.list({
      page:         pagination.page,
      page_size:    pagination.pageSize,
      project_type: filter.project_type || undefined,
      is_active:    filter.is_active !== null ? filter.is_active : undefined,
    })
    projects.value   = res.data.projects
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filter.project_type = null
  filter.is_active    = null
  pagination.page     = 1
  loadProjects()
}

onMounted(loadProjects)

// ── 启用 / 停用 ─────────────────────────────────────────────
const toggleActive = async (row) => {
  await projectApi.update(row.id, { is_active: !row.is_active })
  ElMessage.success('操作成功')
  loadProjects()
}

// ── 新建对话框 ───────────────────────────────────────────────
const createFormRef = ref(null)
const createDialog  = reactive({
  visible: false,
  loading: false,
  form: { project_type: 'game', display_name: '', code_name: '' },
})

const createRules = {
  project_type: [{ required: true, message: '请选择项目类型', trigger: 'change' }],
  display_name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  code_name:    [
    { required: true, message: '请输入项目代号', trigger: 'blur' },
    { pattern: /^[a-z0-9_]+$/, message: '只允许小写字母、数字和下划线', trigger: 'blur' },
  ],
}

const onTypeChange = () => {
  // 切换类型时自动生成代号
  autoGenCode()
}

/** 按类型自动生成项目代号 */
const autoGenCode = () => {
  const type    = createDialog.form.project_type
  const prefix  = type === 'game' ? 'game_' : 'verify_'
  const suffix  = String(Date.now()).slice(-6)   // 用时间戳后 6 位保证唯一性
  createDialog.form.code_name = prefix + suffix
}

const openCreateDialog = () => {
  createDialog.form = { project_type: 'game', display_name: '', code_name: '' }
  autoGenCode()
  createDialog.visible = true
}

const submitCreate = async () => {
  if (!await createFormRef.value?.validate().catch(() => false)) return
  createDialog.loading = true
  try {
    await projectApi.create(createDialog.form)
    ElMessage.success('项目创建成功')
    createDialog.visible = false
    loadProjects()
  } finally {
    createDialog.loading = false
  }
}

// ── 编辑对话框 ───────────────────────────────────────────────
const editFormRef = ref(null)
const editDialog  = reactive({
  visible: false,
  loading: false,
  editId:  null,
  row:     null,
  form:    { display_name: '' },
})

const editRules = {
  display_name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

const openEditDialog = (row) => {
  editDialog.editId    = row.id
  editDialog.row       = row
  editDialog.form      = { display_name: row.display_name }
  editDialog.visible   = true
}

const submitEdit = async () => {
  if (!await editFormRef.value?.validate().catch(() => false)) return
  editDialog.loading = true
  try {
    await projectApi.update(editDialog.editId, editDialog.form)
    ElMessage.success('更新成功')
    editDialog.visible = false
    loadProjects()
  } finally {
    editDialog.loading = false
  }
}

const deleteProject = async (row) => {
  await projectApi.delete(row.id)
  ElMessage.success('项目已删除')
  loadProjects()
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }

.filter-card, .table-card { border-radius: 10px; }
.pagination { margin-top: 16px; justify-content: flex-end; }

.mono     { font-family: 'Cascadia Code', monospace; font-size: 12px; }
.db-name  { color: #6366f1; }
.uuid-val { color: #475569; word-break: break-all; }
.text-muted { color: #94a3b8; font-size: 12px; }

.auth-count {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: #475569; cursor: default;
}

.hint { font-size: 11px; color: #94a3b8; margin-top: 4px; }
.hint code { background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }

.readonly-val  { font-size: 13px; color: #1e293b; }
.readonly-hint { font-size: 11px; color: #94a3b8; margin-left: 6px; }
</style>
