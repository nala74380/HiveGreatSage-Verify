<template>
  <div class="page" v-loading="pageLoading">
    <!-- 面包屑 -->
    <el-breadcrumb separator="/" class="breadcrumb">
      <el-breadcrumb-item :to="{ path: '/users' }">用户管理</el-breadcrumb-item>
      <el-breadcrumb-item>{{ user?.username ?? '加载中...' }}</el-breadcrumb-item>
    </el-breadcrumb>

    <template v-if="user">
      <!-- 用户基本信息 -->
      <el-card shadow="never" class="info-card">
        <div class="user-header">
          <div class="user-avatar">
            {{ user.username.charAt(0).toUpperCase() }}
          </div>
          <div class="user-meta">
            <div class="user-name">{{ user.username }}</div>
            <div class="user-tags">
              <StatusBadge :status="user.status" type="user" />
            </div>
          </div>
          <div class="user-actions">
            <el-button @click="openEditDialog">编辑</el-button>
            <el-button
              :type="user.status === 'active' ? 'warning' : 'success'"
              plain
              @click="toggleStatus"
            >
              {{ user.status === 'active' ? '停用用户' : '启用用户' }}
            </el-button>
          </div>
        </div>

        <el-divider />

        <el-descriptions :column="3" size="small">
          <el-descriptions-item label="用户 ID">
            <span class="mono">{{ user.id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">
            {{ formatDatetime(user.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="最后更新">
            {{ formatDatetime(user.updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="授权项目">
            {{ user.authorization_count || 0 }} 个
          </el-descriptions-item>
          <el-descriptions-item label="有效授权">
            {{ user.active_authorization_count || 0 }} 个
          </el-descriptions-item>
          <el-descriptions-item label="已绑设备">
            <span>
              {{ user.device_binding_count }} 台
            </span>
            <span class="text-muted" style="margin-left:4px" v-if="false">
              / -
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="创建方式">
            {{ user.created_by_admin ? '管理员创建' : `代理创建 — ${user.created_by_agent_username || `ID:${user.created_by_agent_id}`}` }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 项目授权列表 -->
      <el-card shadow="never" class="inner-card">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">
              项目授权
              <el-badge :value="user.authorizations.length" type="primary" style="margin-left:6px" />
            </span>
            <el-button size="small" type="primary" plain @click="openGrantDialog">
              + 授权新项目
            </el-button>
          </div>
        </template>

        <el-empty v-if="!user.authorizations.length" description="暂无项目授权" :image-size="60" />
        <el-table v-else :data="user.authorizations" size="small">
          <el-table-column label="项目名称" min-width="140" prop="game_project_name" />
          <el-table-column label="等级" width="75">
            <template #default="{ row }"><LevelTag :level="row.user_level" /></template>
          </el-table-column>
          <el-table-column label="授权设备" width="90" prop="authorized_devices" />
          <el-table-column label="已激活" width="75" prop="activated_devices" />
          <el-table-column label="未激活" width="75">
            <template #default="{ row }">
              {{ row.inactive_devices != null ? row.inactive_devices : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="到期时间" min-width="160">
            <template #default="{ row }">
              <span v-if="!row.valid_until" class="text-success">永久</span>
              <span v-else>
                {{ formatDate(row.valid_until) }}
                <el-tag :type="expiryTagType(row.valid_until)" size="small" effect="light" style="margin-left:4px">
                  {{ expiryLabel(row.valid_until) }}
                </el-tag>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="75">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                {{ row.status === 'active' ? '有效' : '已停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" type="primary" @click="openEditAuthDialog(row)">编辑</el-button>
              <el-button text size="small" type="success" :disabled="row.status !== 'active'" @click="openUpgradeDialog(row)">升级</el-button>
              <el-button text size="small" type="danger" :disabled="row.status !== 'active'" @click="revokeAuth(row)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 设备绑定记录 -->
      <el-card shadow="never" class="inner-card">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">
              设备绑定
              <el-badge :value="user.device_binding_count" type="info" style="margin-left:6px" />
            </span>
          </div>
        </template>

        <el-empty v-if="!deviceBindings.length && !bindingsLoading" description="暂无设备绑定记录" :image-size="60" />
        <el-skeleton v-if="bindingsLoading" :rows="3" animated />
        <el-table v-else-if="deviceBindings.length" :data="deviceBindings" size="small">
          <el-table-column label="设备指纹" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.device_fingerprint }}</span>
            </template>
          </el-table-column>
          <el-table-column label="绑定时间" width="155">
            <template #default="{ row }">
              {{ formatDatetime(row.bound_at) }}
            </template>
          </el-table-column>
          <el-table-column label="最后活跃" width="155">
            <template #default="{ row }">
              {{ row.last_seen_at ? formatRelativeTime(row.last_seen_at) : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                {{ row.status === 'active' ? '已绑定' : '已解绑' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-popconfirm
                title="确认解绑此设备？"
                confirm-button-text="解绑"
                cancel-button-text="取消"
                @confirm="unbindDevice(row)"
              >
                <template #reference>
                  <el-button
                    text size="small" type="danger"
                    :disabled="row.status !== 'active'"
                  >解绑</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 编辑用户对话框 -->
    <el-dialog v-model="editDialog.visible" title="编辑用户" width="880px" destroy-on-close>
      <el-form ref="editFormRef" :model="editDialog.form" label-width="105px" v-if="user">
        <el-divider content-position="left">账号主体</el-divider>
        <el-form-item label="用户名">
          <span class="readonly-val">{{ user.username }}</span>
        </el-form-item>
        <el-form-item label="创建信息">
          <div>
            <el-tag size="small" effect="plain" :type="user.created_by_type === 'agent' ? 'warning' : 'danger'">
              {{ user.created_by_display }}
            </el-tag>
            <span class="sub-text" style="margin-left:8px">{{ formatDatetime(user.created_at) }}</span>
          </div>
        </el-form-item>
        <el-form-item label="账号状态">
          <el-select v-model="editDialog.form.status" size="small" style="width:150px">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
          </el-select>
        </el-form-item>
        <el-alert type="info" show-icon :closable="false" class="small-alert"
          title="用户等级、设备数、到期时间请在项目授权里分别设置。" />

        <el-divider content-position="left">
          项目授权
          <el-button size="small" type="primary" plain style="margin-left:12px" @click="editDialog.visible = false; openGrantDialog()">
            + 授权新项目
          </el-button>
        </el-divider>
        <el-table :data="user.authorizations" size="small" empty-text="暂无授权" stripe>
          <el-table-column label="项目" min-width="120" prop="game_project_name" />
          <el-table-column label="等级" width="75">
            <template #default="{ row: a }">
              <LevelTag :level="a.user_level" />
            </template>
          </el-table-column>
          <el-table-column label="设备" width="70" prop="authorized_devices" />
          <el-table-column label="到期" min-width="120">
            <template #default="{ row: a }">
              <span v-if="!a.valid_until">永久</span>
              <span v-else>{{ formatDate(a.valid_until) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="70">
            <template #default="{ row: a }">
              <el-tag :type="a.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                {{ a.status === 'active' ? '有效' : '已停用' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-form>
      <template #footer>
        <el-button @click="editDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="editDialog.loading" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 授权新项目对话框 -->
    <el-dialog v-model="grantDialog.visible" title="授权新项目" width="460px" destroy-on-close>
      <el-form :model="grantDialog.form" :rules="grantRules" ref="grantFormRef" label-width="100px">
        <el-form-item label="选择项目" prop="game_project_id">
          <el-select v-model="grantDialog.form.game_project_id" filterable placeholder="请选择项目" style="width:100%">
            <el-option v-for="p in availableProjects" :key="p.id" :label="p.display_name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="授权等级" prop="user_level">
          <el-select v-model="grantDialog.form.user_level" style="width:100%">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option v-if="authStore.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>
        <el-form-item label="授权设备数" prop="authorized_devices">
          <el-input-number v-model="grantDialog.form.authorized_devices" :min="1" style="width:100%" />
          <div style="display:flex;gap:6px;margin-top:4px">
            <el-button size="small" @click="grantDialog.form.authorized_devices = 20">20</el-button>
            <el-button size="small" @click="grantDialog.form.authorized_devices = 50">50</el-button>
            <el-button size="small" @click="grantDialog.form.authorized_devices = 100">100</el-button>
            <el-button size="small" @click="grantDialog.form.authorized_devices = 500">500</el-button>
          </div>
        </el-form-item>
        <el-form-item label="到期时间">
          <div style="display:flex;gap:6px;margin-bottom:6px;flex-wrap:wrap">
            <el-button size="small" @click="setGrantExpiry(30)">一个月</el-button>
            <el-button size="small" @click="setGrantExpiry(90)">三个月</el-button>
            <el-button size="small" @click="setGrantExpiry(365)">一年</el-button>
            <el-button size="small" type="info" plain @click="grantDialog.form.valid_until = null">永久</el-button>
          </div>
          <el-date-picker v-model="grantDialog.form.valid_until" type="datetime" placeholder="不填为永久" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="grantDialog.loading" @click="submitGrant">授权</el-button>
      </template>
    </el-dialog>

    <!-- 编辑授权 -->
    <el-dialog v-model="authEditDialog.visible" title="编辑项目授权" width="420px" destroy-on-close>
      <el-form :model="authEditDialog.form" label-width="100px">
        <el-form-item label="授权等级">
          <el-select v-model="authEditDialog.form.user_level" style="width:100%">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
          </el-select>
        </el-form-item>
        <el-form-item label="授权设备数">
          <el-input-number v-model="authEditDialog.form.authorized_devices" :min="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker v-model="authEditDialog.form.valid_until" type="datetime" placeholder="不填为永久" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="authEditDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="authEditDialog.loading" @click="submitEditAuth">保存</el-button>
      </template>
    </el-dialog>

    <!-- 升级授权 -->
    <el-dialog v-model="upgradeDialog.visible" title="升级设备数" width="400px" destroy-on-close>
      <el-form label-width="100px" v-if="upgradeDialog.row">
        <el-form-item label="当前项目">{{ upgradeDialog.row.game_project_name }}</el-form-item>
        <el-form-item label="当前设备">{{ upgradeDialog.row.authorized_devices }} 台</el-form-item>
        <el-form-item label="新增数量">
          <el-input-number v-model="upgradeDialog.form.additional_devices" :min="1" style="width:140px" />
          <div style="margin-top:4px">
            <el-button size="small" @click="upgradeDialog.form.additional_devices=10">+10</el-button>
            <el-button size="small" @click="upgradeDialog.form.additional_devices=20">+20</el-button>
            <el-button size="small" @click="upgradeDialog.form.additional_devices=50">+50</el-button>
            <el-button size="small" @click="upgradeDialog.form.additional_devices=100">+100</el-button>
          </div>
        </el-form-item>
        <el-form-item label="升级后">{{ (upgradeDialog.row.authorized_devices||0) + (upgradeDialog.form.additional_devices||0) }} 台</el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="upgradeDialog.visible=false">取消</el-button>
        <el-button type="primary" :loading="upgradeDialog.loading" @click="submitUpgrade">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { userApi }    from '@/api/user'
import { agentApi }   from '@/api/agent'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { useAuthStore } from '@/stores/auth'
import StatusBadge from '@/components/common/StatusBadge.vue'
import LevelTag from '@/components/common/LevelTag.vue'
import {
  formatDatetime, formatDate, formatRelativeTime,
  expiryTagType, expiryLabel,
} from '@/utils/format'

const route    = useRoute()
const router   = useRouter()
const authStore = useAuthStore()
const userId   = Number(route.params.id)

// ── 页面数据 ─────────────────────────────────────────────────
const pageLoading    = ref(false)
const user           = ref(null)
const deviceBindings = ref([])
const bindingsLoading = ref(false)
const availableProjects = ref([])

const loadUser = async () => {
  pageLoading.value = true
  try {
    const res = await userApi.detail(userId)
    user.value = res.data
  } catch {
    ElMessage.error('用户不存在')
    router.push('/users')
  } finally {
    pageLoading.value = false
  }
}

const loadDeviceBindings = async () => {
  // 后端 Phase 2 提供设备绑定列表接口，当前用 detail 里的 device_binding_count 展示占位
  // 此处先尝试调用，失败静默
  bindingsLoading.value = true
  try {
    const res = await userApi.deviceBindings(userId)
    deviceBindings.value = res.data
  } catch {
    deviceBindings.value = []
  } finally {
    bindingsLoading.value = false
  }
}

const loadAvailableProjects = async () => {
  if (availableProjects.value.length) return
  try {
    if (authStore.isAdmin) {
      const res = await projectApi.list({ page: 1, page_size: 100, is_active: true })
      availableProjects.value = res.data.projects
    } else {
      const res = await agentApi.myProjects()
      availableProjects.value = res.data
    }
  } catch { /* 静默 */ }
}

onMounted(async () => {
  await loadUser()
  loadDeviceBindings()
})

// ── 启用 / 停用 ─────────────────────────────────────────────
const toggleStatus = async () => {
  const newStatus = user.value.status === 'active' ? 'suspended' : 'active'
  await userApi.update(userId, { status: newStatus })
  ElMessage.success('操作成功')
  loadUser()
}

// ── 编辑 ─────────────────────────────────────────────────────
const editDialog = reactive({ visible: false, loading: false, form: {} })

const openEditDialog = () => {
  editDialog.form = {
    status: user.value.status,
  }
  editDialog.visible = true
}

const submitEdit = async () => {
  editDialog.loading = true
  try {
    await userApi.update(userId, editDialog.form)
    ElMessage.success('更新成功')
    editDialog.visible = false
    loadUser()
  } finally {
    editDialog.loading = false
  }
}

// ── 项目授权 ─────────────────────────────────────────────────
const grantFormRef = ref(null)
const grantDialog  = reactive({ visible: false, loading: false, form: { game_project_id: null, user_level: 'normal', authorized_devices: 20, valid_until: null } })
const grantRules   = { game_project_id: [{ required: true, message: '请选择项目', trigger: 'change' }], user_level: [{ required: true, message: '请选择等级', trigger: 'change' }] }

const authEditDialog = reactive({ visible: false, loading: false, form: { user_level: 'normal', authorized_devices: 20, valid_until: null }, row: null })
const openEditAuthDialog = (row) => {
  authEditDialog.row = row
  authEditDialog.form = { user_level: row.user_level, authorized_devices: row.authorized_devices, valid_until: row.valid_until }
  authEditDialog.visible = true
}
const upgradeDialog = reactive({
  visible: false, loading: false, row: null,
  form: { additional_devices: 10 },
})

const openUpgradeDialog = (row) => {
  upgradeDialog.row = row
  upgradeDialog.form = { additional_devices: 10 }
  upgradeDialog.visible = true
}

const submitUpgrade = async () => {
  if (!upgradeDialog.row || !upgradeDialog.form.additional_devices) return
  upgradeDialog.loading = true
  try {
    await userApi.updateAuth(user.value.id, upgradeDialog.row.id, {
      authorized_devices: (upgradeDialog.row.authorized_devices || 0) + upgradeDialog.form.additional_devices,
    })
    ElMessage.success(`已升级到 ${(upgradeDialog.row.authorized_devices || 0) + upgradeDialog.form.additional_devices} 台`)
    upgradeDialog.visible = false
    await loadUser()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '升级失败')
  } finally {
    upgradeDialog.loading = false
  }
}

const submitEditAuth = async () => {
  if (!authEditDialog.row) return
  authEditDialog.loading = true
  try {
    await userApi.updateAuth(user.value.id, authEditDialog.row.id, authEditDialog.form)
    ElMessage.success('授权已更新')
    authEditDialog.visible = false
    await loadUser()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '更新失败')
  } finally { authEditDialog.loading = false }
}

const openGrantDialog = async () => {
  grantDialog.form    = { game_project_id: null, valid_until: null }
  grantDialog.visible = true
  loadAvailableProjects()
}

const setGrantExpiry = (days) => {
  const d = new Date()
  d.setDate(d.getDate() + days)
  grantDialog.form.valid_until = d
}

const submitGrant = async () => {
  if (!await grantFormRef.value?.validate().catch(() => false)) return
  grantDialog.loading = true
  try {
    await userApi.grantAuth(userId, grantDialog.form)
    ElMessage.success('授权成功')
    grantDialog.visible = false
    loadUser()
  } finally {
    grantDialog.loading = false
  }
}

const revokeAuth = async (auth) => {
  await userApi.revokeAuth(userId, auth.id)
  ElMessage.success('已停用授权')
  loadUser()
}

// ── 解绑设备 ─────────────────────────────────────────────────
const unbindDevice = async (binding) => {
  try {
    await userApi.unbindDevice(userId, binding.id)
    ElMessage.success('设备已解绑')
    loadDeviceBindings()
    loadUser()
  } catch {
    ElMessage.error('解绑失败，请稍后重试')
  }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.breadcrumb { margin-bottom: 4px; font-size: 13px; }

/* 用户头部 */
.info-card { border-radius: 10px; }
.user-header {
  display: flex; align-items: center; gap: 16px;
}
.user-avatar {
  width: 52px; height: 52px; border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff; font-size: 22px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.user-meta { flex: 1; }
.user-name { font-size: 18px; font-weight: 700; color: #1e293b; margin-bottom: 6px; }
.user-tags { display: flex; align-items: center; }
.user-actions { display: flex; gap: 8px; flex-shrink: 0; }

.mono { font-family: 'Cascadia Code', monospace; font-size: 12px; }
.text-success { color: #10b981; font-size: 13px; }
.text-muted   { color: #94a3b8; }
.text-warning { color: #f59e0b; font-weight: 600; }
.field-hint   { font-size: 11px; color: #94a3b8; }

.inner-card { border-radius: 10px; }
.card-title  { font-size: 14px; font-weight: 600; color: #1e293b; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
</style>
