<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>代理管理</h2>
        <p class="page-desc">
          代理是项目售卖与用户授权主体；组织层级用于代理树关系，业务等级用于项目准入、授信建议、自动开通能力和代理治理。用户数量仅作统计，实际业务限制以项目准入、项目授权、点数余额和授权扣点规则为准。
        </p>
      </div>

      <el-button
        v-if="auth.isAdmin"
        type="primary"
        :icon="Plus"
        @click="openCreateDialog"
      >
        新建代理
      </el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width:120px">
            <el-option label="正常" value="active" />
            <el-option label="已停用" value="suspended" />
          </el-select>
        </el-form-item>

        <el-form-item label="项目">
          <el-select v-model="filter.project_id" clearable filterable placeholder="全部项目" style="width:180px">
            <el-option v-for="p in allProjects" :key="p.id" :label="p.display_name" :value="p.id" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadAgents">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
          <el-button :icon="Refresh" :loading="loading" @click="loadAgents">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div v-if="selectedIds.length > 0" class="batch-toolbar">
      <span class="batch-info">已选 {{ selectedIds.length }} 条</span>
      <el-popconfirm :title="`确认删除 ${selectedIds.length} 个代理？`" @confirm="batchDelete">
        <template #reference>
          <el-button type="danger" size="small" :loading="batchLoading">批量删除</el-button>
        </template>
      </el-popconfirm>
      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="agents"
        row-key="id"
        stripe
        style="width:100%"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" />

        <el-table-column prop="username" label="代理名" min-width="145">
          <template #default="{ row }">
            <button class="agent-link" type="button" @click="goDetail(row)">
              {{ row.username }}
            </button>
            <div class="agent-id">ID: {{ row.id }}</div>
          </template>
        </el-table-column>

        <el-table-column label="组织层级" width="90">
          <template #default="{ row }">
            <el-tag type="info" effect="plain" size="small">Lv.{{ row.hierarchy_depth }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="业务等级" width="130">
          <template #default="{ row }">
            <template v-if="row.business_profile">
              <el-tooltip placement="top">
                <template #content>
                  <div class="level-tip">
                    <div>业务等级：Lv.{{ row.business_profile.tier_level }}</div>
                    <div>等级名称：{{ row.business_profile.tier_name }}</div>
                    <div>默认授信：{{ numberText(row.business_profile.credit_limit) }}</div>
                    <div>最高授信：{{ numberText(row.business_profile.max_credit_limit) }}</div>
                  </div>
                </template>
                <el-tag type="primary" effect="light" size="small">
                  {{ row.business_profile.tier_name }}
                </el-tag>
              </el-tooltip>
            </template>
            <el-tag v-else type="info" effect="plain" size="small">未加载</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="风险状态" width="100">
          <template #default="{ row }">
            <el-tag
              :type="riskStatusType(row.business_profile?.risk_status)"
              effect="light"
              size="small"
            >
              {{ riskStatusText(row.business_profile?.risk_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <StatusBadge :status="row.status" type="agent" />
          </template>
        </el-table-column>

        <el-table-column label="已授权项目" min-width="250">
          <template #default="{ row }">
            <div v-if="!row.authorized_projects?.length" class="no-data">未授权项目</div>
            <div v-else class="project-list">
              <el-tooltip
                v-for="p in row.authorized_projects"
                :key="p.project_id"
                :content="`${p.display_name} 直属授权用户数: ${p.user_count ?? 0} 人${p.valid_until ? '  到期: ' + fmtDate(p.valid_until) : '  永久'}`"
                placement="top"
              >
                <div class="proj-badge">
                  <el-tag
                    size="small"
                    effect="light"
                    :type="p.project_type === 'game' ? 'primary' : 'info'"
                  >
                    {{ p.display_name }}
                  </el-tag>
                  <span class="proj-user-count">{{ p.user_count ?? 0 }}人</span>
                </div>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="用户数" width="90" align="center">
          <template #default="{ row }">
            <span class="user-count">{{ row.users_count ?? 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column label="可用点数" width="130" align="right">
          <template #default="{ row }">
            <span :class="row.balance?.available_total > 0 ? 'pts-positive' : 'pts-zero'">
              {{ numberText(row.balance?.available_total) }}
            </span>
            <div class="pts-detail">
              充值 {{ numberText(row.balance?.charged_points) }} +
              授信 {{ numberText((row.balance?.credit_points ?? 0) - (row.balance?.frozen_credit ?? 0)) }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDatetime(row.created_at) }}</template>
        </el-table-column>

        <el-table-column v-if="auth.isAdmin" label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="goDetail(row)">详情</el-button>
            <el-button text size="small" type="primary" @click="openEditDrawer(row)">编辑</el-button>
            <el-button
              text
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm title="确认删除该代理？" @confirm="deleteAgent(row)">
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
        @size-change="loadAgents"
        @current-change="loadAgents"
      />
    </el-card>

    <!-- 新建代理弹窗 -->
    <el-dialog
      v-model="createDialog.visible"
      title="新建代理"
      width="620px"
      destroy-on-close
    >
      <el-form
        ref="createFormRef"
        :model="createDialog.form"
        :rules="createRules"
        label-width="105px"
        autocomplete="off"
      >
        <input type="text" style="display:none" tabindex="-1" aria-hidden="true" />
        <input type="password" style="display:none" tabindex="-1" aria-hidden="true" />

        <el-divider content-position="left">账号主体</el-divider>

        <el-form-item label="代理名" prop="username">
          <el-input
            v-model="createDialog.form.username"
            :name="'agent_name_' + createDialog._uid"
            autocomplete="new-password"
            placeholder="请输入代理名"
            clearable
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="createDialog.form.password"
            :name="'agent_pwd_' + createDialog._uid"
            type="password"
            show-password
            autocomplete="new-password"
            placeholder="请输入密码"
          />
        </el-form-item>

        <el-form-item label="上级代理 ID">
          <el-input-number
            v-model="createDialog.form.parent_agent_id"
            :min="1"
            controls-position="right"
            placeholder="留空=顶级代理"
            style="width:100%"
          />
          <div class="field-hint">留空则创建为顶级代理（直属管理员）。</div>
        </el-form-item>

        <el-divider content-position="left">基础属性</el-divider>

        <el-form-item label="佣金比例">
          <el-input-number
            v-model="createDialog.form.commission_rate"
            :min="0"
            :max="100"
            :precision="2"
            controls-position="right"
            style="width:100%"
          />
          <div class="field-hint">单位：%（留空不设置）。</div>
        </el-form-item>

        <el-divider content-position="left">业务画像</el-divider>

        <el-form-item label="业务等级" prop="tier_level">
          <el-select v-model="createDialog.form.tier_level" style="width:100%">
            <el-option
              v-for="item in levelPolicies"
              :key="item.level"
              :label="`${item.level_name}`"
              :value="item.level"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="风险状态" prop="risk_status">
          <el-select v-model="createDialog.form.risk_status" style="width:100%">
            <el-option label="正常 normal" value="normal" />
            <el-option label="观察 watch" value="watch" />
            <el-option label="限制 restricted" value="restricted" />
            <el-option label="冻结 frozen" value="frozen" />
          </el-select>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="createDialog.form.remark"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="可记录代理来源、合作说明、风险备注等"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="createDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createDialog.loading" @click="submitCreate">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 统一编辑抽屉 -->
    <el-drawer
      v-model="editDrawer.visible"
      size="760px"
      :title="editDrawer.agent ? `编辑代理 — ${editDrawer.agent.username}` : '编辑代理'"
      destroy-on-close
    >
      <div v-loading="editDrawer.loading" class="drawer-body">
        <template v-if="editDrawer.agent">
          <div class="drawer-head">
            <div class="drawer-avatar">
              {{ editDrawer.agent.username.charAt(0).toUpperCase() }}
            </div>
            <div class="drawer-meta">
              <div class="drawer-name">{{ editDrawer.agent.username }}</div>
              <div class="drawer-sub">
                ID: {{ editDrawer.agent.id }}
                <span class="dot">·</span>
                组织层级 Lv.{{ editDrawer.agent.hierarchy_depth }}
                <span class="dot">·</span>
                {{ editDrawer.agent.status === 'active' ? '正常' : '已停用' }}
              </div>
            </div>
          </div>

          <el-tabs v-model="editDrawer.activeTab" class="drawer-tabs">
            <!-- 基础信息 -->
            <el-tab-pane label="基础信息" name="base">
              <el-form label-width="120px" :model="editDrawer.baseForm">
                <el-form-item label="账号状态">
                  <el-select v-model="editDrawer.baseForm.status" style="width:100%">
                    <el-option label="正常 active" value="active" />
                    <el-option label="停用 suspended" value="suspended" />
                  </el-select>
                </el-form-item>

                <el-form-item label="佣金比例">
                  <el-input-number
                    v-model="editDrawer.baseForm.commission_rate"
                    :min="0"
                    :max="100"
                    :precision="2"
                    controls-position="right"
                    style="width:100%"
                  />
                  <div class="field-hint">单位：%。</div>
                </el-form-item>

                <el-form-item label="组织层级">
                  <el-tag type="info" effect="plain">Lv.{{ editDrawer.agent.hierarchy_depth }}</el-tag>
                  <div class="field-hint">组织层级由代理树决定，不在这里直接修改。</div>
                </el-form-item>

                <el-form-item label="上级代理 ID">
                  <span v-if="editDrawer.agent.parent_agent_id" class="mono">
                    {{ editDrawer.agent.parent_agent_id }}
                  </span>
                  <span v-else class="muted">顶级代理</span>
                </el-form-item>

                <el-form-item>
                  <el-button
                    type="primary"
                    :loading="editDrawer.saveLoading"
                    @click="saveBaseAndProfile"
                  >
                    保存基础信息
                  </el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 业务画像 -->
            <el-tab-pane label="业务画像" name="profile">
              <el-form label-width="145px" :model="editDrawer.profileForm">
                <el-form-item label="业务等级">
                  <el-select v-model="editDrawer.profileForm.tier_level" style="width:100%">
                    <el-option
                      v-for="item in levelPolicies"
                      :key="item.level"
                      :label="`${item.level_name}`"
                      :value="item.level"
                    />
                  </el-select>
                </el-form-item>

                <el-form-item label="风险状态">
                  <el-select v-model="editDrawer.profileForm.risk_status" style="width:100%">
                    <el-option label="正常 normal" value="normal" />
                    <el-option label="观察 watch" value="watch" />
                    <el-option label="限制 restricted" value="restricted" />
                    <el-option label="冻结 frozen" value="frozen" />
                  </el-select>
                </el-form-item>

                <el-divider content-position="left">能力覆盖</el-divider>

                <el-form-item label="默认授信覆盖">
                  <el-input-number
                    v-model="editDrawer.profileForm.credit_limit_override"
                    :min="0"
                    :precision="2"
                    controls-position="right"
                    style="width:100%"
                  />
                  <div class="field-hint">留空表示使用业务等级策略默认值。</div>
                </el-form-item>

                <el-form-item label="最高授信覆盖">
                  <el-input-number
                    v-model="editDrawer.profileForm.max_credit_limit_override"
                    :min="0"
                    :precision="2"
                    controls-position="right"
                    style="width:100%"
                  />
                  <div class="field-hint">留空表示使用业务等级策略默认值。</div>
                </el-form-item>

                <el-form-item label="下级创建覆盖">
                  <el-select
                    v-model="editDrawer.profileForm.can_create_sub_agents_override"
                    clearable
                    placeholder="使用等级策略"
                    style="width:100%"
                  >
                    <el-option label="使用等级策略" :value="null" />
                    <el-option label="允许" :value="true" />
                    <el-option label="不允许" :value="false" />
                  </el-select>
                </el-form-item>

                <el-form-item label="最大下级覆盖">
                  <el-input-number
                    v-model="editDrawer.profileForm.max_sub_agents_override"
                    :min="0"
                    controls-position="right"
                    style="width:100%"
                  />
                  <div class="field-hint">留空表示使用业务等级策略默认值。</div>
                </el-form-item>

                <el-form-item label="备注">
                  <el-input
                    v-model="editDrawer.profileForm.remark"
                    type="textarea"
                    :rows="4"
                    maxlength="2000"
                    show-word-limit
                  />
                </el-form-item>

                <el-form-item>
                  <el-button
                    type="primary"
                    :loading="editDrawer.saveLoading"
                    @click="saveBaseAndProfile"
                  >
                    保存业务画像
                  </el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 密码 -->
            <el-tab-pane label="修改密码" name="password">
              <el-alert
                title="自动生成密码时，明文只会在本次响应中返回，请复制后妥善保存。"
                type="warning"
                show-icon
                :closable="false"
                class="inner-alert"
              />

              <el-form label-width="120px" :model="editDrawer.passwordForm">
                <el-form-item label="重置方式">
                  <el-radio-group v-model="editDrawer.passwordForm.auto_generate">
                    <el-radio :label="true">自动生成</el-radio>
                    <el-radio :label="false">手动设置</el-radio>
                  </el-radio-group>
                </el-form-item>

                <el-form-item
                  v-if="!editDrawer.passwordForm.auto_generate"
                  label="新密码"
                >
                  <el-input
                    v-model="editDrawer.passwordForm.new_password"
                    type="password"
                    show-password
                    autocomplete="new-password"
                    placeholder="请输入至少 6 位新密码"
                  />
                </el-form-item>

                <el-form-item>
                  <el-button
                    type="danger"
                    :loading="editDrawer.passwordLoading"
                    @click="resetAgentPassword"
                  >
                    重置密码
                  </el-button>
                </el-form-item>

                <el-form-item v-if="editDrawer.generatedPassword" label="生成密码">
                  <el-input
                    :model-value="editDrawer.generatedPassword"
                    readonly
                  >
                    <template #append>
                      <el-button @click="copyGeneratedPassword">复制</el-button>
                    </template>
                  </el-input>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 授权项目 -->
            <el-tab-pane label="授权项目" name="projects">
              <div class="section-title-row">
                <span class="section-title">已授权项目</span>
                <el-button size="small" :icon="Refresh" @click="loadEditProjectAuths">刷新</el-button>
              </div>

              <el-table
                v-loading="editDrawer.projectLoading"
                :data="editDrawer.projectAuths"
                size="small"
                stripe
                empty-text="暂无授权项目"
              >
                <el-table-column label="项目名称" min-width="150">
                  <template #default="{ row }">
                    {{ row.project_display_name || row.project_name || row.display_name || '—' }}
                  </template>
                </el-table-column>

                <el-table-column label="类型" width="90">
                  <template #default="{ row }">
                    <el-tag
                      :type="row.project_type === 'game' ? 'primary' : 'info'"
                      effect="plain"
                      size="small"
                    >
                      {{ row.project_type === 'game' ? '游戏' : '验证' }}
                    </el-tag>
                  </template>
                </el-table-column>

                <el-table-column label="到期" width="150">
                  <template #default="{ row }">
                    {{ row.valid_until ? fmtDate(row.valid_until) : '永久' }}
                  </template>
                </el-table-column>

                <el-table-column label="状态" width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="light" size="small">
                      {{ row.status === 'active' ? '有效' : '已停用' }}
                    </el-tag>
                  </template>
                </el-table-column>

                <el-table-column width="80" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      text
                      size="small"
                      type="danger"
                      :disabled="row.status !== 'active'"
                      @click="revokeEditAuth(row)"
                    >
                      停用
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>

              <el-divider content-position="left">新增项目授权</el-divider>

              <el-form ref="editAuthFormRef" :model="editDrawer.authForm" :rules="authRules" label-width="90px">
                <el-form-item label="选择项目" prop="project_id">
                  <el-select
                    v-model="editDrawer.authForm.project_id"
                    placeholder="请选择项目"
                    filterable
                    style="width:100%"
                  >
                    <el-option
                      v-for="p in allProjects"
                      :key="p.id"
                      :label="`${p.display_name}（${p.project_type === 'game' ? '游戏' : '验证'}）`"
                      :value="p.id"
                    />
                  </el-select>
                </el-form-item>

                <el-form-item label="到期时间">
                  <div class="expiry-picker-wrap">
                    <div class="quick-btns">
                      <el-button size="small" @click="setEditAuthExpiry(30)">一个月</el-button>
                      <el-button size="small" @click="setEditAuthExpiry(90)">三个月</el-button>
                      <el-button size="small" @click="setEditAuthExpiry(365)">一年</el-button>
                      <el-button size="small" type="info" plain @click="editDrawer.authForm.valid_until = null">
                        永久
                      </el-button>
                    </div>
                    <el-date-picker
                      v-model="editDrawer.authForm.valid_until"
                      type="datetime"
                      placeholder="不填为永久有效"
                      style="width:100%"
                    />
                  </div>
                </el-form-item>

                <el-form-item>
                  <el-button
                    type="primary"
                    :loading="editDrawer.grantLoading"
                    @click="grantEditAuth"
                  >
                    授予权限
                  </el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 点数管理 -->
            <el-tab-pane label="点数管理" name="balance">
              <div class="balance-summary" v-loading="editDrawer.balanceLoading">
                <div class="balance-item charged">
                  <div class="bal-num">{{ numberText(editDrawer.balance?.charged_points) }}</div>
                  <div class="bal-lbl">充值点数</div>
                </div>
                <div class="balance-item credit">
                  <div class="bal-num">{{ numberText(editDrawer.balance?.credit_points) }}</div>
                  <div class="bal-lbl">授信点数</div>
                </div>
                <div class="balance-item frozen">
                  <div class="bal-num">{{ numberText(editDrawer.balance?.frozen_credit) }}</div>
                  <div class="bal-lbl">已冻结授信</div>
                </div>
                <div class="balance-item total">
                  <div class="bal-num highlight">{{ numberText(editDrawer.balance?.available_total) }}</div>
                  <div class="bal-lbl">可用余额</div>
                </div>
              </div>

              <el-tabs v-model="editDrawer.balanceTab" class="balance-tabs">
                <el-tab-pane label="充值" name="recharge">
                  <el-form :model="editDrawer.rechargeForm" label-width="80px" style="margin-top:12px">
                    <el-form-item label="充值点数">
                      <el-input-number
                        v-model="editDrawer.rechargeForm.amount"
                        :min="0.01"
                        :precision="2"
                        :step="100"
                        controls-position="right"
                        style="width:220px"
                      />
                      <div class="quick-btns inline-quick">
                        <el-button size="small" @click="editDrawer.rechargeForm.amount = 100">100</el-button>
                        <el-button size="small" @click="editDrawer.rechargeForm.amount = 500">500</el-button>
                        <el-button size="small" @click="editDrawer.rechargeForm.amount = 1000">1000</el-button>
                        <el-button size="small" @click="editDrawer.rechargeForm.amount = 5000">5000</el-button>
                      </div>
                    </el-form-item>

                    <el-form-item label="备注">
                      <el-input
                        v-model="editDrawer.rechargeForm.description"
                        placeholder="线下付款备注，如：微信转账 ¥100"
                      />
                    </el-form-item>

                    <el-form-item>
                      <el-button
                        type="primary"
                        :loading="editDrawer.balanceOpLoading"
                        @click="doEditRecharge"
                      >
                        确认充值
                      </el-button>
                    </el-form-item>
                  </el-form>
                </el-tab-pane>

                <el-tab-pane label="授信" name="credit">
                  <el-form :model="editDrawer.creditForm" label-width="80px" style="margin-top:12px">
                    <el-form-item label="授信点数">
                      <el-input-number
                        v-model="editDrawer.creditForm.amount"
                        :min="0.01"
                        :precision="2"
                        :step="100"
                        controls-position="right"
                        style="width:220px"
                      />
                    </el-form-item>

                    <el-form-item label="备注">
                      <el-input v-model="editDrawer.creditForm.description" placeholder="授信原因" />
                    </el-form-item>

                    <el-form-item>
                      <el-button
                        type="warning"
                        :loading="editDrawer.balanceOpLoading"
                        @click="doEditCredit"
                      >
                        确认授信
                      </el-button>
                    </el-form-item>
                  </el-form>
                </el-tab-pane>

                <el-tab-pane label="冻结/解冻" name="freeze">
                  <el-form :model="editDrawer.freezeForm" label-width="80px" style="margin-top:12px">
                    <el-form-item label="操作金额">
                      <el-input-number
                        v-model="editDrawer.freezeForm.amount"
                        :min="0.01"
                        :precision="2"
                        controls-position="right"
                        style="width:220px"
                      />
                    </el-form-item>

                    <el-form-item label="备注">
                      <el-input v-model="editDrawer.freezeForm.description" placeholder="冻结/解冻原因" />
                    </el-form-item>

                    <el-form-item>
                      <el-button
                        type="danger"
                        :loading="editDrawer.balanceOpLoading"
                        @click="doEditFreeze"
                      >
                        冻结授信
                      </el-button>
                      <el-button
                        :loading="editDrawer.balanceOpLoading"
                        style="margin-left:12px"
                        @click="doEditUnfreeze"
                      >
                        解冻授信
                      </el-button>
                    </el-form-item>
                  </el-form>
                </el-tab-pane>

                <el-tab-pane label="流水记录" name="txlog">
                  <el-table
                    v-loading="editDrawer.txLoading"
                    :data="editDrawer.transactions"
                    size="small"
                    max-height="320"
                    stripe
                    empty-text="暂无流水"
                    style="margin-top:8px"
                  >
                    <el-table-column label="时间" width="140">
                      <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
                    </el-table-column>
                    <el-table-column label="类型" width="75">
                      <template #default="{ row }">
                        <el-tag size="small" effect="light">{{ row.tx_type_label || row.tx_type }}</el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column label="余额类型" width="90">
                      <template #default="{ row }">
                        {{ row.balance_type === 'charged' ? '充值' : '授信' }}
                      </template>
                    </el-table-column>
                    <el-table-column label="变动" width="90" align="right">
                      <template #default="{ row }">
                        <span :class="Number(row.amount || 0) >= 0 ? 'amt-pos' : 'amt-neg'">
                          {{ Number(row.amount || 0) >= 0 ? '+' : '' }}{{ numberText(row.amount) }}
                        </span>
                      </template>
                    </el-table-column>
                    <el-table-column label="变后余额" width="100" align="right">
                      <template #default="{ row }">{{ numberText(row.balance_after) }}</template>
                    </el-table-column>
                    <el-table-column label="说明" min-width="160" show-overflow-tooltip>
                      <template #default="{ row }">{{ row.business_text || row.description || '—' }}</template>
                    </el-table-column>
                  </el-table>
                </el-tab-pane>
              </el-tabs>
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/AgentList.vue
 * 名称: 代理管理
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.5.0
 * 功能说明:
 *   管理员代理管理列表。
 *   融合代理基础信息、业务画像、密码重置、项目授权、点数管理。
 *
 * 当前业务口径:
 *   - Agent.level 表示组织层级。
 *   - AgentBusinessProfile.tier_level 表示业务等级。
 *   - 用户数量仅作统计展示。
 *   - 代理业务能力由项目授权、项目准入、点数余额、授权扣点和风险治理决定。
 */

import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '@/api/agent'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { adminBalanceApi as balanceApi } from '@/api/admin/balance'
import { adminAgentProfileApi } from '@/api/admin/agentProfile'
import { useAuthStore } from '@/stores/auth'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { formatDatetime } from '@/utils/format'

const auth = useAuthStore()
const router = useRouter()

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
}) : '—'

const numberText = (value) => Number(value || 0).toFixed(2)

const normalizeNullableText = (value) => {
  const text = String(value ?? '').trim()
  return text ? text : null
}

const normalizeNullableNumber = (value) => {
  if (value === null || value === undefined || value === '') return null
  return Number(value)
}

const riskStatusText = (status) => {
  const map = {
    normal: '正常',
    watch: '观察',
    restricted: '限制',
    frozen: '冻结',
  }
  return map[status] || '未知'
}

const riskStatusType = (status) => {
  const map = {
    normal: 'success',
    watch: 'warning',
    restricted: 'danger',
    frozen: 'info',
  }
  return map[status] || 'info'
}

const goDetail = (row) => {
  router.push(`/agents/${row.id}`)
}

// ── 等级策略 ────────────────────────────────────────────────
const DEFAULT_LEVELS = [
  { level: 1, level_name: 'Lv.1 新手代理' },
  { level: 2, level_name: 'Lv.2 标准代理' },
  { level: 3, level_name: 'Lv.3 核心代理' },
  { level: 4, level_name: 'Lv.4 渠道代理' },
]
const levelPolicies = ref([...DEFAULT_LEVELS])

const loadLevelPolicies = async () => {
  try {
    const res = await adminAgentProfileApi.levelPolicies()
    if (Array.isArray(res.data) && res.data.length) {
      levelPolicies.value = res.data
    }
  } catch { /* keep defaults */ }
}

// ── 项目列表 ────────────────────────────────────────────────
const allProjects = ref([])

const loadAllProjects = async () => {
  const res = await projectApi.list({ page: 1, page_size: 100, is_active: true })
  allProjects.value = res.data.projects || []
}

// ── 列表 ────────────────────────────────────────────────────
const loading = ref(false)
const agents = ref([])
const selectedIds = ref([])
const batchLoading = ref(false)
const filter = reactive({ status: null, project_id: null })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const enrichAgentsWithProfiles = async (rows) => {
  if (!rows.length) return []

  const results = await Promise.allSettled(
    rows.map(row => adminAgentProfileApi.businessProfile(row.id))
  )

  return rows.map((row, index) => {
    const result = results[index]
    const profile = result.status === 'fulfilled' ? result.value.data : null

    return {
      ...row,
      business_profile: profile,
    }
  })
}

const loadAgents = async () => {
  loading.value = true

  try {
    await loadLevelPolicies()

    let rows = []
    if (auth.isAdmin) {
      const res = await balanceApi.agentsFull({
        page: pagination.page,
        page_size: pagination.pageSize,
        status: filter.status || undefined,
      })
      rows = res.data.agents || []
      pagination.total = res.data.total || 0
      if (filter.project_id) {
        rows = rows.filter(ag =>
          (ag.project_auths || ag.authorized_projects || []).some(p => p.project_id === filter.project_id)
        )
      }
      agents.value = await enrichAgentsWithProfiles(rows)
    } else {
      // 代理只查看自己下级
      const res = await agentApi.scopeList({
        page: pagination.page,
        page_size: pagination.pageSize,
        status: filter.status || undefined,
      })
      rows = res.data.agents || []
      pagination.total = res.data.total || 0
      agents.value = rows
    }
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filter.status = null
  filter.project_id = null
  pagination.page = 1
  loadAgents()
}

const onSelectionChange = (rows) => {
  selectedIds.value = rows.map(r => r.id)
}

onMounted(loadAgents)

const batchDelete = async () => {
  batchLoading.value = true
  const ids = [...selectedIds.value]

  try {
    const results = await Promise.allSettled(ids.map(id => agentApi.delete(id)))
    const failed = results.filter(r => r.status === 'rejected').length
    const success = results.filter(r => r.status === 'fulfilled').length

    if (failed === 0) {
      ElMessage.success(`已删除 ${success} 个`)
    } else {
      ElMessage.warning(`成功 ${success}，失败 ${failed}`)
    }
    selectedIds.value = []
    loadAgents()
  } finally {
    batchLoading.value = false
  }
}

const deleteAgent = async (row) => {
  await agentApi.delete(row.id)
  ElMessage.success('已删除')
  loadAgents()
}

const batchToggleStatus = async () => {
  batchLoading.value = true
  const ids = [...selectedIds.value]

  try {
    const results = await Promise.allSettled(
      ids.map(id => agentApi.update(id, { status: 'suspended' }))
    )
    const failed = results.filter(r => r.status === 'rejected').length
    const success = results.filter(r => r.status === 'fulfilled').length

    if (failed === 0) {
      ElMessage.success(`已停用 ${success} 个`)
    } else {
      ElMessage.warning(`成功 ${success}，失败 ${failed}`)
    }

    selectedIds.value = []
    loadAgents()
  } finally {
    batchLoading.value = false
  }
}

const toggleStatus = async (row) => {
  await agentApi.update(row.id, {
    status: row.status === 'active' ? 'suspended' : 'active',
  })
  ElMessage.success('操作成功')
  loadAgents()
}

// ── 新建代理 ────────────────────────────────────────────────
const createFormRef = ref(null)

const createDialog = reactive({
  visible: false,
  loading: false,
  _uid: Date.now(),
  form: {
    username: '',
    password: '',
    parent_agent_id: null,
    commission_rate: null,
    tier_level: 1,
    risk_status: 'normal',
    remark: '',
  },
})

const createRules = {
  username: [{ required: true, message: '请输入代理名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  tier_level: [{ required: true, message: '请选择业务等级', trigger: 'change' }],
  risk_status: [{ required: true, message: '请选择风险状态', trigger: 'change' }],
}

const openCreateDialog = async () => {
  await loadLevelPolicies()

  createDialog.form = {
    username: '',
    password: '',
    parent_agent_id: null,
    commission_rate: null,
    tier_level: 1,
    risk_status: 'normal',
    remark: '',
  }

  createDialog._uid = Date.now()
  createDialog.visible = true
}

const submitCreate = async () => {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  createDialog.loading = true

  try {
    const createRes = await agentApi.create({
      username: createDialog.form.username,
      password: createDialog.form.password,
      parent_agent_id: createDialog.form.parent_agent_id || null,
      commission_rate: createDialog.form.commission_rate,
    })

    const newAgentId = createRes.data?.id
    if (newAgentId) {
      await adminAgentProfileApi.updateBusinessProfile(newAgentId, {
        tier_level: createDialog.form.tier_level,
        risk_status: createDialog.form.risk_status,
        remark: normalizeNullableText(createDialog.form.remark),
      })
    }

    ElMessage.success('代理创建成功')
    createDialog.visible = false
    loadAgents()
    // 自动打开编辑抽屉进行项目授权
    if (newAgentId) {
      setTimeout(() => openEditDrawer({ id: newAgentId, username: createDialog.form.username }), 300)
    }
    await loadAgents()
  } finally {
    createDialog.loading = false
  }
}

// ── 统一编辑抽屉 ────────────────────────────────────────────
const editAuthFormRef = ref(null)

const editDrawer = reactive({
  visible: false,
  loading: false,
  saveLoading: false,
  passwordLoading: false,
  projectLoading: false,
  grantLoading: false,
  balanceLoading: false,
  balanceOpLoading: false,
  txLoading: false,

  activeTab: 'base',
  balanceTab: 'recharge',

  agent: null,
  profile: null,
  balance: null,
  projectAuths: [],
  transactions: [],
  generatedPassword: '',

  baseForm: {
    status: 'active',
    commission_rate: null,
  },

  profileForm: {
    tier_level: 1,
    risk_status: 'normal',
    remark: '',
    credit_limit_override: null,
    max_credit_limit_override: null,
    can_create_sub_agents_override: null,
    max_sub_agents_override: null,
  },

  passwordForm: {
    auto_generate: true,
    new_password: '',
  },

  authForm: {
    project_id: null,
    valid_until: null,
  },

  rechargeForm: {
    amount: 100,
    description: '',
  },

  creditForm: {
    amount: 100,
    description: '',
  },

  freezeForm: {
    amount: 100,
    description: '',
  },
})

const authRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
}

const resetEditDrawerState = () => {
  editDrawer.generatedPassword = ''
  editDrawer.activeTab = 'base'
  editDrawer.balanceTab = 'recharge'
  editDrawer.projectAuths = []
  editDrawer.transactions = []
  editDrawer.balance = null
  editDrawer.authForm = { project_id: null, valid_until: null }
  editDrawer.passwordForm = { auto_generate: true, new_password: '' }
  editDrawer.rechargeForm = { amount: 100, description: '' }
  editDrawer.creditForm = { amount: 100, description: '' }
  editDrawer.freezeForm = { amount: 100, description: '' }
}

// 业务等级变更 → 自动填充能力默认值
watch(() => editDrawer.profileForm?.tier_level, (newLevel) => {
  if (!newLevel) return
  const policy = levelPolicies.value.find(p => p.level === newLevel)
  if (!policy) return
  if (editDrawer.profileForm.credit_limit_override == null)
    editDrawer.profileForm.credit_limit_override = policy.default_credit_limit
  if (editDrawer.profileForm.max_credit_limit_override == null)
    editDrawer.profileForm.max_credit_limit_override = policy.max_credit_limit
  if (editDrawer.profileForm.can_create_sub_agents_override == null)
    editDrawer.profileForm.can_create_sub_agents_override = policy.can_create_sub_agents
  if (editDrawer.profileForm.max_sub_agents_override == null)
    editDrawer.profileForm.max_sub_agents_override = policy.max_sub_agents
})

const openEditDrawer = async (row) => {
  resetEditDrawerState()

  editDrawer.visible = true
  editDrawer.loading = true
  editDrawer.agent = row

  try {
    await loadLevelPolicies()
    await loadAllProjects()

    const [detailRes, profileRes] = await Promise.all([
      agentApi.detail(row.id),
      adminAgentProfileApi.businessProfile(row.id),
    ])

    editDrawer.agent = detailRes.data
    editDrawer.profile = profileRes.data

    editDrawer.baseForm = {
      status: detailRes.data.status,
      commission_rate: detailRes.data.commission_rate,
    }

    editDrawer.profileForm = {
      tier_level: profileRes.data?.tier_level || 1,
      risk_status: profileRes.data?.risk_status || 'normal',
      remark: profileRes.data?.remark || '',
      credit_limit_override: profileRes.data?.credit_limit_override ?? null,
      max_credit_limit_override: profileRes.data?.max_credit_limit_override ?? null,
      can_create_sub_agents_override: profileRes.data?.can_create_sub_agents_override ?? null,
      max_sub_agents_override: profileRes.data?.max_sub_agents_override ?? null,
    }

    await Promise.all([
      loadEditProjectAuths(),
      loadEditBalance(),
      loadEditTransactions(),
    ])
  } finally {
    editDrawer.loading = false
  }
}

const saveBaseAndProfile = async () => {
  if (!editDrawer.agent) return

  editDrawer.saveLoading = true

  try {
    await agentApi.update(editDrawer.agent.id, {
      status: editDrawer.baseForm.status,
      commission_rate: editDrawer.baseForm.commission_rate,
    })

    await adminAgentProfileApi.updateBusinessProfile(editDrawer.agent.id, {
      tier_level: editDrawer.profileForm.tier_level,
      risk_status: editDrawer.profileForm.risk_status,
      remark: normalizeNullableText(editDrawer.profileForm.remark),
      credit_limit_override: normalizeNullableNumber(editDrawer.profileForm.credit_limit_override),
      max_credit_limit_override: normalizeNullableNumber(editDrawer.profileForm.max_credit_limit_override),
      can_create_sub_agents_override: editDrawer.profileForm.can_create_sub_agents_override,
      max_sub_agents_override: normalizeNullableNumber(editDrawer.profileForm.max_sub_agents_override),
    })

    ElMessage.success('代理信息已保存')

    const [detailRes, profileRes] = await Promise.all([
      agentApi.detail(editDrawer.agent.id),
      adminAgentProfileApi.businessProfile(editDrawer.agent.id),
    ])

    editDrawer.agent = detailRes.data
    editDrawer.profile = profileRes.data

    await loadAgents()
  } finally {
    editDrawer.saveLoading = false
  }
}

const resetAgentPassword = async () => {
  if (!editDrawer.agent) return

  if (!editDrawer.passwordForm.auto_generate && !editDrawer.passwordForm.new_password) {
    ElMessage.warning('请输入新密码')
    return
  }

  editDrawer.passwordLoading = true
  editDrawer.generatedPassword = ''

  try {
    const res = await adminAgentProfileApi.resetPassword(editDrawer.agent.id, {
      auto_generate: editDrawer.passwordForm.auto_generate,
      new_password: editDrawer.passwordForm.auto_generate
        ? null
        : editDrawer.passwordForm.new_password,
    })

    editDrawer.generatedPassword = res.data?.generated_password || ''
    editDrawer.passwordForm.new_password = ''

    if (editDrawer.generatedPassword) {
      ElMessage.success('密码已重置，请复制生成密码')
    } else {
      ElMessage.success('密码已重置')
    }
  } finally {
    editDrawer.passwordLoading = false
  }
}

const copyGeneratedPassword = async () => {
  if (!editDrawer.generatedPassword) return

  await navigator.clipboard.writeText(editDrawer.generatedPassword)
  ElMessage.success('已复制')
}

// ── 编辑抽屉：项目授权 ──────────────────────────────────────
const loadEditProjectAuths = async () => {
  if (!editDrawer.agent) return

  editDrawer.projectLoading = true

  try {
    const res = await projectApi.listAgentAuths(editDrawer.agent.id)
    editDrawer.projectAuths = Array.isArray(res.data) ? res.data : []
  } finally {
    editDrawer.projectLoading = false
  }
}

const setEditAuthExpiry = (days) => {
  const d = new Date()
  d.setDate(d.getDate() + days)
  editDrawer.authForm.valid_until = d
}

const grantEditAuth = async () => {
  if (!editDrawer.agent) return

  const valid = await editAuthFormRef.value?.validate().catch(() => false)
  if (!valid) return

  editDrawer.grantLoading = true

  try {
    await projectApi.grantAgentAuth(editDrawer.agent.id, {
      project_id: editDrawer.authForm.project_id,
      valid_until: editDrawer.authForm.valid_until || null,
    })

    ElMessage.success('项目授权成功')
    editDrawer.authForm = { project_id: null, valid_until: null }

    await Promise.all([
      loadEditProjectAuths(),
      loadAgents(),
    ])
  } finally {
    editDrawer.grantLoading = false
  }
}

const revokeEditAuth = async (authRow) => {
  if (!editDrawer.agent) return

  await projectApi.revokeAgentAuth(editDrawer.agent.id, authRow.id)
  ElMessage.success('已停用项目授权')

  await Promise.all([
    loadEditProjectAuths(),
    loadAgents(),
  ])
}

// ── 编辑抽屉：点数 ──────────────────────────────────────────
const loadEditBalance = async () => {
  if (!editDrawer.agent) return

  editDrawer.balanceLoading = true

  try {
    const res = await balanceApi.getBalance(editDrawer.agent.id)
    editDrawer.balance = res.data
  } finally {
    editDrawer.balanceLoading = false
  }
}

const loadEditTransactions = async () => {
  if (!editDrawer.agent) return

  editDrawer.txLoading = true

  try {
    const res = await balanceApi.getTransactions(editDrawer.agent.id, {
      page: 1,
      page_size: 50,
    })
    editDrawer.transactions = res.data.transactions || []
  } finally {
    editDrawer.txLoading = false
  }
}

const doEditRecharge = async () => {
  if (!editDrawer.agent) return

  editDrawer.balanceOpLoading = true

  try {
    const res = await balanceApi.recharge(editDrawer.agent.id, {
      amount: editDrawer.rechargeForm.amount,
      description: editDrawer.rechargeForm.description || undefined,
    })

    editDrawer.balance = res.data
    editDrawer.rechargeForm = { amount: 100, description: '' }

    ElMessage.success(`充值成功，可用余额：${numberText(res.data.available_total)} 点`)

    await Promise.all([
      loadEditTransactions(),
      loadAgents(),
    ])
  } finally {
    editDrawer.balanceOpLoading = false
  }
}

const doEditCredit = async () => {
  if (!editDrawer.agent) return

  editDrawer.balanceOpLoading = true

  try {
    const res = await balanceApi.credit(editDrawer.agent.id, {
      amount: editDrawer.creditForm.amount,
      description: editDrawer.creditForm.description || undefined,
    })

    editDrawer.balance = res.data
    editDrawer.creditForm = { amount: 100, description: '' }

    ElMessage.success('授信成功')

    await Promise.all([
      loadEditTransactions(),
      loadAgents(),
    ])
  } finally {
    editDrawer.balanceOpLoading = false
  }
}

const doEditFreeze = async () => {
  if (!editDrawer.agent) return

  editDrawer.balanceOpLoading = true

  try {
    const res = await balanceApi.freeze(editDrawer.agent.id, {
      amount: editDrawer.freezeForm.amount,
      description: editDrawer.freezeForm.description || undefined,
    })

    editDrawer.balance = res.data

    ElMessage.warning(`已冻结 ${numberText(editDrawer.freezeForm.amount)} 点授信`)

    await Promise.all([
      loadEditTransactions(),
      loadAgents(),
    ])
  } finally {
    editDrawer.balanceOpLoading = false
  }
}

const doEditUnfreeze = async () => {
  if (!editDrawer.agent) return

  editDrawer.balanceOpLoading = true

  try {
    const res = await balanceApi.unfreeze(editDrawer.agent.id, {
      amount: editDrawer.freezeForm.amount,
      description: editDrawer.freezeForm.description || undefined,
    })

    editDrawer.balance = res.data

    ElMessage.success(`已解冻 ${numberText(editDrawer.freezeForm.amount)} 点`)

    await Promise.all([
      loadEditTransactions(),
      loadAgents(),
    ])
  } finally {
    editDrawer.balanceOpLoading = false
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

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
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

.agent-link {
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

.agent-link:hover {
  text-decoration: underline;
}

.agent-id {
  margin-top: 2px;
  font-size: 11px;
  color: #94a3b8;
}

.level-tip {
  line-height: 1.8;
}

.field-hint {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.no-data {
  font-size: 12px;
  color: #94a3b8;
}

.project-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.proj-badge {
  display: flex;
  align-items: center;
  gap: 3px;
  background: #f8fafc;
  border-radius: 6px;
  padding: 1px 4px 1px 2px;
  cursor: default;
}

.proj-user-count {
  font-size: 11px;
  color: #6366f1;
  font-weight: 600;
  white-space: nowrap;
}

.user-count {
  font-weight: 700;
  color: #334155;
}

.pts-positive {
  color: #10b981;
  font-weight: 600;
  font-size: 13px;
}

.pts-zero {
  color: #94a3b8;
  font-size: 13px;
}

.pts-detail {
  font-size: 10px;
  color: #94a3b8;
  margin-top: 1px;
}

.drawer-body {
  padding-bottom: 32px;
}

.drawer-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid #e2e8f0;
}

.drawer-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drawer-name {
  font-size: 18px;
  font-weight: 800;
  color: #1e293b;
}

.drawer-sub {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.dot {
  margin: 0 5px;
  color: #cbd5e1;
}

.drawer-tabs {
  margin-top: 14px;
}

.inner-alert {
  margin-bottom: 14px;
  border-radius: 8px;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

.muted {
  color: #94a3b8;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.expiry-picker-wrap {
  width: 100%;
}

.quick-btns {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.inline-quick {
  margin-top: 6px;
  margin-bottom: 0;
}

.balance-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.balance-item {
  background: #f8fafc;
  border-radius: 8px;
  padding: 12px 8px;
  text-align: center;
  border-top: 3px solid transparent;
}

.balance-item.charged {
  border-color: #6366f1;
}

.balance-item.credit {
  border-color: #f59e0b;
}

.balance-item.frozen {
  border-color: #94a3b8;
}

.balance-item.total {
  border-color: #10b981;
}

.bal-num {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
}

.bal-num.highlight {
  color: #10b981;
}

.bal-lbl {
  margin-top: 4px;
  font-size: 11px;
  color: #64748b;
}

.amt-pos {
  color: #10b981;
  font-weight: 600;
}

.amt-neg {
  color: #ef4444;
  font-weight: 600;
}
</style>
