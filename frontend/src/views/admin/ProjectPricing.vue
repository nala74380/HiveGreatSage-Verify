<template>
  <div class="page">
    <div class="page-header">
      <h2>项目定价管理</h2>
      <div class="header-hint">
        试用按周计费；普通 / VIP / SVIP 按月计费；点数保留小数点后两位。
      </div>
    </div>

    <div v-loading="loading">
      <el-card
        v-for="proj in projects"
        :key="proj.id"
        shadow="never"
        class="project-card"
      >
        <template #header>
          <div class="proj-header">
            <div class="proj-info">
              <el-tag :type="proj.project_type === 'game' ? 'primary' : 'info'" effect="plain" size="small">
                {{ proj.project_type === 'game' ? '🎮 游戏项目' : '🔑 验证项目' }}
              </el-tag>
              <span class="proj-name">{{ proj.display_name }}</span>
              <span class="proj-code">{{ proj.code_name }}</span>
            </div>
            <el-button size="small" :icon="Refresh" @click="loadProjectPrices(proj.id)" />
          </div>
        </template>

        <el-table :data="visiblePrices(proj.id)" size="small" stripe>
          <el-table-column label="用户级别" width="120">
            <template #default="{ row }">
              <LevelTag :level="row.user_level" />
            </template>
          </el-table-column>

          <el-table-column label="计费周期" width="120">
            <template #default="{ row }">
              <el-tag effect="plain" type="info">
                {{ row.unit_label || unitLabel(row.user_level) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="点数" min-width="220">
            <template #default="{ row }">
              <div
                v-if="editingCell.projectId === proj.id && editingCell.level === row.user_level"
                class="edit-cell"
              >
                <el-input-number
                  v-model="editingCell.value"
                  :min="0"
                  :precision="2"
                  :step="0.01"
                  controls-position="right"
                  size="small"
                  style="width:160px"
                  @keyup.enter="savePrice(proj.id, row.user_level)"
                />
                <el-button
                  size="small"
                  type="primary"
                  :loading="editingCell.saving"
                  @click="savePrice(proj.id, row.user_level)"
                >
                  保存
                </el-button>
                <el-button size="small" @click="cancelEdit">取消</el-button>
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
                  @click="startEdit(proj.id, row.user_level, row.points_per_device)"
                >
                  {{ row.points_per_device !== null ? '修改' : '设置' }}
                </el-button>

                <el-button
                  v-if="row.points_per_device !== null"
                  text
                  size="small"
                  type="danger"
                  @click="removePrice(proj.id, row.user_level)"
                >
                  清除
                </el-button>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="说明" min-width="260">
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
          <el-button size="small" @click="applyPreset(proj.id, 'free')">全免费</el-button>
          <el-button size="small" @click="applyPreset(proj.id, 'standard')">标准定价</el-button>
          <el-button size="small" type="danger" plain @click="clearAll(proj.id)">清除全部</el-button>
        </div>
      </el-card>

      <el-empty v-if="!loading && !projects.length" description="暂无项目" />
    </div>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/ProjectPricing.vue
 * 名称: 项目定价管理
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能说明:
 *   管理员设置项目定价。
 *
 * 规则:
 *   - 试用 trial：按周 / 每台设备
 *   - 普通 normal：按月 / 每台设备
 *   - VIP：按月 / 每台设备
 *   - SVIP：按月 / 每台设备
 *   - 不显示 tester
 *   - 点数保留小数点后两位
 */

import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { balanceApi } from '@/api/balance'
import { projectApi } from '@/api/project'
import LevelTag from '@/components/common/LevelTag.vue'

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
const projects = ref([])
const priceMap = reactive({})

const editingCell = reactive({
  projectId: null,
  level: null,
  value: 0,
  saving: false,
})

onMounted(async () => {
  loading.value = true
  try {
    const res = await projectApi.list({ page: 1, page_size: 100, is_active: true })
    projects.value = res.data.projects || []
    await Promise.all(projects.value.map(p => loadProjectPrices(p.id)))
  } finally {
    loading.value = false
  }
})

const visiblePrices = (projectId) => {
  return (priceMap[projectId] || []).filter(row => LEVELS.includes(row.user_level))
}

const loadProjectPrices = async (projectId) => {
  const res = await balanceApi.getPrices(projectId)
  priceMap[projectId] = (res.data || []).filter(row => LEVELS.includes(row.user_level))
}

const startEdit = (projectId, level, currentValue) => {
  editingCell.projectId = projectId
  editingCell.level = level
  editingCell.value = Number(currentValue ?? 0)
}

const cancelEdit = () => {
  editingCell.projectId = null
  editingCell.level = null
}

const savePrice = async (projectId, level) => {
  editingCell.saving = true
  try {
    await balanceApi.setPrice(projectId, level, {
      points_per_device: Number(Number(editingCell.value).toFixed(2)),
    })
    ElMessage.success('定价已保存')
    cancelEdit()
    await loadProjectPrices(projectId)
  } finally {
    editingCell.saving = false
  }
}

const removePrice = async (projectId, level) => {
  await ElMessageBox.confirm(`确认清除 ${levelName(level)} 的定价？`, '确认', { type: 'warning' })
  await balanceApi.deletePrice(projectId, level)
  ElMessage.success('已清除')
  await loadProjectPrices(projectId)
}

const applyPreset = async (projectId, presetName) => {
  const preset = PRESETS[presetName]

  if (!preset) {
    await Promise.all(
      LEVELS.map(level =>
        balanceApi.setPrice(projectId, level, { points_per_device: 0.00 }),
      ),
    )
  } else {
    await Promise.all(
      Object.entries(preset).map(([level, pts]) =>
        balanceApi.setPrice(projectId, level, {
          points_per_device: Number(Number(pts).toFixed(2)),
        }),
      ),
    )
  }

  ElMessage.success('批量设置成功')
  await loadProjectPrices(projectId)
}

const clearAll = async (projectId) => {
  await ElMessageBox.confirm('确认清除该项目全部定价？', '确认', { type: 'warning' })
  await Promise.all(
    LEVELS.map(level => balanceApi.deletePrice(projectId, level).catch(() => {})),
  )
  ElMessage.success('已清除全部定价')
  await loadProjectPrices(projectId)
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
  gap: 12px;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1e293b;
}

.header-hint {
  font-size: 12px;
  color: #94a3b8;
}

.project-card {
  border-radius: 10px;
}

.project-card + .project-card {
  margin-top: 16px;
}

.proj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.proj-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.proj-name {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.proj-code {
  font-family: monospace;
  font-size: 12px;
  color: #94a3b8;
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
</style>