<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>系统设置</h2>
        <p class="page-desc">
          系统设置用于管理平台运行配置、网络入口、客户端连接策略、运行诊断和系统信息。
        </p>
      </div>

      <div class="header-actions">
        <el-button @click="loadAll" :loading="loadingAny">
          刷新
        </el-button>
      </div>
    </div>

    <el-alert
      title="当前阶段 D 模式“公网中转 / 隧道”是主部署方式；A/B/C 模式作为附属模式保留。"
      type="info"
      show-icon
      :closable="false"
      class="top-alert"
    />

    <el-card shadow="never" class="settings-card">
      <el-tabs v-model="activeTab">
        <!-- 基础信息 -->
        <el-tab-pane label="基础信息" name="basic">
          <div class="panel">
            <div class="panel-title">平台基础信息</div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="平台名称">
                蜂巢·大圣 (HiveGreatSage)
              </el-descriptions-item>
              <el-descriptions-item label="子系统">
                HiveGreatSage-Verify
              </el-descriptions-item>
              <el-descriptions-item label="当前主部署模式">
                <el-tag type="success" effect="plain">
                  {{ deploymentModeLabel(networkForm.deployment_mode) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="网络配置版本">
                <span class="mono">v{{ networkForm.config_version || 1 }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="当前登录身份">
                <el-tag :type="authStore.isAdmin ? 'danger' : 'warning'" effect="light" size="small">
                  {{ authStore.isAdmin ? '管理员' : `代理 Lv.${authStore.userInfo?.level ?? '?'}` }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="当前显示时区">
                <span class="mono">{{ settings.timezone }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-tab-pane>

        <!-- 显示设置 -->
        <el-tab-pane label="显示设置" name="display">
          <div class="panel">
            <div class="panel-title">显示设置</div>
            <el-form label-width="140px" class="settings-form">
              <el-form-item label="显示时区">
                <el-select v-model="settings.timezone" style="width:320px" @change="onTimezoneChange">
                  <el-option-group label="亚洲">
                    <el-option label="UTC+8 北京 / 上海 / 台北 / 香港" value="Asia/Shanghai" />
                    <el-option label="UTC+8 新加坡" value="Asia/Singapore" />
                    <el-option label="UTC+9 东京 / 首尔" value="Asia/Tokyo" />
                    <el-option label="UTC+7 曼谷 / 河内" value="Asia/Bangkok" />
                    <el-option label="UTC+5:30 孟买" value="Asia/Kolkata" />
                  </el-option-group>
                  <el-option-group label="欧洲">
                    <el-option label="UTC+0 伦敦（冬令时）" value="Europe/London" />
                    <el-option label="UTC+1 柏林 / 巴黎（冬令时）" value="Europe/Berlin" />
                  </el-option-group>
                  <el-option-group label="美洲">
                    <el-option label="UTC-5 纽约（冬令时）" value="America/New_York" />
                    <el-option label="UTC-8 洛杉矶（冬令时）" value="America/Los_Angeles" />
                  </el-option-group>
                  <el-option-group label="通用">
                    <el-option label="UTC+0 世界协调时" value="UTC" />
                  </el-option-group>
                </el-select>
                <span class="setting-note">当前时间：{{ currentTimePreview }}</span>
              </el-form-item>

              <el-form-item>
                <el-button plain @click="resetDisplaySettings">
                  恢复显示默认值
                </el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- 网络设置 -->
        <el-tab-pane label="网络设置" name="network">
          <div class="panel">
            <div class="section-head">
              <div>
                <div class="panel-title">公网入口与中转模式</div>
                <div class="panel-desc">
                  当前主线是 D 模式：家庭服务器部署 Verify，公网云服务器提供稳定入口，家庭服务器主动连出建立中转 / 隧道。
                </div>
              </div>
              <el-button type="primary" :loading="savingNetwork" @click="saveNetworkSettings">
                保存网络设置
              </el-button>
            </div>

            <el-alert
              title="保存网络设置不会立即改变当前后台浏览器的请求地址；它主要用于客户端配置下发、热更新地址生成和网络诊断。"
              type="warning"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <el-form label-width="170px" class="settings-form wide" v-loading="networkLoading">
              <el-form-item label="主部署模式">
                <el-radio-group v-model="networkForm.deployment_mode">
                  <el-radio-button label="relay_tunnel">D 公网中转 / 隧道</el-radio-button>
                  <el-radio-button label="cloud_direct">A 云服务器直部署</el-radio-button>
                  <el-radio-button label="home_direct">B 家庭宽带直连</el-radio-button>
                  <el-radio-button label="reverse_proxy">C 公网反向代理</el-radio-button>
                </el-radio-group>
                <div class="setting-desc">
                  当前建议使用 D 模式。A/B/C 保留为附属模式，便于后续切换部署形态。
                </div>
              </el-form-item>

              <el-divider content-position="left">公网入口配置</el-divider>

              <el-form-item label="对外 API 地址">
                <el-input
                  v-model="networkForm.public_api_base_url"
                  placeholder="如：https://api.example.com"
                  style="width:460px"
                />
                <div class="setting-desc">PC 中控、安卓脚本和外部服务最终访问的公网 API 入口。</div>
              </el-form-item>

              <el-form-item label="管理后台地址">
                <el-input
                  v-model="networkForm.public_admin_base_url"
                  placeholder="如：https://admin.example.com"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="热更新资源地址">
                <el-input
                  v-model="networkForm.public_update_base_url"
                  placeholder="如：https://cdn.example.com/updates"
                  style="width:460px"
                />
                <div class="setting-desc">热更新大文件建议优先放公网云服务器 / CDN / 对象存储，避免全部走家庭隧道。</div>
              </el-form-item>

              <el-form-item label="健康检查地址">
                <el-input
                  v-model="networkForm.health_check_url"
                  placeholder="如：https://api.example.com/health"
                  style="width:460px"
                />
              </el-form-item>

              <el-divider content-position="left">D 模式：公网中转 / 隧道</el-divider>

              <el-form-item label="启用中转 / 隧道">
                <el-switch
                  v-model="networkForm.relay_enabled"
                  inline-prompt
                  active-text="启用"
                  inactive-text="关闭"
                />
              </el-form-item>

              <el-form-item label="中转模式">
                <el-select v-model="networkForm.relay_mode" style="width:260px">
                  <el-option label="FRP（现阶段推荐）" value="frp" />
                  <el-option label="WireGuard / VPN" value="wireguard" />
                  <el-option label="Cloudflared Tunnel" value="cloudflared" />
                  <el-option label="自建 Gateway" value="custom_gateway" />
                  <el-option label="手动配置" value="manual" />
                </el-select>
              </el-form-item>

              <el-form-item label="中转公网地址">
                <el-input
                  v-model="networkForm.relay_url"
                  placeholder="如：https://relay.example.com 或 https://api.example.com"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="中转健康检查">
                <el-input
                  v-model="networkForm.relay_health_url"
                  placeholder="如：https://relay.example.com/health"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="家庭节点 ID">
                <el-input v-model="networkForm.home_node_id" style="width:260px" />
              </el-form-item>

              <el-form-item label="家庭节点名称">
                <el-input v-model="networkForm.home_node_name" style="width:260px" />
              </el-form-item>

              <el-form-item label="家庭本地 Verify">
                <el-input
                  v-model="networkForm.home_local_verify_url"
                  placeholder="如：http://127.0.0.1:8000"
                  style="width:460px"
                />
                <div class="setting-desc danger">
                  仅管理员可见，不会下发给 PC 中控或安卓脚本。
                </div>
              </el-form-item>

              <el-divider content-position="left">反向代理与真实 IP</el-divider>

              <el-form-item label="启用反向代理">
                <el-switch
                  v-model="networkForm.reverse_proxy_enabled"
                  inline-prompt
                  active-text="启用"
                  inactive-text="关闭"
                />
              </el-form-item>

              <el-form-item label="反向代理地址">
                <el-input
                  v-model="networkForm.reverse_proxy_url"
                  placeholder="如：https://api.example.com"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="强制 HTTPS">
                <el-switch
                  v-model="networkForm.force_https"
                  inline-prompt
                  active-text="是"
                  inactive-text="否"
                />
              </el-form-item>

              <el-form-item label="真实 IP Header">
                <el-select v-model="networkForm.real_ip_header" style="width:260px">
                  <el-option label="X-Forwarded-For" value="X-Forwarded-For" />
                  <el-option label="X-Real-IP" value="X-Real-IP" />
                  <el-option label="CF-Connecting-IP" value="CF-Connecting-IP" />
                  <el-option label="不使用" value="none" />
                </el-select>
                <div class="setting-desc">
                  该设置会影响登录日志真实 IP、后续风控和限流判断。
                </div>
              </el-form-item>

              <el-form-item label="可信代理校验">
                <el-switch
                  v-model="networkForm.trusted_proxy_enabled"
                  inline-prompt
                  active-text="启用"
                  inactive-text="关闭"
                />
              </el-form-item>

              <el-form-item label="可信代理 IP">
                <el-input
                  v-model="trustedProxyIpsText"
                  type="textarea"
                  :rows="3"
                  placeholder="一行一个 IP，例如：&#10;1.2.3.4&#10;10.0.0.1"
                  style="width:460px"
                />
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- 客户端连接 -->
        <el-tab-pane label="客户端连接" name="client">
          <div class="panel">
            <div class="section-head">
              <div>
                <div class="panel-title">客户端连接策略</div>
                <div class="panel-desc">
                  PC 中控和安卓脚本后续可通过 /api/client/network-config 拉取这些配置，并使用版本号和备用地址进行回退。
                </div>
              </div>
              <el-button type="primary" :loading="savingNetwork" @click="saveNetworkSettings">
                保存客户端连接
              </el-button>
            </div>

            <el-form label-width="170px" class="settings-form wide" v-loading="networkLoading">
              <el-form-item label="启用配置下发">
                <el-switch
                  v-model="networkForm.client_config_enabled"
                  inline-prompt
                  active-text="启用"
                  inactive-text="关闭"
                />
              </el-form-item>

              <el-form-item label="配置版本">
                <el-input-number
                  v-model="networkForm.config_version"
                  :min="1"
                  disabled
                  controls-position="right"
                  style="width:160px"
                />
                <span class="setting-note">每次保存后端会自动 +1</span>
              </el-form-item>

              <el-form-item label="PC 中控 API 地址">
                <el-input
                  v-model="networkForm.pc_client_api_url"
                  placeholder="为空时使用对外 API 地址"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="安卓脚本 API 地址">
                <el-input
                  v-model="networkForm.android_client_api_url"
                  placeholder="为空时使用对外 API 地址"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="备用 API 地址">
                <el-input
                  v-model="backupApiUrlsText"
                  type="textarea"
                  :rows="4"
                  placeholder="一行一个备用地址，例如：&#10;https://api-bak1.example.com&#10;https://api-bak2.example.com"
                  style="width:460px"
                />
              </el-form-item>

              <el-form-item label="请求超时">
                <el-input-number
                  v-model="networkForm.client_timeout_seconds"
                  :min="3"
                  :max="120"
                  controls-position="right"
                  style="width:160px"
                />
                <span class="setting-note">秒。D 模式链路较长，建议 15 秒。</span>
              </el-form-item>

              <el-form-item label="请求重试次数">
                <el-input-number
                  v-model="networkForm.client_retry_count"
                  :min="1"
                  :max="10"
                  controls-position="right"
                  style="width:160px"
                />
              </el-form-item>

              <el-form-item label="心跳间隔">
                <el-input-number
                  v-model="networkForm.heartbeat_interval_seconds"
                  :min="10"
                  :max="300"
                  controls-position="right"
                  style="width:160px"
                />
                <span class="setting-note">秒。建议 30 秒。</span>
              </el-form-item>

              <el-form-item label="允许客户端拉取">
                <el-switch
                  v-model="networkForm.allow_client_config_pull"
                  inline-prompt
                  active-text="允许"
                  inactive-text="禁止"
                />
              </el-form-item>

              <el-form-item label="允许自动回退">
                <el-switch
                  v-model="networkForm.allow_client_auto_failover"
                  inline-prompt
                  active-text="允许"
                  inactive-text="禁止"
                />
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- 运行诊断 -->
        <el-tab-pane label="运行诊断" name="diagnostics">
          <div class="panel">
            <div class="section-head">
              <div>
                <div class="panel-title">运行诊断</div>
                <div class="panel-desc">
                  当前先提供基础诊断；后续会扩展公网入口、中转服务、家庭节点和请求 Header 诊断。
                </div>
              </div>
              <el-button :loading="diagnosticsLoading" @click="loadDiagnostics">
                刷新诊断
              </el-button>
            </div>

            <el-descriptions :column="2" border size="small" v-loading="diagnosticsLoading">
              <el-descriptions-item label="状态">
                <el-tag :type="diagnostics.status === 'ok' ? 'success' : 'danger'">
                  {{ diagnostics.status || '未知' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="服务器时间">
                <span class="mono">{{ diagnostics.server_time || '—' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="网络设置已加载">
                {{ diagnostics.network_settings_loaded ? '是' : '否' }}
              </el-descriptions-item>
              <el-descriptions-item label="部署模式">
                {{ deploymentModeLabel(diagnostics.deployment_mode) }}
              </el-descriptions-item>
              <el-descriptions-item label="公网 API 地址">
                <span class="mono">{{ diagnostics.public_api_base_url || '未配置' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="中转状态">
                {{ diagnostics.relay_enabled ? '启用' : '关闭' }} / {{ diagnostics.relay_mode || '—' }}
              </el-descriptions-item>
              <el-descriptions-item label="中转地址" :span="2">
                <span class="mono">{{ diagnostics.relay_url || '未配置' }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-tab-pane>

        <!-- 热更新设置 -->
        <el-tab-pane label="热更新设置" name="updates">
          <div class="placeholder-panel">
            <div class="placeholder-title">热更新设置</div>
            <div class="placeholder-desc">
              后续将接入热更新总开关、PC/安卓更新策略、默认更新通道、强制更新、灰度比例、更新包公网基础地址和校验策略。
            </div>
          </div>
        </el-tab-pane>

        <!-- 安全设置 -->
        <el-tab-pane label="安全设置" name="security">
          <div class="placeholder-panel">
            <div class="placeholder-title">安全设置</div>
            <div class="placeholder-desc">
              后续将接入登录失败锁定、设备绑定策略、管理员访问限制、真实 IP 可信代理规则等。SECRET_KEY、数据库密码、Redis 密码不允许在前台修改。
            </div>
          </div>
        </el-tab-pane>

        <!-- 日志与审计 -->
        <el-tab-pane label="日志与审计" name="logs">
          <div class="placeholder-panel">
            <div class="placeholder-title">日志与审计</div>
            <div class="placeholder-desc">
              后续将接入登录日志保留策略、设备运行缓存清理策略、管理员操作日志、代理操作日志和异常日志采集。账务账本不在普通清理范围内。
            </div>
          </div>
        </el-tab-pane>

        <!-- 数据维护 -->
        <el-tab-pane label="数据维护" name="maintenance">
          <div class="placeholder-panel">
            <div class="placeholder-title">数据维护</div>
            <div class="placeholder-desc">
              后续将接入刷新配置缓存、导出基础配置、查看数据库迁移版本、跳转账务对账等维护能力。高风险操作必须二次确认。
            </div>
          </div>
        </el-tab-pane>

        <!-- 关于系统 -->
        <el-tab-pane label="关于系统" name="about">
          <div class="panel">
            <div class="panel-title">关于系统</div>
            <div class="about-info">
              <div class="about-row">
                <span class="about-label">平台名称</span>
                <span>蜂巢·大圣 (HiveGreatSage)</span>
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
                <span class="about-label">网络配置版本</span>
                <span class="mono">v{{ networkForm.config_version || 1 }}</span>
              </div>
              <div class="about-row">
                <span class="about-label">当前登录身份</span>
                <el-tag :type="authStore.isAdmin ? 'danger' : 'warning'" effect="light" size="small">
                  {{ authStore.isAdmin ? '管理员' : `代理 Lv.${authStore.userInfo?.level ?? '?'}` }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/views/admin/SettingsView.vue
 * 名称: 系统设置
 * 作者: 蜂巢·大圣 (HiveGreatSage)
 * 时间: 2026-04-30
 * 版本: V2.0.0
 * 功能说明:
 *   平台级系统设置入口。
 *
 * 本版重点:
 *   1. 从单页卡片升级为 Tabs 结构。
 *   2. D 模式：公网中转 / 隧道模式作为主部署模式。
 *   3. 网络设置支持前台编辑保存。
 *   4. 客户端连接策略支持保存。
 *   5. 运行诊断初步接入。
 */

import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { systemSettingsApi } from '@/api/systemSettings'

const settings = useSettingsStore()
const authStore = useAuthStore()

const activeTab = ref('network')
const backendTimezone = ref('Asia/Shanghai')

const networkLoading = ref(false)
const savingNetwork = ref(false)
const diagnosticsLoading = ref(false)

const loadingAny = computed(() => networkLoading.value || savingNetwork.value || diagnosticsLoading.value)

const networkForm = reactive({
  deployment_mode: 'relay_tunnel',

  public_api_base_url: '',
  public_admin_base_url: '',
  public_update_base_url: '',
  health_check_url: '',

  reverse_proxy_enabled: true,
  reverse_proxy_url: '',
  force_https: true,
  real_ip_header: 'X-Forwarded-For',
  trusted_proxy_enabled: false,
  trusted_proxy_ips: [],

  relay_enabled: true,
  relay_mode: 'frp',
  relay_url: '',
  relay_health_url: '',
  home_node_id: 'home-main-001',
  home_node_name: '家庭主节点',
  home_local_verify_url: 'http://127.0.0.1:8000',

  client_config_enabled: true,
  config_version: 1,
  pc_client_api_url: '',
  android_client_api_url: '',
  backup_api_urls: [],
  client_timeout_seconds: 15,
  client_retry_count: 3,
  heartbeat_interval_seconds: 30,
  allow_client_config_pull: true,
  allow_client_auto_failover: true,
})

const diagnostics = reactive({
  status: '',
  server_time: '',
  network_settings_loaded: false,
  deployment_mode: '',
  public_api_base_url: '',
  relay_enabled: false,
  relay_mode: '',
  relay_url: '',
})

const backupApiUrlsText = ref('')
const trustedProxyIpsText = ref('')

const now = ref(new Date())
let timer = null

const currentTimePreview = computed(() => {
  return now.value.toLocaleString('zh-CN', {
    timeZone: settings.timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
})

const deploymentModeLabel = (mode) => {
  const map = {
    relay_tunnel: 'D 公网中转 / 隧道模式',
    cloud_direct: 'A 云服务器直接部署',
    home_direct: 'B 家庭宽带直连',
    reverse_proxy: 'C 公网服务器反向代理',
  }
  return map[mode] || mode || '未知'
}

const splitLines = (value) => {
  return String(value || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

const joinLines = (items) => {
  return Array.isArray(items) ? items.join('\n') : ''
}

const loadNetworkSettings = async () => {
  networkLoading.value = true

  try {
    const res = await systemSettingsApi.getNetworkSettings()
    Object.assign(networkForm, res.data || {})

    backupApiUrlsText.value = joinLines(networkForm.backup_api_urls)
    trustedProxyIpsText.value = joinLines(networkForm.trusted_proxy_ips)
  } finally {
    networkLoading.value = false
  }
}

const buildNetworkPayload = () => {
  return {
    ...networkForm,
    backup_api_urls: splitLines(backupApiUrlsText.value),
    trusted_proxy_ips: splitLines(trustedProxyIpsText.value),
  }
}

const saveNetworkSettings = async () => {
  await ElMessageBox.confirm(
    '确认保存系统网络设置？保存后会更新客户端网络配置版本，但不会立即改变当前后台浏览器的请求地址。',
    '保存网络设置',
    { type: 'warning' },
  )

  savingNetwork.value = true

  try {
    const payload = buildNetworkPayload()
    const res = await systemSettingsApi.updateNetworkSettings(payload)

    Object.assign(networkForm, res.data || {})
    backupApiUrlsText.value = joinLines(networkForm.backup_api_urls)
    trustedProxyIpsText.value = joinLines(networkForm.trusted_proxy_ips)

    ElMessage.success(`网络设置已保存，配置版本 v${networkForm.config_version}`)
  } finally {
    savingNetwork.value = false
  }
}

const loadDiagnostics = async () => {
  diagnosticsLoading.value = true

  try {
    const res = await systemSettingsApi.getDiagnostics()
    Object.assign(diagnostics, res.data || {})
  } finally {
    diagnosticsLoading.value = false
  }
}

const loadAll = async () => {
  try {
    await Promise.all([
      loadNetworkSettings(),
      loadDiagnostics(),
    ])
  } catch (error) {
    console.error(error)
    ElMessage.error('系统设置加载失败')
  }
}

const onTimezoneChange = (val) => {
  ElMessage.success(`时区已切换为 ${val}，所有时间展示立即生效`)
}

const resetDisplaySettings = () => {
  settings.reset()
  ElMessage.success('显示设置已恢复默认')
}

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date()
  }, 1000)

  loadAll()
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.top-alert,
.settings-card {
  border-radius: 10px;
}

.panel {
  padding: 4px 0 8px;
}

.panel-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 12px;
}

.panel-desc {
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
  max-width: 900px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.inner-alert {
  border-radius: 8px;
  margin-bottom: 16px;
}

.settings-form {
  max-width: 760px;
  padding-top: 8px;
}

.settings-form.wide {
  max-width: 980px;
}

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

.setting-desc.danger {
  color: #dc2626;
}

.placeholder-panel {
  border: 1px dashed #cbd5e1;
  background: #f8fafc;
  border-radius: 10px;
  padding: 24px;
}

.placeholder-title {
  font-size: 16px;
  font-weight: 800;
  color: #1e293b;
}

.placeholder-desc {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.about-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

.about-row {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: #475569;
}

.about-label {
  width: 140px;
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 12px;
}

.mono {
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
}

:deep(.el-divider__text) {
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}
</style>