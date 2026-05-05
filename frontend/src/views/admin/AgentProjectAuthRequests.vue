<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>项目授权申请</h2>
        <p class="page-desc">
          审核代理提交的项目开通申请；审核通过后系统会自动写入代理项目授权。
        </p>
      </div>
      <el-button :icon="Refresh" @click="loadRequests" :loading="loading">刷新</el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filter">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部状态" style="width:160px">
            <el-option label="待审核" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="已取消" value="cancelled" />
            <el-option label="自动通过" value="auto_approved" />
          </el-select>
        </el-form-item>

        <el-form-item label="代理">
          <el-select v-model="filter.agent_id" clearable filterable placeholder="全部代理" style="width:190px">
            <el-option v-for="ag in allAgents" :key="ag.id" :label="`${ag.username} (ID:${ag.id})`" :value="ag.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="项目ID">
          <el-input-number
            v-model="filter.project_id"
            :min="1"
            controls-position="right"
            style="width:130px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table
        v-loading="loading"
        :data="requests"
        stripe
        row-key="id"
        style="width:100%"
      >
        <el-table-column prop="id" label="ID" width="80" />

        <el-table-column label="代理" min-width="150">
          <template #default="{ row }">
            <div class="main-text">{{ row.agent_username || `ID=${row.agent_id}` }}</div>
            <div class="sub-text">ID={{ row.agent_id }} · Lv.{{ row.agent_level || '-' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="项目" min-width="170">
          <template #default="{ row }">
            <div class="main-text">{{ row.project_name || `ID=${row.project_id}` }}</div>
            <div class="sub-text">{{ row.project_code || '-' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="105">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" effect="light">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="申请说明" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.request_reason">{{ row.request_reason }}</span>
            <span v-else class="text-muted">未填写</span>
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

            <span v-else class="text-muted">待审核</span>
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
              <el-button text size="small" type="success" @click="openApprove(row)">批准</el-button>
              <el-button text size="small" type="danger" @click="openReject(row)">拒绝</el-button>
            </template>
            <span v-else class="text-muted">无操作</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager-row">
        <span class="total-text">共 {{ total }} 条</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          layout="sizes, prev, pager, next"
          :total="total"
          @current-change="loadRequests"
          @size-change="loadRequests"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="approveDialog.visible"
      title="批准项目开通申请"
      width="560px"
      destroy-on-close
    >
      <el-form label-width="115px">
        <el-form-item label="代理">
          <span class="main-text">{{ approveDialog.row?.agent_username }}</span>
        </el-form-item>

        <el-form-item label="项目">
          <span class="main-text">{{ approveDialog.row?.project_name }}</span>
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

    <el-dialog
      v-model="rejectDialog.visible"
      title="拒绝项目开通申请"
      width="560px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="代理">
          <span class="main-text">{{ rejectDialog.row?.agent_username }}</span>
        </el-form-item>

        <el-form-item label="项目">
          <span class="main-text">{{ rejectDialog.row?.project_name }}</span>
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
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/AgentProjectAuthRequests.vue
 * 名称: 管理员代理项目授权申请审核页面
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能说明:
 *   管理员查看、批准、拒绝代理项目开通申请。
 */

import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { adminProjectAccessApi } from '@/api/admin/projectAccess'
import { agentApi } from '@/api/agent'
import { formatDatetime } from '@/utils/format'

const loading = ref(false)
const allAgents = ref([])
const requests = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

const filter = reactive({
  status: '',
  agent_id: null,
  project_id: null,
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

const statusLabel = (status) => {
  const map = {
    pending: '待审核',
    approved: '已通过',
    rejected: '已拒绝',
    cancelled: '已取消',
    auto_approved: '自动通过',
  }
  return map[status] || status
}

const statusTagType = (status) => {
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
  loading.value = true

  try {
    const res = await adminProjectAccessApi.requests({
      page: page.value,
      page_size: pageSize.value,
      status: filter.status || undefined,
      agent_id: filter.agent_id || undefined,
      project_id: filter.project_id || undefined,
    })

    requests.value = res.data.requests || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

const search = () => {
  page.value = 1
  loadRequests()
}

const resetFilter = () => {
  filter.status = ''
  filter.agent_id = null
  filter.project_id = null
  page.value = 1
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
    await loadRequests()
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

const loadAllAgents = async () => {
  try {
    const res = await agentApi.list({ page_size: 500, status: 'active' })
    allAgents.value = res.data.agents || []
  } catch { /* 静默 */ }
}

onMounted(() => { loadAllAgents(); loadRequests() })
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
}

.filter-card,
.table-card {
  border-radius: 10px;
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

.text-muted {
  color: #94a3b8;
  font-size: 12px;
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
</style>