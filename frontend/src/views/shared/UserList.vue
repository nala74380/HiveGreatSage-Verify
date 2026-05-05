<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>用户管理</h2>
        <p class="page-desc">
          用户是账号主体；等级、设备数、到期时间按项目授权分别管理。
        </p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建用户</el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width:110px">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>

        <el-form-item label="授权等级">
          <el-select v-model="filter.level" clearable placeholder="全部" style="width:120px">
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
            style="width:190px"
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

        <el-form-item v-if="auth.isAdmin" label="创建代理">
          <el-select
            v-model="filter.creator_agent_id"
            clearable
            filterable
            placeholder="全部代理"
            style="width:180px"
          >
            <el-option
              v-for="ag in allAgents"
              :key="ag.id"
              :label="`${ag.username} (ID:${ag.id})`"
              :value="ag.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="searchUsers">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>

      <div v-if="filter.project_id" class="filter-hint">
        当前已按项目筛选，列表中的“项目授权明细”只显示所选项目。
      </div>
    </el-card>

    <!-- 批量操作 -->
    <div v-if="selectedIds.length > 0" class="batch-toolbar">
      <span class="batch-info">已选 {{ selectedIds.length }} 条</span>

      <el-button
        type="danger"
        size="small"
        :loading="batchLoading"
        @click="batchDelete"
      >
        批量删除
      </el-button>

      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <!-- 用户列表 -->
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

        <el-table-column label="用户名" min-width="140">
          <template #default="{ row }">
            <div class="user-main">
              <el-button
                text
                class="username-link"
                @click="router.push({ path: '/devices', query: { user_id: row.id, username: row.username } })"
              >
                {{ row.username }}
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
                  {{ row.created_by_display }}
                </el-tag>
              </el-button>

              <el-tag
                v-else
                size="small"
                effect="plain"
                :type="row.created_by_type === 'admin' ? 'danger' : 'info'"
              >
                {{ row.created_by_display }}
              </el-tag>

              <div class="sub-text">{{ formatDatetime(row.created_at) }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="项目授权明细" min-width="590">
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
                  <span class="auth-project-name">{{ authItem.game_project_name }}</span>
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
                  <span>已激活：{{ authItem.activated_devices }}</span>
                  <span>未激活：{{ displayInactiveDevices(authItem) }}</span>
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

        <el-table-column label="授权数" width="85" align="center">
          <template #default="{ row }">
            <el-tooltip
              :content="`总授权记录 ${row.authorization_count} 条；当前显示 ${row.authorizations?.length || 0} 条`"
              placement="top"
            >
              <span class="auth-count">
                {{ row.authorizations?.length || 0 }}
                <span class="auth-count-total">/{{ row.authorization_count }}</span>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="230" fixed="right">
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
            <el-popconfirm
              v-if="auth.isAdmin"
              title="确认删除该用户？删除后用户列表将不再显示，但授权、设备、流水记录会保留用于审计。"
              confirm-button-text="确认删除"
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
    <el-dialog v-model="createDialog.visible" title="新建用户" width="720px" destroy-on-close>
      <el-form ref="createFormRef" :model="createDialog.form" :rules="createRules" label-width="110px">
        <el-divider content-position="left">账号主体</el-divider>

        <el-form-item label="用户名" prop="username">
          <el-input v-model="createDialog.form.username" placeholder="3-64 字符" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="createDialog.form.password" type="password" show-password placeholder="至少 6 字符" />
        </el-form-item>

        <el-alert
          v-if="auth.isAdmin"
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
            placeholder="可选；选择后将创建用户并授予该项目"
            style="width:100%"
            filterable
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="`${p.display_name}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <template v-if="createDialog.form.project_id">
          <el-form-item label="项目内等级">
            <el-select v-model="createDialog.form.auth_user_level" style="width:180px">
              <el-option label="试用" value="trial" />
              <el-option label="普通" value="normal" />
              <el-option label="VIP" value="vip" />
              <el-option label="SVIP" value="svip" />
              <el-option v-if="auth.isAdmin" label="测试" value="tester" />
            </el-select>
          </el-form-item>

          <el-form-item label="授权设备数">
            <div class="device-limit-wrap">
              <el-input-number
                v-model="createDialog.form.authorized_devices"
                :min="auth.isAgent ? 1 : 0"
                :step="10"
                controls-position="right"
                style="width:170px"
              />
              <span v-if="auth.isAdmin && createDialog.form.authorized_devices === 0" class="hint-text">无限制</span>
            </div>

            <div class="quick-btns" style="margin-top:6px">
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
                style="width:100%"
              />
            </div>

            <div v-if="auth.isAgent" class="hint-text">
              代理授权项目会按项目定价、项目内等级、授权设备数、授权周期扣点。
            </div>
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-drawer v-model="editDialog.visible" title="编辑用户" size="700px" destroy-on-close>
      <template #header>
        <div class="drawer-header-row">
          <div class="drawer-avatar">{{ (editDialog.row?.username || '?').charAt(0).toUpperCase() }}</div>
          <div class="drawer-meta">
            <div class="drawer-name">{{ editDialog.row?.username }}</div>
            <div class="drawer-sub">
              ID: {{ editDialog.row?.id }}
              <span class="dot">·</span>
              {{ editDialog.row?.created_by_display }}
              <span class="dot">·</span>
              {{ editDialog.row?.status === 'active' ? '正常' : editDialog.row?.status === 'suspended' ? '已停用' : '已过期' }}
            </div>
          </div>
        </div>
      </template>

      <el-tabs v-model="editDialog.activeTab">
        <el-tab-pane label="基础信息" name="base">
          <el-form ref="editFormRef" :model="editDialog.form" label-width="100px">
            <el-form-item label="用户名">
              <span class="readonly-val">{{ editDialog.row?.username }}</span>
            </el-form-item>
            <el-form-item label="创建信息">
              <el-tag size="small" effect="plain" :type="editDialog.row?.created_by_type === 'agent' ? 'warning' : 'danger'">
                {{ editDialog.row?.created_by_display }}
              </el-tag>
              <span class="sub-text" style="margin-left:8px">{{ formatDatetime(editDialog.row?.created_at) }}</span>
            </el-form-item>
            <el-form-item label="账号状态">
              <el-select v-model="editDialog.form.status" style="width:160px">
                <el-option label="正常" value="active" />
                <el-option label="已停用" value="suspended" />
                <el-option label="已过期" value="expired" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="editDialog.loading" @click="submitEdit">保存</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="密码" name="password">
          <el-form label-width="100px">
            <el-form-item label="新密码">
              <el-input v-model="editDialog.password.new_password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input v-model="editDialog.password.confirm_password" type="password" show-password placeholder="再次输入" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="editDialog.passwordLoading" @click="submitPassword(false)">修改密码</el-button>
              <el-button type="primary" :loading="editDialog.passwordLoading" @click="submitPassword(false)">修改密码</el-button>
              <el-button v-if="auth.isAdmin" type="warning" plain :loading="editDialog.passwordLoading" @click="submitPassword(true)">查询密码（生成新密码并复制）</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="editDialog.generatedPassword" type="success" show-icon :closable="false" class="small-alert">
            <template #title>
              新密码：<strong class="generated-password">{{ editDialog.generatedPassword }}</strong>
              <el-button text size="small" @click="copyPassword">复制</el-button>
            </template>
          </el-alert>
        </el-tab-pane>

        <el-tab-pane label="项目授权" name="auths">
          <div class="auth-section-title">
            已授权项目
            <el-button size="small" :icon="Refresh" @click="loadEditAuths" style="margin-left:8px" />
          </div>
          <el-table :data="editDialog.auths" size="small" empty-text="暂无授权" stripe style="margin-bottom:16px">
            <el-table-column label="项目" min-width="120" prop="game_project_name" />
            <el-table-column label="等级" width="75">
              <template #default="{ row }"><LevelTag :level="row.user_level" /></template>
            </el-table-column>
            <el-table-column label="设备" width="80">
              <template #default="{ row }">{{ displayDeviceLimit(row.authorized_devices) }}</template>
            </el-table-column>
            <el-table-column label="到期" width="130">
              <template #default="{ row }">
                <span v-if="!row.valid_until" class="expiry-permanent">永久</span>
                <span v-else>{{ formatDate(row.valid_until) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="70">
              <template #default="{ row }">
                <el-tag :type="authStatusType(row)" size="small" effect="light">{{ authStatusText(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ row }">
                <el-button text size="small" @click="openAuthEditDialog(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="unauthorizedProjects.length" class="unauth-block">
            <div class="section-title">未授权项目 — 可授权</div>
            <div class="project-tags">
              <el-tag v-for="p in unauthorizedProjects" :key="p.id" size="small" effect="plain" type="info" style="margin:4px">
                {{ p.display_name }}
                <el-button text size="small" style="margin-left:4px" @click="quickGrantAuth(p)">+ 授权</el-button>
              </el-tag>
            </div>
          </div>
          <span v-else class="no-auth">所有项目已授权</span>

          <el-divider />
          <el-form :inline="true" :model="editDialog.grantForm" label-width="0" @submit.prevent>
            <el-select v-model="editDialog.grantForm.project_id" filterable placeholder="选择项目" style="width:180px">
              <el-option v-for="p in allProjects" :key="p.id" :label="p.display_name" :value="p.id" />
            </el-select>
            <el-select v-model="editDialog.grantForm.user_level" style="width:110px;margin-left:8px">
              <el-option label="试用" value="trial" />
              <el-option label="普通" value="normal" />
              <el-option label="VIP" value="vip" />
              <el-option label="SVIP" value="svip" />
              <el-option v-if="auth.isAdmin" label="测试" value="tester" />
            </el-select>
            <el-input-number v-model="editDialog.grantForm.authorized_devices" :min="1" style="width:100px;margin-left:8px" placeholder="设备数" />
            <el-button type="primary" size="small" :loading="editDialog.grantLoading" @click="quickGrantDo" style="margin-left:8px">授权</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>

    <!-- 项目授权弹窗 -->
    <el-dialog
      v-model="projectAuthDialog.visible"
      :title="`项目授权 — ${projectAuthDialog.username}`"
      width="760px"
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
          stripe
        >
          <el-table-column label="项目名称" min-width="140" prop="game_project_name" />
          <el-table-column label="等级" width="85">
            <template #default="{ row }">
              <LevelTag :level="row.user_level" />
            </template>
          </el-table-column>
          <el-table-column label="设备" width="160">
            <template #default="{ row }">
              授权 {{ displayDeviceLimit(row.authorized_devices) }} /
              激活 {{ row.activated_devices }}
            </template>
          </el-table-column>
          <el-table-column label="到期" width="150">
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
              <el-tag :type="authStatusType(row)" size="small" effect="light">
                {{ authStatusText(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column width="110" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="auth.isAdmin"
                text
                size="small"
                @click="openAuthEditDialog(row)"
              >
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
      </div>

      <el-divider content-position="left">授予新项目</el-divider>

      <el-form ref="projectAuthFormRef" :model="projectAuthDialog.form" :rules="projectAuthRules" label-width="110px">
        <el-form-item label="选择项目" prop="game_project_id">
          <el-select
            v-model="projectAuthDialog.form.game_project_id"
            filterable
            style="width:100%"
            :loading="projectAuthDialog.projectsLoading"
          >
            <el-option
              v-for="p in grantableProjects"
              :key="p.id"
              :label="`${p.display_name}${p.project_type === 'game' ? ' 🎮' : ' 🔑'}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="项目内等级" prop="user_level">
          <el-select v-model="projectAuthDialog.form.user_level" style="width:180px">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option v-if="auth.isAdmin" label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <el-form-item label="授权设备数" prop="authorized_devices">
          <div class="device-limit-wrap">
            <el-input-number
              v-model="projectAuthDialog.form.authorized_devices"
              :min="auth.isAgent ? 1 : 0"
              :step="10"
              controls-position="right"
              style="width:170px"
            />
            <span v-if="auth.isAdmin && projectAuthDialog.form.authorized_devices === 0" class="hint-text">无限制</span>
          </div>

          <div class="quick-btns" style="margin-top:6px">
            <el-button size="small" @click="projectAuthDialog.form.authorized_devices = 20">20</el-button>
            <el-button size="small" @click="projectAuthDialog.form.authorized_devices = 50">50</el-button>
            <el-button size="small" @click="projectAuthDialog.form.authorized_devices = 100">100</el-button>
            <el-button size="small" @click="projectAuthDialog.form.authorized_devices = 500">500</el-button>
            <el-button
              v-if="auth.isAdmin"
              size="small"
              type="info"
              plain
              @click="projectAuthDialog.form.authorized_devices = 0"
            >
              无限
            </el-button>
          </div>
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
          title="代理授权项目会按项目定价、项目内等级、授权设备数、授权周期扣除点数。"
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

    <!-- 管理员编辑项目授权 -->
    <el-dialog
      v-model="authEditDialog.visible"
      title="编辑项目授权"
      width="620px"
      destroy-on-close
    >
      <el-form :model="authEditDialog.form" label-width="110px">
        <el-form-item label="项目">
          <span class="readonly-val">{{ authEditDialog.row?.game_project_name }}</span>
        </el-form-item>

        <el-form-item label="项目内等级">
          <el-select v-model="authEditDialog.form.user_level" style="width:180px">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
            <el-option label="测试" value="tester" />
          </el-select>
        </el-form-item>

        <el-form-item label="授权设备数">
          <div class="device-limit-wrap">
            <el-input-number
              v-model="authEditDialog.form.authorized_devices"
              :min="0"
              :step="10"
              controls-position="right"
              style="width:170px"
            />
            <span v-if="authEditDialog.form.authorized_devices === 0" class="hint-text">无限制</span>
          </div>
        </el-form-item>

        <el-form-item label="到期时间">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setAuthEditExpiry(7)">+7天</el-button>
              <el-button size="small" @click="setAuthEditExpiry(30)">+30天</el-button>
              <el-button size="small" @click="setAuthEditExpiry(90)">+90天</el-button>
              <el-button size="small" type="info" plain @click="authEditDialog.form.valid_until = null">永久</el-button>
            </div>

            <el-date-picker
              v-model="authEditDialog.form.valid_until"
              type="datetime"
              placeholder="不填为永久"
              style="width:100%"
            />
          </div>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="authEditDialog.form.status" style="width:180px">
            <el-option label="有效" value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>

        <el-alert
          title="当前管理员修改授权不触发扣点；代理侧修改授权的补扣/退款规则后续单独治理。"
          type="warning"
          show-icon
          :closable="false"
          class="small-alert"
        />
      </el-form>

      <template #footer>
        <el-button @click="authEditDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="authEditDialog.loading" @click="submitAuthEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 创建者详情 -->
    <el-dialog
      v-model="creatorDialog.visible"
      title="创建者详情"
      width="900px"
      destroy-on-close
    >
      <div v-loading="creatorDialog.loading">
        <template v-if="creatorDialog.agent">
          <el-card shadow="never" class="creator-detail-card">
            <div class="creator-profile">
              <div class="creator-avatar">{{ creatorDialog.agent.username?.charAt(0)?.toUpperCase() }}</div>
              <div class="creator-meta">
                <div class="creator-name">
                  {{ creatorDialog.agent.username }}
                  <el-tag type="warning" size="small" effect="light">Lv.{{ creatorDialog.agent.level }}</el-tag>
                  <el-tag
                    :type="creatorDialog.agent.status === 'active' ? 'success' : 'danger'"
                    size="small"
                    effect="light"
                  >
                    {{ creatorDialog.agent.status === 'active' ? '正常' : '停用' }}
                  </el-tag>
                </div>

                <div class="creator-desc">
                  ID={{ creatorDialog.agent.id }} ·
                  用户总数={{ creatorDialog.agent.users_total ?? 0 }} ·
                  已创建用户={{ creatorDialog.agent.users_total }}
                </div>

                <div class="creator-desc">
                  可用点数={{ fmtPoint(creatorDialog.agent.balance?.available_total) }} ·
                  充值={{ fmtPoint(creatorDialog.agent.balance?.charged_points) }} ·
                  授信={{ fmtPoint(creatorDialog.agent.balance?.credit_points) }} ·
                  冻结={{ fmtPoint(creatorDialog.agent.balance?.frozen_credit) }}
                </div>
              </div>
            </div>
          </el-card>

          <el-divider content-position="left">授权项目</el-divider>

          <div class="project-tags">
            <el-tag
              v-for="p in creatorDialog.agent.authorized_projects || []"
              :key="p.project_id"
              effect="plain"
              type="primary"
            >
              {{ p.display_name }}
            </el-tag>
            <span v-if="!creatorDialog.agent.authorized_projects?.length" class="no-auth">暂无授权项目</span>
          </div>

          <el-divider content-position="left">该代理创建的用户</el-divider>

          <el-table :data="creatorDialog.users" size="small" stripe max-height="360">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户名" min-width="130" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <StatusBadge :status="row.status" type="user" />
              </template>
            </el-table-column>
            <el-table-column label="项目授权" min-width="420">
              <template #default="{ row }">
                <div v-if="row.authorizations?.length" class="mini-auth-list">
                  <span
                    v-for="item in row.authorizations"
                    :key="item.id"
                    class="mini-auth-item"
                  >
                    {{ item.game_project_name }}
                    <LevelTag :level="item.user_level" />
                    {{ displayDeviceLimit(item.authorized_devices) }}台
                  </span>
                </div>
                <span v-else class="no-auth">未授权</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/UserList.vue
 * 名称: 用户管理页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.3.2
 * 功能说明:
 *   用户管理页面。
 *
 * 本版修改:
 *   - 代理端编辑用户弹窗不显示管理员说明型提示。
 *   - 管理员端仍保留账号主体说明与密码安全说明。
 */

import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { userApi } from '@/api/user'
import { agentApi } from '@/api/agent'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { useAuthStore } from '@/stores/auth'

import StatusBadge from '@/components/common/StatusBadge.vue'
import LevelTag from '@/components/common/LevelTag.vue'
import { formatDatetime, formatDate, expiryTagType, expiryLabel } from '@/utils/format'

const auth = useAuthStore()
const router = useRouter()

const allProjects = ref([])
const users = ref([])
const loading = ref(false)
const selectedIds = ref([])
const batchLoading = ref(false)

const filter = reactive({
  status: null,
  level: null,
  project_id: null,
  creator_agent_id: null,
})

const allAgents = ref([])
const loadAllAgents = async () => {
  try {
    const res = await agentApi.list({ page_size: 500, status: 'active' })
    allAgents.value = res.data.agents || []
  } catch { /* 静默 */ }
}

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

onMounted(async () => {
  const tasks = [loadUsers(), loadProjects()]
  if (auth.isAdmin) {
    tasks.push(loadAllAgents())
  }
  await Promise.all(tasks)
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
  } catch (err) {
    console.error('[UserList] 加载项目失败:', err)
    allProjects.value = []
  }
}

const loadUsers = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      status: filter.status || undefined,
      level: filter.level || undefined,
      project_id: filter.project_id || undefined,
      creator_agent_id: auth.isAdmin ? (filter.creator_agent_id || undefined) : undefined,
    }

    const res = await userApi.list(params)
    users.value = res.data.users || []
    pagination.total = res.data.total || 0
  } finally {
    loading.value = false
  }
}

const searchUsers = () => {
  pagination.page = 1
  loadUsers()
}

const resetFilter = () => {
  filter.status = null
  filter.level = null
  filter.project_id = null
  filter.creator_agent_id = null
  pagination.page = 1
  loadUsers()
}

const onSelectionChange = (rows) => {
  selectedIds.value = rows.map(r => r.id)
}

const batchDelete = async () => {
  const ids = [...selectedIds.value]

  if (!ids.length) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认批量删除已选中的 ${ids.length} 个用户？删除后用户列表将不再显示，但授权、设备、流水记录会保留用于审计。`,
      '批量删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }

  batchLoading.value = true

  try {
    const results = await Promise.allSettled(
      ids.map(id => userApi.delete(id)),
    )

    const success = results.filter(r => r.status === 'fulfilled').length
    const failed = results.length - success

    if (failed === 0) {
      ElMessage.success(`已删除 ${success} 个用户`)
    } else {
      ElMessage.warning(`成功 ${success} 个，失败 ${failed} 个；失败项请检查是否有权限删除`)
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
  try {
    await ElMessageBox.confirm(
      `确认删除用户「${row.username}」？删除后用户列表将不再显示，但授权、设备、流水记录会保留用于审计。`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }

  await userApi.delete(row.id)
  ElMessage.success('已删除用户')
  await loadUsers()
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

const authStatusText = (row) => {
  if (row.is_expired) return '已过期'
  if (row.status === 'active') return '有效'
  if (row.status === 'suspended') return '已停用'
  if (row.status === 'expired') return '已过期'
  return row.status || '未知'
}

const authStatusType = (row) => {
  if (row.is_expired || row.status === 'expired') return 'danger'
  if (row.status === 'active') return 'success'
  if (row.status === 'suspended') return 'info'
  return 'info'
}

const fmtPoint = (val) => Number(val || 0).toFixed(2)

/* ── 新建用户 ─────────────────────────────────────────────── */

const createFormRef = ref(null)

const createDialog = reactive({
  visible: false,
  loading: false,
  form: {
    username: '',
    password: '',
    project_id: null,
    auth_user_level: 'normal',
    authorized_devices: 20,
    auth_valid_until: null,
  },
})

const createRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const openCreateDialog = () => {
  createDialog.form = {
    username: '',
    password: '',
    project_id: null,
    auth_user_level: 'normal',
    authorized_devices: 20,
    auth_valid_until: auth.isAdmin ? null : daysLater(30),
  }
  createDialog.visible = true
}

const setCreateAuthExpiry = (n) => {
  createDialog.form.auth_valid_until = daysLater(n)
}

const submitCreate = async () => {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  if (createDialog.form.project_id) {
    if (auth.isAgent && !createDialog.form.auth_valid_until) {
      ElMessage.warning('代理授权项目必须设置到期时间')
      return
    }

    if (auth.isAgent && createDialog.form.authorized_devices <= 0) {
      ElMessage.warning('代理授权设备数必须大于 0')
      return
    }
  }

  createDialog.loading = true

  try {
    const createRes = await userApi.create({
      username: createDialog.form.username,
      password: createDialog.form.password,
    })

    const newUserId = createRes.data?.id

    if (createDialog.form.project_id && newUserId) {
      const authRes = await userApi.grantAuth(newUserId, {
        game_project_id: createDialog.form.project_id,
        user_level: createDialog.form.auth_user_level,
        authorized_devices: createDialog.form.authorized_devices,
        valid_until: createDialog.form.auth_valid_until || null,
      })

      if (auth.isAgent && authRes.data?.consumed_points) {
        ElMessage.success(`用户创建并授权成功，已扣除 ${fmtPoint(authRes.data.consumed_points)} 点`)
      } else {
        ElMessage.success('用户创建并授权成功')
      }
    } else {
      ElMessage.success('用户创建成功')
    }

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
  activeTab: 'base',
  generatedPassword: '',
  grantForm: { project_id: null, user_level: 'normal', authorized_devices: 20 },
  grantLoading: false,
  form: {
    status: 'active',
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
    status: row.status,
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

const submitEdit = async () => {
  editDialog.loading = true
  try {
    await userApi.update(editDialog.editId, {
      status: editDialog.form.status,
    })
    ElMessage.success('账号状态已更新')
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
    user_level: 'normal',
    authorized_devices: 20,
    valid_until: null,
  },
})

const projectAuthRules = {
  game_project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  user_level: [{ required: true, message: '请选择项目内等级', trigger: 'change' }],
  authorized_devices: [{ required: true, message: '请输入授权设备数', trigger: 'blur' }],
}

const grantableProjects = computed(() => {
  const activeAuthedIds = new Set(
    projectAuthDialog.auths
      .filter(item => item.status === 'active')
      .map(item => item.game_project_id),
  )
  return allProjects.value.filter(p => !activeAuthedIds.has(p.id))
})

const openProjectAuthDialog = async (row) => {
  projectAuthDialog.userId = row.id
  projectAuthDialog.username = row.username
  projectAuthDialog.form = {
    game_project_id: null,
    user_level: 'normal',
    authorized_devices: 20,
    valid_until: auth.isAdmin ? null : daysLater(30),
  }
  projectAuthDialog.visible = true
  await loadUserAuths()
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

const loadEditAuths = async () => {
  if (!editDialog.row?.id) return
  try {
    const res = await userApi.detail(editDialog.row.id)
    editDialog.auths = res.data.authorizations || []
  } catch { /* 静默 */ }
}

const quickGrantAuth = (p) => {
  editDialog.grantForm.project_id = p.id
  editDialog.grantForm.user_level = 'normal'
  editDialog.grantForm.authorized_devices = 20
}

const quickGrantDo = async () => {
  if (!editDialog.row?.id || !editDialog.grantForm.project_id) return
  editDialog.grantLoading = true
  try {
    await userApi.grantAuth(editDialog.row.id, {
      game_project_id: editDialog.grantForm.project_id,
      user_level: editDialog.grantForm.user_level,
      authorized_devices: editDialog.grantForm.authorized_devices,
      valid_until: auth.isAdmin ? null : new Date(Date.now() + 30*86400000).toISOString(),
    })
    ElMessage.success('授权成功')
    editDialog.grantForm.project_id = null
    await loadEditAuths()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '授权失败')
  } finally {
    editDialog.grantLoading = false
  }
}

const setUserAuthExpiry = (n) => {
  projectAuthDialog.form.valid_until = daysLater(n)
}

const grantUserProjectAuth = async () => {
  const valid = await projectAuthFormRef.value?.validate().catch(() => false)
  if (!valid) return

  if (auth.isAgent && !projectAuthDialog.form.valid_until) {
    ElMessage.warning('代理授权项目必须设置到期时间')
    return
  }

  if (auth.isAgent && projectAuthDialog.form.authorized_devices <= 0) {
    ElMessage.warning('代理授权设备数必须大于 0')
    return
  }

  projectAuthDialog.grantLoading = true

  try {
    const res = await userApi.grantAuth(projectAuthDialog.userId, {
      game_project_id: projectAuthDialog.form.game_project_id,
      user_level: projectAuthDialog.form.user_level,
      authorized_devices: projectAuthDialog.form.authorized_devices,
      valid_until: projectAuthDialog.form.valid_until || null,
    })

    if (auth.isAgent && res.data.consumed_points) {
      ElMessage.success(`授权成功，已扣除 ${fmtPoint(res.data.consumed_points)} 点`)
    } else {
      ElMessage.success('授权成功')
    }

    projectAuthDialog.form = {
      game_project_id: null,
      user_level: 'normal',
      authorized_devices: 20,
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

/* ── 管理员编辑授权 ───────────────────────────────────────── */

const authEditDialog = reactive({
  visible: false,
  loading: false,
  row: null,
  userId: null,
  form: {
    user_level: 'normal',
    authorized_devices: 20,
    valid_until: null,
    status: 'active',
  },
})

const openAuthEditDialog = (row) => {
  authEditDialog.row = row
  authEditDialog.userId = editDialog.visible ? editDialog.editId : projectAuthDialog.userId
  authEditDialog.form = {
    user_level: row.user_level,
    authorized_devices: row.authorized_devices,
    valid_until: row.valid_until ? new Date(row.valid_until) : null,
    status: row.status,
  }
  authEditDialog.visible = true
}

const setAuthEditExpiry = (n) => {
  const base = authEditDialog.form.valid_until || new Date()
  authEditDialog.form.valid_until = daysLater(n, base)
}

const submitAuthEdit = async () => {
  authEditDialog.loading = true
  try {
    await userApi.updateAuth(authEditDialog.userId, authEditDialog.row.id, {
      user_level: authEditDialog.form.user_level,
      authorized_devices: authEditDialog.form.authorized_devices,
      valid_until: authEditDialog.form.valid_until || null,
      status: authEditDialog.form.status,
    })

    ElMessage.success('项目授权已更新')
    authEditDialog.visible = false

    if (editDialog.visible) {
      const res = await userApi.detail(editDialog.editId)
      editDialog.auths = res.data.authorizations || []
      editDialog.row = res.data
    }

    if (projectAuthDialog.visible) {
      await loadUserAuths()
    }

    await loadUsers()
  } finally {
    authEditDialog.loading = false
  }
}

/* ── 创建者详情 ───────────────────────────────────────────── */

const creatorDialog = reactive({
  visible: false,
  loading: false,
  agent: null,
  users: [],
})

const openCreatorDetail = async (agentId) => {
  creatorDialog.visible = true
  creatorDialog.loading = true
  creatorDialog.agent = null
  creatorDialog.users = []

  try {
    const res = await userApi.creatorAgentDetail(agentId, {
      page: 1,
      page_size: 200,
    })
    creatorDialog.agent = res.data.agent
    creatorDialog.users = res.data.users || []
  } finally {
    creatorDialog.loading = false
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
  font-size: 13px;
  color: #64748b;
}

.filter-card,
.table-card {
  border-radius: 10px;
}

.filter-hint {
  font-size: 12px;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 8px 10px;
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

.user-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.username-link {
  font-weight: 500;
  color: #2563eb !important;
  padding: 0;
  height: auto;
  justify-content: flex-start;
}

.creator-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.creator-link {
  padding: 0;
  height: auto;
  justify-content: flex-start;
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

.auth-count {
  font-size: 13px;
  color: #1e293b;
}

.auth-count-total {
  color: #94a3b8;
  font-size: 11px;
}

.expiry-permanent {
  color: #10b981;
  font-size: 12px;
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

.creator-detail-card {
  border-radius: 10px;
}

.creator-profile {
  display: flex;
  gap: 14px;
  align-items: center;
}

.creator-avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b, #ef4444);
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.creator-meta {
  flex: 1;
}

.creator-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 17px;
  font-weight: 700;
  color: #1e293b;
}

.creator-desc {
  margin-top: 5px;
  font-size: 12px;
  color: #64748b;
}

.mini-auth-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mini-auth-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  color: #475569;
}

.drawer-header-row { display: flex; align-items: center; gap: 14px; padding: 4px 0; }
.drawer-avatar { width:44px; height:44px; border-radius:50%; background:#2563eb; color:#fff; display:flex; align-items:center; justify-content:center; font-size:18px; font-weight:600; flex-shrink:0; }
.drawer-meta { display: flex; flex-direction: column; gap: 2px; }
.drawer-name { font-size: 16px; font-weight: 600; color: #1e293b; }
.drawer-sub { font-size: 13px; color: #64748b; }
.dot { margin: 0 6px; color: #cbd5e1; }
</style>
