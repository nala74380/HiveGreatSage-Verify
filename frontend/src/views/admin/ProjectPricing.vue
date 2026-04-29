<template>
  <div class="page">
    <div class="page-header">
      <h2>项目定价管理</h2>
      <div class="header-hint">设置各项目按用户级别授权一台设备的点数消耗</div>
    </div>

    <!-- 项目列表 -->
    <div v-loading="loading">
      <el-card v-for="proj in projects" :key="proj.id" shadow="never" class="project-card">
        <template #header>
          <div class="proj-header">
            <div class="proj-info">
              <el-tag :type="proj.project_type === 'game' ? 'primary' : 'info'" effect="plain" size="small">
                {{ proj.project_type === 'game' ? '🎮 游戏项目' : '🔑 普通验证' }}
              </el-tag>
              <span class="proj-name">{{ proj.display_name }}</span>
              <span class="proj-code">{{ proj.code_name }}</span>
            </div>
            <el-button size="small" :icon="Refresh" @click="loadProjectPrices(proj.id)" />
          </div>
        </template>

        <!-- 各级别定价表格 -->
        <el-table :data="priceMap[proj.id] || []" size="small" stripe>
          <el-table-column label="用户级别" width="120">
            <template #default="{ row }">
              <LevelTag :level="row.user_level" />
            </template>
          </el-table-column>

          <el-table-column label="每台设备（点数）" min-width="200">
            <template #default="{ row }">
              <div v-if="editingCell.projectId === proj.id && editingCell.level === row.user_level"
                class="edit-cell">
                <el-input-number
                  v-model="editingCell.value"
                  :min="0" :precision="4" :step="0.01"
                  controls-position="right" size="small"
                  style="width:160px"
                  @keyup.enter="savePrice(proj.id, row.user_level)"
                />
                <el-button size="small" type="primary" :loading="editingCell.saving"
                  @click="savePrice(proj.id, row.user_level)">保存</el-button>
                <el-button size="small" @click="cancelEdit">取消</el-button>
              </div>
              <div v-else class="price-display">
                <span v-if="row.points_per_device !== null" class="price-val">
                  {{ row.points_per_device.toFixed(4) }} 点
                </span>
                <span v-else class="no-price">未设置</span>
                <el-button text size="small" type="primary"
                  @click="startEdit(proj.id, row.user_level, row.points_per_device)">
                  {{ row.points_per_device !== null ? '修改' : '设置' }}
                </el-button>
                <el-button v-if="row.points_per_device !== null"
                  text size="small" type="danger"
                  @click="removePrice(proj.id, row.user_level)">清除</el-button>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="说明" min-width="200">
            <template #default="{ row }">
              <span v-if="row.points_per_device !== null" class="price-desc">
                授权 1 台设备扣 {{ row.points_per_device.toFixed(4) }} 点
              </span>
              <span v-else class="no-price">代理无需扣点即可为此级别授权</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 快速批量设置 -->
        <div class="batch-price-row">
          <span class="batch-label">快速设置：</span>
          <el-button size="small" @click="applyPreset(proj.id, 'free')">全免费</el-button>
          <el-button size="small" @click="applyPreset(proj.id, 'standard')">标准定价</el-button>
          <el-button size="small" type="danger" plain @click="clearAll(proj.id)">清除全部</el-button>
        </div>
      </el-card>

      <el-empty v-if="!loading && !projects.length" description="暂无游戏项目" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { balanceApi } from '@/api/balance'
import { projectApi } from '@/api/project'
import LevelTag from '@/components/common/LevelTag.vue'

const LEVELS = ['trial', 'normal', 'vip', 'svip', 'tester']

// 标准定价预设（可按业务调整）
const PRESETS = {
  standard: { trial: 0.01, normal: 2.0, vip: 3.5, svip: 5.0, tester: 0 },
}

const loading   = ref(false)
const projects  = ref([])
const priceMap  = reactive({})   // { [projectId]: [...levelPrices] }

const editingCell = reactive({ projectId: null, level: null, value: 0, saving: false })

onMounted(async () => {
  loading.value = true
  try {
    const res = await projectApi.list({ page: 1, page_size: 100, is_active: true })
    projects.value = res.data.projects
    await Promise.all(projects.value.map(p => loadProjectPrices(p.id)))
  } finally { loading.value = false }
})

const loadProjectPrices = async (projectId) => {
  const res = await balanceApi.getPrices(projectId)
  priceMap[projectId] = res.data
}

const startEdit = (projectId, level, currentValue) => {
  editingCell.projectId = projectId
  editingCell.level     = level
  editingCell.value     = currentValue ?? 0
}

const cancelEdit = () => {
  editingCell.projectId = null
  editingCell.level     = null
}

const savePrice = async (projectId, level) => {
  editingCell.saving = true
  try {
    await balanceApi.setPrice(projectId, level, { points_per_device: editingCell.value })
    ElMessage.success('定价已保存')
    cancelEdit()
    await loadProjectPrices(projectId)
  } finally { editingCell.saving = false }
}

const removePrice = async (projectId, level) => {
  await ElMessageBox.confirm(`确认清除 ${level} 级别的定价？`, '确认', { type: 'warning' })
  await balanceApi.deletePrice(projectId, level)
  ElMessage.success('已清除')
  await loadProjectPrices(projectId)
}

const applyPreset = async (projectId, presetName) => {
  const preset = PRESETS[presetName]
  if (!preset) {
    // free 预设：全部设为 0
    await Promise.all(LEVELS.map(l => balanceApi.setPrice(projectId, l, { points_per_device: 0 })))
  } else {
    await Promise.all(
      Object.entries(preset).map(([level, pts]) =>
        balanceApi.setPrice(projectId, level, { points_per_device: pts })
      )
    )
  }
  ElMessage.success('批量设置成功')
  await loadProjectPrices(projectId)
}

const clearAll = async (projectId) => {
  await ElMessageBox.confirm('确认清除该项目所有定价？', '确认', { type: 'warning' })
  await Promise.all(LEVELS.map(l => balanceApi.deletePrice(projectId, l).catch(() => {})))
  ElMessage.success('已清除全部定价')
  await loadProjectPrices(projectId)
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; gap: 12px; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }
.header-hint { font-size: 12px; color: #94a3b8; }

.project-card { border-radius: 10px; }

.proj-header { display: flex; align-items: center; justify-content: space-between; }
.proj-info   { display: flex; align-items: center; gap: 10px; }
.proj-name   { font-size: 15px; font-weight: 600; color: #1e293b; }
.proj-code   { font-family: monospace; font-size: 12px; color: #94a3b8; }

.edit-cell     { display: flex; align-items: center; gap: 6px; }
.price-display { display: flex; align-items: center; gap: 8px; }
.price-val     { font-size: 14px; font-weight: 600; color: #6366f1; }
.no-price      { font-size: 12px; color: #94a3b8; }
.price-desc    { font-size: 12px; color: #64748b; }

.batch-price-row {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; padding-top: 12px; border-top: 1px solid #f1f5f9;
}
.batch-label { font-size: 12px; color: #64748b; }
</style>
