<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>用户管理</h2>
        <p class="page-desc">
          用户是账号主体；项目等级、授权设备数量、项目到期时间全部归属“用户 × 项目授权”。
        </p>
      </div>

      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        新建用户
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 110px">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>

        <el-form-item label="项目授权等级">
          <el-select v-model="filter.level" clearable placeholder="全部" style="width: 140px">
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
            filterable
            placeholder="全部项目"
            style="width: 190px"
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="projectName(p)"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="auth.isAdmin" label="创建代理">
          <el-select
            v-model="filter.creator_agent_id"
            clearable
            filterable
            placeholder="全部代理"
            style="width: 180px"
          >
            <el-option
              v-for="ag in allAgents"
              :key="ag.id"
              :label="`${ag.username} (ID:${ag.id})`"
              :value="ag.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="auth.isAdmin" label="代理业务等级">
          <el-select
            v-model="filter.creator_agent_tier_level"
            clearable
            placeholder="全部"
            style="width: 130px"
          >
            <el-option label="Lv.1" :value="1" />
            <el-option label="Lv.2" :value="2" />
            <el-option label="Lv.3" :value="3" />
            <el-option label="Lv.4" :value="4" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="auth.isAdmin" label="可创建下级">
          <el-select
            v-model="filter.creator_agent_can_create_sub_agents"
            clearable
            placeholder="全部"
            style="width: 130px"
          >
            <el-option label="可以" :value="true" />
            <el-option label="不可以" :value="false" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="auth.isAdmin" label="代理风险状态">
          <el-select
            v-model="filter.creator_agent_risk_status"
            clearable
            placeholder="全部"
            style="width: 150px"
          >
            <el-option label="正常" value="normal" />
            <el-option label="观察" value="watch" />
            <el-option label="受限" value="restricted" />
            <el-option label="冻结" value="frozen" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="searchUsers">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
          <el-button :icon="Refresh" :loading="loading" @click="loadUsers">刷新</el-button>
        </el-form-item>
      </el-form>

      <div v-if="filter.project_id" class="filter-hint">
        当前已按项目筛选，列表中的“项目授权明细”只显示所选项目。
      </div>
    </el-card>

    <!-- 批量操作 -->
    <div v-if="auth.isAdmin && selectedIds.length > 0" class="batch-toolbar">
      <span class="batch-info">已选 {{ selectedIds.length }} 条</span>

      <el-button
        type="danger"
        size="small"
        :loading="batchLoading"
        @click="batchDelete"
      >
        批量删除
      </el-button>

      <el-button size="small" @click="clearSelection">
        取消选择
      </el-button>
    </div>

    <!-- 用户列表 -->
    <el-card shadow="never" class="table-card">
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="users"
        row-key="id"
        stripe
        style="width: 100%"
        @selection-change="onSelectionChange"
      >
        <el-table-column v-if="auth.isAdmin" type="selection" width="44" />

        <el-table-column prop="id" label="ID" width="65" />

        <el-table-column label="用户名" min-width="140">
          <template #default="{ row }">
            <div class="user-main">
              <el-button
                text
                class="username-link"
                @click="router.push(`/users/${row.id}`)"
              >
                {{ row.username }}
              </el-button>
              <el-button
                text
                size="small"
                class="device-entry-link"
                @click="router.push({ path: '/devices', query: { user_id: row.id, username: row.username } })"
              >
                设备
              </el-button>
              <StatusBadge :status="row.status" type="user" />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="创建者" min-width="170">
          <template #default="{ row }">
            <div class="creator-cell">
              <el-button
                v-if="row.created_by_type === 'agent' && row.created_by_agent_id && auth.isAdmin"
                text
                class="creator-link"
                @click="openCreatorDetail(row.created_by_agent_id)"
              >
                <el-tag size="small" effect="plain" type="warning">
                  {{ row.created_by_display || '代理' }}
                </el-tag>
              </el-button>

              <el-tag
                v-else
                size="small"
                effect="plain"
                :type="row.created_by_type === 'admin' ? 'danger' : 'info'"
              >
                {{ row.created_by_display || '未知' }}
              </el-tag>

              <div class="sub-text">
                {{ row.created_at ? formatDatetime(row.created_at) : '—' }}
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="项目授权明细" min-width="610">
          <template #default="{ row }">
            <span v-if="!row.authorizations?.length" class="no-auth">
              {{ filter.project_id ? '该项目未授权' : '暂无项目授权' }}
            </span>

            <div v-else class="auth-list">
              <div
                v-for="authItem in row.authorizations"
                :key="authItem.id"
                class="auth-card"
              >
                <div class="auth-title-row">
                  <span class="auth-project-name">
                    {{ authProjectName(authItem) }}
                  </span>

                  <LevelTag :level="authItem.user_level" />

                  <el-tag
                    size="small"
                    effect="plain"
                    :type="authStatusType(authItem)"
                  >
                    {{ authStatusText(authItem) }}
                  </el-tag>
                </div>

                <div class="auth-meta-row">
                  <span>授权设备：{{ displayDeviceLimit(authItem.authorized_devices) }}</span>
                  <span>已激活：{{ authItem.activated_devices ?? 0 }}</span>
                  <span>未激活：{{ displayInactiveDevices(authItem) }}</span>
                </div>

                <div class="auth-expiry-row">
                  项目到期：
                  <span v-if="!authItem.valid_until" class="expiry-permanent">
                    永久有效
                  </span>
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

        <el-table-column label="项目授权数" width="110" align="center">
          <template #default="{ row }">
            <el-tooltip
              :content="`总项目授权记录 ${row.authorization_count || 0} 条；当前显示 ${row.authorizations?.length || 0} 条`"
              placement="top"
            >
              <span class="auth-count">
                {{ row.authorizations?.length || 0 }}
                <span class="auth-count-total">/{{ row.authorization_count || 0 }}</span>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="router.push(`/users/${row.id}`)">
              详情
            </el-button>

            <el-button text size="small" type="primary" @click="openEditDialog(row)">
              编辑
            </el-button>

            <el-button
              text
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>

            <el-popconfirm
              v-if="auth.isAdmin"
              title="确认删除该用户？管理员删除会触发符合条件的返点清算；授权、设备、流水记录会保留用于审计。"
              confirm-button-text="确认删除"
              cancel-button-text="取消"
              @confirm="deleteUser(row)"
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
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @size-change="loadUsers"
        @current-change="loadUsers"
      />
    </el-card>

    <!-- 新建用户 -->
    <el-dialog v-model="createDialog.visible" title="新建用户" width="720px" destroy-on-close>
      <el-form
        ref="createFormRef"
        :model="createDialog.form"
        :rules="createRules"
        label-width="120px"
      >
        <el-divider content-position="left">账号主体</el-divider>

        <el-form-item label="用户名" prop="username">
          <el-input v-model="createDialog.form.username" placeholder="3-64 字符" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="createDialog.form.password"
            type="password"
            show-password
            placeholder="至少 6 字符"
          />
        </el-form-item>

        <el-alert
          title="用户等级、设备数、到期时间不再属于用户主体，而是属于项目授权。"
          type="info"
          show-icon
          :closable="false"
          class="small-alert"
        />

        <el-divider content-position="left">可选：同时添加项目授权</el-divider>

        <el-form-item label="授权项目">
          <el-select
            v-model="createDialog.form.project_id"
            clearable
            filterable
            placeholder="可选；选择后将创建用户并授予该项目"
            style="width: 100%"
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="`${projectName(p)}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <template v-if="createDialog.form.project_id">
          <el-form-item label="项目等级">
            <el-select v-model="createDialog.form.auth_user_level" style="width: 180px">
              <el-option label="试用" value="trial" />
              <el-option label="普通" value="normal" />
              <el-option label="VIP" value="vip" />
              <el-option label="SVIP" value="svip" />
              <el-option v-if="auth.isAdmin" label="测试" value="tester" />
            </el-select>
          </el-form-item>

          <el-form-item label="授权设备数量">
            <div class="device-limit-wrap">
              <el-input-number
                v-model="createDialog.form.authorized_devices"
                :min="auth.isAgent ? 1 : 0"
                :step="10"
                controls-position="right"
                style="width: 170px"
              />

              <span
                v-if="auth.isAdmin && Number(createDialog.form.authorized_devices || 0) === 0"
                class="hint-text"
              >
                无限设备
              </span>
            </div>

            <div class="quick-btns">
              <el-button size="small" @click="createDialog.form.authorized_devices = 20">20</el-button>
              <el-button size="small" @click="createDialog.form.authorized_devices = 50">50</el-button>
              <el-button size="small" @click="createDialog.form.authorized_devices = 100">100</el-button>
              <el-button size="small" @click="createDialog.form.authorized_devices = 500">500</el-button>
              <el-button
                v-if="auth.isAdmin"
                size="small"
                type="info"
                plain
                @click="createDialog.form.authorized_devices = 0"
              >
                无限
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="项目到期时间">
            <div class="expiry-picker-wrap">
              <div class="quick-btns">
                <el-button size="small" @click="setCreateAuthExpiry(7)">一周</el-button>
                <el-button size="small" @click="setCreateAuthExpiry(30)">一个月</el-button>
                <el-button size="small" @click="setCreateAuthExpiry(90)">三个月</el-button>
                <el-button size="small" @click="setCreateAuthExpiry(365)">一年</el-button>
                <el-button
                  v-if="auth.isAdmin"
                  size="small"
                  type="info"
                  plain
                  @click="createDialog.form.auth_valid_until = null"
                >
                  永久
                </el-button>
              </div>

              <el-date-picker
                v-model="createDialog.form.auth_valid_until"
                type="datetime"
                :placeholder="auth.isAdmin ? '不填为永久有效' : '代理必须设置到期时间'"
                style="width: 100%"
              />
            </div>

            <div v-if="auth.isAgent" class="hint-text">
              代理授权项目会按项目定价、项目等级、授权设备数量、授权周期扣点。当前仍是先创建用户、再授权项目的非原子流程；扣点预览与原子创建接口待接入，可能出现用户创建成功但授权失败。
            </div>
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-drawer v-model="editDialog.visible" title="编辑用户" size="760px" destroy-on-close>
      <template #header>
        <div class="drawer-header-row">
          <div class="drawer-avatar">
            {{ (editDialog.row?.username || '?').charAt(0).toUpperCase() }}
          </div>

          <div class="drawer-meta">
            <div class="drawer-name">
              {{ editDialog.row?.username }}
            </div>
            <div class="drawer-sub">
              ID: {{ editDialog.row?.id }}
              <span class="dot">·</span>
              {{ editDialog.row?.created_by_display || '未知创建者' }}
              <span class="dot">·</span>
              {{ userStatusText(editDialog.row?.status) }}
            </div>
          </div>
        </div>
      </template>

      <el-tabs v-model="editDialog.activeTab">
        <el-tab-pane label="基础信息" name="base">
          <el-form :model="editDialog.form" label-width="110px">
            <el-form-item label="用户名">
              <span class="readonly-val">{{ editDialog.row?.username }}</span>
            </el-form-item>

            <el-form-item label="创建信息">
              <el-tag
                size="small"
                effect="plain"
                :type="editDialog.row?.created_by_type === 'agent' ? 'warning' : 'danger'"
              >
                {{ editDialog.row?.created_by_display || '未知' }}
              </el-tag>

              <span class="sub-text inline-sub-text">
                {{ editDialog.row?.created_at ? formatDatetime(editDialog.row.created_at) : '—' }}
              </span>
            </el-form-item>

            <el-form-item label="账号状态">
              <el-select v-model="editDialog.form.status" style="width: 180px">
                <el-option label="正常" value="active" />
                <el-option label="已停用" value="suspended" />
                <el-option label="已过期" value="expired" />
              </el-select>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="editDialog.loading"
                @click="submitEdit"
              >
                保存基础信息
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="密码" name="password">
          <el-form label-width="110px">
            <el-form-item label="新密码">
              <el-input
                v-model="editDialog.password.new_password"
                type="password"
                show-password
                placeholder="至少 6 位"
              />
            </el-form-item>

            <el-form-item label="确认密码">
              <el-input
                v-model="editDialog.password.confirm_password"
                type="password"
                show-password
                placeholder="再次输入"
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
                生成新密码
              </el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="editDialog.generatedPassword"
            type="success"
            show-icon
            :closable="false"
            class="small-alert"
          >
            <template #title>
              新密码：
              <strong class="generated-password">{{ editDialog.generatedPassword }}</strong>
              <el-button text size="small" @click="copyPassword">复制</el-button>
            </template>
          </el-alert>
        </el-tab-pane>

        <el-tab-pane label="项目授权" name="auths">
          <div class="auth-section-title">
            已授权项目
            <el-button
              size="small"
              :icon="Refresh"
              @click="loadEditAuths"
              class="small-refresh-btn"
            />
          </div>

          <el-table
            :data="editDialog.auths"
            size="small"
            empty-text="暂无项目授权"
            stripe
            class="auth-table"
          >
            <el-table-column label="项目" min-width="150">
              <template #default="{ row }">
                {{ authProjectName(row) }}
              </template>
            </el-table-column>

            <el-table-column label="项目等级" width="100">
              <template #default="{ row }">
                <LevelTag :level="row.user_level" />
              </template>
            </el-table-column>

            <el-table-column label="授权设备数量" width="130">
              <template #default="{ row }">
                {{ displayDeviceLimit(row.authorized_devices) }}
              </template>
            </el-table-column>

            <el-table-column label="项目到期时间" width="150">
              <template #default="{ row }">
                <span v-if="!row.valid_until" class="expiry-permanent">永久</span>
                <span v-else>{{ formatDate(row.valid_until) }}</span>
              </template>
            </el-table-column>

            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="authStatusType(row)" size="small" effect="light">
                  {{ authStatusText(row) }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button text size="small" @click="openAuthEditDialog(row)">
                  编辑
                </el-button>

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

          <div v-if="unauthorizedProjects.length" class="unauth-block">
            <div class="section-title">未授权项目 — 可授权</div>
            <div class="project-tags">
              <el-tag
                v-for="p in unauthorizedProjects"
                :key="p.id"
                size="small"
                effect="plain"
                type="info"
                class="project-tag"
              >
                {{ projectName(p) }}
                <el-button text size="small" class="tag-action" @click="quickGrantAuth(p)">
                  + 授权
                </el-button>
              </el-tag>
            </div>
          </div>

          <span v-else class="no-auth">所有项目已授权</span>

          <el-divider />

          <el-form :model="editDialog.grantForm" label-width="120px" @submit.prevent>
            <el-form-item label="授权项目">
              <el-select
                v-model="editDialog.grantForm.project_id"
                filterable
                placeholder="选择项目"
                style="width: 100%"
              >
                <el-option
                  v-for="p in unauthorizedProjects"
                  :key="p.id"
                  :label="projectName(p)"
                  :value="p.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="项目等级">
              <el-select v-model="editDialog.grantForm.user_level" style="width: 180px">
                <el-option label="试用" value="trial" />
                <el-option label="普通" value="normal" />
                <el-option label="VIP" value="vip" />
                <el-option label="SVIP" value="svip" />
                <el-option v-if="auth.isAdmin" label="测试" value="tester" />
              </el-select>
            </el-form-item>

            <el-form-item label="授权设备数量">
              <div class="device-limit-wrap">
                <el-input-number
                  v-model="editDialog.grantForm.authorized_devices"
                  :min="auth.isAgent ? 1 : 0"
                  :step="10"
                  controls-position="right"
                  style="width: 170px"
                />

                <span
                  v-if="auth.isAdmin && Number(editDialog.grantForm.authorized_devices || 0) === 0"
                  class="hint-text"
                >
                  无限设备
                </span>
              </div>

              <div class="quick-btns">
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 20">20</el-button>
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 50">50</el-button>
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 100">100</el-button>
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 500">500</el-button>
                <el-button
                  v-if="auth.isAdmin"
                  size="small"
                  type="info"
                  plain
                  @click="editDialog.grantForm.authorized_devices = 0"
                >
                  无限
                </el-button>
              </div>
            </el-form-item>

            <el-form-item label="项目到期时间">
              <div class="expiry-picker-wrap">
                <div class="quick-btns">
                  <el-button size="small" @click="setGrantAuthExpiry(7)">一周</el-button>
                  <el-button size="small" @click="setGrantAuthExpiry(30)">一个月</el-button>
                  <el-button size="small" @click="setGrantAuthExpiry(90)">三个月</el-button>
                  <el-button size="small" @click="setGrantAuthExpiry(365)">一年</el-button>
                  <el-button
                    v-if="auth.isAdmin"
                    size="small"
                    type="info"
                    plain
                    @click="editDialog.grantForm.valid_until = null"
                  >
                    永久
                  </el-button>
                </div>

                <el-date-picker
                  v-model="editDialog.grantForm.valid_until"
                  type="datetime"
                  :placeholder="auth.isAdmin ? '不填为永久有效' : '代理必须设置到期时间'"
                  style="width: 100%"
                />
              </div>

              <div v-if="auth.isAgent" class="hint-text">
                代理授权会扣点，扣点预览待接入；当前提交后由后端直接扣点并创建授权。
              </div>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="editDialog.grantLoading"
                @click="quickGrantDo"
              >
                授权
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane v-if="auth.isAdmin" label="设备绑定" name="devices">
          <el-alert
            title="设备绑定治理待接入：当前先提供按用户进入设备页的入口，后续补齐设备解绑、异常标记和授权状态联动。"
            type="info"
            show-icon
            :closable="false"
            class="small-alert"
          />

          <div class="governance-panel">
            <div class="governance-row">
              <span class="governance-label">用户设备</span>
              <el-button
                type="primary"
                plain
                size="small"
                @click="router.push({ path: '/devices', query: { user_id: editDialog.row?.id, username: editDialog.row?.username } })"
              >
                查看设备
              </el-button>
            </div>

            <el-table
              :data="editDialog.auths"
              size="small"
              empty-text="暂无项目授权，无法按授权查看设备状态"
              stripe
            >
              <el-table-column label="项目" min-width="150">
                <template #default="{ row }">
                  {{ authProjectName(row) }}
                </template>
              </el-table-column>

              <el-table-column label="授权状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="authStatusType(row)" size="small" effect="light">
                    {{ authStatusText(row) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="授权设备" width="110">
                <template #default="{ row }">
                  {{ displayDeviceLimit(row.authorized_devices) }}
                </template>
              </el-table-column>

              <el-table-column label="已激活" width="90">
                <template #default="{ row }">
                  {{ row.activated_devices ?? 0 }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="账务与冻结" name="finance">
          <el-alert
            :title="auth.isAdmin
              ? '账务与冻结记录待接入：管理员应可查看扣点快照、返点记录、冻结权益记录和清算状态。'
              : '账务与冻结记录待接入：代理仅可查看自己相关的扣点预览和冻结权益状态。'"
            type="info"
            show-icon
            :closable="false"
            class="small-alert"
          />

          <div class="placeholder-grid">
            <div class="placeholder-item">
              <div class="placeholder-title">扣点快照</div>
              <div class="placeholder-text">待接入</div>
            </div>

            <div class="placeholder-item">
              <div class="placeholder-title">返点记录</div>
              <div class="placeholder-text">{{ auth.isAdmin ? '待接入' : '仅管理员可查看清算明细' }}</div>
            </div>

            <div class="placeholder-item">
              <div class="placeholder-title">冻结权益记录</div>
              <div class="placeholder-text">待接入 AuthorizationFreezeRecord</div>
            </div>

            <div class="placeholder-item">
              <div class="placeholder-title">启用恢复记录</div>
              <div class="placeholder-text">待接入</div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="auth.isAdmin" label="审计日志" name="audit">
          <el-alert
            title="审计日志待接入：后续展示创建用户、状态修改、密码修改、授权调整、停用启用、删除清算、设备解绑等事件。"
            type="info"
            show-icon
            :closable="false"
            class="small-alert"
          />

          <el-timeline class="audit-placeholder">
            <el-timeline-item timestamp="待接入" type="primary">
              用户与授权审计日志
            </el-timeline-item>
            <el-timeline-item timestamp="待接入">
              设备与账务审计日志
            </el-timeline-item>
          </el-timeline>
        </el-tab-pane>

        <el-tab-pane v-if="auth.isAdmin" label="代理治理" name="creator">
          <el-alert
            title="创建代理治理待接入：后续补齐代理业务等级、风险状态、创建下级能力、项目授权状态和钱包状态。"
            type="info"
            show-icon
            :closable="false"
            class="small-alert"
          />

          <div class="governance-panel">
            <div class="governance-row">
              <span class="governance-label">创建来源</span>
              <el-tag
                size="small"
                effect="plain"
                :type="editDialog.row?.created_by_type === 'agent' ? 'warning' : 'danger'"
              >
                {{ editDialog.row?.created_by_display || '未知' }}
              </el-tag>
            </div>

            <div
              v-if="editDialog.row?.created_by_type === 'agent' && editDialog.row?.created_by_agent_id"
              class="governance-row"
            >
              <span class="governance-label">创建代理</span>
              <el-button
                type="primary"
                plain
                size="small"
                @click="openCreatorDetail(editDialog.row.created_by_agent_id)"
              >
                查看代理详情
              </el-button>
            </div>

            <div class="placeholder-grid">
              <div class="placeholder-item">
                <div class="placeholder-title">业务等级</div>
                <div class="placeholder-text">待接入</div>
              </div>
              <div class="placeholder-item">
                <div class="placeholder-title">风险状态</div>
                <div class="placeholder-text">待接入</div>
              </div>
              <div class="placeholder-item">
                <div class="placeholder-title">创建下级能力</div>
                <div class="placeholder-text">待接入</div>
              </div>
              <div class="placeholder-item">
                <div class="placeholder-title">钱包状态</div>
                <div class="placeholder-text">待接入</div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>

    <!-- 编辑项目授权 -->
    <el-dialog
      v-model="authEditDialog.visible"
      title="编辑项目授权"
      width="620px"
      destroy-on-close
    >
      <el-form :model="authEditDialog.form" label-width="120px">
        <el-form-item label="项目">
          <span class="readonly-val">{{ authProjectName(authEditDialog.row) }}</span>
        </el-form-item>

        <el-form-item label="项目等级">
          <el-select v-model="authEditDialog.form.user_level" style="width: 180px">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <el-form-item label="授权设备数量">
          <div class="device-limit-wrap">
            <el-input-number
              v-model="authEditDialog.form.authorized_devices"
              :min="auth.isAgent ? 1 : 0"
              :step="10"
              controls-position="right"
              style="width: 170px"
            />

            <span
              v-if="auth.isAdmin && Number(authEditDialog.form.authorized_devices || 0) === 0"
              class="hint-text"
            >
              无限设备
            </span>
          </div>
        </el-form-item>

        <el-form-item label="项目到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setAuthEditExpiry(7)">+7天</el-button>
              <el-button size="small" @click="setAuthEditExpiry(30)">+30天</el-button>
              <el-button size="small" @click="setAuthEditExpiry(90)">+90天</el-button>
              <el-button size="small" @click="setAuthEditExpiry(365)">+365天</el-button>
              <el-button
                v-if="auth.isAdmin"
                size="small"
                type="info"
                plain
                @click="authEditDialog.form.valid_until = null"
              >
                永久
              </el-button>
            </div>

            <el-date-picker
              v-model="authEditDialog.form.valid_until"
              type="datetime"
              :placeholder="auth.isAdmin ? '不填为永久有效' : '代理必须设置到期时间'"
              style="width: 100%"
            />
          </div>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="authEditDialog.form.status" style="width: 180px">
            <el-option label="有效" value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>

        <el-alert
          title="当前编辑会更新用户在该项目下的授权等级、设备数量、项目到期时间和状态。"
          type="info"
          show-icon
          :closable="false"
          class="small-alert"
        />
      </el-form>

      <template #footer>
        <el-button @click="authEditDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="authEditDialog.loading"
          @click="saveAuthEdit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/UserList.vue
 * 名称: 用户管理页面
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 日期/时间: 2026-05-08
 * 版本: V1.4.0
 *
 * 功能说明:
 *   - 用户超级列表。
 *   - 用户主体与项目授权解耦。
 *   - “授权数”统一命名为“项目授权数”。
 *   - 新建用户、编辑用户、快捷授权、授权编辑均支持“项目到期时间”。
 *
 * 当前边界:
 *   - User 是账号主体。
 *   - Authorization 是用户在某项目下的授权记录。
 *   - 项目等级、授权设备数量、项目到期时间全部归属 Authorization。
 */

import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { userApi } from '@/api/user'
import { agentApi } from '@/api/agent'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { useAuthStore } from '@/stores/auth'

import StatusBadge from '@/components/common/StatusBadge.vue'
import LevelTag from '@/components/common/LevelTag.vue'
import {
  formatDate,
  formatDatetime,
  expiryTagType,
  expiryLabel,
} from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()

const tableRef = ref(null)
const createFormRef = ref(null)

const loading = ref(false)
const batchLoading = ref(false)

const users = ref([])
const allProjects = ref([])
const allAgents = ref([])
const selectedIds = ref([])

const filter = reactive({
  status: null,
  level: null,
  project_id: null,
  creator_agent_id: null,
  creator_agent_tier_level: null,
  creator_agent_can_create_sub_agents: null,
  creator_agent_risk_status: null,
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const createDialog = reactive({
  visible: false,
  loading: false,
  form: buildCreateForm(),
})

const editDialog = reactive({
  visible: false,
  row: null,
  activeTab: 'base',
  loading: false,
  passwordLoading: false,
  grantLoading: false,
  generatedPassword: '',
  form: {
    status: 'active',
  },
  password: {
    new_password: '',
    confirm_password: '',
  },
  auths: [],
  grantForm: buildGrantForm(),
})

const authEditDialog = reactive({
  visible: false,
  loading: false,
  row: null,
  form: {
    user_level: 'normal',
    authorized_devices: 20,
    valid_until: null,
    status: 'active',
  },
})

const createRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '用户名长度应为 3-64 字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

const unauthorizedProjects = computed(() => {
  const authedIds = new Set(
    (editDialog.auths || [])
      .map(item => Number(item.game_project_id || item.project_id))
      .filter(Boolean)
  )

  return allProjects.value.filter(p => !authedIds.has(Number(p.id)))
})

function buildCreateForm() {
  return {
    username: '',
    password: '',
    project_id: null,
    auth_user_level: 'normal',
    authorized_devices: 20,
    auth_valid_until: null,
  }
}

function buildGrantForm(projectId = null) {
  return {
    project_id: projectId,
    user_level: 'normal',
    authorized_devices: 20,
    valid_until: null,
  }
}

function projectName(project) {
  return (
    project?.display_name ||
    project?.project_display_name ||
    project?.project_name ||
    project?.game_project_name ||
    project?.code_name ||
    project?.project_code ||
    '未命名项目'
  )
}

function authProjectName(authItem) {
  return (
    authItem?.game_project_name ||
    authItem?.project_display_name ||
    authItem?.project_name ||
    authItem?.display_name ||
    authItem?.game_name ||
    '未命名项目'
  )
}

function normalizeProject(project) {
  return {
    ...project,
    display_name: projectName(project),
  }
}

function normalizeAuthItem(item) {
  return {
    ...item,
    game_project_name: authProjectName(item),
    activated_devices: item.activated_devices ?? 0,
    authorized_devices: item.authorized_devices ?? 0,
  }
}

function normalizeUserRow(row) {
  const authorizations = Array.isArray(row.authorizations)
    ? row.authorizations.map(normalizeAuthItem)
    : []

  return {
    ...row,
    authorizations,
    authorization_count: row.authorization_count ?? authorizations.length,
  }
}

function displayDeviceLimit(value) {
  return Number(value || 0) === 0 ? '无限制' : `${value} 台`
}

function displayInactiveDevices(item) {
  if (item.inactive_devices !== undefined && item.inactive_devices !== null) {
    return item.inactive_devices
  }

  const authorized = Number(item.authorized_devices || 0)
  const activated = Number(item.activated_devices || 0)

  if (authorized === 0) return '不限'
  return Math.max(authorized - activated, 0)
}

function authStatusText(item) {
  if (!item) return '未知'
  if (item.is_expired || item.status === 'expired') return '已过期'
  if (item.status === 'active') return '有效'
  if (item.status === 'suspended') return '已停用'
  return item.status || '未知'
}

function authStatusType(item) {
  if (!item) return 'info'
  if (item.is_expired || item.status === 'expired') return 'warning'
  if (item.status === 'active') return 'success'
  if (item.status === 'suspended') return 'info'
  return 'info'
}

function userStatusText(status) {
  const map = {
    active: '正常',
    suspended: '已停用',
    expired: '已过期',
  }

  return map[status] || status || '未知'
}

function isoOrNull(value) {
  if (!value) return null
  return new Date(value).toISOString()
}

function setDateAfterDays(target, field, days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  target[field] = d
}

function setCreateAuthExpiry(days) {
  setDateAfterDays(createDialog.form, 'auth_valid_until', days)
}

function setGrantAuthExpiry(days) {
  setDateAfterDays(editDialog.grantForm, 'valid_until', days)
}

function setAuthEditExpiry(days) {
  setDateAfterDays(authEditDialog.form, 'valid_until', days)
}

async function loadLookups() {
  const projectReq = projectApi.list({
    page: 1,
    page_size: 100,
    is_active: true,
  })

  const agentReq = auth.isAdmin
    ? agentApi.list({ page: 1, page_size: 500 })
    : Promise.resolve({ data: { agents: [] } })

  const [projectRes, agentRes] = await Promise.all([projectReq, agentReq])

  allProjects.value = (projectRes.data.projects || []).map(normalizeProject)
  allAgents.value = agentRes.data.agents || []
}

async function loadUsers() {
  loading.value = true

  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }

    if (filter.status) params.status = filter.status
    if (filter.level) params.level = filter.level
    if (filter.project_id) params.project_id = filter.project_id
    if (filter.creator_agent_id) params.creator_agent_id = filter.creator_agent_id
    if (filter.creator_agent_tier_level) {
      params.creator_agent_tier_level = filter.creator_agent_tier_level
    }
    if (filter.creator_agent_can_create_sub_agents !== null) {
      params.creator_agent_can_create_sub_agents = filter.creator_agent_can_create_sub_agents
    }
    if (filter.creator_agent_risk_status) {
      params.creator_agent_risk_status = filter.creator_agent_risk_status
    }

    const res = await userApi.list(params)

    users.value = (res.data.users || []).map(normalizeUserRow)
    pagination.total = res.data.total || 0
  } finally {
    loading.value = false
  }
}

function searchUsers() {
  pagination.page = 1
  loadUsers()
}

function resetFilter() {
  filter.status = null
  filter.level = null
  filter.project_id = null
  filter.creator_agent_id = null
  filter.creator_agent_tier_level = null
  filter.creator_agent_can_create_sub_agents = null
  filter.creator_agent_risk_status = null
  pagination.page = 1
  loadUsers()
}

function onSelectionChange(rows) {
  selectedIds.value = rows.map(row => row.id)
}

function clearSelection() {
  selectedIds.value = []
  tableRef.value?.clearSelection?.()
}

async function batchDelete() {
  if (!selectedIds.value.length) return
  if (!auth.isAdmin) {
    ElMessage.warning('只有管理员可以批量删除用户')
    clearSelection()
    return
  }

  await ElMessageBox.confirm(
    `确认删除 ${selectedIds.value.length} 个用户？管理员删除会触发符合条件的返点清算；授权、设备、流水记录会保留用于审计。`,
    '批量删除确认',
    {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )

  batchLoading.value = true

  try {
    await Promise.all(selectedIds.value.map(id => userApi.delete(id)))
    ElMessage.success('批量删除完成')
    clearSelection()
    await loadUsers()
  } finally {
    batchLoading.value = false
  }
}

function openCreatorDetail(agentId) {
  router.push(`/agents/${agentId}`)
}

function openCreateDialog() {
  createDialog.form = buildCreateForm()
  createDialog.visible = true
}

async function submitCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  if (createDialog.form.project_id && auth.isAgent && !createDialog.form.auth_valid_until) {
    ElMessage.warning('代理创建项目授权时必须设置项目到期时间')
    return
  }

  createDialog.loading = true

  try {
    const res = await userApi.create({
      username: createDialog.form.username,
      password: createDialog.form.password,
    })

    const userId = res.data?.id

    if (userId && createDialog.form.project_id) {
      await userApi.grantAuth(userId, {
        game_project_id: createDialog.form.project_id,
        user_level: createDialog.form.auth_user_level,
        authorized_devices: createDialog.form.authorized_devices,
        valid_until: isoOrNull(createDialog.form.auth_valid_until),
      })
    }

    ElMessage.success('用户创建成功')
    createDialog.visible = false
    await loadUsers()
  } finally {
    createDialog.loading = false
  }
}

async function openEditDialog(row) {
  editDialog.visible = true
  editDialog.row = normalizeUserRow(row)
  editDialog.activeTab = 'base'
  editDialog.form = {
    status: row.status,
  }
  editDialog.password = {
    new_password: '',
    confirm_password: '',
  }
  editDialog.generatedPassword = ''
  editDialog.grantForm = buildGrantForm()

  await loadEditAuths()
}

async function loadEditAuths() {
  if (!editDialog.row?.id) return

  const res = await userApi.detail(editDialog.row.id)
  const detail = res.data || {}

  const auths = Array.isArray(detail.authorizations)
    ? detail.authorizations
    : Array.isArray(detail.user?.authorizations)
      ? detail.user.authorizations
      : []

  editDialog.auths = auths.map(normalizeAuthItem)
}

async function submitEdit() {
  if (!editDialog.row?.id) return

  editDialog.loading = true

  try {
    await userApi.update(editDialog.row.id, {
      status: editDialog.form.status,
    })

    ElMessage.success('基础信息已保存')
    editDialog.row.status = editDialog.form.status
    await loadUsers()
  } finally {
    editDialog.loading = false
  }
}

async function submitPassword(autoGenerate) {
  if (!editDialog.row?.id) return

  if (!autoGenerate) {
    if (!editDialog.password.new_password) {
      ElMessage.warning('请输入新密码')
      return
    }

    if (editDialog.password.new_password !== editDialog.password.confirm_password) {
      ElMessage.warning('两次输入的密码不一致')
      return
    }
  }

  editDialog.passwordLoading = true
  editDialog.generatedPassword = ''

  try {
    const payload = autoGenerate
      ? { auto_generate: true }
      : {
          auto_generate: false,
          new_password: editDialog.password.new_password,
        }

    const res = await userApi.updatePassword(editDialog.row.id, payload)

    editDialog.generatedPassword = res.data?.generated_password || ''
    editDialog.password.new_password = ''
    editDialog.password.confirm_password = ''

    ElMessage.success(editDialog.generatedPassword ? '密码已重置，请复制生成密码' : '密码已修改')
  } finally {
    editDialog.passwordLoading = false
  }
}

async function copyPassword() {
  if (!editDialog.generatedPassword) return

  await navigator.clipboard.writeText(editDialog.generatedPassword)
  ElMessage.success('已复制')
}

function quickGrantAuth(project) {
  editDialog.grantForm = buildGrantForm(project.id)
  editDialog.activeTab = 'auths'
}

async function quickGrantDo() {
  if (!editDialog.row?.id) return

  if (!editDialog.grantForm.project_id) {
    ElMessage.warning('请选择授权项目')
    return
  }

  if (auth.isAgent && !editDialog.grantForm.valid_until) {
    ElMessage.warning('代理授权项目时必须设置项目到期时间')
    return
  }

  editDialog.grantLoading = true

  try {
    await userApi.grantAuth(editDialog.row.id, {
      game_project_id: editDialog.grantForm.project_id,
      user_level: editDialog.grantForm.user_level,
      authorized_devices: editDialog.grantForm.authorized_devices,
      valid_until: isoOrNull(editDialog.grantForm.valid_until),
    })

    ElMessage.success('项目授权成功')
    editDialog.grantForm = buildGrantForm()

    await Promise.all([
      loadEditAuths(),
      loadUsers(),
    ])
  } finally {
    editDialog.grantLoading = false
  }
}

function openAuthEditDialog(row) {
  authEditDialog.row = row
  authEditDialog.form = {
    user_level: row.user_level || 'normal',
    authorized_devices: row.authorized_devices ?? 20,
    valid_until: row.valid_until ? new Date(row.valid_until) : null,
    status: row.status || 'active',
  }
  authEditDialog.visible = true
}

async function saveAuthEdit() {
  if (!editDialog.row?.id || !authEditDialog.row?.id) return

  if (auth.isAgent && !authEditDialog.form.valid_until) {
    ElMessage.warning('代理修改项目授权时必须设置项目到期时间')
    return
  }

  authEditDialog.loading = true

  try {
    await userApi.updateAuth(editDialog.row.id, authEditDialog.row.id, {
      user_level: authEditDialog.form.user_level,
      authorized_devices: authEditDialog.form.authorized_devices,
      valid_until: isoOrNull(authEditDialog.form.valid_until),
      status: authEditDialog.form.status,
    })

    ElMessage.success('项目授权已更新')
    authEditDialog.visible = false

    await Promise.all([
      loadEditAuths(),
      loadUsers(),
    ])
  } finally {
    authEditDialog.loading = false
  }
}

async function revokeUserAuth(row) {
  if (!editDialog.row?.id || !row?.id) return

  await userApi.suspendAuth(editDialog.row.id, row.id)
  ElMessage.success('项目授权已停用，剩余权益已冻结')

  await Promise.all([
    loadEditAuths(),
    loadUsers(),
  ])
}

async function toggleStatus(row) {
  const nextStatus = row.status === 'active' ? 'suspended' : 'active'

  await userApi.update(row.id, {
    status: nextStatus,
  })

  ElMessage.success('操作成功')
  await loadUsers()
}

async function deleteUser(row) {
  await userApi.delete(row.id)
  ElMessage.success('用户已删除')
  await loadUsers()
}

onMounted(async () => {
  await loadLookups()
  await loadUsers()
})
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
  line-height: 1.6;
}

.filter-card,
.table-card {
  border-radius: 10px;
}

.filter-hint {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 10px 12px;
}

.batch-info {
  color: #9a3412;
  font-size: 13px;
  font-weight: 600;
}

.user-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username-link {
  padding: 0;
  font-weight: 700;
  color: #2563eb;
}

.device-entry-link {
  padding: 0;
  font-size: 12px;
}

.creator-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.creator-link {
  padding: 0;
}

.sub-text,
.hint-text,
.drawer-sub {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 4px;
}

.inline-sub-text {
  margin-left: 8px;
}

.no-auth {
  color: #94a3b8;
  font-size: 12px;
}

.auth-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.auth-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 10px;
  background: #f8fafc;
}

.auth-title-row,
.auth-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.auth-project-name {
  font-weight: 700;
  color: #1e293b;
}

.auth-meta-row,
.auth-expiry-row {
  margin-top: 5px;
  font-size: 12px;
  color: #64748b;
}

.expiry-permanent {
  color: #10b981;
  font-weight: 600;
}

.auth-count {
  font-weight: 700;
  color: #2563eb;
}

.auth-count-total {
  color: #94a3b8;
  font-size: 12px;
  margin-left: 2px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.small-alert {
  margin: 10px 0;
}

.drawer-header-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drawer-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
}

.drawer-name {
  font-size: 18px;
  font-weight: 800;
  color: #1e293b;
}

.dot {
  margin: 0 4px;
  color: #cbd5e1;
}

.readonly-val {
  color: #475569;
  font-weight: 600;
}

.generated-password {
  font-family: "Cascadia Code", monospace;
  color: #047857;
}

.auth-section-title {
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 10px;
}

.small-refresh-btn {
  margin-left: 8px;
}

.auth-table {
  margin-bottom: 16px;
}

.unauth-block {
  margin-top: 12px;
  padding: 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 6px;
}

.project-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.project-tag {
  margin: 4px;
}

.tag-action {
  margin-left: 4px;
}

.device-limit-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quick-btns {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.expiry-picker-wrap {
  width: 100%;
}

.governance-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.governance-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 32px;
}

.governance-label {
  width: 88px;
  color: #64748b;
  font-size: 13px;
}

.placeholder-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.placeholder-item {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #f8fafc;
}

.placeholder-title {
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}

.placeholder-text {
  margin-top: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.audit-placeholder {
  margin-top: 16px;
}

@media (max-width: 900px) {
  .page-header {
    flex-direction: column;
    gap: 12px;
  }

  .placeholder-grid {
    grid-template-columns: 1fr;
  }
}
</style>
