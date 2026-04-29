<template>
  <div class="page">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建用户</el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width:110px">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>

        <el-form-item label="级别">
          <el-select v-model="filter.level" clearable placeholder="全部" style="width:110px">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <el-form-item label="项目">
          <el-select
            v-model="filter.project_id"
            clearable
            placeholder="全部项目"
            style="width:180px"
            filterable
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="p.display_name"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadUsers">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div v-if="selectedIds.length > 0" class="batch-toolbar">
      <span class="batch-info">已选 {{ selectedIds.length }} 条</span>
      <el-popconfirm
        :title="`确认批量删除 ${selectedIds.length} 个用户？（软删除）`"
        confirm-button-text="删除"
        cancel-button-text="取消"
        @confirm="batchDelete"
      >
        <template #reference>
          <el-button type="danger" size="small" :loading="batchLoading">批量删除</el-button>
        </template>
      </el-popconfirm>
      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="users"
        row-key="id"
        stripe
        style="width:100%"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="id" label="ID" width="65" />

        <el-table-column label="用户名" min-width="130">
          <template #default="{ row }">
            <el-button
              text
              class="username-link"
              @click="router.push({ path: '/devices', query: { user_id: row.id, username: row.username } })"
            >
              {{ row.username }}
            </el-button>
          </template>
        </el-table-column>

        <el-table-column label="创建信息" min-width="165">
          <template #default="{ row }">
            <div class="creator-cell">
              <div>
                <el-tag
                  size="small"
                  effect="plain"
                  :type="row.created_by_type === 'agent' ? 'warning' : 'danger'"
                >
                  {{ row.created_by_display }}
                </el-tag>
              </div>
              <div class="sub-text">{{ formatDatetime(row.created_at) }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="级别" width="75">
          <template #default="{ row }">
            <LevelTag :level="row.user_level" />
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <StatusBadge :status="row.status" type="user" />
          </template>
        </el-table-column>

        <el-table-column label="项目授权明细" min-width="440">
          <template #default="{ row }">
            <span v-if="!row.authorizations?.length" class="no-auth">未授权</span>

            <div v-else class="auth-list">
              <div
                v-for="authItem in row.authorizations"
                :key="authItem.id"
                class="auth-card"
              >
                <div class="auth-title-row">
                  <span class="auth-project-name">{{ authItem.game_project_name }}</span>
                  <LevelTag :level="authItem.user_level" />
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="authItem.status === 'active' ? 'success' : 'info'"
                  >
                    {{ authItem.status === 'active' ? '有效' : '已停用' }}
                  </el-tag>
                </div>

                <div class="auth-meta-row">
                  <span>授权 {{ displayDeviceLimit(authItem.authorized_devices) }} 台</span>
                  <span>已激活 {{ authItem.activated_devices }} 台</span>
                  <span>未激活 {{ displayInactiveDevices(authItem) }} 台</span>
                </div>

                <div class="auth-expiry-row">
                  到期：
                  <span v-if="!authItem.valid_until" class="expiry-permanent">永久有效</span>
                  <span v-else>
                    {{ formatDate(authItem.valid_until) }}
                    <el-tag
                      :type="expiryTagType(authItem.valid_until)"
                      size="small"
                      effect="light"
                    >
                      {{ expiryLabel(authItem.valid_until) }}
                    </el-tag>
                  </span>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="用户总设备" width="105" align="center">
          <template #default="{ row }">
            <el-tooltip
              :content="`用户维度已绑 ${row.device_binding_count} 台，上限 ${row.max_devices === 0 ? '无限制' : row.max_devices}`"
              placement="top"
            >
              <span :class="['device-count', isNearLimit(row) ? 'near-limit' : '']">
                {{ row.device_binding_count }}
                <span class="device-limit">/{{ row.max_devices === 0 ? '∞' : row.max_devices }}</span>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="账号到期" min-width="145">
          <template #default="{ row }">
            <span v-if="!row.expired_at" class="expiry-permanent">永久有效</span>
            <div v-else class="expiry-cell">
              <span class="expiry-date">{{ formatDate(row.expired_at) }}</span>
              <el-tag :type="expiryTagType(row.expired_at)" effect="light" size="small">
                {{ expiryLabel(row.expired_at) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="245" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="router.push(`/users/${row.id}`)">详情</el-button>
            <el-button text size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button
              text
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-button text size="small" type="primary" @click="openProjectAuthDialog(row)">授权</el-button>
            <el-popconfirm
              v-if="auth.isAdmin"
              title="确认删除该用户？（软删除）"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="deleteUser(row)"
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
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @size-change="loadUsers"
        @current-change="loadUsers"
      />
    </el-card>

    <!-- 新建用户 -->
    <el-dialog v-model="createDialog.visible" title="新建用户" width="560px" destroy-on-close>
      <el-form ref="createFormRef" :model="createDialog.form" :rules="createRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createDialog.form.username" placeholder="3-64 字符" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="createDialog.form.password" type="password" show-password placeholder="至少 6 字符" />
        </el-form-item>

        <el-form-item label="级别" prop="user_level">
          <el-select v-model="createDialog.form.user_level" style="width:100%">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <el-form-item label="授权项目">
          <el-select
            v-model="createDialog.form.project_id"
            clearable
            placeholder="可选；代理选择后会按项目定价扣点"
            style="width:100%"
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="`${p.display_name}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`"
              :value="p.id"
            />
          </el-select>
          <div v-if="auth.isAgent" class="hint-text">
            代理创建用户并授权项目时，将按项目、级别、设备数、周期扣点。
          </div>
        </el-form-item>

        <el-form-item label="设备上限">
          <div class="device-limit-wrap">
            <el-input-number
              v-model="createDialog.form.max_devices"
              :min="auth.isAgent ? 1 : 0"
              :step="10"
              controls-position="right"
              style="width:150px"
            />
            <span v-if="auth.isAdmin && createDialog.form.max_devices === 0" class="hint-text">无限制</span>
          </div>

          <div class="quick-btns" style="margin-top:6px">
            <el-button size="small" @click="createDialog.form.max_devices = 20">20</el-button>
            <el-button size="small" @click="createDialog.form.max_devices = 50">50</el-button>
            <el-button size="small" @click="createDialog.form.max_devices = 100">100</el-button>
            <el-button size="small" @click="createDialog.form.max_devices = 500">500</el-button>
            <el-button
              v-if="auth.isAdmin"
              size="small"
              type="info"
              plain
              @click="createDialog.form.max_devices = 0"
            >
              无限
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setCreateExpiry(7)">一周</el-button>
              <el-button size="small" @click="setCreateExpiry(30)">一个月</el-button>
              <el-button size="small" @click="setCreateExpiry(90)">三个月</el-button>
              <el-button size="small" @click="setCreateExpiry(365)">一年</el-button>
              <el-button
                v-if="auth.isAdmin"
                size="small"
                type="info"
                plain
                @click="createDialog.form.expired_at = null"
              >
                永久
              </el-button>
            </div>

            <el-date-picker
              v-model="createDialog.form.expired_at"
              type="datetime"
              :placeholder="auth.isAdmin ? '不填为永久有效' : '代理必须设置到期时间'"
              style="width:100%"
            />
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-dialog v-model="editDialog.visible" title="编辑用户" width="720px" destroy-on-close>
      <el-form ref="editFormRef" :model="editDialog.form" label-width="95px">
        <el-form-item label="用户名">
          <span class="readonly-val">{{ editDialog.row?.username }}</span>
        </el-form-item>

        <el-form-item label="创建信息">
          <div>
            <el-tag
              size="small"
              effect="plain"
              :type="editDialog.row?.created_by_type === 'agent' ? 'warning' : 'danger'"
            >
              {{ editDialog.row?.created_by_display }}
            </el-tag>
            <span class="sub-text" style="margin-left:8px">
              {{ formatDatetime(editDialog.row?.created_at) }}
            </span>
          </div>
        </el-form-item>

        <el-form-item label="级别">
          <el-select v-model="editDialog.form.user_level" size="small" style="width:150px">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <el-form-item label="设备上限">
          <div class="device-limit-wrap">
            <el-input-number
              v-model="editDialog.form.max_devices"
              :min="auth.isAgent ? 1 : 0"
              :step="10"
              controls-position="right"
              style="width:150px"
            />
            <span class="hint-text">已绑 {{ editDialog.row?.device_binding_count ?? 0 }} 台</span>
          </div>

          <div class="quick-btns" style="margin-top:6px">
            <el-button size="small" @click="editDialog.form.max_devices = 20">20</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = 50">50</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = 100">100</el-button>
            <el-button size="small" @click="editDialog.form.max_devices = 500">500</el-button>
            <el-button
              v-if="auth.isAdmin"
              size="small"
              type="info"
              plain
              @click="editDialog.form.max_devices = 0"
            >
              无限
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="账号到期">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="addRenewDays(7)">+7天</el-button>
              <el-button size="small" @click="addRenewDays(30)">+30天</el-button>
              <el-button size="small" @click="addRenewDays(90)">+90天</el-button>
              <el-button
                v-if="auth.isAdmin"
                size="small"
                type="info"
                plain
                @click="editDialog.form.expired_at = null"
              >
                永久
              </el-button>
            </div>

            <el-date-picker
              v-model="editDialog.form.expired_at"
              type="datetime"
              placeholder="设置账号到期时间"
              style="width:100%"
            />
          </div>
        </el-form-item>

        <el-divider content-position="left">密码</el-divider>

        <el-alert
          title="系统不保存旧密码明文。管理员自动重置后只会一次性显示新密码；关闭弹窗后不可再次查看。"
          type="info"
          show-icon
          :closable="false"
          class="small-alert"
        />

        <el-form-item label="新密码">
          <el-input
            v-model="editDialog.password.new_password"
            type="password"
            show-password
            placeholder="手动输入新密码，至少 6 位"
          />
        </el-form-item>

        <el-form-item label="确认密码">
          <el-input
            v-model="editDialog.password.confirm_password"
            type="password"
            show-password
            placeholder="再次输入新密码"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="editDialog.passwordLoading"
            @click="submitPassword(false)"
          >
            修改密码
          </el-button>

          <el-button
            v-if="auth.isAdmin"
            type="warning"
            plain
            :loading="editDialog.passwordLoading"
            @click="submitPassword(true)"
          >
            自动生成新密码
          </el-button>
        </el-form-item>

        <el-alert
          v-if="editDialog.generatedPassword"
          type="success"
          show-icon
          :closable="false"
          class="small-alert"
        >
          <template #title>
            新密码：<strong class="generated-password">{{ editDialog.generatedPassword }}</strong>
            <el-button text size="small" @click="copyPassword">复制</el-button>
          </template>
        </el-alert>

        <el-divider content-position="left">项目授权情况</el-divider>

        <el-table :data="editDialog.auths" size="small" empty-text="暂无授权项目">
          <el-table-column label="项目" min-width="130" prop="game_project_name" />
          <el-table-column label="级别" width="80">
            <template #default="{ row }">
              <LevelTag :level="row.user_level" />
            </template>
          </el-table-column>
          <el-table-column label="授权设备" width="90">
            <template #default="{ row }">{{ displayDeviceLimit(row.authorized_devices) }}</template>
          </el-table-column>
          <el-table-column label="已激活" width="80" prop="activated_devices" />
          <el-table-column label="未激活" width="80">
            <template #default="{ row }">{{ displayInactiveDevices(row) }}</template>
          </el-table-column>
          <el-table-column label="到期" min-width="130">
            <template #default="{ row }">
              <span v-if="!row.valid_until" class="expiry-permanent">永久</span>
              <span v-else>{{ formatDate(row.valid_until) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="unauth-block">
          <div class="section-title">未授权项目</div>
          <div v-if="unauthorizedProjects.length" class="project-tags">
            <el-tag
              v-for="p in unauthorizedProjects"
              :key="p.id"
              size="small"
              effect="plain"
              type="info"
            >
              {{ p.display_name }}
            </el-tag>
          </div>
          <span v-else class="no-auth">无</span>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="editDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="editDialog.loading" @click="submitEdit">保存基础信息</el-button>
      </template>
    </el-dialog>

    <!-- 项目授权弹窗 -->
    <el-dialog
      v-model="projectAuthDialog.visible"
      :title="`项目授权 — ${projectAuthDialog.username}`"
      width="650px"
      destroy-on-close
    >
      <div class="auth-section">
        <div class="auth-section-title">
          已授权项目
          <el-button size="small" :icon="Refresh" @click="loadUserAuths" style="margin-left:8px" />
        </div>

        <el-table
          v-loading="projectAuthDialog.listLoading"
          :data="projectAuthDialog.auths"
          size="small"
          empty-text="暂无授权"
        >
          <el-table-column label="项目名称" min-width="140" prop="game_project_name" />
          <el-table-column label="级别" width="80">
            <template #default="{ row }">
              <LevelTag :level="row.user_level" />
            </template>
          </el-table-column>
          <el-table-column label="设备" width="150">
            <template #default="{ row }">
              授权 {{ displayDeviceLimit(row.authorized_devices) }} /
              激活 {{ row.activated_devices }}
            </template>
          </el-table-column>
          <el-table-column label="到期" width="140">
            <template #default="{ row }">
              <span v-if="!row.valid_until" class="expiry-permanent">永久</span>
              <span v-else>
                {{ formatDate(row.valid_until) }}
                <el-tag :type="expiryTagType(row.valid_until)" size="small" effect="light">
                  {{ expiryLabel(row.valid_until) }}
                </el-tag>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="75">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                {{ row.status === 'active' ? '有效' : '已停' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column width="70" fixed="right">
            <template #default="{ row }">
              <el-button
                text
                size="small"
                type="danger"
                :disabled="row.status !== 'active'"
                @click="revokeUserAuth(row)"
              >
                停用
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-divider content-position="left">授予新项目</el-divider>

      <el-form ref="projectAuthFormRef" :model="projectAuthDialog.form" :rules="projectAuthRules" label-width="90px">
        <el-form-item label="选择项目" prop="game_project_id">
          <el-select
            v-model="projectAuthDialog.form.game_project_id"
            filterable
            style="width:100%"
            :loading="projectAuthDialog.projectsLoading"
          >
            <el-option
              v-for="p in availableProjects"
              :key="p.id"
              :label="`${p.display_name}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setUserAuthExpiry(7)">一周</el-button>
              <el-button size="small" @click="setUserAuthExpiry(30)">一个月</el-button>
              <el-button size="small" @click="setUserAuthExpiry(90)">三个月</el-button>
              <el-button size="small" @click="setUserAuthExpiry(365)">一年</el-button>
              <el-button
                v-if="auth.isAdmin"
                size="small"
                type="info"
                plain
                @click="projectAuthDialog.form.valid_until = null"
              >
                永久
              </el-button>
            </div>

            <el-date-picker
              v-model="projectAuthDialog.form.valid_until"
              type="datetime"
              :placeholder="auth.isAdmin ? '不填为永久' : '代理必须选择到期时间'"
              style="width:100%"
            />
          </div>
        </el-form-item>

        <el-alert
          v-if="auth.isAgent"
          title="代理授权项目会按项目定价、用户级别、设备上限、授权周期扣除点数。"
          type="warning"
          show-icon
          :closable="false"
          class="small-alert"
        />

        <el-form-item>
          <el-button
            type="primary"
            :loading="projectAuthDialog.grantLoading"
            @click="grantUserProjectAuth"
          >
            授权
          </el-button>
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
import { userApi } from '@/api/user'
import { agentApi } from '@/api/agent'
import { projectApi } from '@/api/project'
import { useAuthStore } from '@/stores/auth'
import StatusBadge from '@/components/common/StatusBadge.vue'
import LevelTag from '@/components/common/LevelTag.vue'
import { formatDatetime, formatDate, expiryTagType, expiryLabel } from '@/utils/format'

const auth = useAuthStore()
const router = useRouter()

const allProjects = ref([])
const availableProjects = ref([])

const loading = ref(false)
const users = ref([])
const selectedIds = ref([])
const batchLoading = ref(false)

const filter = reactive({
  status: null,
  level: null,
  project_id: null,
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

onMounted(async () => {
  await loadProjects()
  await loadUsers()
})

const loadProjects = async () => {
  try {
    if (auth.isAdmin) {
      const res = await projectApi.list({ page: 1, page_size: 200, is_active: true })
      allProjects.value = res.data.projects || []
    } else {
      const res = await agentApi.myProjects()
      allProjects.value = Array.isArray(res.data) ? res.data : []
    }
  } catch {
    allProjects.value = []
  }
}

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await userApi.list({
      page: pagination.page,
      page_size: pagination.pageSize,
      status: filter.status || undefined,
      level: filter.level || undefined,
      project_id: filter.project_id || undefined,
    })
    users.value = res.data.users || []
    pagination.total = res.data.total || 0
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filter.status = null
  filter.level = null
  filter.project_id = null
  pagination.page = 1
  loadUsers()
}

const onSelectionChange = (rows) => {
  selectedIds.value = rows.map(r => r.id)
}

const batchDelete = async () => {
  batchLoading.value = true
  try {
    const ids = [...selectedIds.value]
    const results = await Promise.allSettled(ids.map(id => userApi.delete(id)))
    const success = results.filter(r => r.status === 'fulfilled').length
    const failed = results.length - success

    if (failed === 0) {
      ElMessage.success(`已删除 ${success} 个用户`)
    } else {
      ElMessage.warning(`成功 ${success} 个，失败 ${failed} 个`)
    }

    selectedIds.value = []
    await loadUsers()
  } finally {
    batchLoading.value = false
  }
}

const toggleStatus = async (row) => {
  await userApi.update(row.id, {
    status: row.status === 'active' ? 'suspended' : 'active',
  })
  ElMessage.success('操作成功')
  await loadUsers()
}

const deleteUser = async (row) => {
  await userApi.delete(row.id)
  ElMessage.success('已删除用户')
  await loadUsers()
}

const isNearLimit = (row) => {
  const limit = row.max_devices
  if (!limit) return false
  return row.device_binding_count / limit >= 0.8
}

const displayDeviceLimit = (val) => {
  return val === 0 ? '∞' : val
}

const displayInactiveDevices = (row) => {
  return row.inactive_devices === null || row.inactive_devices === undefined
    ? '—'
    : row.inactive_devices
}

const daysLater = (n, base = null) => {
  const d = base ? new Date(base) : new Date()
  d.setDate(d.getDate() + n)
  return d
}

/* ── 新建用户 ─────────────────────────────────────────────── */

const createFormRef = ref(null)

const createDialog = reactive({
  visible: false,
  loading: false,
  form: {
    username: '',
    password: '',
    user_level: 'normal',
    max_devices: 20,
    expired_at: null,
    project_id: null,
  },
})

const createRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  user_level: [{ required: true, message: '请选择级别', trigger: 'change' }],
}

const setCreateExpiry = (n) => {
  createDialog.form.expired_at = daysLater(n)
}

const openCreateDialog = () => {
  createDialog.form = {
    username: '',
    password: '',
    user_level: 'normal',
    max_devices: 20,
    expired_at: auth.isAdmin ? null : daysLater(30),
    project_id: null,
  }
  createDialog.visible = true
}

const submitCreate = async () => {
  if (!await createFormRef.value?.validate().catch(() => false)) return

  if (auth.isAgent && !createDialog.form.expired_at) {
    ElMessage.warning('代理创建用户必须设置到期时间')
    return
  }

  createDialog.loading = true

  try {
    const { project_id, ...baseForm } = createDialog.form
    const res = await userApi.create(baseForm)
    const newUserId = res.data?.id

    if (project_id && newUserId) {
      await userApi.grantAuth(newUserId, {
        game_project_id: project_id,
        valid_until: createDialog.form.expired_at || null,
      })
    }

    ElMessage.success('用户创建成功')
    createDialog.visible = false
    await loadUsers()
  } finally {
    createDialog.loading = false
  }
}

/* ── 编辑用户 ─────────────────────────────────────────────── */

const editFormRef = ref(null)

const editDialog = reactive({
  visible: false,
  loading: false,
  passwordLoading: false,
  editId: null,
  row: null,
  auths: [],
  generatedPassword: '',
  form: {
    user_level: 'normal',
    max_devices: 20,
    expired_at: null,
  },
  password: {
    new_password: '',
    confirm_password: '',
  },
})

const unauthorizedProjects = computed(() => {
  const authedIds = new Set(editDialog.auths.map(a => a.game_project_id))
  return allProjects.value.filter(p => !authedIds.has(p.id))
})

const openEditDialog = async (row) => {
  editDialog.row = row
  editDialog.editId = row.id
  editDialog.generatedPassword = ''
  editDialog.password = {
    new_password: '',
    confirm_password: '',
  }
  editDialog.form = {
    user_level: row.user_level,
    max_devices: row.max_devices,
    expired_at: row.expired_at ? new Date(row.expired_at) : null,
  }

  editDialog.visible = true

  try {
    const res = await userApi.detail(row.id)
    editDialog.auths = res.data.authorizations || []
    editDialog.row = res.data
  } catch {
    editDialog.auths = row.authorizations || []
  }
}

const addRenewDays = (n) => {
  const base = editDialog.row?.expired_at ? new Date(editDialog.row.expired_at) : new Date()
  editDialog.form.expired_at = daysLater(n, base)
}

const submitEdit = async () => {
  editDialog.loading = true
  try {
    await userApi.update(editDialog.editId, {
      user_level: editDialog.form.user_level,
      max_devices: editDialog.form.max_devices,
      expired_at: editDialog.form.expired_at || null,
    })
    ElMessage.success('更新成功')
    editDialog.visible = false
    await loadUsers()
  } finally {
    editDialog.loading = false
  }
}

const submitPassword = async (autoGenerate) => {
  if (!autoGenerate) {
    if (!editDialog.password.new_password || editDialog.password.new_password.length < 6) {
      ElMessage.warning('请输入至少 6 位新密码')
      return
    }
    if (editDialog.password.new_password !== editDialog.password.confirm_password) {
      ElMessage.warning('两次输入的新密码不一致')
      return
    }
  }

  editDialog.passwordLoading = true

  try {
    const res = await userApi.updatePassword(editDialog.editId, {
      auto_generate: autoGenerate,
      new_password: autoGenerate ? null : editDialog.password.new_password,
    })

    editDialog.generatedPassword = res.data.generated_password || ''
    editDialog.password.new_password = ''
    editDialog.password.confirm_password = ''

    ElMessage.success('密码已更新')
  } finally {
    editDialog.passwordLoading = false
  }
}

const copyPassword = async () => {
  if (!editDialog.generatedPassword) return
  await navigator.clipboard.writeText(editDialog.generatedPassword)
  ElMessage.success('已复制新密码')
}

/* ── 项目授权 ─────────────────────────────────────────────── */

const projectAuthFormRef = ref(null)

const projectAuthDialog = reactive({
  visible: false,
  userId: null,
  username: '',
  auths: [],
  listLoading: false,
  projectsLoading: false,
  grantLoading: false,
  form: {
    game_project_id: null,
    valid_until: null,
  },
})

const projectAuthRules = {
  game_project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
}

const openProjectAuthDialog = async (row) => {
  projectAuthDialog.userId = row.id
  projectAuthDialog.username = row.username
  projectAuthDialog.form = {
    game_project_id: null,
    valid_until: auth.isAdmin ? null : daysLater(30),
  }
  projectAuthDialog.visible = true

  await loadUserAuths()

  if (!availableProjects.value.length) {
    projectAuthDialog.projectsLoading = true
    try {
      availableProjects.value = allProjects.value
    } finally {
      projectAuthDialog.projectsLoading = false
    }
  }
}

const loadUserAuths = async () => {
  projectAuthDialog.listLoading = true
  try {
    const res = await userApi.detail(projectAuthDialog.userId)
    projectAuthDialog.auths = res.data.authorizations || []
  } finally {
    projectAuthDialog.listLoading = false
  }
}

const setUserAuthExpiry = (n) => {
  projectAuthDialog.form.valid_until = daysLater(n)
}

const grantUserProjectAuth = async () => {
  if (!await projectAuthFormRef.value?.validate().catch(() => false)) return

  if (auth.isAgent && !projectAuthDialog.form.valid_until) {
    ElMessage.warning('代理授权项目必须设置到期时间')
    return
  }

  projectAuthDialog.grantLoading = true

  try {
    const res = await userApi.grantAuth(projectAuthDialog.userId, {
      game_project_id: projectAuthDialog.form.game_project_id,
      valid_until: projectAuthDialog.form.valid_until || null,
    })

    if (auth.isAgent && res.data.consumed_points) {
      ElMessage.success(`授权成功，已扣除 ${Number(res.data.consumed_points).toFixed(2)} 点`)
    } else {
      ElMessage.success('授权成功')
    }

    projectAuthDialog.form = {
      game_project_id: null,
      valid_until: auth.isAdmin ? null : daysLater(30),
    }

    await loadUserAuths()
    await loadUsers()
  } finally {
    projectAuthDialog.grantLoading = false
  }
}

const revokeUserAuth = async (authRow) => {
  await userApi.revokeAuth(projectAuthDialog.userId, authRow.id)
  ElMessage.success('已停用授权')
  await loadUserAuths()
  await loadUsers()
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
  align-items: center;
  justify-content: space-between;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1e293b;
}

.filter-card,
.table-card {
  border-radius: 10px;
}

.batch-toolbar {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-info {
  font-size: 13px;
  color: #1d4ed8;
  font-weight: 500;
}

.username-link {
  font-weight: 500;
  color: #2563eb !important;
  padding: 0;
  height: auto;
}

.creator-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.sub-text {
  font-size: 11px;
  color: #94a3b8;
}

.no-auth {
  font-size: 12px;
  color: #94a3b8;
}

.auth-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.auth-card {
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 8px;
  padding: 8px 10px;
}

.auth-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.auth-project-name {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.auth-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 5px;
  font-size: 12px;
  color: #64748b;
}

.auth-expiry-row {
  margin-top: 5px;
  font-size: 12px;
  color: #64748b;
}

.device-count {
  font-size: 13px;
  cursor: default;
}

.device-limit {
  color: #94a3b8;
  font-size: 11px;
  margin-left: 1px;
}

.device-count.near-limit {
  color: #f59e0b;
  font-weight: 700;
}

.expiry-permanent {
  color: #10b981;
  font-size: 12px;
}

.expiry-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.expiry-date {
  font-size: 12px;
  color: #475569;
}

.device-limit-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hint-text {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}

.quick-btns {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.expiry-picker-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.readonly-val {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.auth-section {
  margin-bottom: 8px;
}

.auth-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.small-alert {
  margin-bottom: 12px;
  border-radius: 8px;
}

.generated-password {
  font-family: 'Cascadia Code', Consolas, monospace;
  color: #166534;
  margin: 0 6px;
}

.unauth-block {
  margin-top: 12px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
}

.project-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>