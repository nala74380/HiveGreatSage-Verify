<template>
  <div class="page">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建用户</el-button>
    </div>

    <!-- 过滤栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width:110px">
            <el-option label="正常"   value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="filter.level" clearable placeholder="全部" style="width:110px">
            <el-option label="试用"  value="trial" />
            <el-option label="普通"  value="normal" />
            <el-option label="VIP"   value="vip" />
            <el-option label="SVIP"  value="svip" />
            <el-option label="测试"  value="tester" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目">
          <el-select v-model="filter.project_id" clearable placeholder="全部项目" style="width:180px" filterable>
            <el-option v-for="p in allProjects" :key="p.id" :label="p.display_name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadUsers">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 批量操作 -->
    <div v-if="selectedIds.length > 0" class="batch-toolbar">
      <span class="batch-info">已选 {{ selectedIds.length }} 条</span>
      <el-popconfirm :title="`确认批量删除 ${selectedIds.length} 个用户？（软删除）`" confirm-button-text="删除" cancel-button-text="取消" @confirm="batchDelete">
        <template #reference>
          <el-button type="danger" size="small" :loading="batchLoading">批量删除</el-button>
        </template>
      </el-popconfirm>
      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <!-- 用户表格 -->
    <el-card shadow="never" class="table-card">
      <el-table v-loading="loading" :data="users" row-key="id" stripe style="width:100%" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="id" label="ID" width="65" />
        <el-table-column label="用户名" min-width="130">
          <template #default="{ row }">
            <el-button text class="username-link"
              @click="router.push({ path: '/devices', query: { user_id: row.id, username: row.username } })"
            >{{ row.username }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="75">
          <template #default="{ row }"><LevelTag :level="row.user_level" /></template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }"><StatusBadge :status="row.status" type="user" /></template>
        </el-table-column>
        <el-table-column label="授权项目" min-width="180">
          <template #default="{ row }">
            <span v-if="!row.active_project_names?.length" class="no-auth">未授权</span>
            <div v-else class="project-tags">
              <el-tag v-for="name in row.active_project_names" :key="name" size="small" effect="plain" type="primary" class="project-tag">{{ name }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="已绑设备" width="95" align="center">
          <template #default="{ row }">
            <el-tooltip :content="`已绑 ${row.device_binding_count} 台，上限 ${row.max_devices === 0 ? '无限制' : row.max_devices}`" placement="top">
              <span :class="['device-count', isNearLimit(row) ? 'near-limit' : '']">
                {{ row.device_binding_count }}<span class="device-limit">/{{ row.max_devices === 0 ? '∞' : row.max_devices }}</span>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="到期时间" min-width="150">
          <template #default="{ row }">
            <span v-if="!row.expired_at" class="expiry-permanent">永久有效</span>
            <div v-else class="expiry-cell">
              <span class="expiry-date">{{ formatDate(row.expired_at) }}</span>
              <el-tag :type="expiryTagType(row.expired_at)" effect="light" size="small">{{ expiryLabel(row.expired_at) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="router.push(`/users/${row.id}`)">详情</el-button>
            <el-button text size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button text size="small" :type="row.status === 'active' ? 'warning' : 'success'" @click="toggleStatus(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button>
            <el-button text size="small" type="primary" @click="openProjectAuthDialog(row)">授权</el-button>
            <el-popconfirm v-if="auth.isAdmin" title="确认删除该用户？（软删除）" confirm-button-text="删除" cancel-button-text="取消" @confirm="deleteUser(row)">
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
        @size-change="loadUsers" @current-change="loadUsers" />
    </el-card>

    <!-- ───── 新建用户 ───── -->
    <el-dialog v-model="createDialog.visible" title="新建用户" width="520px" destroy-on-close>
      <el-form ref="createFormRef" :model="createDialog.form" :rules="createRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createDialog.form.username" placeholder="3-64 字符" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createDialog.form.password" type="password" show-password placeholder="至少 6 字符" />
        </el-form-item>
        <el-form-item label="级别" prop="user_level">
          <el-select v-model="createDialog.form.user_level" style="width:100%">
            <el-option label="试用"  value="trial" />
            <el-option label="普通"  value="normal" />
            <el-option label="VIP"   value="vip" />
            <el-option label="SVIP"  value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <!-- 授权项目：创建时选填，后续在详情页继续添加 -->
        <el-form-item label="授权项目">
          <el-select v-model="createDialog.form.project_id" clearable
            placeholder="可选，创建后可在详情页添加更多" style="width:100%">
            <el-option
              v-for="p in allProjects" :key="p.id"
              :label="`${p.display_name}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`"
              :value="p.id"
            />
          </el-select>
          <div v-if="auth.isAgent && !allProjects.length" class="hint-warn">
            ⚠ 暂无可授权项目，请联系管理员
          </div>
        </el-form-item>

        <!-- 设备上限：默认 20，代理不显示"无限制" -->
        <el-form-item label="设备上限">
          <div class="device-limit-wrap">
            <el-input-number v-model="createDialog.form.max_devices" :min="0" :step="10"
              controls-position="right" style="width:150px" />
            <span v-if="auth.isAdmin && createDialog.form.max_devices === 0" class="hint-text">无限制</span>
          </div>
          <div class="quick-btns" style="margin-top:6px">
            <el-button size="small" @click="createDialog.form.max_devices = 20">20</el-button>
            <el-button size="small" @click="createDialog.form.max_devices = 50">50</el-button>
            <el-button size="small" @click="createDialog.form.max_devices = 100">100</el-button>
            <el-button size="small" @click="createDialog.form.max_devices = 500">500</el-button>
            <!-- 无限制仅 Admin 显示 -->
            <el-button v-if="auth.isAdmin" size="small" type="info" plain @click="createDialog.form.max_devices = 0">无限制</el-button>
          </div>
        </el-form-item>

        <!-- 到期时间：代理不显示"永久" -->
        <el-form-item label="到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setCreateExpiry(7)">一周</el-button>
              <el-button size="small" @click="setCreateExpiry(30)">一个月</el-button>
              <el-button size="small" @click="setCreateExpiry(90)">三个月</el-button>
              <el-button size="small" @click="setCreateExpiry(365)">一年</el-button>
              <!-- 永久仅 Admin 显示 -->
              <el-button v-if="auth.isAdmin" size="small" type="info" plain @click="createDialog.form.expired_at = null">永久</el-button>
            </div>
            <el-date-picker v-model="createDialog.form.expired_at" type="datetime"
              :placeholder="auth.isAdmin ? '不填为永久有效' : '请选择到期时间'" style="width:100%" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- ───── 编辑用户 ───── -->
    <el-dialog v-model="editDialog.visible" title="编辑用户" width="500px" destroy-on-close>
      <el-form ref="editFormRef" :model="editDialog.form" label-width="90px">
        <el-form-item label="用户名">
          <span class="readonly-val">{{ editDialog.row?.username }}</span>
        </el-form-item>
        <el-form-item label="级别">
          <LevelTag :level="editDialog.row?.user_level" style="margin-right:8px" />
          <el-select v-model="editDialog.form.user_level" size="small" style="width:130px">
            <el-option label="试用"  value="trial" />
            <el-option label="普通"  value="normal" />
            <el-option label="VIP"   value="vip" />
            <el-option label="SVIP"  value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备上限">
          <div class="device-limit-wrap">
            <el-input-number v-model="editDialog.form.max_devices" :min="0" :step="10"
              controls-position="right" style="width:150px" />
            <span class="hint-text">已绑 {{ editDialog.row?.device_binding_count ?? 0 }} 台</span>
          </div>
          <div class="quick-btns" style="margin-top:6px">
            <el-button size="small" @click="editDialog.form.max_devices = 20">20</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = 50">50</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = 100">100</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = 500">500</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = (editDialog.form.max_devices||0)+100">+100</el-button>
            <el-button v-if="auth.isAdmin" size="small" type="info" plain @click="editDialog.form.max_devices = 0">无限制</el-button>
          </div>
        </el-form-item>
        <el-form-item label="当前到期">
          <span v-if="!editDialog.row?.expired_at" class="expiry-permanent">永久有效</span>
          <span v-else>
            {{ formatDatetime(editDialog.row.expired_at) }}
            <el-tag :type="expiryTagType(editDialog.row.expired_at)" size="small" effect="light" style="margin-left:6px">{{ expiryLabel(editDialog.row.expired_at) }}</el-tag>
          </span>
        </el-form-item>
        <el-form-item label="续费">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="addRenewDays(7)">+7天</el-button>
              <el-button size="small" @click="addRenewDays(30)">+30天</el-button>
              <el-button size="small" @click="addRenewDays(90)">+90天</el-button>
              <el-button v-if="auth.isAdmin" size="small" type="info" plain @click="editDialog.form.expired_at = null; editDialog.renewDays = 0">永久</el-button>
            </div>
            <el-date-picker v-model="editDialog.form.expired_at" type="datetime" placeholder="直接设置新到期时间" style="width:100%" @change="editDialog.renewDays = 0" />
            <span v-if="editDialog.renewDays > 0" class="renew-hint">续费后到期：<strong>{{ renewedExpiryLabel }}</strong></span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="editDialog.loading" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- ───── 项目授权弹窗 ───── -->
    <el-dialog v-model="projectAuthDialog.visible" :title="`项目授权 — ${projectAuthDialog.username}`" width="600px" destroy-on-close>
      <div class="auth-section">
        <div class="auth-section-title">
          已授权项目
          <el-button size="small" :icon="Refresh" @click="loadUserAuths" style="margin-left:8px" />
        </div>
        <el-table v-loading="projectAuthDialog.listLoading" :data="projectAuthDialog.auths" size="small" empty-text="暂无授权">
          <el-table-column label="项目名称" min-width="140" prop="game_project_name" />
          <el-table-column label="到期" width="130">
            <template #default="{ row }">
              <span v-if="!row.valid_until" class="expiry-permanent">永久</span>
              <span v-else>{{ formatDate(row.valid_until) }} <el-tag :type="expiryTagType(row.valid_until)" size="small" effect="light">{{ expiryLabel(row.valid_until) }}</el-tag></span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="75">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">{{ row.status === 'active' ? '有效' : '已停' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column width="70" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" type="danger" :disabled="row.status !== 'active'" @click="revokeUserAuth(row)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-divider content-position="left">授予新项目</el-divider>
      <el-form ref="projectAuthFormRef" :model="projectAuthDialog.form" :rules="projectAuthRules" label-width="90px">
        <el-form-item label="选择项目" prop="game_project_id">
          <el-select v-model="projectAuthDialog.form.game_project_id" filterable style="width:100%" :loading="projectAuthDialog.projectsLoading">
            <el-option v-for="p in availableProjects" :key="p.id"
              :label="`${p.display_name}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setUserAuthExpiry(30)">一个月</el-button>
              <el-button size="small" @click="setUserAuthExpiry(90)">三个月</el-button>
              <el-button size="small" @click="setUserAuthExpiry(365)">一年</el-button>
              <el-button size="small" type="info" plain @click="projectAuthDialog.form.valid_until = null">永久</el-button>
            </div>
            <el-date-picker v-model="projectAuthDialog.form.valid_until" type="datetime" placeholder="不填为永久" style="width:100%" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="projectAuthDialog.grantLoading" @click="grantUserProjectAuth">授权</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { userApi }    from '@/api/user'
import { agentApi }   from '@/api/agent'
import { projectApi } from '@/api/project'
import { useAuthStore } from '@/stores/auth'
import StatusBadge from '@/components/common/StatusBadge.vue'
import LevelTag    from '@/components/common/LevelTag.vue'
import { formatDatetime, formatDate, expiryTagType, expiryLabel } from '@/utils/format'

const auth   = useAuthStore()
const router = useRouter()

function isNearLimit(row) {
  const limit = row.max_devices
  if (!limit) return false
  return row.device_binding_count / limit >= 0.8
}
function daysLater(n, base = null) {
  const d = base ? new Date(base) : new Date()
  d.setDate(d.getDate() + n)
  return d
}

// ── 项目列表（按角色分流）─────────────────────────────────────
const allProjects      = ref([])
const availableProjects = ref([])

onMounted(async () => {
  try {
    if (auth.isAdmin) {
      const res = await projectApi.list({ page: 1, page_size: 200, is_active: true })
      allProjects.value = res.data.projects
    } else {
      const res = await agentApi.myProjects()
      allProjects.value = res.data
    }
  } catch { /* 静默 */ }
  loadUsers()
})

// ── 列表 ─────────────────────────────────────────────────────
const loading      = ref(false)
const users        = ref([])
const selectedIds  = ref([])
const batchLoading = ref(false)
const filter       = reactive({ status: null, level: null, project_id: null })
const pagination   = reactive({ page: 1, pageSize: 20, total: 0 })

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await userApi.list({
      page:       pagination.page,
      page_size:  pagination.pageSize,
      status:     filter.status     || undefined,
      level:      filter.level      || undefined,
      project_id: filter.project_id || undefined,
    })
    users.value      = res.data.users
    pagination.total = res.data.total
  } finally { loading.value = false }
}

const resetFilter = () => {
  filter.status = null; filter.level = null; filter.project_id = null
  pagination.page = 1
  loadUsers()
}

const onSelectionChange = (rows) => { selectedIds.value = rows.map(r => r.id) }

const batchDelete = async () => {
  batchLoading.value = true
  const ids = [...selectedIds.value]
  try {
    const results = await Promise.allSettled(ids.map(id => userApi.delete(id)))
    const failed  = results.filter(r => r.status === 'rejected')
    const success = results.filter(r => r.status === 'fulfilled').length
    if (failed.length === 0) {
      ElMessage.success(`已删除 ${success} 个用户`)
    } else {
      ElMessage.warning(`成功 ${success} 个，失败 ${failed.length} 个`)
    }
    selectedIds.value = []
    loadUsers()
  } catch (e) {
    ElMessage.error('批量删除失败，请重试')
  } finally {
    batchLoading.value = false
  }
}

const toggleStatus = async (row) => {
  await userApi.update(row.id, { status: row.status === 'active' ? 'suspended' : 'active' })
  ElMessage.success('操作成功')
  loadUsers()
}

const deleteUser = async (row) => {
  await userApi.delete(row.id)
  ElMessage.success('已删除用户')
  loadUsers()
}

// ── 新建 ─────────────────────────────────────────────────────
const createFormRef = ref(null)
const createDialog  = reactive({
  visible: false, loading: false,
  // 默认设备上限 20，代理创建时更合理
  form: { username: '', password: '', user_level: 'normal', max_devices: 20, expired_at: null, project_id: null },
})
const createRules = {
  username:   [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password:   [{ required: true, message: '请输入密码',   trigger: 'blur' }],
  user_level: [{ required: true, message: '请选择级别',   trigger: 'change' }],
}
const setCreateExpiry = (n) => { createDialog.form.expired_at = daysLater(n) }
const openCreateDialog = () => {
  createDialog.form = {
    username: '', password: '', user_level: 'normal',
    max_devices: 20,             // 默认 20
    expired_at: daysLater(30),   // 默认一个月（代理常用）
    project_id: null,
  }
  createDialog.visible = true
}

const submitCreate = async () => {
  if (!await createFormRef.value?.validate().catch(() => false)) return
  createDialog.loading = true
  try {
    const { project_id, ...baseForm } = createDialog.form
    // 先创建用户
    const res = await userApi.create(baseForm)
    const newUserId = res.data?.id

    // 若选了项目，直接授权
    if (project_id && newUserId) {
      await userApi.grantAuth(newUserId, {
        game_project_id: project_id,
        valid_until: null,
      })
    }

    ElMessage.success('用户创建成功')
    createDialog.visible = false
    loadUsers()
  } finally { createDialog.loading = false }
}

// ── 编辑 ─────────────────────────────────────────────────────
const editFormRef = ref(null)
const editDialog  = reactive({
  visible: false, loading: false, editId: null, row: null, renewDays: 0,
  form: { user_level: 'normal', max_devices: 20, expired_at: null },
})
const renewedExpiryLabel = computed(() => {
  if (!editDialog.renewDays) return ''
  const base = editDialog.row?.expired_at ? new Date(editDialog.row.expired_at) : new Date()
  return daysLater(editDialog.renewDays, base).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
})
const openEditDialog = (row) => {
  editDialog.row = row; editDialog.editId = row.id; editDialog.renewDays = 0
  editDialog.form = { user_level: row.user_level, max_devices: row.max_devices, expired_at: row.expired_at ? new Date(row.expired_at) : null }
  editDialog.visible = true
}
const addRenewDays = (n) => {
  editDialog.renewDays = n
  const base = editDialog.row?.expired_at ? new Date(editDialog.row.expired_at) : new Date()
  editDialog.form.expired_at = daysLater(n, base)
}
const submitEdit = async () => {
  editDialog.loading = true
  try {
    await userApi.update(editDialog.editId, { user_level: editDialog.form.user_level, max_devices: editDialog.form.max_devices, expired_at: editDialog.form.expired_at || null })
    ElMessage.success('更新成功')
    editDialog.visible = false
    loadUsers()
  } finally { editDialog.loading = false }
}

// ── 项目授权 ─────────────────────────────────────────────────
const projectAuthFormRef = ref(null)
const projectAuthDialog  = reactive({
  visible: false, userId: null, username: '',
  auths: [], listLoading: false, projectsLoading: false, grantLoading: false,
  form: { game_project_id: null, valid_until: null },
})
const projectAuthRules = { game_project_id: [{ required: true, message: '请选择项目', trigger: 'change' }] }

const openProjectAuthDialog = async (row) => {
  projectAuthDialog.userId = row.id; projectAuthDialog.username = row.username
  projectAuthDialog.form   = { game_project_id: null, valid_until: null }
  projectAuthDialog.visible = true
  loadUserAuths()
  if (!availableProjects.value.length) {
    projectAuthDialog.projectsLoading = true
    try {
      availableProjects.value = allProjects.value.length
        ? allProjects.value
        : auth.isAdmin
          ? (await projectApi.list({ page: 1, page_size: 200, is_active: true })).data.projects
          : (await agentApi.myProjects()).data
    } finally { projectAuthDialog.projectsLoading = false }
  }
}
const loadUserAuths = async () => {
  projectAuthDialog.listLoading = true
  try {
    const res = await userApi.detail(projectAuthDialog.userId)
    projectAuthDialog.auths = res.data.authorizations || []
  } finally { projectAuthDialog.listLoading = false }
}
const setUserAuthExpiry = (n) => { const d = new Date(); d.setDate(d.getDate() + n); projectAuthDialog.form.valid_until = d }
const grantUserProjectAuth = async () => {
  if (!await projectAuthFormRef.value?.validate().catch(() => false)) return
  projectAuthDialog.grantLoading = true
  try {
    await userApi.grantAuth(projectAuthDialog.userId, { game_project_id: projectAuthDialog.form.game_project_id, valid_until: projectAuthDialog.form.valid_until || null })
    ElMessage.success('授权成功')
    projectAuthDialog.form = { game_project_id: null, valid_until: null }
    availableProjects.value = []
    loadUserAuths(); loadUsers()
  } finally { projectAuthDialog.grantLoading = false }
}
const revokeUserAuth = async (authRow) => {
  await userApi.revokeAuth(projectAuthDialog.userId, authRow.id)
  ElMessage.success('已停用授权')
  loadUserAuths(); loadUsers()
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }
.filter-card, .table-card { border-radius: 10px; }

.batch-toolbar {
  background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
  padding: 8px 16px; display: flex; align-items: center; gap: 12px;
}
.batch-info { font-size: 13px; color: #1d4ed8; font-weight: 500; }
.username-link { font-weight: 500; color: #2563eb !important; padding: 0; height: auto; }
.no-auth { font-size: 12px; color: #94a3b8; }
.project-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.project-tag  { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.device-count { font-size: 13px; cursor: default; }
.device-limit { color: #94a3b8; font-size: 11px; margin-left: 1px; }
.device-count.near-limit { color: #f59e0b; font-weight: 700; }
.expiry-permanent { color: #10b981; font-size: 12px; }
.expiry-cell { display: flex; flex-direction: column; gap: 2px; }
.expiry-date { font-size: 12px; color: #475569; }
.device-limit-wrap { display: flex; align-items: center; gap: 8px; }
.hint-text { font-size: 11px; color: #94a3b8; }
.hint-warn  { font-size: 11px; color: #f59e0b; margin-top: 4px; }
.quick-btns { display: flex; gap: 6px; flex-wrap: wrap; }
.expiry-picker-wrap { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.renew-hint { font-size: 12px; color: #475569; }
.renew-hint strong { color: #2563eb; }
.readonly-val { font-size: 14px; color: #1e293b; font-weight: 500; }
.auth-section { margin-bottom: 8px; }
.auth-section-title { font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 8px; display: flex; align-items: center; }
.pagination { margin-top: 16px; justify-content: flex-end; }
</style>
