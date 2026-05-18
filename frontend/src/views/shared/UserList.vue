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
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 110px" @change="searchUsers">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>

        <el-form-item label="项目授权等级">
          <el-select v-model="filter.level" clearable placeholder="全部" style="width: 140px" @change="searchUsers">
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
            @change="searchUsers"
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="projectOptionLabel(p)"
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
            @change="searchUsers"
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
                @click="openUserDevices(row)"
              >
                {{ row.username }}
              </el-button>
              <el-button
                text
                size="small"
                class="device-entry-link"
                @click="openUserDevices(row)"
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

        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openUserDevices(row)">
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
              :label="projectOptionLabel(p)"
              :value="p.id"
              :disabled="isProjectOptionDisabled(p)"
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

      <el-tabs v-model="editDialog.activeTab" @tab-change="handleEditTabChange">
        <el-tab-pane label="账号与安全" name="base">
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
                保存账号状态
              </el-button>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">密码治理</el-divider>

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

        <el-tab-pane label="授权与设备" name="auths">
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

            <el-table-column label="操作" width="280" fixed="right">
              <template #default="{ row }">
                <el-button text size="small" :disabled="row.status !== 'active'" @click="openAuthUpgradeDialog(row)">
                  新增设备
                </el-button>
                <el-button text size="small" :disabled="row.status !== 'active'" @click="openAuthRenewDialog(row)">
                  续费
                </el-button>
                <el-button text size="small" :disabled="row.status !== 'active'" @click="openAuthLevelDialog(row)">
                  升级
                </el-button>

                <el-button
                  v-if="row.status === 'active'"
                  text
                  size="small"
                  type="danger"
                  @click="suspendUserAuth(row)"
                >
                  停用
                </el-button>
                <el-button
                  v-else-if="row.status === 'suspended'"
                  text
                  size="small"
                  type="success"
                  @click="enableUserAuth(row)"
                >
                  启用
                </el-button>
                <el-button
                  v-else
                  text
                  size="small"
                  disabled
                >
                  已过期
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
                @change="resetGrantPreview"
              >
                <el-option
                  v-for="p in unauthorizedProjects"
                  :key="p.id"
                  :label="projectOptionLabel(p)"
                  :value="p.id"
                  :disabled="isProjectOptionDisabled(p)"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="项目等级">
              <el-select v-model="editDialog.grantForm.user_level" style="width: 180px" @change="resetGrantPreview">
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
                  @change="resetGrantPreview"
                />

                <span
                  v-if="auth.isAdmin && Number(editDialog.grantForm.authorized_devices || 0) === 0"
                  class="hint-text"
                >
                  无限设备
                </span>
              </div>

              <div class="quick-btns">
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 20; resetGrantPreview()">20</el-button>
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 50; resetGrantPreview()">50</el-button>
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 100; resetGrantPreview()">100</el-button>
                <el-button size="small" @click="editDialog.grantForm.authorized_devices = 500; resetGrantPreview()">500</el-button>
                <el-button
                  v-if="auth.isAdmin"
                  size="small"
                  type="info"
                  plain
                  @click="editDialog.grantForm.authorized_devices = 0; resetGrantPreview()"
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
                    @click="editDialog.grantForm.valid_until = null; resetGrantPreview()"
                  >
                    永久
                  </el-button>
                </div>

                <el-date-picker
                  v-model="editDialog.grantForm.valid_until"
                  type="datetime"
                  :placeholder="auth.isAdmin ? '不填为永久有效' : '代理必须设置到期时间'"
                  style="width: 100%"
                  @change="resetGrantPreview"
                />
              </div>

              <div v-if="auth.isAgent" class="hint-text">
                代理授权会扣点，请先预览扣点；当前提交后由后端扣点并创建授权。
              </div>

              <div v-if="editDialog.grantPreview" class="cost-preview-panel">
                <div class="preview-title">扣点预览</div>
                <div class="preview-grid">
                  <span>预计扣点</span>
                  <strong>{{ fmtMoney(editDialog.grantPreview.total_cost) }} 点</strong>
                  <span>计费周期</span>
                  <strong>{{ editDialog.grantPreview.period_count }} {{ editDialog.grantPreview.billing_period_name }}</strong>
                  <span>购买时长</span>
                  <strong>{{ editDialog.grantPreview.paid_hours }} 小时</strong>
                  <span>可用余额</span>
                  <strong>{{ fmtMoney(editDialog.grantPreview.available_total) }} 点</strong>
                  <span>充值消耗</span>
                  <strong>{{ fmtMoney(editDialog.grantPreview.charged_consumed || 0) }} 点</strong>
                  <span>授信消耗</span>
                  <strong>{{ fmtMoney(editDialog.grantPreview.credit_consumed || 0) }} 点</strong>
                  <span>操作后余额</span>
                  <strong>
                    {{
                      editDialog.grantPreview.available_total_after == null
                        ? '-'
                        : `${fmtMoney(editDialog.grantPreview.available_total_after)} 点`
                    }}
                  </strong>
                </div>
                <el-alert
                  v-if="editDialog.grantPreview.enough_balance === false"
                  title="代理可用点数不足，提交授权会失败"
                  type="warning"
                  show-icon
                  :closable="false"
                  class="small-alert"
                />
              </div>
            </el-form-item>

            <el-form-item>
              <el-button
                v-if="auth.isAgent"
                :loading="editDialog.grantPreviewLoading"
                @click="previewGrantAuthCost"
              >
                预览扣点
              </el-button>
              <el-button
                type="primary"
                :loading="editDialog.grantLoading"
                @click="quickGrantDo"
              >
                授权
              </el-button>
            </el-form-item>
          </el-form>

          <div v-if="auth.isAdmin" class="governance-panel auth-device-panel">
            <div class="governance-row">
              <div>
                <div class="section-title">设备绑定</div>
                <div class="hint-text">按“账号 + 项目 + 设备编号”治理绑定，编辑页展示当前用户设备并支持解绑。</div>
              </div>
              <div class="device-action-group">
                <el-button
                  :icon="Refresh"
                  size="small"
                  :loading="editDialog.deviceLoading"
                  @click="loadEditDevices"
                >
                  刷新设备
                </el-button>
                <el-button
                  type="primary"
                  plain
                  size="small"
                  @click="openUserDevices(editDialog.row)"
                >
                  进入设备列表
                </el-button>
              </div>
            </div>

            <el-table
              v-loading="editDialog.deviceLoading"
              :data="editDialog.devices"
              size="small"
              empty-text="暂无设备绑定"
              stripe
            >
              <el-table-column label="设备编号" min-width="150">
                <template #default="{ row }">
                  {{ row.device_id || '-' }}
                </template>
              </el-table-column>

              <el-table-column label="项目" min-width="130">
                <template #default="{ row }">
                  {{ deviceProjectLabel(row) }}
                </template>
              </el-table-column>

              <el-table-column label="在线状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.is_online ? 'success' : 'info'" size="small" effect="light">
                    {{ row.is_online ? '在线' : '离线' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="绑定状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="light">
                    {{ row.status === 'active' ? '已绑定' : row.status || '-' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="最后心跳" width="170">
                <template #default="{ row }">
                  {{ row.last_seen_at ? formatDatetime(row.last_seen_at) : '-' }}
                </template>
              </el-table-column>

              <el-table-column label="操作" width="90" fixed="right">
                <template #default="{ row }">
                  <el-popconfirm
                    title="确认解绑该设备？解绑后设备需要重新通过账号、项目和设备编号验证。"
                    confirm-button-text="确认解绑"
                    cancel-button-text="取消"
                    @confirm="unbindEditDevice(row)"
                  >
                    <template #reference>
                      <el-button
                        text
                        size="small"
                        type="danger"
                        :disabled="row.status !== 'active'"
                      >
                        解绑
                      </el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="账务与冻结" name="finance">
          <el-alert
            :title="auth.isAdmin
              ? '已接入授权冻结权益记录；扣点快照和返点记录将继续按用户维度补齐。'
              : '代理可通过授权动作查看扣点预览；冻结权益状态由管理员侧查看。'"
            type="info"
            show-icon
            :closable="false"
            class="small-alert"
          />

          <div v-if="auth.isAdmin" class="finance-panel">
            <div class="auth-section-title">
              授权扣点快照
              <el-button
                size="small"
                :icon="Refresh"
                :loading="editDialog.finance.chargeLoading"
                @click="loadUserCharges"
                class="small-refresh-btn"
              />
            </div>

            <el-table
              v-loading="editDialog.finance.chargeLoading"
              :data="editDialog.finance.charges"
              size="small"
              stripe
              empty-text="暂无授权扣点快照"
            >
              <el-table-column label="项目" min-width="150">
                <template #default="{ row }">
                  {{ row.project_name || row.game_project_code || '-' }}
                </template>
              </el-table-column>

              <el-table-column label="等级/设备" width="120">
                <template #default="{ row }">
                  <LevelTag :level="row.user_level" />
                  <div class="sub-text">{{ displayDeviceLimit(row.authorized_devices) }}</div>
                </template>
              </el-table-column>

              <el-table-column label="扣点" width="160">
                <template #default="{ row }">
                  <div>{{ fmtMoney(row.original_cost) }} 点</div>
                  <div class="sub-text">充值 {{ fmtMoney(row.charged_consumed) }}</div>
                  <div class="sub-text">授信 {{ fmtMoney(row.credit_consumed) }}</div>
                </template>
              </el-table-column>

              <el-table-column label="返点状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="refundStatusTag(row.refund_status)" size="small" effect="light">
                    {{ refundStatusLabel(row.refund_status) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="有效期" min-width="220">
                <template #default="{ row }">
                  <div>{{ formatDatetime(row.valid_from) }}</div>
                  <div class="sub-text">至 {{ formatDatetime(row.valid_until) }}</div>
                </template>
              </el-table-column>
            </el-table>

            <div class="pager-row compact-pager">
              <span class="total-text">共 {{ editDialog.finance.chargeTotal }} 条</span>
              <el-pagination
                v-model:current-page="editDialog.finance.chargePage"
                v-model:page-size="editDialog.finance.chargePageSize"
                :page-sizes="[10, 20, 50]"
                layout="sizes, prev, pager, next"
                :total="editDialog.finance.chargeTotal"
                @size-change="loadUserCharges"
                @current-change="loadUserCharges"
              />
            </div>
          </div>

          <div v-if="auth.isAdmin" class="finance-panel">
            <div class="auth-section-title">
              删除返点记录
              <el-button
                size="small"
                :icon="Refresh"
                :loading="editDialog.finance.refundLoading"
                @click="loadUserRefunds"
                class="small-refresh-btn"
              />
            </div>

            <el-table
              v-loading="editDialog.finance.refundLoading"
              :data="editDialog.finance.refunds"
              size="small"
              stripe
              empty-text="暂无删除返点记录"
            >
              <el-table-column label="项目" min-width="150">
                <template #default="{ row }">
                  {{ row.project_name || row.game_project_code || '-' }}
                </template>
              </el-table-column>

              <el-table-column label="原扣点" width="110">
                <template #default="{ row }">
                  {{ fmtMoney(row.original_cost) }} 点
                </template>
              </el-table-column>

              <el-table-column label="返点" width="160">
                <template #default="{ row }">
                  <div class="amount-in">+{{ fmtMoney(row.refunded_points) }} 点</div>
                  <div class="sub-text">充值 {{ fmtMoney(row.refunded_charged) }}</div>
                  <div class="sub-text">授信 {{ fmtMoney(row.refunded_credit) }}</div>
                </template>
              </el-table-column>

              <el-table-column label="使用情况" min-width="170">
                <template #default="{ row }">
                  <div>购买 {{ row.last_refund_paid_hours || row.paid_hours || 0 }} 小时</div>
                  <div class="sub-text">已用 {{ row.last_refund_used_hours || 0 }} 小时</div>
                  <div class="sub-text">已用 {{ fmtMoney(row.last_refund_used_cost) }} 点</div>
                </template>
              </el-table-column>

              <el-table-column label="返点时间" width="170">
                <template #default="{ row }">
                  {{ formatDatetime(row.refunded_at) }}
                </template>
              </el-table-column>
            </el-table>

            <div class="pager-row compact-pager">
              <span class="total-text">共 {{ editDialog.finance.refundTotal }} 条</span>
              <el-pagination
                v-model:current-page="editDialog.finance.refundPage"
                v-model:page-size="editDialog.finance.refundPageSize"
                :page-sizes="[10, 20, 50]"
                layout="sizes, prev, pager, next"
                :total="editDialog.finance.refundTotal"
                @size-change="loadUserRefunds"
                @current-change="loadUserRefunds"
              />
            </div>
          </div>

          <div v-if="auth.isAdmin" class="finance-panel">
            <div class="auth-section-title">
              授权冻结权益记录
              <el-button
                size="small"
                :icon="Refresh"
                :loading="editDialog.finance.freezeLoading"
                @click="loadUserFreezes"
                class="small-refresh-btn"
              />
            </div>

            <el-table
              v-loading="editDialog.finance.freezeLoading"
              :data="editDialog.finance.freezes"
              size="small"
              stripe
              empty-text="暂无授权冻结记录"
            >
              <el-table-column label="项目" min-width="150">
                <template #default="{ row }">
                  {{ row.project_name || row.game_project_code || '-' }}
                </template>
              </el-table-column>

              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="freezeStatusTag(row.status)" size="small" effect="light">
                    {{ freezeStatusLabel(row.status) }}
                  </el-tag>
                  <div class="sub-text">{{ freezeTypeLabel(row.freeze_type) }}</div>
                </template>
              </el-table-column>

              <el-table-column label="冻结权益" min-width="160">
                <template #default="{ row }">
                  <div>{{ row.remaining_hours ?? '-' }} 小时</div>
                  <div class="sub-text">{{ fmtMoney(row.estimated_points) }} 点</div>
                </template>
              </el-table-column>

              <el-table-column label="冻结时间" width="170">
                <template #default="{ row }">
                  {{ formatDatetime(row.frozen_at) }}
                </template>
              </el-table-column>

              <el-table-column label="释放/清算" width="170">
                <template #default="{ row }">
                  {{ row.released_at ? formatDatetime(row.released_at) : (row.settled_at ? formatDatetime(row.settled_at) : '-') }}
                </template>
              </el-table-column>
            </el-table>

            <div class="pager-row compact-pager">
              <span class="total-text">共 {{ editDialog.finance.freezeTotal }} 条</span>
              <el-pagination
                v-model:current-page="editDialog.finance.freezePage"
                v-model:page-size="editDialog.finance.freezePageSize"
                :page-sizes="[10, 20, 50]"
                layout="sizes, prev, pager, next"
                :total="editDialog.finance.freezeTotal"
                @size-change="loadUserFreezes"
                @current-change="loadUserFreezes"
              />
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="auth.isAdmin" label="审计日志" name="audit">
          <el-alert
            title="按当前用户聚合展示用户、授权、设备与账务相关审计日志。"
            type="info"
            show-icon
            :closable="false"
            class="small-alert"
          />

          <div class="auth-section-title">
            用户审计日志
            <el-button
              size="small"
              :icon="Refresh"
              :loading="editDialog.audit.loading"
              @click="loadUserAuditLogs"
              class="small-refresh-btn"
            />
          </div>

          <el-table
            v-loading="editDialog.audit.loading"
            :data="editDialog.audit.logs"
            size="small"
            stripe
            empty-text="暂无审计日志"
          >
            <el-table-column label="时间" width="170">
              <template #default="{ row }">
                {{ formatDatetime(row.created_at) }}
              </template>
            </el-table-column>

            <el-table-column label="操作" min-width="220">
              <template #default="{ row }">
                <div class="main-text">{{ row.summary || row.action }}</div>
                <div class="sub-text">{{ row.action }}</div>
              </template>
            </el-table-column>

            <el-table-column label="操作者" width="120">
              <template #default="{ row }">
                {{ actorLabel(row) }}
              </template>
            </el-table-column>

            <el-table-column label="目标" width="150">
              <template #default="{ row }">
                <div>{{ row.target_type || '-' }}</div>
                <div class="sub-text">{{ row.target_id || '-' }}</div>
              </template>
            </el-table-column>

            <el-table-column label="请求ID" min-width="160">
              <template #default="{ row }">
                <span class="mono-text">{{ row.request_id || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>

          <div class="pager-row compact-pager">
            <span class="total-text">共 {{ editDialog.audit.total }} 条</span>
            <el-pagination
              v-model:current-page="editDialog.audit.page"
              v-model:page-size="editDialog.audit.pageSize"
              :page-sizes="[10, 20, 50]"
              layout="sizes, prev, pager, next"
              :total="editDialog.audit.total"
              @size-change="loadUserAuditLogs"
              @current-change="loadUserAuditLogs"
            />
          </div>
        </el-tab-pane>

      </el-tabs>
    </el-drawer>

    <el-dialog
      v-model="authUpgradeDialog.visible"
      title="新增授权设备"
      width="720px"
      destroy-on-close
    >
      <el-form :model="authUpgradeDialog.form" label-width="120px">
        <el-form-item label="项目">
          <span class="readonly-val">{{ authProjectName(authUpgradeDialog.row) }}</span>
        </el-form-item>

        <el-form-item label="当前设备数">
          <span class="readonly-val">{{ displayDeviceLimit(authUpgradeDialog.row?.authorized_devices) }}</span>
        </el-form-item>

        <el-form-item label="当前到期">
          <span class="readonly-val">{{ authUpgradeDialog.row?.valid_until ? formatDatetime(authUpgradeDialog.row.valid_until) : '永久' }}</span>
        </el-form-item>

        <el-form-item label="当前批次">
          <div class="batch-list-panel" v-loading="authUpgradeDialog.batchesLoading">
            <div
              v-for="batch in authUpgradeDialog.batches"
              :key="batch.id"
              class="batch-chip"
            >
              <strong>批次 {{ batch.id }}</strong>
              <span>{{ batch.authorized_devices }} 台，已绑 {{ batch.bound_devices }} 台</span>
              <span>到期 {{ batch.valid_until ? formatDatetime(batch.valid_until) : '永久' }}</span>
              <span>剩余 {{ remainingHoursText(batch.remaining_hours) }}</span>
            </div>
            <span v-if="!authUpgradeDialog.batches.length" class="hint-text">暂无批次数据</span>
          </div>
        </el-form-item>

        <el-form-item label="新增设备数">
          <el-input-number
            v-model="authUpgradeDialog.form.additional_devices"
            :min="1"
            :step="1"
            controls-position="right"
            style="width: 170px"
            @change="previewAuthUpgrade"
          />
        </el-form-item>

        <el-form-item label="处理方式">
          <el-radio-group v-model="authUpgradeDialog.form.mode" @change="previewAuthUpgrade">
            <el-radio-button label="append">追加新批次</el-radio-button>
            <el-radio-button label="average">平均后并批</el-radio-button>
            <el-radio-button label="topup_align">补时后并批</el-radio-button>
          </el-radio-group>
          <div class="mode-explain">{{ addDeviceModeExplain(authUpgradeDialog.form.mode) }}</div>
        </el-form-item>

        <div v-if="authUpgradeDialog.preview" class="cost-preview-panel upgrade-preview-panel">
          <div class="preview-title">新增设备扣点预览</div>
          <div class="preview-grid">
            <span>原设备数</span>
            <strong>{{ displayDeviceLimit(authUpgradeDialog.preview.old_devices) }}</strong>
            <span>新设备数</span>
            <strong>{{ displayDeviceLimit(authUpgradeDialog.preview.new_devices) }}</strong>
            <span>新增设备</span>
            <strong>{{ authUpgradeDialog.preview.additional_devices }} 台</strong>
            <span>预计扣点</span>
            <strong>{{ fmtMoney(authUpgradeDialog.preview.consumed_points) }} 点</strong>
            <span>新到期</span>
            <strong>{{ authUpgradeDialog.preview.new_expiry ? formatDate(authUpgradeDialog.preview.new_expiry) : '-' }}</strong>
            <template v-if="authUpgradeDialog.preview.available_total != null">
              <span>可用余额</span>
              <strong>{{ fmtMoney(authUpgradeDialog.preview.available_total) }} 点</strong>
              <span>充值消耗</span>
              <strong>{{ fmtMoney(authUpgradeDialog.preview.charged_consumed || 0) }} 点</strong>
              <span>授信消耗</span>
              <strong>{{ fmtMoney(authUpgradeDialog.preview.credit_consumed || 0) }} 点</strong>
              <span>操作后余额</span>
              <strong>{{ fmtMoney(authUpgradeDialog.preview.available_total_after || 0) }} 点</strong>
            </template>
            <template v-if="authUpgradeDialog.form.mode === 'topup_align'">
              <span>新设备扣点</span>
              <strong>{{ fmtMoney(authUpgradeDialog.preview.new_devices_cost || 0) }} 点</strong>
              <span>旧设备补时扣点</span>
              <strong>{{ fmtMoney(authUpgradeDialog.preview.old_devices_topup_cost || 0) }} 点</strong>
              <span>旧设备剩余</span>
              <strong>{{ authUpgradeDialog.preview.old_remaining_hours ?? 0 }} 小时</strong>
              <span>补时小时</span>
              <strong>{{ authUpgradeDialog.preview.topup_delta_hours ?? 0 }} 小时</strong>
            </template>
          </div>
        </div>

        <el-alert
          title="扣点预览会随新增设备数和处理方式自动刷新；后续命令中心接入后，提交也将直接走批次化动作。"
          type="info"
          show-icon
          :closable="false"
          class="small-alert"
        />
      </el-form>

      <template #footer>
        <el-button @click="authUpgradeDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="authUpgradeDialog.loading"
          :disabled="!authUpgradeDialog.preview"
          @click="submitAuthUpgrade"
        >
          确认新增
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="authRenewDialog.visible"
      title="授权续费"
      width="720px"
      destroy-on-close
    >
      <el-form :model="authRenewDialog.form" label-width="120px">
        <el-form-item label="项目">
          <span class="readonly-val">{{ authProjectName(authRenewDialog.row) }}</span>
        </el-form-item>

        <el-form-item label="当前到期">
          <span class="readonly-val">{{ authRenewDialog.row?.valid_until ? formatDate(authRenewDialog.row.valid_until) : '-' }}</span>
        </el-form-item>

        <el-form-item label="当前批次">
          <div class="batch-list-panel" v-loading="authRenewDialog.batchesLoading">
            <div
              v-for="batch in authRenewDialog.batches"
              :key="batch.id"
              class="batch-chip"
            >
              <strong>批次 {{ batch.id }}</strong>
              <span>{{ batch.authorized_devices }} 台，已绑 {{ batch.bound_devices }} 台</span>
              <span>到期 {{ batch.valid_until ? formatDatetime(batch.valid_until) : '永久' }}</span>
              <span>剩余 {{ remainingHoursText(batch.remaining_hours) }}</span>
            </div>
            <span v-if="!authRenewDialog.batches.length" class="hint-text">暂无批次数据</span>
          </div>
        </el-form-item>

        <el-form-item label="续费到期">
          <div class="expiry-picker-wrap">
            <div class="quick-btns">
              <el-button size="small" @click="setAuthRenewExpiry(30)">+30天</el-button>
              <el-button size="small" @click="setAuthRenewExpiry(90)">+90天</el-button>
              <el-button size="small" @click="setAuthRenewExpiry(365)">+365天</el-button>
            </div>
            <el-date-picker
              v-model="authRenewDialog.form.valid_until"
              type="datetime"
              placeholder="选择新的到期时间"
              style="width: 100%"
              @change="previewAuthRenew"
            />
          </div>
        </el-form-item>

        <div v-if="authRenewDialog.preview" class="cost-preview-panel upgrade-preview-panel">
          <div class="preview-title">续费扣点预览</div>
          <div class="preview-grid">
            <span>设备数</span>
            <strong>{{ displayDeviceLimit(authRenewDialog.preview.authorized_devices) }}</strong>
            <span>原到期</span>
            <strong>{{ authRenewDialog.preview.old_valid_until ? formatDate(authRenewDialog.preview.old_valid_until) : '-' }}</strong>
            <span>新到期</span>
            <strong>{{ formatDate(authRenewDialog.preview.new_valid_until) }}</strong>
            <span>预计扣点</span>
            <strong>{{ fmtMoney(authRenewDialog.preview.total_cost) }} 点</strong>
            <span>可用余额</span>
            <strong>{{ fmtMoney(authRenewDialog.preview.available_total) }} 点</strong>
            <span>充值消耗</span>
            <strong>{{ fmtMoney(authRenewDialog.preview.charged_consumed || 0) }} 点</strong>
            <span>授信消耗</span>
            <strong>{{ fmtMoney(authRenewDialog.preview.credit_consumed || 0) }} 点</strong>
            <span>操作后余额</span>
            <strong>{{ fmtMoney(authRenewDialog.preview.available_total_after || 0) }} 点</strong>
          </div>
          <el-alert
            v-if="authRenewDialog.preview.enough_balance === false"
            title="代理可用点数不足，提交续费会失败"
            type="warning"
            show-icon
            :closable="false"
            class="small-alert"
          />
        </div>
      </el-form>

      <template #footer>
        <el-button @click="authRenewDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="authRenewDialog.loading"
          :disabled="!authRenewDialog.preview"
          @click="submitAuthRenew"
        >
          确认续费
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="authLevelDialog.visible"
      title="授权等级升级"
      width="720px"
      destroy-on-close
    >
      <el-form :model="authLevelDialog.form" label-width="120px">
        <el-form-item label="项目">
          <span class="readonly-val">{{ authProjectName(authLevelDialog.row) }}</span>
        </el-form-item>

        <el-form-item label="当前等级">
          <LevelTag :level="authLevelDialog.row?.user_level" />
        </el-form-item>

        <el-form-item label="当前批次">
          <div class="batch-list-panel" v-loading="authLevelDialog.batchesLoading">
            <div
              v-for="batch in authLevelDialog.batches"
              :key="batch.id"
              class="batch-chip"
            >
              <strong>批次 {{ batch.id }}</strong>
              <span>{{ batch.authorized_devices }} 台，已绑 {{ batch.bound_devices }} 台</span>
              <span>到期 {{ batch.valid_until ? formatDatetime(batch.valid_until) : '永久' }}</span>
              <span>剩余 {{ remainingHoursText(batch.remaining_hours) }}</span>
            </div>
            <span v-if="!authLevelDialog.batches.length" class="hint-text">暂无批次数据</span>
          </div>
        </el-form-item>

        <el-form-item label="升级到">
          <el-select v-model="authLevelDialog.form.user_level" style="width: 180px" @change="previewAuthLevelUpgrade">
            <el-option label="试用" value="trial" />
            <el-option label="普通" value="normal" />
            <el-option label="VIP" value="vip" />
            <el-option label="SVIP" value="svip" />
          </el-select>
        </el-form-item>

        <div v-if="authLevelDialog.preview" class="cost-preview-panel upgrade-preview-panel">
          <div class="preview-title">等级升级差价预览</div>
          <div class="preview-grid">
            <span>原等级</span>
            <strong>{{ authLevelDialog.preview.old_user_level_name }}</strong>
            <span>新等级</span>
            <strong>{{ authLevelDialog.preview.new_user_level_name }}</strong>
            <span>旧成本</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.old_total_cost) }} 点</strong>
            <span>新成本</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.new_total_cost) }} 点</strong>
            <span>差价扣点</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.difference_cost) }} 点</strong>
            <span>可用余额</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.available_total) }} 点</strong>
            <span>充值消耗</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.charged_consumed || 0) }} 点</strong>
            <span>授信消耗</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.credit_consumed || 0) }} 点</strong>
            <span>操作后余额</span>
            <strong>{{ fmtMoney(authLevelDialog.preview.available_total_after || 0) }} 点</strong>
          </div>
          <el-alert
            v-if="authLevelDialog.preview.enough_balance === false"
            title="代理可用点数不足，提交升级会失败"
            type="warning"
            show-icon
            :closable="false"
            class="small-alert"
          />
        </div>
      </el-form>

      <template #footer>
        <el-button @click="authLevelDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="authLevelDialog.loading"
          :disabled="!authLevelDialog.preview"
          @click="submitAuthLevelUpgrade"
        >
          确认升级
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
import { useRoute, useRouter } from 'vue-router'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { userApi } from '@/api/user'
import { agentApi } from '@/api/agent'
import { accountingApi } from '@/api/accounting'
import { auditApi } from '@/api/audit'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { agentProjectAccessApi } from '@/api/agent/projectAccess'
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
const route = useRoute()
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
  grantPreviewLoading: false,
  grantPreview: null,
  grantPreviewPayload: '',
  grantIdempotencyKey: '',
  generatedPassword: '',
  form: {
    status: 'active',
  },
  password: {
    new_password: '',
    confirm_password: '',
  },
  auths: [],
  deviceLoading: false,
  devices: [],
  grantForm: buildGrantForm(),
  finance: {
    chargeLoading: false,
    charges: [],
    chargePage: 1,
    chargePageSize: 10,
    chargeTotal: 0,
    refundLoading: false,
    refunds: [],
    refundPage: 1,
    refundPageSize: 10,
    refundTotal: 0,
    freezeLoading: false,
    freezes: [],
    freezePage: 1,
    freezePageSize: 10,
    freezeTotal: 0,
  },
  audit: {
    loading: false,
    logs: [],
    page: 1,
    pageSize: 20,
    total: 0,
  },
})

const authUpgradeDialog = reactive({
  visible: false,
  loading: false,
  previewLoading: false,
  batchesLoading: false,
  batches: [],
  row: null,
  preview: null,
  idempotencyKey: '',
  form: {
    additional_devices: 1,
    mode: 'append',
  },
})

const authRenewDialog = reactive({
  visible: false,
  loading: false,
  previewLoading: false,
  batchesLoading: false,
  batches: [],
  row: null,
  preview: null,
  idempotencyKey: '',
  form: {
    valid_until: null,
  },
})

const authLevelDialog = reactive({
  visible: false,
  loading: false,
  previewLoading: false,
  batchesLoading: false,
  batches: [],
  row: null,
  preview: null,
  idempotencyKey: '',
  form: {
    user_level: 'vip',
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

function newIdempotencyKey(prefix = 'ui') {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
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

function deviceProjectLabel(device) {
  if (device?.game_project_name || device?.project_display_name || device?.project_name) {
    return device.game_project_name || device.project_display_name || device.project_name
  }

  const projectId = Number(device?.game_project_id || device?.project_id)
  const project = allProjects.value.find(item => Number(item.id) === projectId)
  if (project) return projectName(project)

  return projectId ? `项目#${projectId}` : '-'
}

function normalizeProject(project) {
  return {
    ...project,
    display_name: projectName(project),
  }
}

function normalizeCatalogProject(project) {
  return normalizeProject({
    ...project,
    is_catalog_item: true,
  })
}

function projectPriceText(project, level) {
  const prices = Array.isArray(project?.prices) ? project.prices : []
  const item = prices.find(p => p.level === level)
  if (!item) return '未定价'
  return `${fmtMoney(item.points)}点/${item.unit_label || '周期/设备'}`
}

function projectAccessText(project) {
  if (!auth.isAgent || !project?.is_catalog_item) return ''
  if (project.is_authorized) {
    return project.auth_valid_until
      ? `已授权，到期 ${formatDate(project.auth_valid_until)}`
      : '已授权，永久'
  }
  if (project.access_status === 'pending') return '申请中'
  if (project.access_status === 'apply_available') return '可申请，未开通'
  if (project.access_status === 'auto_open_available') return '可自助开通'
  return '未开通'
}

function levelLabel(level) {
  const map = {
    trial: '试用',
    normal: '普通',
    vip: 'VIP',
    svip: 'SVIP',
    tester: '测试',
  }
  return map[level] || level || '-'
}

function projectOptionLabel(project) {
  const base = projectName(project)
  if (!auth.isAgent || !project?.is_catalog_item) return base

  const level = editDialog.visible
    ? editDialog.grantForm.user_level
    : createDialog.form.auth_user_level
  return `${base}｜${projectAccessText(project)}｜${levelLabel(level)} ${projectPriceText(project, level)}`
}

function isProjectOptionDisabled(project) {
  return auth.isAgent && project?.is_catalog_item && !project.is_authorized
}

function normalizeAuthItem(item) {
  return {
    ...item,
    game_project_name: authProjectName(item),
    activated_devices: item.activated_devices ?? 0,
    authorized_devices: item.authorized_devices ?? 0,
  }
}

function normalizeDeviceBinding(item) {
  return {
    ...item,
    is_online: Boolean(item?.is_online),
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

function remainingHoursText(hours) {
  if (hours === null || hours === undefined) return '永久'
  const safeHours = Number(hours || 0)
  if (safeHours <= 0) return '已到期'
  const days = Math.floor(safeHours / 24)
  const restHours = safeHours % 24
  if (days <= 0) return `${restHours} 小时`
  return restHours ? `${days} 天 ${restHours} 小时` : `${days} 天`
}

function addDeviceModeExplain(mode) {
  const map = {
    append: '新增设备单独形成新批次，旧设备到期时间不变。',
    average: '把旧批次剩余时间和新增设备购买时间按设备数平均，最后统一为一个到期时间。',
    topup_align: '新增设备按目标时间购买，同时把旧的短批次补齐到同一到期时间，补出来的时间需要扣点。',
  }
  return map[mode] || ''
}

function fmtMoney(value) {
  return Number(value || 0).toFixed(2)
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

function freezeStatusLabel(status) {
  const map = {
    frozen: '冻结中',
    released: '已释放',
    refunded: '已清算',
    cancelled: '已取消',
  }
  return map[status] || status || '-'
}

function freezeStatusTag(status) {
  const map = {
    frozen: 'warning',
    released: 'success',
    refunded: 'info',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

function freezeTypeLabel(type) {
  const map = {
    agent_suspend: '代理停用冻结',
    admin_suspend: '管理员停用冻结',
  }
  return map[type] || type || '-'
}

function refundStatusLabel(status) {
  const map = {
    none: '未返点',
    partial: '部分返点',
    refunded: '已返点',
    skipped: '已跳过',
  }
  return map[status] || status || '未返点'
}

function refundStatusTag(status) {
  const map = {
    none: 'info',
    partial: 'warning',
    refunded: 'success',
    skipped: 'info',
  }
  return map[status] || 'info'
}

function actorLabel(row) {
  if (!row?.actor_type) return '-'
  return row.actor_id ? `${row.actor_type}#${row.actor_id}` : row.actor_type
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
  resetGrantPreview()
}

function setAuthRenewExpiry(days) {
  const base = authRenewDialog.row?.valid_until
    ? new Date(authRenewDialog.row.valid_until)
    : new Date()
  base.setDate(base.getDate() + days)
  authRenewDialog.form.valid_until = base
  previewAuthRenew()
}

function resetGrantPreview() {
  editDialog.grantPreview = null
  editDialog.grantPreviewPayload = ''
  editDialog.grantIdempotencyKey = ''
}

function resetAuthUpgradePreview() {
  authUpgradeDialog.preview = null
  authUpgradeDialog.idempotencyKey = ''
}

function resetAuthRenewPreview() {
  authRenewDialog.preview = null
  authRenewDialog.idempotencyKey = ''
}

function resetAuthLevelPreview() {
  authLevelDialog.preview = null
  authLevelDialog.idempotencyKey = ''
}

async function loadLookups() {
  const projectReq = auth.isAgent
    ? agentProjectAccessApi.catalog()
    : projectApi.list({
        page: 1,
        page_size: 100,
        is_active: true,
      })

  const agentReq = auth.isAdmin
    ? agentApi.list({ page: 1, page_size: 500 })
    : Promise.resolve({ data: { agents: [] } })

  const [projectRes, agentRes] = await Promise.all([projectReq, agentReq])

  const projectRows = auth.isAgent
    ? (projectRes.data || []).map(normalizeCatalogProject)
    : (projectRes.data.projects || []).map(normalizeProject)
  allProjects.value = projectRows
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

function openUserDevices(row) {
  if (!row?.id) return
  router.push({ path: '/devices', query: { user_id: row.id, username: row.username } })
}

async function openEditDialog(row, initialTab = 'base') {
  editDialog.visible = true
  editDialog.row = normalizeUserRow(row)
  editDialog.activeTab = initialTab === 'password'
    ? 'base'
    : initialTab === 'devices'
      ? 'auths'
      : initialTab
  editDialog.form = {
    status: row.status,
  }
  editDialog.password = {
    new_password: '',
    confirm_password: '',
  }
  editDialog.generatedPassword = ''
  editDialog.devices = []
  editDialog.deviceLoading = false
  editDialog.grantForm = buildGrantForm()
  resetGrantPreview()
  editDialog.finance.charges = []
  editDialog.finance.chargePage = 1
  editDialog.finance.chargeTotal = 0
  editDialog.finance.refunds = []
  editDialog.finance.refundPage = 1
  editDialog.finance.refundTotal = 0
  editDialog.finance.freezes = []
  editDialog.finance.freezePage = 1
  editDialog.finance.freezeTotal = 0
  editDialog.audit.logs = []
  editDialog.audit.page = 1
  editDialog.audit.total = 0

  await Promise.all([
    loadEditAuths(),
    auth.isAdmin ? loadEditDevices() : Promise.resolve(),
  ])
}

function handleEditTabChange(tabName) {
  if (tabName === 'auths' && auth.isAdmin) {
    loadEditDevices()
  } else if (tabName === 'finance' && auth.isAdmin) {
    loadUserFinance()
  } else if (tabName === 'audit' && auth.isAdmin) {
    loadUserAuditLogs()
  }
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

async function loadEditDevices() {
  if (!auth.isAdmin || !editDialog.row?.id) return

  editDialog.deviceLoading = true

  try {
    const res = await userApi.deviceBindings(editDialog.row.id)
    editDialog.devices = (res.data?.devices || []).map(normalizeDeviceBinding)
  } finally {
    editDialog.deviceLoading = false
  }
}

async function unbindEditDevice(row) {
  if (!auth.isAdmin || !editDialog.row?.id || !row?.id) return

  await userApi.unbindDevice(editDialog.row.id, row.id)
  ElMessage.success('设备已解绑')

  await Promise.all([
    loadEditDevices(),
    loadEditAuths(),
    loadUsers(),
  ])
}

async function loadAuthorizationBatches(row, dialogState) {
  if (!editDialog.row?.id || !row?.id) {
    dialogState.batches = []
    return
  }

  dialogState.batchesLoading = true
  try {
    const res = await userApi.authBatches(editDialog.row.id, row.id)
    dialogState.batches = res.data?.batches || []
  } finally {
    dialogState.batchesLoading = false
  }
}

async function loadUserFreezes() {
  if (!auth.isAdmin || !editDialog.row?.id) return

  editDialog.finance.freezeLoading = true

  try {
    const res = await accountingApi.freezes({
      page: editDialog.finance.freezePage,
      page_size: editDialog.finance.freezePageSize,
      user_id: editDialog.row.id,
    })
    editDialog.finance.freezes = res.data.freezes || []
    editDialog.finance.freezeTotal = res.data.total || 0
  } finally {
    editDialog.finance.freezeLoading = false
  }
}

async function loadUserFinance() {
  await Promise.all([
    loadUserCharges(),
    loadUserRefunds(),
    loadUserFreezes(),
  ])
}

async function loadUserCharges() {
  if (!auth.isAdmin || !editDialog.row?.id) return

  editDialog.finance.chargeLoading = true

  try {
    const res = await accountingApi.charges({
      page: editDialog.finance.chargePage,
      page_size: editDialog.finance.chargePageSize,
      user_id: editDialog.row.id,
    })
    editDialog.finance.charges = res.data.charges || []
    editDialog.finance.chargeTotal = res.data.total || 0
  } finally {
    editDialog.finance.chargeLoading = false
  }
}

async function loadUserRefunds() {
  if (!auth.isAdmin || !editDialog.row?.id) return

  editDialog.finance.refundLoading = true

  try {
    const res = await accountingApi.refunds({
      page: editDialog.finance.refundPage,
      page_size: editDialog.finance.refundPageSize,
      user_id: editDialog.row.id,
    })
    editDialog.finance.refunds = res.data.refunds || []
    editDialog.finance.refundTotal = res.data.total || 0
  } finally {
    editDialog.finance.refundLoading = false
  }
}

async function loadUserAuditLogs() {
  if (!auth.isAdmin || !editDialog.row?.id) return

  editDialog.audit.loading = true

  try {
    const res = await auditApi.list({
      page: editDialog.audit.page,
      page_size: editDialog.audit.pageSize,
      user_id: editDialog.row.id,
    })
    editDialog.audit.logs = res.data.logs || []
    editDialog.audit.total = res.data.total || 0
  } finally {
    editDialog.audit.loading = false
  }
}

async function submitEdit() {
  if (!editDialog.row?.id) return

  editDialog.loading = true

  try {
    await userApi.update(editDialog.row.id, {
      status: editDialog.form.status,
    })

    ElMessage.success('账号状态已保存')
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
  resetGrantPreview()
  editDialog.activeTab = 'auths'
}

function buildGrantPayload() {
  return {
    game_project_id: editDialog.grantForm.project_id,
    user_level: editDialog.grantForm.user_level,
    authorized_devices: editDialog.grantForm.authorized_devices,
    valid_until: isoOrNull(editDialog.grantForm.valid_until),
  }
}

async function previewGrantAuthCost() {
  if (!editDialog.row?.id) return

  if (!editDialog.grantForm.project_id) {
    ElMessage.warning('请选择授权项目')
    return
  }

  if (auth.isAgent && !editDialog.grantForm.valid_until) {
    ElMessage.warning('代理授权项目时必须设置项目到期时间')
    return
  }

  editDialog.grantPreviewLoading = true

  try {
    const payload = buildGrantPayload()
    const res = await userApi.previewGrantAuth(editDialog.row.id, payload)
    editDialog.grantPreview = res.data
    editDialog.grantPreviewPayload = JSON.stringify(payload)
    editDialog.grantIdempotencyKey = newIdempotencyKey('grant')
  } finally {
    editDialog.grantPreviewLoading = false
  }
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

  const payload = buildGrantPayload()
  if (auth.isAgent && !editDialog.grantPreview) {
    ElMessage.warning('请先预览扣点')
    return
  }
  if (auth.isAgent && editDialog.grantPreviewPayload !== JSON.stringify(payload)) {
    ElMessage.warning('授权参数已变更，请重新预览扣点')
    return
  }

  editDialog.grantLoading = true

  try {
    await userApi.grantAuth(
      editDialog.row.id,
      payload,
      editDialog.grantIdempotencyKey || newIdempotencyKey('grant')
    )

    ElMessage.success('项目授权成功')
    editDialog.grantForm = buildGrantForm()
    resetGrantPreview()

    await Promise.all([
      loadEditAuths(),
      loadUsers(),
    ])
  } finally {
    editDialog.grantLoading = false
  }
}

async function openAuthUpgradeDialog(row) {
  if (row.status !== 'active') {
    ElMessage.warning('只有有效授权可以新增设备')
    return
  }

  authUpgradeDialog.row = row
  authUpgradeDialog.batches = []
  authUpgradeDialog.form = {
    additional_devices: 1,
    mode: 'append',
  }
  resetAuthUpgradePreview()
  authUpgradeDialog.visible = true
  await loadAuthorizationBatches(row, authUpgradeDialog)
  await previewAuthUpgrade()
}

async function openAuthRenewDialog(row) {
  if (row.status !== 'active') {
    ElMessage.warning('只有有效授权可以续费')
    return
  }

  authRenewDialog.row = row
  authRenewDialog.batches = []
  const defaultRenewUntil = row.valid_until ? new Date(row.valid_until) : new Date()
  defaultRenewUntil.setDate(defaultRenewUntil.getDate() + 30)
  authRenewDialog.form = {
    valid_until: defaultRenewUntil,
  }
  resetAuthRenewPreview()
  authRenewDialog.visible = true
  await loadAuthorizationBatches(row, authRenewDialog)
  await previewAuthRenew()
}

async function openAuthLevelDialog(row) {
  if (row.status !== 'active') {
    ElMessage.warning('只有有效授权可以升级等级')
    return
  }

  const nextLevel = row.user_level === 'vip' ? 'svip' : 'vip'
  authLevelDialog.row = row
  authLevelDialog.batches = []
  authLevelDialog.form = {
    user_level: nextLevel,
  }
  resetAuthLevelPreview()
  authLevelDialog.visible = true
  await loadAuthorizationBatches(row, authLevelDialog)
  await previewAuthLevelUpgrade()
}

async function previewAuthUpgrade() {
  if (!editDialog.row?.id || !authUpgradeDialog.row?.id) return
  if (Number(authUpgradeDialog.form.additional_devices || 0) <= 0) {
    ElMessage.warning('新增设备数必须大于 0')
    return
  }

  authUpgradeDialog.previewLoading = true

  try {
    const res = await userApi.upgradePreview(
      editDialog.row.id,
      authUpgradeDialog.row.id,
      authUpgradeDialog.form.additional_devices,
      authUpgradeDialog.form.mode
    )
    authUpgradeDialog.preview = res.data
    authUpgradeDialog.idempotencyKey = newIdempotencyKey('add-devices')
  } catch {
    authUpgradeDialog.preview = null
  } finally {
    authUpgradeDialog.previewLoading = false
  }
}

async function submitAuthUpgrade() {
  if (!editDialog.row?.id || !authUpgradeDialog.row?.id) return
  if (!authUpgradeDialog.preview) {
    ElMessage.warning('请先预览扣点')
    return
  }

  authUpgradeDialog.loading = true

  try {
    await userApi.upgradeAuth(
      editDialog.row.id,
      authUpgradeDialog.row.id,
      {
        additional_devices: authUpgradeDialog.form.additional_devices,
        mode: authUpgradeDialog.form.mode,
      },
      authUpgradeDialog.idempotencyKey || newIdempotencyKey('add-devices')
    )

    ElMessage.success('授权设备数已新增')
    authUpgradeDialog.visible = false
    resetAuthUpgradePreview()

    await Promise.all([
      loadEditAuths(),
      loadUsers(),
    ])
  } finally {
    authUpgradeDialog.loading = false
  }
}

async function previewAuthRenew() {
  if (!editDialog.row?.id || !authRenewDialog.row?.id) return
  if (!authRenewDialog.form.valid_until) {
    ElMessage.warning('请选择新的到期时间')
    return
  }

  authRenewDialog.previewLoading = true

  try {
    const res = await userApi.renewPreview(editDialog.row.id, authRenewDialog.row.id, {
      valid_until: isoOrNull(authRenewDialog.form.valid_until),
    })
    authRenewDialog.preview = res.data
    authRenewDialog.idempotencyKey = newIdempotencyKey('renew')
  } catch {
    authRenewDialog.preview = null
  } finally {
    authRenewDialog.previewLoading = false
  }
}

async function submitAuthRenew() {
  if (!editDialog.row?.id || !authRenewDialog.row?.id) return
  if (!authRenewDialog.preview) {
    ElMessage.warning('请先预览扣点')
    return
  }

  authRenewDialog.loading = true

  try {
    await userApi.renewAuth(
      editDialog.row.id,
      authRenewDialog.row.id,
      {
        valid_until: isoOrNull(authRenewDialog.form.valid_until),
      },
      authRenewDialog.idempotencyKey || newIdempotencyKey('renew')
    )

    ElMessage.success('项目授权已续费')
    authRenewDialog.visible = false
    resetAuthRenewPreview()

    await Promise.all([
      loadEditAuths(),
      loadUsers(),
    ])
  } finally {
    authRenewDialog.loading = false
  }
}

async function previewAuthLevelUpgrade() {
  if (!editDialog.row?.id || !authLevelDialog.row?.id) return
  if (!authLevelDialog.form.user_level) {
    ElMessage.warning('请选择升级后的等级')
    return
  }

  authLevelDialog.previewLoading = true

  try {
    const res = await userApi.levelUpgradePreview(editDialog.row.id, authLevelDialog.row.id, {
      user_level: authLevelDialog.form.user_level,
    })
    authLevelDialog.preview = res.data
    authLevelDialog.idempotencyKey = newIdempotencyKey('level-upgrade')
  } catch {
    authLevelDialog.preview = null
  } finally {
    authLevelDialog.previewLoading = false
  }
}

async function submitAuthLevelUpgrade() {
  if (!editDialog.row?.id || !authLevelDialog.row?.id) return
  if (!authLevelDialog.preview) {
    ElMessage.warning('请先预览扣点')
    return
  }

  authLevelDialog.loading = true

  try {
    await userApi.levelUpgradeAuth(
      editDialog.row.id,
      authLevelDialog.row.id,
      {
        user_level: authLevelDialog.form.user_level,
      },
      authLevelDialog.idempotencyKey || newIdempotencyKey('level-upgrade')
    )

    ElMessage.success('项目授权等级已升级')
    authLevelDialog.visible = false
    resetAuthLevelPreview()

    await Promise.all([
      loadEditAuths(),
      loadUsers(),
    ])
  } finally {
    authLevelDialog.loading = false
  }
}

async function suspendUserAuth(row) {
  if (!editDialog.row?.id || !row?.id) return

  await userApi.suspendAuth(editDialog.row.id, row.id)
  ElMessage.success('项目授权已停用，剩余权益已冻结')

  await Promise.all([
    loadEditAuths(),
    loadUsers(),
  ])
}

async function enableUserAuth(row) {
  if (!editDialog.row?.id || !row?.id) return

  await userApi.enableAuth(editDialog.row.id, row.id)
  ElMessage.success('项目授权已启用，冻结权益已释放')

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

async function openFromRouteFocusUser() {
  const raw = route.query?.focus_user_id
  const focusUserId = Number(raw)
  if (!Number.isInteger(focusUserId) || focusUserId <= 0) return

  const clearFocusQuery = async () => {
    const nextQuery = { ...route.query }
    delete nextQuery.focus_user_id
    await router.replace({ path: '/users', query: nextQuery })
  }

  const hit = users.value.find(item => Number(item.id) === focusUserId)
  if (hit) {
    await openEditDialog(hit)
    await clearFocusQuery()
    return
  }

  try {
    const res = await userApi.detail(focusUserId)
    await openEditDialog(normalizeUserRow(res.data || {}))
  } catch {
    ElMessage.warning('未找到目标用户')
  } finally {
    await clearFocusQuery()
  }
}

onMounted(async () => {
  await loadLookups()
  await loadUsers()
  await openFromRouteFocusUser()
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

.batch-list-panel {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.batch-chip {
  display: grid;
  grid-template-columns: 90px repeat(3, minmax(0, 1fr));
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
  color: #475569;
  font-size: 12px;
}

.batch-chip strong {
  color: #1e293b;
}

.mode-explain {
  width: 100%;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.governance-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.auth-device-panel {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #e2e8f0;
}

.governance-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 32px;
}

.auth-device-panel .governance-row {
  align-items: flex-start;
  justify-content: space-between;
}

.device-action-group {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
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

.cost-preview-panel {
  max-width: 520px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.preview-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: #1e293b;
}

.preview-grid {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 6px 12px;
  margin-bottom: 10px;
  color: #64748b;
}

.preview-grid strong {
  color: #0f172a;
}

.upgrade-preview-panel {
  margin: 4px 0 16px 120px;
}

.finance-panel {
  margin-top: 16px;
}

.compact-pager {
  margin-top: 12px;
}

.mono-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

@media (max-width: 900px) {
  .page-header {
    flex-direction: column;
    gap: 12px;
  }

  .placeholder-grid {
    grid-template-columns: 1fr;
  }

  .batch-chip {
    grid-template-columns: 1fr;
  }

  .upgrade-preview-panel {
    margin-left: 0;
  }
}
</style>
