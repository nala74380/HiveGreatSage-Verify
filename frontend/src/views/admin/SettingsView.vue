<template>
  <div class="page">
    <div class="page-header">
      <h2>系统设置</h2>
      <el-button @click="resetAll" plain>恢复默认</el-button>
    </div>

    <!-- 显示设置 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-title">
          <el-icon><Clock /></el-icon>
          显示设置
        </div>
      </template>

      <el-form label-width="120px" class="settings-form">
        <!-- 时区选择 -->
        <el-form-item label="显示时区">
          <el-select v-model="settings.timezone" style="width:260px" @change="onTimezoneChange">
            <el-option-group label="亚洲">
              <el-option label="UTC+8  北京 / 上海 / 台北 / 香港" value="Asia/Shanghai" />
              <el-option label="UTC+8  新加坡"                     value="Asia/Singapore" />
              <el-option label="UTC+9  东京 / 首尔"                value="Asia/Tokyo" />
              <el-option label="UTC+7  曼谷 / 河内"                value="Asia/Bangkok" />
              <el-option label="UTC+5:30 孟买"                    value="Asia/Kolkata" />
            </el-option-group>
            <el-option-group label="欧洲">
              <el-option label="UTC+0  伦敦（冬令时）"             value="Europe/London" />
              <el-option label="UTC+1  柏林 / 巴黎（冬令时）"      value="Europe/Berlin" />
            </el-option-group>
            <el-option-group label="美洲">
              <el-option label="UTC-5  纽约（冬令时）"              value="America/New_York" />
              <el-option label="UTC-8  洛杉矶（冬令时）"            value="America/Los_Angeles" />
            </el-option-group>
            <el-option-group label="通用">
              <el-option label="UTC+0  世界协调时"                  value="UTC" />
            </el-option-group>
          </el-select>
          <span class="setting-note">当前时间：{{ currentTimePreview }}</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 网络设置（Phase 2+ 占位） -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-title">
          <el-icon><Connection /></el-icon>
          网络设置
          <el-tag type="info" size="small" effect="plain" style="margin-left:8px">Phase 2+</el-tag>
        </div>
      </template>

      <el-form label-width="120px" class="settings-form">
        <!-- 网络中转 -->
        <el-form-item label="网络中转地址">
          <el-input
            v-model="networkForm.relay_url"
            placeholder="如：https://relay.example.com（留空表示直连）"
            style="width:360px"
            disabled
          />
          <div class="setting-desc">PC中控和安卓脚本通过中转服务器访问验证系统，适用于内网穿透场景。</div>
        </el-form-item>

        <!-- 反向代理 -->
        <el-form-item label="反向代理">
          <el-input
            v-model="networkForm.reverse_proxy_url"
            placeholder="如：https://api.yourdomain.com（留空表示直连）"
            style="width:360px"
            disabled
          />
          <div class="setting-desc">通过 Nginx 等反向代理暴露服务，隐藏真实服务器地址。</div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" disabled>保存网络设置（Phase 2 实现）</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 关于 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-title">
          <el-icon><InfoFilled /></el-icon>
          关于
        </div>
      </template>
      <div class="about-info">
        <div class="about-row">
          <span class="about-label">平台名称</span>
          <span>蜂巢·大圣 (Hive-GreatSage)</span>
        </div>
        <div class="about-row">
          <span class="about-label">后端版本</span>
          <span class="mono">HiveGreatSage-Verify v0.1.0</span>
        </div>
        <div class="about-row">
          <span class="about-label">后端时区</span>
          <span class="mono">{{ backendTimezone }} (UTC+8，数据库以 UTC 存储)</span>
        </div>
        <div class="about-row">
          <span class="about-label">前端展示时区</span>
          <span class="mono">{{ settings.timezone }}</span>
        </div>
        <div class="about-row">
          <span class="about-label">当前登录身份</span>
          <el-tag :type="authStore.isAdmin ? 'danger' : 'warning'" effect="light" size="small">
            {{ authStore.isAdmin ? '管理员' : `代理 Lv.${authStore.userInfo?.level ?? '?'}` }}
          </el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Clock, Connection, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore }     from '@/stores/auth'
import { formatDatetime }   from '@/utils/format'

const settings  = useSettingsStore()
const authStore = useAuthStore()

// 后端时区（固定显示，来自 .env 配置）
const backendTimezone = ref('Asia/Shanghai')

// 网络设置（Phase 2 占位，不可编辑）
const networkForm = ref({ relay_url: '', reverse_proxy_url: '' })

// ── 当前时间实时预览 ─────────────────────────────────────────
const now = ref(new Date())
let timer = null

const currentTimePreview = computed(() => {
  return now.value.toLocaleString('zh-CN', {
    timeZone: settings.timezone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
})

onMounted(() => {
  timer = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => clearInterval(timer))

// ── 时区变更 ─────────────────────────────────────────────────
const onTimezoneChange = (val) => {
  ElMessage.success(`时区已切换为 ${val}，所有时间展示立即生效`)
}

// ── 恢复默认 ─────────────────────────────────────────────────
const resetAll = () => {
  settings.reset()
  ElMessage.success('已恢复默认设置')
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }

.page-header {
  display: flex; align-items: center; justify-content: space-between;
}
.page-header h2 { margin: 0; font-size: 18px; color: #1e293b; }

.settings-card { border-radius: 10px; }

.card-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600; color: #1e293b;
}

.settings-form { max-width: 700px; padding-top: 8px; }

.setting-note {
  margin-left: 12px;
  font-size: 12px;
  color: #64748b;
  font-family: 'Cascadia Code', monospace;
}

.setting-desc {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
  line-height: 1.6;
}

/* 关于区域 */
.about-info { display: flex; flex-direction: column; gap: 12px; padding: 4px 0; }

.about-row {
  display: flex; align-items: center; gap: 16px;
  font-size: 13px; color: #475569;
}

.about-label {
  width: 120px;
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 12px;
}

.mono { font-family: 'Cascadia Code', monospace; font-size: 12px; }
</style>
