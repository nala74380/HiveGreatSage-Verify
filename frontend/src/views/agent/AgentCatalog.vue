<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>项目目录</h2>
        <p class="page-desc">
          查看当前平台项目、代理授权状态、用户级别价格与各级别功能差异。
        </p>
      </div>
      <el-button :icon="Refresh" @click="fetchCatalog" :loading="loading">刷新</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-alert
      v-else
      title="说明：已授权项目可用于创建用户并分配项目授权；未授权项目需联系管理员开通。"
      type="info"
      show-icon
      :closable="false"
      class="tip-alert"
    />

    <el-card shadow="never" class="level-card">
      <template #header>
        <div class="level-card-header">
          <span class="card-title">用户级别功能说明</span>
          <el-tag size="small" effect="plain" type="info">按项目授权等级生效</el-tag>
        </div>
      </template>

      <div class="level-grid">
        <div class="level-block trial">
          <div class="level-title-row">
            <LevelTag level="trial" />
            <span class="level-title">试用用户</span>
          </div>
          <div class="level-desc">等同普通用户，用于短期体验与测试授权。</div>
          <ul class="level-list">
            <li>具备普通用户同等基础功能。</li>
            <li>计费周期按周计算。</li>
          </ul>
        </div>

        <div class="level-block normal">
          <div class="level-title-row">
            <LevelTag level="normal" />
            <span class="level-title">普通用户</span>
          </div>
          <div class="level-desc">基础功能级别。</div>
          <ul class="level-list">
            <li>可使用项目基础验证能力。</li>
            <li>可使用普通用户范围内的基础功能。</li>
          </ul>
        </div>

        <div class="level-block vip">
          <div class="level-title-row">
            <LevelTag level="vip" />
            <span class="level-title">VIP 用户</span>
          </div>
          <div class="level-desc">包含普通用户的所有功能，并增加高级能力。</div>
          <ul class="level-list">
            <li>包含普通用户的所有功能。</li>
            <li>可使用游戏账户数据库。</li>
            <li>可试用组队功能。</li>
            <li>具备物品价格聚合功能。</li>
          </ul>
        </div>

        <div class="level-block svip">
          <div class="level-title-row">
            <LevelTag level="svip" />
            <span class="level-title">SVIP 用户</span>
          </div>
          <div class="level-desc">包含 VIP 用户的所有功能，并增加更高阶配置能力。</div>
          <ul class="level-list">
            <li>包含 VIP 用户的所有功能。</li>
            <li>具备游戏账号不同属性设定功能。</li>
            <li>可扩展其他高级功能。</li>
          </ul>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="projects"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="display_name" label="项目名称" min-width="160" />

        <el-table-column prop="code_name" label="项目代号" min-width="140">
          <template #default="{ row }">
            <span class="mono">{{ row.code_name }}</span>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag :type="row.project_type === 'game' ? 'primary' : 'info'" effect="plain">
              {{ row.project_type === 'game' ? '游戏项目' : '验证项目' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="各级别点数价格" min-width="420">
          <template #default="{ row }">
            <div class="price-list">
              <template v-if="row.display_prices.length">
                <span
                  v-for="item in row.display_prices"
                  :key="item.level"
                  class="price-item"
                >
                  <LevelTag :level="item.level" />
                  <span class="price-num">{{ formatPrice(item) }}</span>
                </span>
              </template>
              <span v-else class="text-muted">暂未定价</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="授权状态" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.is_authorized" type="success" effect="light">
              已授权
            </el-tag>
            <el-tag v-else type="info" effect="plain">
              未授权
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.is_authorized"
              size="small"
              type="success"
              plain
              disabled
            >
              已授权
            </el-button>

            <el-button
              v-else
              size="small"
              type="primary"
              plain
              @click="showApplyHint(row)"
            >
              申请授权
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && projects.length === 0"
        description="暂无可展示项目"
        :image-size="80"
      />
    </el-card>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/agent/AgentCatalog.vue
 * 名称: 代理项目目录页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   代理查看项目目录、项目价格、当前代理授权状态、用户级别功能差异。
 *
 * 展示规则:
 *   1. 已授权项目显示“已授权”，不再显示“申请授权”。
 *   2. 代理端不展示 tester 级别价格。
 *   3. 页面不显示“测试用户级别不对代理展示”说明文案。
 *   4. 价格顺序固定为：试用 → 普通 → VIP → SVIP。
 *   5. 新增试用 / 普通 / VIP / SVIP 功能差异说明。
 */

import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { agentBalanceApi } from '@/api/balance'
import { agentApi } from '@/api/agent'
import LevelTag from '@/components/common/LevelTag.vue'

const loading = ref(false)
const projects = ref([])
const error = ref('')

const DISPLAY_LEVEL_ORDER = ['trial', 'normal', 'vip', 'svip']

const LEVEL_ALIASES = {
  trial: 'trial',
  '试用': 'trial',

  normal: 'normal',
  common: 'normal',
  ordinary: 'normal',
  '普通': 'normal',

  vip: 'vip',
  VIP: 'vip',

  svip: 'svip',
  SVIP: 'svip',

  test: 'test',
  tester: 'test',
  testing: 'test',
  '测试': 'test',
}

const LEVEL_UNIT_LABELS = {
  trial: '点/周/设备',
  normal: '点/月/设备',
  vip: '点/月/设备',
  svip: '点/月/设备',
}

const normalizeLevel = (level) => {
  if (level === null || level === undefined) {
    return ''
  }

  const raw = String(level).trim()
  return LEVEL_ALIASES[raw] || LEVEL_ALIASES[raw.toLowerCase()] || raw.toLowerCase()
}

const normalizeProjectList = (data) => {
  if (Array.isArray(data)) {
    return data
  }

  if (Array.isArray(data?.projects)) {
    return data.projects
  }

  if (Array.isArray(data?.items)) {
    return data.items
  }

  return []
}

const normalizeAuthorizedProjects = (data) => {
  if (Array.isArray(data)) {
    return data
  }

  if (Array.isArray(data?.authorized_projects)) {
    return data.authorized_projects
  }

  if (Array.isArray(data?.projects)) {
    return data.projects
  }

  if (Array.isArray(data?.items)) {
    return data.items
  }

  return []
}

const projectKeys = (project) => {
  const keys = []

  const candidates = [
    project?.id,
    project?.project_id,
    project?.game_project_id,
    project?.code_name,
    project?.project_code,
    project?.code,
  ]

  for (const item of candidates) {
    if (item !== null && item !== undefined && item !== '') {
      keys.push(String(item))
    }
  }

  return keys
}

const buildAuthorizedKeySet = (authorizedProjects) => {
  const set = new Set()

  for (const item of authorizedProjects) {
    for (const key of projectKeys(item)) {
      set.add(key)
    }
  }

  return set
}

const isProjectAuthorized = (project, authorizedKeySet) => {
  return projectKeys(project).some(key => authorizedKeySet.has(key))
}

const buildDisplayPrices = (rawPrices) => {
  if (!rawPrices) {
    return []
  }

  const priceMap = new Map()

  if (!Array.isArray(rawPrices) && typeof rawPrices === 'object') {
    for (const [level, points] of Object.entries(rawPrices)) {
      const normalized = normalizeLevel(level)

      if (normalized === 'test') {
        continue
      }

      if (!DISPLAY_LEVEL_ORDER.includes(normalized)) {
        continue
      }

      priceMap.set(normalized, points)
    }
  }

  if (Array.isArray(rawPrices)) {
    for (const item of rawPrices) {
      const normalized = normalizeLevel(item.user_level ?? item.level ?? item.name)

      if (normalized === 'test') {
        continue
      }

      if (!DISPLAY_LEVEL_ORDER.includes(normalized)) {
        continue
      }

      priceMap.set(
        normalized,
        item.points_per_device ?? item.points ?? item.price ?? 0,
      )
    }
  }

  return DISPLAY_LEVEL_ORDER
    .filter(level => priceMap.has(level))
    .map(level => ({
      level,
      points: priceMap.get(level),
      unitLabel: LEVEL_UNIT_LABELS[level] || '点/设备',
    }))
}

const mergeCatalogWithAuth = (catalogProjects, authorizedProjects) => {
  const authorizedKeySet = buildAuthorizedKeySet(authorizedProjects)

  return catalogProjects.map(project => ({
    ...project,
    is_authorized: isProjectAuthorized(project, authorizedKeySet),
    display_prices: buildDisplayPrices(project.prices),
  }))
}

const formatPrice = (item) => {
  const points = Number(item.points || 0).toFixed(2)
  return `${points} ${item.unitLabel}`
}

const getErrorMessage = (err) => {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail || err?.response?.data?.message

  if (status === 401) {
    return '项目目录接口返回 401：当前代理登录态未被后端认可。请确认 Chrome 中仍是代理账号登录，并检查后端代理鉴权。'
  }

  if (status === 403) {
    return '项目目录接口返回 403：当前账号无权访问项目目录。'
  }

  if (status === 404) {
    return '项目目录接口返回 404：后端尚未注册 /api/agents/my/catalog 或 /api/agents/my-projects，请确认后端已更新并重启。'
  }

  if (status === 500) {
    return '项目目录接口返回 500：后端内部异常，请查看 PyCharm 后端控制台日志。'
  }

  if (detail) {
    return `项目目录加载失败：${detail}`
  }

  return `项目目录加载失败：${err?.message || '未知错误'}`
}

const fetchCatalog = async () => {
  loading.value = true
  error.value = ''

  try {
    const [catalogRes, authorizedRes] = await Promise.all([
      agentBalanceApi.catalog(),
      agentApi.myProjects(),
    ])

    const catalogProjects = normalizeProjectList(catalogRes.data)
    const authorizedProjects = normalizeAuthorizedProjects(authorizedRes.data)

    projects.value = mergeCatalogWithAuth(catalogProjects, authorizedProjects)
  } catch (err) {
    console.error('[AgentCatalog] 加载项目目录失败:', err)
    projects.value = []
    error.value = getErrorMessage(err)
  } finally {
    loading.value = false
  }
}

const showApplyHint = async (row) => {
  await ElMessageBox.alert(
    `项目「${row.display_name}」当前尚未对你的代理账号开通。请联系管理员为你的代理账号开通该项目授权。`,
    '申请授权说明',
    {
      confirmButtonText: '知道了',
      type: 'info',
    },
  )
}

onMounted(fetchCatalog)
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
  align-items: center;
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
}

.tip-alert,
.level-card,
.table-card {
  border-radius: 10px;
}

.level-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.level-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.level-block {
  border-radius: 10px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.level-block.trial {
  background: #f8fafc;
}

.level-block.normal {
  background: #eff6ff;
}

.level-block.vip {
  background: #fff7ed;
}

.level-block.svip {
  background: #fef2f2;
}

.level-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.level-desc {
  margin-top: 8px;
  font-size: 12px;
  color: #475569;
  line-height: 1.7;
}

.level-list {
  margin: 8px 0 0;
  padding-left: 16px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.8;
}

.mono {
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
}

.price-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.price-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  padding: 3px 8px;
}

.price-num {
  font-size: 12px;
  color: #475569;
  font-weight: 600;
}

.text-muted {
  color: #94a3b8;
  font-size: 12px;
}
</style>