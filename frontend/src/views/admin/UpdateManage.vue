<template>
  <div class="page">
    <div class="page-header"><h2>热更新管理</h2></div>

    <!-- 选择项目 -->
    <el-card shadow="never" class="select-card">
      <el-form inline>
        <el-form-item label="选择项目">
          <el-select
            v-model="selectedProjectId"
            placeholder="请选择项目（游戏项目 / 验证项目均支持）"
            style="width:320px"
            filterable
            @change="onProjectChange"
          >
            <el-option
              v-for="p in allProjects"
              :key="p.id"
              :label="p.display_name"
              :value="p.id"
            >
              <span>{{ p.display_name }}</span>
              <span class="option-meta">
                {{ p.project_type === 'game' ? '🎮' : '🔑' }} {{ p.code_name }}
              </span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item v-if="selectedProject">
          <el-tag type="info" effect="plain" size="small" class="mono">
            {{ selectedProject.code_name }}
          </el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <template v-if="selectedProject">
      <el-row :gutter="16">
        <!-- PC 端 -->
        <el-col :span="12">
          <el-card shadow="never" class="client-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">🖥 PC 端</span>
                <el-tag v-if="versions.pc" :type="versions.pc.force_update ? 'danger' : 'success'" effect="plain" size="small">
                  v{{ versions.pc.version }}{{ versions.pc.force_update ? ' 强制' : '' }}
                </el-tag>
                <el-tag v-else type="info" effect="plain" size="small">暂无版本</el-tag>
              </div>
            </template>

            <div v-if="versions.pc" class="version-info">
              <el-descriptions :column="1" size="small" border>
                <el-descriptions-item label="版本号"><span class="mono">{{ versions.pc.version }}</span></el-descriptions-item>
                <el-descriptions-item label="发布时间">{{ formatDatetime(versions.pc.released_at) }}</el-descriptions-item>
                <el-descriptions-item label="SHA-256"><span class="mono text-muted">{{ versions.pc.checksum_sha256?.slice(0, 20) }}…</span></el-descriptions-item>
                <el-descriptions-item label="强制更新">
                  <el-tag :type="versions.pc.force_update ? 'danger' : 'success'" size="small">{{ versions.pc.force_update ? '是' : '否' }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item v-if="versions.pc.release_notes" label="更新说明">{{ versions.pc.release_notes }}</el-descriptions-item>
              </el-descriptions>
            </div>
            <el-empty v-else description="暂未发布 PC 端版本" :image-size="60" />

            <el-divider content-position="left">发布新版本</el-divider>
            <UploadVersionForm
              client-type="pc"
              :project-id="selectedProject.id"
              @uploaded="loadVersions"
            />
          </el-card>
        </el-col>

        <!-- 安卓端 -->
        <el-col :span="12">
          <el-card shadow="never" class="client-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">📱 安卓端</span>
                <el-tag v-if="versions.android" :type="versions.android.force_update ? 'danger' : 'success'" effect="plain" size="small">
                  v{{ versions.android.version }}{{ versions.android.force_update ? ' 强制' : '' }}
                </el-tag>
                <el-tag v-else type="info" effect="plain" size="small">暂无版本</el-tag>
              </div>
            </template>

            <div v-if="versions.android" class="version-info">
              <el-descriptions :column="1" size="small" border>
                <el-descriptions-item label="版本号"><span class="mono">{{ versions.android.version }}</span></el-descriptions-item>
                <el-descriptions-item label="发布时间">{{ formatDatetime(versions.android.released_at) }}</el-descriptions-item>
                <el-descriptions-item label="SHA-256"><span class="mono text-muted">{{ versions.android.checksum_sha256?.slice(0, 20) }}…</span></el-descriptions-item>
                <el-descriptions-item label="强制更新">
                  <el-tag :type="versions.android.force_update ? 'danger' : 'success'" size="small">{{ versions.android.force_update ? '是' : '否' }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item v-if="versions.android.release_notes" label="更新说明">{{ versions.android.release_notes }}</el-descriptions-item>
              </el-descriptions>
            </div>
            <el-empty v-else description="暂未发布安卓端版本" :image-size="60" />

            <el-divider content-position="left">发布新版本</el-divider>
            <UploadVersionForm
              client-type="android"
              :project-id="selectedProject.id"
              @uploaded="loadVersions"
            />
          </el-card>
        </el-col>
      </el-row>

      <!-- 版本历史 -->
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
              <el-tag v-if="row.is_active" type="success" size="small" effect="dark" style="margin-left:6px">当前</el-tag>
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
            <template #default="{ row }">{{ formatDatetime(row.released_at) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!versionHistory.length && !historyLoading" description="暂无版本历史" :image-size="60" />
      </el-card>
    </template>

    <el-card v-else shadow="never" class="empty-hint">
      <el-empty description="请先选择项目（游戏项目和验证项目均支持热更新）" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { adminProjectApi as projectApi } from '@/api/admin/project'
import http from '@/api/http'
import { formatDatetime } from '@/utils/format'
import UploadVersionForm from '@/components/common/UploadVersionForm.vue'

const allProjects      = ref([])
const selectedProjectId = ref(null)

const selectedProject = computed(() =>
  allProjects.value.find(p => p.id === selectedProjectId.value) ?? null
)

onMounted(async () => {
  try {
    // 加载所有已启用项目（游戏 + 验证）
    const res = await projectApi.list({ page: 1, page_size: 200, is_active: true })
    allProjects.value = res.data.projects
    if (allProjects.value.length === 1) {
      selectedProjectId.value = allProjects.value[0].id
      loadVersions()
    }
  } catch { /* 静默 */ }
})

const versions        = reactive({ pc: null, android: null })
const versionsLoading = ref(false)

const onProjectChange = () => {
  versions.pc      = null
  versions.android = null
  versionHistory.value = []
  loadVersions()
}

const loadVersions = async () => {
  if (!selectedProjectId.value) return
  versionsLoading.value = true
  try {
    const id = selectedProjectId.value
    const [pcRes, androidRes] = await Promise.allSettled([
      http.get(`/admin/api/updates/${id}/pc/latest`),
      http.get(`/admin/api/updates/${id}/android/latest`),
    ])
    versions.pc      = pcRes.status      === 'fulfilled' ? pcRes.value.data      : null
    versions.android = androidRes.status === 'fulfilled' ? androidRes.value.data : null
  } finally {
    versionsLoading.value = false
    loadHistory()
  }
}

const historyClientType = ref('android')
const historyLoading    = ref(false)
const versionHistory    = ref([])

const loadHistory = async () => {
  if (!selectedProjectId.value) return
  historyLoading.value = true
  try {
    const res = await http.get(
      `/admin/api/updates/${selectedProjectId.value}/${historyClientType.value}/history`
    )
    versionHistory.value = res.data.versions ?? []
  } catch {
    versionHistory.value = []
  } finally {
    historyLoading.value = false
  }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }
.select-card, .client-card, .inner-card, .empty-hint { border-radius: 10px; }
.option-meta { margin-left: 8px; font-size: 11px; color: #94a3b8; font-family: monospace; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #1e293b; }
.version-info { margin-bottom: 8px; }
.mono { font-family: 'Cascadia Code', monospace; font-size: 12px; }
.text-muted { color: #94a3b8; }
</style>
