<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <h2>个人主页</h2>
      <el-tag type="warning" effect="dark">代理账号</el-tag>
    </div>

    <template v-if="profile">
      <!-- 基本信息卡片 -->
      <el-card shadow="never" class="info-card">
        <div class="agent-header">
          <div class="agent-avatar">{{ profile.username.charAt(0).toUpperCase() }}</div>
          <div class="agent-meta">
            <div class="agent-name">{{ profile.username }}</div>
            <div class="agent-tags">
              <el-tag type="warning" effect="light" size="small">Lv.{{ profile.level }} 代理</el-tag>
              <el-tag
                :type="profile.status === 'active' ? 'success' : 'danger'"
                effect="light"
                size="small"
                style="margin-left:6px"
              >
                {{ profile.status === 'active' ? '正常' : '已停用' }}
              </el-tag>
            </div>
          </div>
        </div>

        <el-divider />

        <el-descriptions :column="3" size="small">
          <el-descriptions-item label="代理 ID">
            <span class="mono">{{ profile.id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">
            {{ formatDatetime(profile.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="上级代理">
            <span v-if="profile.parent_agent">
              {{ profile.parent_agent.username }} (Lv.{{ profile.parent_agent.level }})
            </span>
            <span v-else class="text-muted">顶级代理（管理员直属）</span>
          </el-descriptions-item>
          <el-descriptions-item label="佣金比例">
            <span v-if="profile.commission_rate !== null">{{ profile.commission_rate }}%</span>
            <span v-else class="text-muted">未设置</span>
          </el-descriptions-item>
          <el-descriptions-item label="用户配额">
            <span v-if="profile.max_users === 0" class="text-success">无限制</span>
            <span v-else>
              {{ profile.users_total }} / {{ profile.max_users }}
              <el-progress
                :percentage="Math.min(100, Math.round(profile.users_total / profile.max_users * 100))"
                :stroke-width="6"
                :color="profile.users_total / profile.max_users >= 0.9 ? '#f56c6c' : '#409eff'"
                :show-text="false"
                style="width:80px;display:inline-block;margin-left:8px;vertical-align:middle"
              />
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="剩余配额">
            <span v-if="profile.max_users === 0" class="text-success">不限</span>
            <span v-else-if="profile.users_quota_left !== null">
              <span :class="profile.users_quota_left <= 10 ? 'text-danger' : ''">
                {{ profile.users_quota_left }} 个
              </span>
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 用户统计 -->
      <el-row :gutter="12">
        <el-col :span="8">
          <div class="stat-card total">
            <div class="stat-num">{{ profile.users_total }}</div>
            <div class="stat-lbl">我的用户总数</div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-card active">
            <div class="stat-num">{{ profile.users_active }}</div>
            <div class="stat-lbl">正常用户</div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-card suspended">
            <div class="stat-num">{{ profile.users_suspended }}</div>
            <div class="stat-lbl">已停用用户</div>
          </div>
        </el-col>
      </el-row>

      <!-- 余额概览 -->
      <el-card shadow="never" class="inner-card">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">点数余额</span>
            <router-link to="/balance" class="view-link">查看流水 →</router-link>
          </div>
        </template>

        <el-row :gutter="12">
          <el-col :span="8">
            <div class="mini-balance-card">
              <div class="mini-label">充值点数</div>
              <div class="mini-value">{{ fmt(balance.recharge_balance) }}</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="mini-balance-card">
              <div class="mini-label">授信点数</div>
              <div class="mini-value">{{ fmt(balance.credit_balance) }}</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="mini-balance-card">
              <div class="mini-label">冻结授信</div>
              <div class="mini-value frozen">{{ fmt(balance.frozen_credit) }}</div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- 已授权项目 -->
      <el-card shadow="never" class="inner-card">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">
              已授权项目
              <el-badge :value="profile.authorized_projects.length" type="primary" style="margin-left:6px" />
            </span>
            <el-button size="small" type="primary" plain @click="$router.push('/catalog')">查看项目目录</el-button>
          </div>
        </template>

        <el-empty
          v-if="!profile.authorized_projects.length"
          description="暂无项目授权，请联系管理员"
          :image-size="60"
        />
        <el-table v-else :data="profile.authorized_projects" size="small">
          <el-table-column label="项目名称" min-width="150" prop="display_name" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.project_type === 'game' ? 'primary' : 'info'"
                effect="plain"
                size="small"
              >
                {{ row.project_type === 'game' ? '🎮 游戏' : '🔑 验证' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="项目代号" width="140">
            <template #default="{ row }">
              <span class="mono">{{ row.code_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="授权到期" min-width="160">
            <template #default="{ row }">
              <span v-if="!row.valid_until" class="text-success">永久有效</span>
              <span v-else>
                {{ formatDate(row.valid_until) }}
                <el-tag
                  :type="row.is_expired ? 'danger' : expiryTagType(row.valid_until)"
                  size="small"
                  effect="light"
                  style="margin-left:4px"
                >
                  {{ row.is_expired ? '已过期' : expiryLabel(row.valid_until) }}
                </el-tag>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="75">
            <template #default="{ row }">
              <el-tag :type="row.is_expired ? 'danger' : 'success'" size="small" effect="light">
                {{ row.is_expired ? '已过期' : '有效' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 快捷操作 -->
      <el-card shadow="never" class="inner-card">
        <template #header><span class="card-title">快捷操作</span></template>
        <div class="quick-actions">
          <el-button type="primary" :icon="User" @click="$router.push('/users')">管理我的用户</el-button>
          <el-button type="success" :icon="Plus" @click="$router.push('/users')">新建用户</el-button>
          <el-button :icon="Monitor" @click="$router.push('/devices')">设备监控</el-button>
          <el-button :icon="Tickets" @click="$router.push('/catalog')">项目目录</el-button>
          <el-button :icon="Wallet" @click="$router.push('/balance')">我的余额</el-button>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/shared/AgentProfile.vue
 * 名称: 代理个人主页
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   代理登录后的个人主页。
 *   展示代理基本信息、用户统计、余额概览、已授权项目、快捷操作。
 *
 * 改进内容:
 *   V1.1.0 - 新增余额概览，并把项目目录/我的余额接入快捷操作
 *   V1.0.0 - 初始代理个人主页
 *
 * 调试信息:
 *   Network 应出现：
 *     GET /api/agents/me
 *     GET /api/agents/my/balance
 */

import { ref, onMounted } from 'vue'
import { User, Plus, Monitor, Tickets, Wallet } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '@/api/agent'
import { agentBalanceApi } from '@/api/balance'
import { formatDatetime, formatDate, expiryTagType, expiryLabel } from '@/utils/format'

const loading = ref(false)
const profile = ref(null)

const balance = ref({
  recharge_balance: 0,
  credit_balance: 0,
  frozen_credit: 0,
})

const fmt = (val) => {
  const n = Number(val || 0)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

const fetchProfile = async () => {
  const res = await agentApi.me()
  profile.value = res.data
}

const fetchBalance = async () => {
  const res = await agentBalanceApi.myBalance()
  balance.value = {
    recharge_balance: res.data.recharge_balance ?? 0,
    credit_balance: res.data.credit_balance ?? 0,
    frozen_credit: res.data.frozen_credit ?? 0,
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchProfile(),
      fetchBalance(),
    ])
  } catch {
    ElMessage.error('获取代理个人信息失败')
  } finally {
    loading.value = false
  }
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
  align-items: center;
  justify-content: space-between;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1e293b;
}

.info-card,
.inner-card {
  border-radius: 10px;
}

/* 代理头部 */
.agent-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.agent-avatar {
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

.agent-meta {
  flex: 1;
}

.agent-name {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.agent-tags {
  display: flex;
  align-items: center;
}

/* 统计卡片 */
.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.07);
  border-left: 4px solid transparent;
}

.stat-card.total {
  border-color: #6366f1;
}

.stat-card.active {
  border-color: #10b981;
}

.stat-card.suspended {
  border-color: #94a3b8;
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1;
}

.stat-lbl {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

.mini-balance-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
}

.mini-label {
  font-size: 12px;
  color: #64748b;
}

.mini-value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
}

.mini-value.frozen {
  color: #f59e0b;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

.text-success {
  color: #10b981;
}

.text-danger {
  color: #ef4444;
  font-weight: 600;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.view-link {
  color: #2563eb;
  font-size: 13px;
  text-decoration: none;
}

.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 4px 0;
}
</style>