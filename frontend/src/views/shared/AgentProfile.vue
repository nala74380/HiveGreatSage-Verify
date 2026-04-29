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
                effect="light" size="small"
                style="margin-left:6px"
              >{{ profile.status === 'active' ? '正常' : '已停用' }}</el-tag>
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

      <!-- 已授权项目 -->
      <el-card shadow="never" class="inner-card">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">
              已授权项目
              <el-badge :value="profile.authorized_projects.length" type="primary" style="margin-left:6px" />
            </span>
            <el-button size="small" type="primary" plain @click="openCatalogDialog">申请更多项目</el-button>
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
                effect="plain" size="small"
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
                  size="small" effect="light" style="margin-left:4px"
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
        </div>
      </el-card>
    </template>
  </div>

  <!-- 项目目录 + 申请授权 弹窗 -->
  <el-dialog v-model="catalogDialog.visible" title="项目目录与申请授权"
    width="680px" destroy-on-close>
    <el-table v-loading="catalogDialog.loading" :data="catalogDialog.projects" stripe size="small">
      <el-table-column label="项目名称" min-width="140" prop="display_name" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag :type="row.project_type === 'game' ? 'primary' : 'info'" effect="plain" size="small">
            {{ row.project_type === 'game' ? '游戏' : '验证' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="各级别单价" min-width="220">
        <template #default="{ row }">
          <div class="price-grid">
            <span v-for="(pts, level) in row.prices" :key="level" class="price-item">
              <LevelTag :level="level" />
              <span class="price-pts">{{ pts }} 点</span>
            </span>
            <span v-if="!Object.keys(row.prices||{}).length" class="text-muted">暂未定价</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="授权状态" width="100">
        <template #default="{ row }">
          <el-tag v-if="isAuthorized(row.id)" type="success" effect="light" size="small">已授权</el-tag>
          <el-tag v-else type="info" effect="plain" size="small">未授权</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isAuthorized(row.id)"
            size="small" type="primary"
            :loading="catalogDialog.applyingId === row.id"
            @click="applyAuth(row)">
            申请授权
          </el-button>
          <span v-else class="text-muted" style="font-size:12px">已拥有</span>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <div class="catalog-footer">
        <span class="text-muted" style="font-size:12px">
          申请后需管理员审核授权，审核完成后项目将出现在已授权列表。
        </span>
        <el-button @click="catalogDialog.visible = false">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { User, Plus, Monitor } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '@/api/agent'
import { balanceApi } from '@/api/balance'
import { formatDatetime, formatDate, expiryTagType, expiryLabel } from '@/utils/format'
import LevelTag from '@/components/common/LevelTag.vue'

const loading = ref(false)
const profile = ref(null)

onMounted(async () => {
  loading.value = true
  try {
    const res = await agentApi.me()
    profile.value = res.data
  } catch {
    ElMessage.error('获取个人信息失败')
  } finally {
    loading.value = false
  }
})

// ── 项目目录弹窗 ─────────────────────────────────────
const catalogDialog = reactive({
  visible: false,
  loading: false,
  projects: [],
  applyingId: null,
})

const isAuthorized = (projectId) => {
  return profile.value?.authorized_projects?.some(p => p.id === projectId || p.project_id === projectId)
}

const openCatalogDialog = async () => {
  catalogDialog.visible = true
  catalogDialog.loading = true
  try {
    const res = await balanceApi.catalog()
    catalogDialog.projects = res.data
  } catch {
    ElMessage.error('加载项目目录失败')
  } finally {
    catalogDialog.loading = false
  }
}

const applyAuth = async (row) => {
  catalogDialog.applyingId = row.id
  try {
    // 发送申请通知给管理员（目前以通知弹框模拟， Phase 2 引入审批流程）
    // 当前展示: 弹出提示说明已提交申请
    ElMessage.success(`已提交「${row.display_name}」的授权申请，请联系管理员开通。`)
  } finally {
    catalogDialog.applyingId = null
  }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }

.info-card, .inner-card { border-radius: 10px; }

/* 代理头部 */
.agent-header { display: flex; align-items: center; gap: 16px; }
.agent-avatar {
  width: 52px; height: 52px; border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b, #ef4444);
  color: #fff; font-size: 22px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.agent-meta { flex: 1; }
.agent-name { font-size: 18px; font-weight: 700; color: #1e293b; margin-bottom: 6px; }
.agent-tags { display: flex; align-items: center; }

/* 统计卡片 */
.stat-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.07); border-left: 4px solid transparent;
}
.stat-card.total     { border-color: #6366f1; }
.stat-card.active    { border-color: #10b981; }
.stat-card.suspended { border-color: #94a3b8; }
.stat-num { font-size: 28px; font-weight: 700; color: #1e293b; line-height: 1; }
.stat-lbl { font-size: 12px; color: #64748b; margin-top: 4px; }

.mono        { font-family: 'Cascadia Code', monospace; font-size: 12px; }
.text-muted  { color: #94a3b8; font-size: 12px; }
.text-success{ color: #10b981; }
.text-danger { color: #ef4444; font-weight: 600; }

.card-title      { font-size: 14px; font-weight: 600; color: #1e293b; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }

.quick-actions { display: flex; gap: 12px; flex-wrap: wrap; padding: 4px 0; }

/* 项目目录弹窗 */
.price-grid  { display: flex; flex-wrap: wrap; gap: 6px; }
.price-item  { display: flex; align-items: center; gap: 3px; }
.price-pts   { font-size: 11px; color: #6366f1; font-weight: 600; }
.catalog-footer { display: flex; align-items: center; justify-content: space-between; width: 100%; }
</style>
