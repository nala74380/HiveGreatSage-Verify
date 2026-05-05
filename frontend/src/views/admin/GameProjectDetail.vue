<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <div class="breadcrumb-line">
          <el-button text size="small" @click="$router.push('/projects')">
            ← 返回项目管理
          </el-button>
        </div>

        <h2>项目详情</h2>
        <p class="page-desc">
          项目详情页承载单项目全量能力：概览、定价、准入策略、授权申请、热更新。
        </p>
      </div>

      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">
          刷新
        </el-button>
      </div>
    </div>

    <template v-if="project">
      <el-card shadow="never" class="info-card">
        <div class="project-head">
          <div class="project-avatar">
            {{ project.project_type === 'game' ? '🎮' : '🔑' }}
          </div>

          <div class="project-main">
            <div class="project-title-row">
              <span class="project-name">{{ project.display_name }}</span>

              <el-tag
                :type="project.project_type === 'game' ? 'primary' : 'info'"
                effect="plain"
                size="small"
              >
                {{ project.project_type === 'game' ? '游戏项目' : '普通验证项目' }}
              </el-tag>

              <el-tag
                :type="project.is_active ? 'success' : 'info'"
                effect="light"
                size="small"
              >
                {{ project.is_active ? '启用' : '停用' }}
              </el-tag>
            </div>

            <div class="project-sub">
              ID: {{ project.id }}
              <span class="dot">·</span>
              项目代号：<span class="mono">{{ project.code_name }}</span>
              <span class="dot">·</span>
              创建时间：{{ formatDatetime(project.created_at) }}
            </div>
          </div>
        </div>

        <el-divider />

        <el-descriptions :column="2" size="small">
          <el-descriptions-item label="项目 UUID">
            <span class="mono uuid-text">{{ project.project_uuid }}</span>
            <el-button
              text
              size="small"
              :icon="CopyDocument"
              @click="copyText(project.project_uuid, 'UUID 已复制')"
            />
          </el-descriptions-item>

          <el-descriptions-item label="数据库名">
            <template v-if="project.db_name">
              <span class="mono db-name">{{ project.db_name }}</span>
              <el-button
                text
                size="small"
                :icon="CopyDocument"
                @click="copyText(project.db_name, '数据库名已复制')"
              />
            </template>
            <span v-else class="muted">无独立数据库</span>
          </el-descriptions-item>

          <el-descriptions-item label="项目名称">
            {{ project.display_name }}
          </el-descriptions-item>

          <el-descriptions-item label="项目状态">
            {{ project.is_active ? '启用' : '停用' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-row :gutter="12">
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-num">{{ project.authorized_user_count ?? 0 }}</div>
            <div class="stat-label">已授权用户</div>
          </div>
        </el-col>

        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-num">{{ project.authorized_agent_count ?? 0 }}</div>
            <div class="stat-label">已授权代理</div>
          </div>
        </el-col>

        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-num">{{ pendingRequestCount }}</div>
            <div class="stat-label">待审核申请</div>
          </div>
        </el-col>

        <el-col :span="6">
          <div class="stat-card" :class="{ highlight: project.is_active }">
            <div class="stat-num">{{ project.is_active ? '启用' : '停用' }}</div>
            <div class="stat-label">当前状态</div>
          </div>
        </el-col>
      </el-row>

      <el-card shadow="never" class="tab-card">
        <el-tabs v-model="activeTab">
          <!-- 概览 -->
          <el-tab-pane label="概览" name="overview">
            <div class="overview-grid">
              <div class="overview-block">
                <div class="block-title">基础信息</div>

                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item label="项目 ID">
                    {{ project.id }}
                  </el-descriptions-item>

                  <el-descriptions-item label="项目名称">
                    {{ project.display_name }}
                  </el-descriptions-item>

                  <el-descriptions-item label="项目代号">
                    <span class="mono">{{ project.code_name }}</span>
                  </el-descriptions-item>

                  <el-descriptions-item label="项目类型">
                    {{ project.project_type === 'game' ? '游戏项目' : '普通验证项目' }}
                  </el-descriptions-item>

                  <el-descriptions-item label="项目状态">
                    {{ project.is_active ? '启用' : '停用' }}
                  </el-descriptions-item>

                  <el-descriptions-item label="创建时间">
                    {{ formatDatetime(project.created_at) }}
                  </el-descriptions-item>
                </el-descriptions>
              </div>

              <div class="overview-block">
                <div class="block-title">功能概览</div>

                <div class="action-grid">
                  <el-button type="primary" plain @click="activeTab = 'pricing'">
                    定价
                  </el-button>
                  <el-button type="primary" plain @click="activeTab = 'access'">
                    准入策略
                  </el-button>
                  <el-button type="primary" plain @click="activeTab = 'requests'">
                    授权申请
                  </el-button>
                  <el-button type="primary" plain @click="activeTab = 'updates'">
                    热更新
                  </el-button>
                </div>

                <el-alert
                  title="项目 UUID 是跨端稳定标识，普通编辑不允许变更或重新生成。"
                  type="info"
                  show-icon
                  :closable="false"
                  class="inner-alert overview-alert"
                />
              </div>
            </div>
          </el-tab-pane>

          <!-- 定价 -->
          <el-tab-pane label="定价" name="pricing">
            <el-alert
              title="试用按周计费；普通 / VIP / SVIP 按月计费。未设置价格时，代理不能对此级别进行扣点授权。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-table
              v-loading="priceLoading"
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
                  <div v-if="priceEdit.level === row.user_level" class="edit-cell">
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

                    <el-button size="small" @click="cancelPriceEdit">
                      取消
                    </el-button>
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

              <el-table-column label="说明" min-width="280">
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

          <!-- 准入策略 -->
          <el-tab-pane label="准入策略" name="access">
            <el-alert
              title="项目开通本身不扣点；代理给用户授权项目时才扣点。隐藏项目不会出现在代理项目目录中。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-form
              v-loading="accessLoading"
              :model="accessForm"
              label-width="150px"
              class="access-form"
            >
              <el-form-item label="可见性模式">
                <el-select v-model="accessForm.visibility_mode" style="width:300px">
                  <el-option label="公开可见：所有代理可见" value="public" />
                  <el-option label="等级限制：达到等级才可见" value="level_limited" />
                  <el-option label="指定代理：仅邀请代理可见" value="invite_only" />
                  <el-option label="隐藏：代理端不展示" value="hidden" />
                </el-select>
              </el-form-item>

              <el-form-item label="开通模式">
                <el-select v-model="accessForm.open_mode" style="width:300px">
                  <el-option label="必须审核" value="manual_review" />
                  <el-option label="按等级自动开通" value="auto_by_level" />
                  <el-option label="按条件自动开通" value="auto_by_condition" />
                  <el-option label="禁止申请" value="disabled" />
                </el-select>
              </el-form-item>

              <el-divider content-position="left">等级门槛</el-divider>

              <el-form-item label="最低可见业务等级">
                <el-input-number
                  v-model="accessForm.min_visible_agent_level"
                  :min="1"
                  :max="4"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="最低申请业务等级">
                <el-input-number
                  v-model="accessForm.min_apply_agent_level"
                  :min="1"
                  :max="4"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="最低自动开通等级">
                <el-select
                  v-model="accessForm.min_auto_open_agent_level"
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
                  v-model="accessForm.min_available_points"
                  :min="0"
                  :precision="2"
                  :step="100"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="是否允许申请">
                <el-switch v-model="accessForm.allow_apply" />
              </el-form-item>

              <el-form-item label="是否允许自动开通">
                <el-switch v-model="accessForm.allow_auto_open" />
              </el-form-item>

              <el-form-item label="申请理由必填">
                <el-switch v-model="accessForm.require_request_reason" />
              </el-form-item>

              <el-form-item label="拒绝后冷却小时">
                <el-input-number
                  v-model="accessForm.cooldown_hours_after_reject"
                  :min="0"
                  :step="1"
                  controls-position="right"
                />
              </el-form-item>

              <el-form-item label="策略启用">
                <el-switch v-model="accessForm.is_active" />
              </el-form-item>

              <el-alert
                v-if="accessForm.visibility_mode === 'hidden'"
                title="隐藏项目会自动禁止申请和自动开通；代理项目目录不会展示该项目。"
                type="warning"
                show-icon
                :closable="false"
                class="small-alert"
              />

              <el-alert
                v-if="accessForm.open_mode === 'auto_by_condition'"
                title="按条件自动开通会额外校验最低可用点数。"
                type="info"
                show-icon
                :closable="false"
                class="small-alert"
              />

              <el-form-item class="access-save-row">
                <el-button
                  type="primary"
                  :loading="accessSaving"
                  @click="submitAccessPolicy"
                >
                  保存准入策略
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- 授权申请 -->
          <el-tab-pane label="授权申请" name="requests">
            <div class="request-toolbar">
              <el-form inline :model="requestFilter">
                <el-form-item label="状态">
                  <el-select
                    v-model="requestFilter.status"
                    clearable
                    placeholder="全部状态"
                    style="width:150px"
                  >
                    <el-option label="待审核" value="pending" />
                    <el-option label="已通过" value="approved" />
                    <el-option label="已拒绝" value="rejected" />
                    <el-option label="已取消" value="cancelled" />
                    <el-option label="自动通过" value="auto_approved" />
                  </el-select>
                </el-form-item>

                <el-form-item label="代理 ID">
                  <el-input-number
                    v-model="requestFilter.agent_id"
                    :min="1"
                    controls-position="right"
                    style="width:130px"
                  />
                </el-form-item>

                <el-form-item>
                  <el-button type="primary" @click="searchRequests">查询</el-button>
                  <el-button @click="resetRequestFilter">重置</el-button>
                  <el-button :icon="Refresh" :loading="requestsLoading" @click="loadRequests">
                    刷新
                  </el-button>
                </el-form-item>
              </el-form>
            </div>

            <el-alert
              title="授权申请属于审核流。批准后会自动写入代理项目授权；项目开通本身不扣点，代理给用户授权项目时才扣点。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-table
              v-loading="requestsLoading"
              :data="requests"
              stripe
              row-key="id"
              style="width:100%"
              empty-text="暂无授权申请"
            >
              <el-table-column prop="id" label="ID" width="70" />

              <el-table-column label="代理" min-width="150">
                <template #default="{ row }">
                  <div class="main-text">{{ row.agent_username || `ID=${row.agent_id}` }}</div>
                  <div class="sub-text">ID={{ row.agent_id }} · 业务等级 Lv.{{ row.agent_level || '-' }}</div>
                </template>
              </el-table-column>

              <el-table-column label="项目" min-width="170">
                <template #default="{ row }">
                  <div class="main-text">{{ row.project_name || project.display_name }}</div>
                  <div class="sub-text">{{ row.project_code || project.code_name || '-' }}</div>
                </template>
              </el-table-column>

              <el-table-column label="状态" width="105">
                <template #default="{ row }">
                  <el-tag :type="requestStatusType(row.status)" effect="light">
                    {{ requestStatusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column label="申请说明" min-width="240" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.request_reason">{{ row.request_reason }}</span>
                  <span v-else class="muted">未填写</span>
                </template>
              </el-table-column>

              <el-table-column label="审核信息" min-width="260">
                <template #default="{ row }">
                  <template v-if="row.status === 'auto_approved'">
                    <div class="main-text">系统自动通过</div>
                    <div class="sub-text">{{ row.auto_approve_reason || '—' }}</div>
                  </template>

                  <template v-else-if="row.reviewed_at">
                    <div class="main-text">
                      {{ row.reviewed_by_admin_username || `管理员ID=${row.reviewed_by_admin_id}` }}
                    </div>
                    <div class="sub-text">{{ formatDatetime(row.reviewed_at) }}</div>
                    <div v-if="row.review_note" class="review-note">{{ row.review_note }}</div>
                  </template>

                  <span v-else class="muted">待审核</span>
                </template>
              </el-table-column>

              <el-table-column label="申请时间" width="160">
                <template #default="{ row }">
                  {{ formatDatetime(row.created_at) }}
                </template>
              </el-table-column>

              <el-table-column label="操作" width="145" fixed="right">
                <template #default="{ row }">
                  <template v-if="row.status === 'pending'">
                    <el-button text size="small" type="success" @click="openApprove(row)">
                      批准
                    </el-button>
                    <el-button text size="small" type="danger" @click="openReject(row)">
                      拒绝
                    </el-button>
                  </template>
                  <span v-else class="muted">无操作</span>
                </template>
              </el-table-column>
            </el-table>

            <div class="pager-row">
              <span class="total-text">共 {{ requestPagination.total }} 条</span>
              <el-pagination
                v-model:current-page="requestPagination.page"
                v-model:page-size="requestPagination.pageSize"
                :page-sizes="[20, 50, 100]"
                layout="sizes, prev, pager, next"
                :total="requestPagination.total"
                @current-change="loadRequests"
                @size-change="loadRequests"
              />
            </div>
          </el-tab-pane>

          <!-- 热更新 -->
          <el-tab-pane label="热更新" name="updates">
            <el-alert
              title="热更新按项目维度管理，PC 端和安卓端分别维护版本。上传后会刷新最新版本和历史记录。"
              type="info"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-row :gutter="16">
              <el-col :span="12">
                <el-card shadow="never" class="client-card">
                  <template #header>
                    <div class="card-header-row">
                      <span class="card-title">🖥 PC 端</span>
                      <el-tag
                        v-if="versions.pc"
                        :type="versions.pc.force_update ? 'danger' : 'success'"
                        effect="plain"
                        size="small"
                      >
                        v{{ versions.pc.version }}{{ versions.pc.force_update ? ' 强制' : '' }}
                      </el-tag>
                      <el-tag v-else type="info" effect="plain" size="small">暂无版本</el-tag>
                    </div>
                  </template>

                  <div v-loading="versionsLoading">
                    <div v-if="versions.pc" class="version-info">
                      <el-descriptions :column="1" size="small" border>
                        <el-descriptions-item label="版本号">
                          <span class="mono">{{ versions.pc.version }}</span>
                        </el-descriptions-item>
                        <el-descriptions-item label="发布时间">
                          {{ formatDatetime(versions.pc.released_at) }}
                        </el-descriptions-item>
                        <el-descriptions-item label="SHA-256">
                          <span class="mono muted">
                            {{ versions.pc.checksum_sha256?.slice(0, 20) }}…
                          </span>
                        </el-descriptions-item>
                        <el-descriptions-item label="强制更新">
                          <el-tag :type="versions.pc.force_update ? 'danger' : 'success'" size="small">
                            {{ versions.pc.force_update ? '是' : '否' }}
                          </el-tag>
                        </el-descriptions-item>
                        <el-descriptions-item v-if="versions.pc.release_notes" label="更新说明">
                          {{ versions.pc.release_notes }}
                        </el-descriptions-item>
                      </el-descriptions>
                    </div>

                    <el-empty v-else description="暂未发布 PC 端版本" :image-size="60" />
                  </div>

                  <el-divider content-position="left">发布新版本</el-divider>

                  <UploadVersionForm
                    client-type="pc"
                    :project-id="project.id"
                    @uploaded="loadVersions"
                  />
                </el-card>
              </el-col>

              <el-col :span="12">
                <el-card shadow="never" class="client-card">
                  <template #header>
                    <div class="card-header-row">
                      <span class="card-title">📱 安卓端</span>
                      <el-tag
                        v-if="versions.android"
                        :type="versions.android.force_update ? 'danger' : 'success'"
                        effect="plain"
                        size="small"
                      >
                        v{{ versions.android.version }}{{ versions.android.force_update ? ' 强制' : '' }}
                      </el-tag>
                      <el-tag v-else type="info" effect="plain" size="small">暂无版本</el-tag>
                    </div>
                  </template>

                  <div v-loading="versionsLoading">
                    <div v-if="versions.android" class="version-info">
                      <el-descriptions :column="1" size="small" border>
                        <el-descriptions-item label="版本号">
                          <span class="mono">{{ versions.android.version }}</span>
                        </el-descriptions-item>
                        <el-descriptions-item label="发布时间">
                          {{ formatDatetime(versions.android.released_at) }}
                        </el-descriptions-item>
                        <el-descriptions-item label="SHA-256">
                          <span class="mono muted">
                            {{ versions.android.checksum_sha256?.slice(0, 20) }}…
                          </span>
                        </el-descriptions-item>
                        <el-descriptions-item label="强制更新">
                          <el-tag :type="versions.android.force_update ? 'danger' : 'success'" size="small">
                            {{ versions.android.force_update ? '是' : '否' }}
                          </el-tag>
                        </el-descriptions-item>
                        <el-descriptions-item v-if="versions.android.release_notes" label="更新说明">
                          {{ versions.android.release_notes }}
                        </el-descriptions-item>
                      </el-descriptions>
                    </div>

                    <el-empty v-else description="暂未发布安卓端版本" :image-size="60" />
                  </div>

                  <el-divider content-position="left">发布新版本</el-divider>

                  <UploadVersionForm
                    client-type="android"
                    :project-id="project.id"
                    @uploaded="loadVersions"
                  />
                </el-card>
              </el-col>
            </el-row>

            <el-card shadow="never" class="inner-card">
              <template #header>
                <div class="card-header-row">
                  <span class="card-title">版本历史</span>
                  <el-radio-group v-model="historyClientType" size="small" @change="loadHistory">
                    <el-radio-button label="pc">PC 端</el-radio-button>
                    <el-radio-button label="android">安卓端</el-radio-button>
                  </el-radio-group>
                </div>
              </template>

              <el-table v-loading="historyLoading" :data="versionHistory" size="small">
                <el-table-column prop="version" label="版本号" width="130">
                  <template #default="{ row }">
                    <span class="mono">{{ row.version }}</span>
                    <el-tag
                      v-if="row.is_active"
                      type="success"
                      size="small"
                      effect="dark"
                      style="margin-left:6px"
                    >
                      当前
                    </el-tag>
                  </template>
                </el-table-column>

                <el-table-column label="强制更新" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.force_update ? 'danger' : 'info'" size="small" effect="plain">
                      {{ row.force_update ? '强制' : '可选' }}
                    </el-tag>
                  </template>
                </el-table-column>

                <el-table-column prop="release_notes" label="更新说明" min-width="180" show-overflow-tooltip />

                <el-table-column label="发布时间" width="155">
                  <template #default="{ row }">
                    {{ formatDatetime(row.released_at) }}
                  </template>
                </el-table-column>
              </el-table>

              <el-empty
                v-if="!versionHistory.length && !historyLoading"
                description="暂无版本历史"
                :image-size="60"
              />
            </el-card>
          </el-tab-pane>

          <!-- 用户功能 -->
          <el-tab-pane label="用户功能" name="features">
            <el-alert
              title="各授权等级在不同项目类型下的功能权限。游戏项目支持完整功能，验证项目仅支持基础验证。"
              type="info" show-icon :closable="false" class="inner-alert"
            />
            <el-table :data="featureTable" border size="small" style="margin-top:16px">
              <el-table-column prop="feature" label="功能 / 权限" width="160" fixed />
              <el-table-column label="试用" width="100" align="center">
                <template #default="{ row }">{{ row.trial }}</template>
              </el-table-column>
              <el-table-column label="普通" width="100" align="center">
                <template #default="{ row }">{{ row.normal }}</template>
              </el-table-column>
              <el-table-column label="VIP" width="100" align="center">
                <template #default="{ row }">{{ row.vip }}</template>
              </el-table-column>
              <el-table-column label="SVIP" width="100" align="center">
                <template #default="{ row }">{{ row.svip }}</template>
              </el-table-column>
              <el-table-column label="测试" width="100" align="center">
                <template #default="{ row }">{{ row.tester }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <!-- 批准申请 -->
      <el-dialog
        v-model="approveDialog.visible"
        title="批准项目开通申请"
        width="560px"
        destroy-on-close
      >
        <el-form label-width="115px">
          <el-form-item label="代理">
            <span class="main-text">{{ approveDialog.row?.agent_username || `ID=${approveDialog.row?.agent_id}` }}</span>
          </el-form-item>

          <el-form-item label="项目">
            <span class="main-text">{{ approveDialog.row?.project_name || project.display_name }}</span>
          </el-form-item>

          <el-form-item label="授权到期时间">
            <el-date-picker
              v-model="approveDialog.form.valid_until"
              type="datetime"
              placeholder="不填表示永久有效"
              style="width:100%"
            />
          </el-form-item>

          <el-form-item label="审核备注">
            <el-input
              v-model="approveDialog.form.review_note"
              type="textarea"
              :rows="4"
              maxlength="1000"
              show-word-limit
              placeholder="可填写批准原因或备注。"
            />
          </el-form-item>

          <el-alert
            title="批准后会自动写入 agent_project_auth，代理端项目目录会显示为已授权。项目开通本身不扣点。"
            type="success"
            show-icon
            :closable="false"
          />
        </el-form>

        <template #footer>
          <el-button @click="approveDialog.visible = false">取消</el-button>
          <el-button type="success" :loading="approveDialog.loading" @click="submitApprove">
            批准
          </el-button>
        </template>
      </el-dialog>

      <!-- 拒绝申请 -->
      <el-dialog
        v-model="rejectDialog.visible"
        title="拒绝项目开通申请"
        width="560px"
        destroy-on-close
      >
        <el-form label-width="100px">
          <el-form-item label="代理">
            <span class="main-text">{{ rejectDialog.row?.agent_username || `ID=${rejectDialog.row?.agent_id}` }}</span>
          </el-form-item>

          <el-form-item label="项目">
            <span class="main-text">{{ rejectDialog.row?.project_name || project.display_name }}</span>
          </el-form-item>

          <el-form-item label="拒绝原因">
            <el-input
              v-model="rejectDialog.form.review_note"
              type="textarea"
              :rows="5"
              maxlength="1000"
              show-word-limit
              placeholder="请填写拒绝原因，代理端可看到该审核备注。"
            />
          </el-form-item>
        </el-form>

        <template #footer>
          <el-button @click="rejectDialog.visible = false">取消</el-button>
          <el-button type="danger" :loading="rejectDialog.loading" @click="submitReject">
            拒绝
          </el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/GameProjectDetail.vue
 * 名称: 项目详情页
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V1.2.0
 * 功能说明:
 *   管理员查看并管理单项目全量能力：
 *     - 概览
 *     - 定价
 *     - 准入策略
 *     - 授权申请
 *     - 热更新
 *
 * 当前业务口径:
 *   - 项目详情页是单项目能力承载页。
 *   - 项目定价和项目准入在详情页可直接配置。
 *   - 授权申请在详情页按当前项目过滤并审核。
 *   - 热更新在详情页按当前项目发布 PC / 安卓版本。
 *   - 项目 UUID 是跨端稳定标识，不允许普通变更或重新生成。
 */

import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import { adminBalanceApi as balanceApi } from '@/api/admin/balance'
import { adminProjectAccessApi } from '@/api/admin/projectAccess'
import http from '@/api/http'
import { formatDatetime } from '@/utils/format'
import UploadVersionForm from '@/components/common/UploadVersionForm.vue'

const route = useRoute()

const LEVELS = ['trial', 'normal', 'vip', 'svip']

const PRESETS = {
  standard: {
    trial: 0.01,
    normal: 2.00,
    vip: 3.50,
    svip: 5.00,
  },
}

const loading = ref(false)
const activeTab = ref('overview')
const project = ref(null)

const featureTable = computed(() => {
  const isGame = project.value?.project_type === 'game'
  return [
    { feature: '基础验证登录', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✓' },
    { feature: 'Token 自动刷新', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✓' },
    { feature: '设备心跳上报', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✓' },
    { feature: '脚本参数同步', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✓' },
    { feature: '热更新检查', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✓' },
    { feature: 'PC 中控连接', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✓' },
    { feature: '游戏自动化脚本', trial: isGame ? '✓' : '✗', normal: isGame ? '✓' : '✗', vip: isGame ? '✓' : '✗', svip: isGame ? '✓' : '✗', tester: isGame ? '✓' : '✗' },
    { feature: '设备数量上限', trial: '100', normal: '500', vip: '1000', svip: '无限', tester: '无限' },
    { feature: '代理可见', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✗' },
    { feature: '代理可管理', trial: '✓', normal: '✓', vip: '✓', svip: '✓', tester: '✗' },
    { feature: '代理可计费', trial: '✓', normal: '✓', vip: '✓', svip: '✗', tester: '✗' },
  ]
})

const projectId = computed(() => Number(route.params.id))

const copyText = async (text, message = '已复制') => {
  if (!text) return

  await navigator.clipboard.writeText(text)
  ElMessage.success(message)
}

const syncTabFromQuery = () => {
  const tab = String(route.query.tab || '')
  if (['overview', 'pricing', 'access', 'requests', 'updates'].includes(tab)) {
    activeTab.value = tab
  }
}

// ── 项目基础信息 ────────────────────────────────────────────
const loadProject = async () => {
  if (!projectId.value) return

  const res = await projectApi.detail(projectId.value)
  project.value = res.data
}

// ── 定价 ────────────────────────────────────────────────────
const priceLoading = ref(false)
const prices = ref([])

const priceEdit = reactive({
  level: null,
  value: 0,
  saving: false,
})

const visiblePrices = computed(() => {
  return (prices.value || []).filter(row => LEVELS.includes(row.user_level))
})

const loadPrices = async () => {
  if (!projectId.value) return

  priceLoading.value = true

  try {
    const res = await balanceApi.getPrices(projectId.value)
    prices.value = (res.data || []).filter(row => LEVELS.includes(row.user_level))
  } finally {
    priceLoading.value = false
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
    await balanceApi.setPrice(projectId.value, level, {
      points_per_device: Number(Number(priceEdit.value).toFixed(2)),
    })

    ElMessage.success('定价已保存')
    cancelPriceEdit()
    await loadPrices()
  } finally {
    priceEdit.saving = false
  }
}

const removePrice = async (level) => {
  await ElMessageBox.confirm(`确认清除 ${levelName(level)} 的定价？`, '确认', { type: 'warning' })
  await balanceApi.deletePrice(projectId.value, level)
  ElMessage.success('已清除')
  await loadPrices()
}

const applyPreset = async (presetName) => {
  const preset = PRESETS[presetName]

  if (!preset) {
    await Promise.all(
      LEVELS.map(level =>
        balanceApi.setPrice(projectId.value, level, { points_per_device: 0.00 }),
      ),
    )
  } else {
    await Promise.all(
      Object.entries(preset).map(([level, pts]) =>
        balanceApi.setPrice(projectId.value, level, {
          points_per_device: Number(Number(pts).toFixed(2)),
        }),
      ),
    )
  }

  ElMessage.success('批量设置成功')
  await loadPrices()
}

const clearAllPrices = async () => {
  await ElMessageBox.confirm('确认清除该项目全部定价？', '确认', { type: 'warning' })

  await Promise.all(
    LEVELS.map(level => balanceApi.deletePrice(projectId.value, level).catch(() => {})),
  )

  ElMessage.success('已清除全部定价')
  await loadPrices()
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

// ── 准入策略 ────────────────────────────────────────────────
const accessLoading = ref(false)
const accessSaving = ref(false)
const accessRow = ref(null)

const defaultAccessForm = () => ({
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
})

const accessForm = reactive(defaultAccessForm())

const resetAccessForm = (data = defaultAccessForm()) => {
  Object.assign(accessForm, data)
}

const loadAccessPolicy = async () => {
  if (!projectId.value) return

  accessLoading.value = true

  try {
    const res = await adminProjectAccessApi.policies({
      page: 1,
      page_size: 500,
    })

    const rows = res.data.policies || []
    const row = rows.find(item => Number(item.project_id) === Number(projectId.value))

    accessRow.value = row || null

    if (row) {
      resetAccessForm({
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
      })
    } else {
      resetAccessForm()
    }
  } finally {
    accessLoading.value = false
  }
}

const validateAccessForm = () => {
  if (accessForm.allow_auto_open && !['auto_by_level', 'auto_by_condition'].includes(accessForm.open_mode)) {
    ElMessage.warning('允许自动开通时，开通模式必须选择“按等级自动”或“按条件自动”')
    return false
  }

  if (['auto_by_level', 'auto_by_condition'].includes(accessForm.open_mode) && !accessForm.min_auto_open_agent_level) {
    ElMessage.warning('自动开通模式下必须设置最低自动开通等级')
    return false
  }

  if (accessForm.min_apply_agent_level < accessForm.min_visible_agent_level) {
    ElMessage.warning('最低申请等级不应低于最低可见等级')
    return false
  }

  return true
}

const submitAccessPolicy = async () => {
  if (!validateAccessForm()) return

  accessSaving.value = true

  try {
    await adminProjectAccessApi.updatePolicy(projectId.value, accessForm)
    ElMessage.success('项目准入策略已保存')
    await loadAccessPolicy()
  } finally {
    accessSaving.value = false
  }
}

// ── 授权申请 ────────────────────────────────────────────────
const requestsLoading = ref(false)
const requests = ref([])

const requestFilter = reactive({
  status: '',
  agent_id: null,
})

const requestPagination = reactive({
  page: 1,
  pageSize: 50,
  total: 0,
})

const approveDialog = reactive({
  visible: false,
  loading: false,
  row: null,
  form: {
    valid_until: null,
    review_note: '',
  },
})

const rejectDialog = reactive({
  visible: false,
  loading: false,
  row: null,
  form: {
    review_note: '',
  },
})

const pendingRequestCount = computed(() => {
  return requests.value.filter(item => item.status === 'pending').length
})

const requestStatusLabel = (status) => {
  const map = {
    pending: '待审核',
    approved: '已通过',
    rejected: '已拒绝',
    cancelled: '已取消',
    auto_approved: '自动通过',
  }
  return map[status] || status
}

const requestStatusType = (status) => {
  const map = {
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    cancelled: 'info',
    auto_approved: 'success',
  }
  return map[status] || 'info'
}

const loadRequests = async () => {
  if (!projectId.value) return

  requestsLoading.value = true

  try {
    const res = await adminProjectAccessApi.requests({
      page: requestPagination.page,
      page_size: requestPagination.pageSize,
      status: requestFilter.status || undefined,
      agent_id: requestFilter.agent_id || undefined,
      project_id: projectId.value,
    })

    requests.value = res.data.requests || []
    requestPagination.total = res.data.total || 0
  } finally {
    requestsLoading.value = false
  }
}

const searchRequests = () => {
  requestPagination.page = 1
  loadRequests()
}

const resetRequestFilter = () => {
  requestFilter.status = ''
  requestFilter.agent_id = null
  requestPagination.page = 1
  loadRequests()
}

const openApprove = (row) => {
  approveDialog.row = row
  approveDialog.form = {
    valid_until: null,
    review_note: '',
  }
  approveDialog.visible = true
}

const submitApprove = async () => {
  approveDialog.loading = true

  try {
    await adminProjectAccessApi.approveRequest(approveDialog.row.id, {
      valid_until: approveDialog.form.valid_until || null,
      review_note: approveDialog.form.review_note || null,
    })

    ElMessage.success('已批准申请，并开通代理项目授权')
    approveDialog.visible = false

    await Promise.all([
      loadRequests(),
      loadProject(),
    ])
  } finally {
    approveDialog.loading = false
  }
}

const openReject = (row) => {
  rejectDialog.row = row
  rejectDialog.form = {
    review_note: '',
  }
  rejectDialog.visible = true
}

const submitReject = async () => {
  if (!rejectDialog.form.review_note.trim()) {
    ElMessage.warning('请填写拒绝原因')
    return
  }

  rejectDialog.loading = true

  try {
    await adminProjectAccessApi.rejectRequest(rejectDialog.row.id, {
      review_note: rejectDialog.form.review_note.trim(),
    })

    ElMessage.success('已拒绝申请')
    rejectDialog.visible = false
    await loadRequests()
  } finally {
    rejectDialog.loading = false
  }
}

// ── 热更新 ──────────────────────────────────────────────────
const versions = reactive({
  pc: null,
  android: null,
})

const versionsLoading = ref(false)
const historyClientType = ref('android')
const historyLoading = ref(false)
const versionHistory = ref([])

const loadVersions = async () => {
  if (!projectId.value) return

  versionsLoading.value = true

  try {
    const [pcRes, androidRes] = await Promise.allSettled([
      http.get(`/admin/api/updates/${projectId.value}/pc/latest`),
      http.get(`/admin/api/updates/${projectId.value}/android/latest`),
    ])

    versions.pc = pcRes.status === 'fulfilled' ? pcRes.value.data : null
    versions.android = androidRes.status === 'fulfilled' ? androidRes.value.data : null
  } finally {
    versionsLoading.value = false
    await loadHistory()
  }
}

const loadHistory = async () => {
  if (!projectId.value) return

  historyLoading.value = true

  try {
    const res = await http.get(
      `/admin/api/updates/${projectId.value}/${historyClientType.value}/history`,
    )
    versionHistory.value = res.data.versions ?? []
  } catch {
    versionHistory.value = []
  } finally {
    historyLoading.value = false
  }
}

// ── 总加载 ──────────────────────────────────────────────────
const loadAll = async () => {
  if (!projectId.value) return

  loading.value = true

  try {
    await Promise.all([
      loadProject(),
      loadPrices(),
      loadAccessPolicy(),
      loadRequests(),
      loadVersions(),
    ])
  } catch (error) {
    ElMessage.error('加载项目详情失败')
    throw error
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  syncTabFromQuery()
  loadAll()
})

watch(
  () => route.params.id,
  () => {
    activeTab.value = 'overview'
    requestPagination.page = 1
    syncTabFromQuery()
    loadAll()
  },
)

watch(
  () => route.query.tab,
  () => {
    syncTabFromQuery()
  },
)
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

.breadcrumb-line {
  margin-bottom: 4px;
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

.header-actions {
  display: flex;
  gap: 8px;
}

.info-card,
.tab-card,
.client-card,
.inner-card {
  border-radius: 10px;
}

.project-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.project-avatar {
  width: 54px;
  height: 54px;
  border-radius: 16px;
  background: linear-gradient(135deg, #eff6ff, #eef2ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  flex-shrink: 0;
}

.project-main {
  flex: 1;
}

.project-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.project-name {
  font-size: 20px;
  font-weight: 800;
  color: #1e293b;
}

.project-sub {
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}

.dot {
  margin: 0 6px;
  color: #cbd5e1;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

.uuid-text {
  color: #475569;
  word-break: break-all;
}

.db-name {
  color: #6366f1;
}

.muted {
  color: #94a3b8;
  font-size: 12px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  border-left: 4px solid #6366f1;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
}

.stat-card.highlight {
  border-left-color: #10b981;
}

.stat-num {
  font-size: 24px;
  font-weight: 800;
  color: #1e293b;
  line-height: 1;
}

.stat-label {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.overview-block {
  min-width: 0;
}

.block-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 10px;
}

.action-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.inner-alert {
  margin-bottom: 14px;
  border-radius: 8px;
}

.overview-alert {
  margin-top: 16px;
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

.access-form {
  max-width: 760px;
}

.small-alert {
  margin-top: 10px;
  border-radius: 8px;
}

.access-save-row {
  margin-top: 16px;
}

.request-toolbar {
  margin-bottom: 12px;
}

.main-text {
  font-size: 13px;
  color: #1e293b;
  font-weight: 600;
}

.sub-text {
  margin-top: 3px;
  font-size: 12px;
  color: #94a3b8;
}

.review-note {
  margin-top: 4px;
  font-size: 12px;
  color: #475569;
  line-height: 1.5;
}

.pager-row {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.total-text {
  color: #64748b;
  font-size: 13px;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.version-info {
  margin-bottom: 8px;
}

.inner-card {
  margin-top: 16px;
}

.client-card {
  min-height: 100%;
}
</style>
