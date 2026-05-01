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
      title="当前阶段 D 模式“公网中转 / 隧道”是主部署方式；A/B/C 模式作为附属模式保留。点击模式只切换编辑页面，保存后才真正生效。"
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

              <el-descriptions-item label="当前生效部署模式">
                <el-tag type="success" effect="plain">
                  {{ deploymentModeLabel(savedMode || networkForm.deployment_mode) }}
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
          <div class="panel" v-loading="networkLoading">
            <div class="section-head">
              <div>
                <div class="panel-title">网络设置：ABCD 部署模式</div>
                <div class="panel-desc">
                  网络设置负责公网入口、反向代理、中转隧道、客户端连接策略和网络诊断。当前推荐 D 模式：家庭无公网 IP，公网云服务器作为稳定入口，家庭服务器主动连出。
                </div>
              </div>
            </div>

            <div class="mode-status-bar">
              <div>
                <span class="status-label">当前生效模式：</span>
                <el-tag type="success" effect="plain">
                  {{ deploymentModeLabel(savedMode) }}
                </el-tag>
              </div>

              <div>
                <span class="status-label">正在编辑模式：</span>
                <el-tag :type="modeChanged ? 'warning' : 'info'" effect="plain">
                  {{ deploymentModeLabel(editingMode) }}
                </el-tag>
              </div>

              <div>
                <span class="status-label">配置版本：</span>
                <span class="mono">v{{ networkForm.config_version || 1 }}</span>
              </div>
            </div>

            <el-alert
              v-if="modeChanged"
              title="当前只是切换到该模式的编辑页面，尚未保存。客户端不会收到这些配置，直到点击底部“保存网络设置”。"
              type="warning"
              show-icon
              :closable="false"
              class="inner-alert"
            />

            <div class="mode-grid">
              <button
                v-for="mode in modeOptions"
                :key="mode.value"
                type="button"
                :class="['mode-card', editingMode === mode.value ? 'active' : '']"
                @click="editingMode = mode.value"
              >
                <div class="mode-code">{{ mode.code }}</div>
                <div class="mode-name">{{ mode.name }}</div>
                <div class="mode-desc">{{ mode.desc }}</div>

                <el-tag
                  v-if="mode.value === savedMode"
                  size="small"
                  type="success"
                  effect="plain"
                  class="mode-tag"
                >
                  当前生效
                </el-tag>

                <el-tag
                  v-if="mode.value === 'relay_tunnel'"
                  size="small"
                  type="warning"
                  effect="plain"
                  class="mode-tag"
                >
                  当前主线
                </el-tag>
              </button>
            </div>

            <!-- A 模式 -->
            <div v-if="editingMode === 'cloud_direct'" class="mode-panel">
              <div class="mode-panel-title">A 模式：云服务器直接部署</div>

              <div class="mode-flow">
                PC 中控 / 安卓脚本 / 管理后台
                <span> → </span>
                云服务器公网入口
                <span> → </span>
                Nginx / Caddy
                <span> → </span>
                Verify 后端
                <span> → </span>
                PostgreSQL / Redis
              </div>

              <div class="mode-text">
                <p>A 模式表示 Verify 主服务、数据库、Redis 都部署在云服务器上。它是中后期正式运行最稳定、链路最短的模式。</p>
                <p>A 模式需要区分“有域名”和“无域名公网 IP”两种情况。</p>
              </div>

              <div class="mode-two-cols">
                <div class="mode-info-box">
                  <h4>A1：有域名，推荐正式部署</h4>
                  <p>推荐结构：域名 HTTPS → Nginx / Caddy → 127.0.0.1:8000 → Verify。</p>
                  <p>示例：public_api_base_url = https://api.example.com</p>
                  <p>优点：支持 HTTPS、证书、访问日志、限流、静态资源、后续扩展。</p>
                </div>

                <div class="mode-info-box warning">
                  <h4>A2：无域名，仅公网 IP</h4>
                  <p>可以临时使用 http://公网IP:8000 或 http://公网IP。</p>
                  <p>仅建议开发、内测、临时验证使用。</p>
                  <p>正式运行不建议裸露 Uvicorn 端口，仍建议使用 Nginx / Caddy 做入口。</p>
                </div>
              </div>

              <div class="mode-risk">
                <strong>风险提示：</strong>
                PostgreSQL / Redis 不允许暴露公网；无域名无 HTTPS 的方式不适合正式生产；热更新大文件后期建议迁移到对象存储或 CDN。
              </div>
            </div>

            <!-- B 模式 -->
            <div v-if="editingMode === 'home_direct'" class="mode-panel">
              <div class="mode-panel-title">B 模式：家庭宽带直连</div>

              <div class="mode-flow">
                PC 中控 / 安卓脚本 / 管理后台
                <span> → </span>
                家庭公网 IP / DDNS
                <span> → </span>
                路由器端口映射
                <span> → </span>
                家庭服务器 Nginx / Caddy
                <span> → </span>
                Verify
              </div>

              <div class="mode-text">
                <p>B 模式要求家庭宽带具备真正可访问的公网 IPv4，或者公网 IPv6。</p>
                <p>如果路由器 WAN IP 与外网查询 IP 不一致，大概率是 CGNAT，B 模式不可用，应使用 D 模式。</p>
              </div>

              <div class="mode-two-cols">
                <div class="mode-info-box">
                  <h4>是否需要 Nginx / Caddy？</h4>
                  <p>技术上可以不用，例如公网IP:8000 → 路由器端口映射 → Verify。</p>
                  <p>但实际强烈建议使用 Nginx / Caddy，统一 80/443、HTTPS、日志、反代和后续静态资源。</p>
                </div>

                <div class="mode-info-box warning">
                  <h4>使用前置检查</h4>
                  <p>1. 家庭宽带是否有公网 IP / IPv6？</p>
                  <p>2. 是否完成路由器端口映射？</p>
                  <p>3. 是否配置 DDNS？</p>
                  <p>4. 是否能稳定访问 /health？</p>
                </div>
              </div>

              <div class="mode-risk">
                <strong>风险提示：</strong>
                家庭断电、宽带重拨、IP 变化、运营商封端口都会导致服务不可用。家庭无公网 IP 时不要选择 B。
              </div>
            </div>

            <!-- C 模式 -->
            <div v-if="editingMode === 'reverse_proxy'" class="mode-panel">
              <div class="mode-panel-title">C 模式：公网服务器反向代理</div>

              <div class="mode-flow">
                PC 中控 / 安卓脚本 / 管理后台
                <span> → </span>
                云服务器 Nginx / Caddy
                <span> → </span>
                家庭服务器源站
                <span> → </span>
                Verify
              </div>

              <div class="mode-text">
                <p>C 模式表示客户端只访问云服务器，云服务器再反向代理到家庭服务器 Verify。</p>
                <p>它的关键前提是：云服务器必须能够访问家庭服务器源站。</p>
              </div>

              <div class="mode-two-cols">
                <div class="mode-info-box">
                  <h4>C 模式成立条件</h4>
                  <p>1. 家庭服务器有公网 IP / DDNS；或</p>
                  <p>2. 云服务器和家庭服务器处于同一 VPN / WireGuard / Tailscale / ZeroTier 网络；或</p>
                  <p>3. 家庭服务器已经暴露出云服务器可访问的源站地址。</p>
                </div>

                <div class="mode-info-box danger">
                  <h4>重要边界</h4>
                  <p>普通 Nginx / Caddy 反向代理不能穿透 CGNAT。</p>
                  <p>如果家庭无公网 IP，且没有 VPN / 隧道，C 模式不能单独成立。</p>
                  <p>这种情况应使用 D 模式。</p>
                </div>
              </div>

              <div class="mode-risk">
                <strong>风险提示：</strong>
                云服务器到家庭源站不可达时，公网入口会出现 502 / 504；真实 IP Header 必须正确配置。
              </div>
            </div>

            <!-- D 模式 -->
            <div v-if="editingMode === 'relay_tunnel'" class="mode-panel">
              <div class="mode-panel-title">D 模式：公网中转 / 隧道模式（当前主线）</div>

              <div class="mode-flow">
                PC 中控 / 安卓脚本 / 管理后台
                <span> → </span>
                公网云服务器
                <span> → </span>
                中转 / 隧道
                <span> ← </span>
                家庭服务器主动连出
                <span> → </span>
                家庭 Verify
              </div>

              <div class="mode-text">
                <p>D 模式已确认前提：家庭无公网 IP。外部客户端不能主动访问家庭服务器，因此必须由家庭服务器主动连接公网云服务器。</p>
                <p>当前阶段建议固定为 relay_only：PC 中控 / 安卓脚本永远访问公网云服务器入口，公网云服务器再通过隧道访问家庭 Verify。</p>
                <p>在家庭无公网 IP 的前提下，客户端不能真正直连家庭 Verify。所谓“直连”只能是直连公网云服务器入口，链路内部仍然经过中转 / 隧道。</p>
              </div>

              <div class="mode-two-cols">
                <div class="mode-info-box">
                  <h4>推荐落地：FRP + 云 Nginx</h4>
                  <p>客户端 → https://api.example.com → 云 Nginx / Caddy → frps/frpc → 家庭 Verify。</p>
                  <p>适合当前阶段快速落地，家庭服务器不需要公网 IP。</p>
                </div>

                <div class="mode-info-box">
                  <h4>中期方案：WireGuard + 云 Nginx</h4>
                  <p>云服务器和家庭服务器组成虚拟内网，云 Nginx 反代到家庭节点虚拟 IP。</p>
                  <p>更适合中期稳定运行，但初始配置比 FRP 更复杂。</p>
                </div>
              </div>

              <el-divider content-position="left">D 模式：中转 / 家庭节点配置</el-divider>

              <el-form label-width="180px" class="settings-form wide">
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
                  <div class="input-with-action">
                    <el-input
                      v-model="networkForm.relay_url"
                      placeholder="如：https://relay.example.com 或 https://api.example.com"
                      style="width:460px"
                    />
                    <el-button
                      :loading="urlTestLoading.relay_url"
                      @click="testUrl('中转公网地址', networkForm.relay_url, 'relay_url')"
                    >
                      测试
                    </el-button>
                  </div>
                  <UrlTestResult :result="urlTestResults.relay_url" />
                </el-form-item>

                <el-form-item label="中转健康检查">
                  <div class="input-with-action">
                    <el-input
                      v-model="networkForm.relay_health_url"
                      placeholder="如：https://relay.example.com/health"
                      style="width:460px"
                    />
                    <el-button
                      :loading="urlTestLoading.relay_health_url"
                      @click="testUrl('中转健康检查', networkForm.relay_health_url, 'relay_health_url')"
                    >
                      测试
                    </el-button>
                  </div>
                  <UrlTestResult :result="urlTestResults.relay_health_url" />
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

                <el-divider content-position="left">D 模式：连接策略</el-divider>

                <el-form-item label="路由策略">
                  <el-select v-model="networkForm.route_strategy" style="width:340px">
                    <el-option label="relay_only：仅走公网中转 / 隧道（当前推荐）" value="relay_only" />
                    <el-option label="auto_direct_with_relay_fallback：直连优先，失败回中转" value="auto_direct_with_relay_fallback" disabled />
                    <el-option label="direct_only：仅直连（当前不推荐）" value="direct_only" disabled />
                    <el-option label="manual：手动控制" value="manual" />
                  </el-select>
                  <div class="setting-desc">
                    家庭无公网 IP 时应使用 relay_only。自动直连仅在未来有公网 IPv6、DDNS 或 VPN/Mesh 时再启用。
                  </div>
                </el-form-item>

                <el-form-item label="优先线路">
                  <el-select v-model="networkForm.preferred_route" style="width:220px">
                    <el-option label="relay：中转优先" value="relay" />
                    <el-option label="direct：直连优先" value="direct" disabled />
                    <el-option label="auto：自动选择" value="auto" disabled />
                  </el-select>
                </el-form-item>

                <el-form-item label="启用直连候选">
                  <el-switch
                    v-model="networkForm.direct_enabled"
                    inline-prompt
                    active-text="启用"
                    inactive-text="关闭"
                    :disabled="networkForm.route_strategy === 'relay_only'"
                  />
                  <div class="setting-desc">
                    当前 D 模式前提是家庭无公网 IP，因此默认关闭。若未来有公网 IPv6 / VPN / Mesh，可再打开。
                  </div>
                </el-form-item>

                <el-form-item label="直连候选地址">
                  <el-input
                    v-model="directCandidateUrlsText"
                    type="textarea"
                    :rows="4"
                    :disabled="!networkForm.direct_enabled"
                    placeholder="一行一个直连候选地址，例如：&#10;https://home-ddns.example.com&#10;https://[IPv6地址]"
                    style="width:520px"
                  />

                  <div class="setting-desc">
                    当前阶段不建议填写。家庭无公网 IP 时，这些地址通常不可用。
                  </div>

                  <div class="backup-test-list" v-if="splitLines(directCandidateUrlsText).length">
                    <div
                      v-for="(url, index) in splitLines(directCandidateUrlsText)"
                      :key="`${url}-${index}`"
                      class="backup-test-item"
                    >
                      <span class="mono">{{ url }}</span>
                      <el-button
                        size="small"
                        :loading="urlTestLoading[`direct_${index}`]"
                        @click="testUrl(`直连候选 ${index + 1}`, url, `direct_${index}`)"
                      >
                        测试
                      </el-button>
                      <UrlTestResult :result="urlTestResults[`direct_${index}`]" compact />
                    </div>
                  </div>
                </el-form-item>

                <el-form-item label="直连健康检查">
                  <div class="input-with-action">
                    <el-input
                      v-model="networkForm.direct_health_url"
                      :disabled="!networkForm.direct_enabled"
                      placeholder="如：https://home-ddns.example.com/health"
                      style="width:460px"
                    />
                    <el-button
                      :disabled="!networkForm.direct_enabled"
                      :loading="urlTestLoading.direct_health_url"
                      @click="testUrl('直连健康检查', networkForm.direct_health_url, 'direct_health_url')"
                    >
                      测试
                    </el-button>
                  </div>
                  <UrlTestResult :result="urlTestResults.direct_health_url" />
                </el-form-item>

                <el-form-item label="直连连续成功次数">
                  <el-input-number
                    v-model="networkForm.direct_min_success_count"
                    :min="1"
                    :max="10"
                    :disabled="!networkForm.direct_enabled"
                    controls-position="right"
                    style="width:160px"
                  />
                </el-form-item>

                <el-form-item label="失败回退阈值">
                  <el-input-number
                    v-model="networkForm.direct_failback_threshold"
                    :min="1"
                    :max="10"
                    :disabled="!networkForm.direct_enabled"
                    controls-position="right"
                    style="width:160px"
                  />
                </el-form-item>

                <el-form-item label="直连后保留中转">
                  <el-switch
                    v-model="networkForm.relay_keepalive_after_direct"
                    inline-prompt
                    active-text="保留"
                    inactive-text="关闭"
                    :disabled="!networkForm.direct_enabled"
                  />
                  <div class="setting-desc">
                    即使未来直连可用，也建议保留中转作为控制面和回退线路。
                  </div>
                </el-form-item>
              </el-form>

              <div class="mode-risk">
                <strong>当前策略：</strong>
                家庭无公网 IP 时，不做客户端真正直连家庭 Verify。D 模式当前应按 relay_only 运行，公网云服务器入口必须长期保留。
              </div>
            </div>

            <el-divider content-position="left">通用公网入口配置</el-divider>

            <el-form label-width="170px" class="settings-form wide">
              <el-form-item label="对外 API 地址">
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.public_api_base_url"
                    placeholder="如：https://api.example.com 或 http://1.2.3.4:8000"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.public_api_base_url"
                    @click="testUrl('对外 API 地址', networkForm.public_api_base_url, 'public_api_base_url')"
                  >
                    测试
                  </el-button>
                </div>
                <div class="setting-desc">
                  PC 中控、安卓脚本和外部服务最终访问的公网 API 入口。D 模式下通常是云服务器入口，不是家庭服务器内网地址。
                </div>
                <UrlTestResult :result="urlTestResults.public_api_base_url" />
              </el-form-item>

              <el-form-item label="管理后台地址">
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.public_admin_base_url"
                    placeholder="如：https://admin.example.com 或 https://api.example.com"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.public_admin_base_url"
                    @click="testUrl('管理后台地址', networkForm.public_admin_base_url, 'public_admin_base_url')"
                  >
                    测试
                  </el-button>
                </div>
                <UrlTestResult :result="urlTestResults.public_admin_base_url" />
              </el-form-item>

              <el-form-item label="热更新资源地址">
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.public_update_base_url"
                    placeholder="如：https://cdn.example.com/updates"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.public_update_base_url"
                    @click="testUrl('热更新资源地址', networkForm.public_update_base_url, 'public_update_base_url')"
                  >
                    测试
                  </el-button>
                </div>
                <div class="setting-desc">
                  热更新大文件建议优先放公网云服务器 / CDN / 对象存储。D 模式下不建议长期全部走家庭隧道。
                </div>
                <UrlTestResult :result="urlTestResults.public_update_base_url" />
              </el-form-item>

              <el-form-item label="健康检查地址">
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.health_check_url"
                    placeholder="如：https://api.example.com/health"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.health_check_url"
                    @click="testUrl('健康检查地址', networkForm.health_check_url, 'health_check_url')"
                  >
                    测试
                  </el-button>
                </div>
                <UrlTestResult :result="urlTestResults.health_check_url" />
              </el-form-item>
            </el-form>

            <el-divider content-position="left">反向代理与真实 IP</el-divider>

            <el-form label-width="170px" class="settings-form wide">
              <el-form-item label="启用反向代理">
                <el-switch
                  v-model="networkForm.reverse_proxy_enabled"
                  inline-prompt
                  active-text="启用"
                  inactive-text="关闭"
                />
                <div class="setting-desc">
                  A/B/D 正式运行都建议使用 Nginx / Caddy 作为公网入口层。测试期可以不用，但不推荐长期裸露 Uvicorn。
                </div>
              </el-form-item>

              <el-form-item label="反向代理地址">
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.reverse_proxy_url"
                    placeholder="如：https://api.example.com"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.reverse_proxy_url"
                    @click="testUrl('反向代理地址', networkForm.reverse_proxy_url, 'reverse_proxy_url')"
                  >
                    测试
                  </el-button>
                </div>
                <UrlTestResult :result="urlTestResults.reverse_proxy_url" />
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
                  该设置会影响登录日志真实 IP、后续风控和限流判断。只有来自可信代理的 Header 才应该被信任。
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

            <div class="network-save-footer">
              <div class="save-footer-info">
                <div>
                  <span class="status-label">当前生效：</span>
                  <strong>{{ deploymentModeLabel(savedMode) }}</strong>
                </div>
                <div>
                  <span class="status-label">准备保存：</span>
                  <strong :class="{ changed: modeChanged }">{{ deploymentModeLabel(editingMode) }}</strong>
                </div>
                <div>
                  <span class="status-label">配置版本：</span>
                  <span class="mono">v{{ networkForm.config_version || 1 }}</span>
                </div>
                <div>
                  <span class="status-label">D 策略：</span>
                  <span class="mono">{{ networkForm.route_strategy || 'relay_only' }}</span>
                </div>
              </div>

              <div class="save-footer-actions">
                <el-button @click="resetEditingMode">
                  回到生效模式
                </el-button>
                <el-button
                  type="primary"
                  :loading="savingNetwork"
                  @click="saveNetworkSettings"
                >
                  保存网络设置
                </el-button>
              </div>
            </div>
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
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.pc_client_api_url"
                    placeholder="为空时使用对外 API 地址"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.pc_client_api_url"
                    @click="testUrl('PC 中控 API 地址', networkForm.pc_client_api_url || networkForm.public_api_base_url, 'pc_client_api_url')"
                  >
                    测试
                  </el-button>
                </div>
                <UrlTestResult :result="urlTestResults.pc_client_api_url" />
              </el-form-item>

              <el-form-item label="安卓脚本 API 地址">
                <div class="input-with-action">
                  <el-input
                    v-model="networkForm.android_client_api_url"
                    placeholder="为空时使用对外 API 地址"
                    style="width:460px"
                  />
                  <el-button
                    :loading="urlTestLoading.android_client_api_url"
                    @click="testUrl('安卓脚本 API 地址', networkForm.android_client_api_url || networkForm.public_api_base_url, 'android_client_api_url')"
                  >
                    测试
                  </el-button>
                </div>
                <UrlTestResult :result="urlTestResults.android_client_api_url" />
              </el-form-item>

              <el-form-item label="备用 API 地址">
                <el-input
                  v-model="backupApiUrlsText"
                  type="textarea"
                  :rows="4"
                  placeholder="一行一个备用地址，例如：&#10;https://api-bak1.example.com&#10;https://api-bak2.example.com"
                  style="width:460px"
                />

                <div class="backup-test-list" v-if="splitLines(backupApiUrlsText).length">
                  <div
                    v-for="(url, index) in splitLines(backupApiUrlsText)"
                    :key="`${url}-${index}`"
                    class="backup-test-item"
                  >
                    <span class="mono">{{ url }}</span>
                    <el-button
                      size="small"
                      :loading="urlTestLoading[`backup_${index}`]"
                      @click="testUrl(`备用 API ${index + 1}`, url, `backup_${index}`)"
                    >
                      测试
                    </el-button>
                    <UrlTestResult :result="urlTestResults[`backup_${index}`]" compact />
                  </div>
                </div>
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

              <el-form-item>
                <el-button type="primary" :loading="savingNetwork" @click="saveNetworkSettings">
                  保存客户端连接
                </el-button>
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
                  D 模式链路较长，诊断需要分层观察：本机服务、数据库、Redis、公网入口、中转层、请求 Header。
                </div>
              </div>
              <el-button :loading="diagnosticsLoading" @click="loadDiagnostics">
                刷新诊断
              </el-button>
            </div>

            <el-descriptions :column="2" border size="small" v-loading="diagnosticsLoading">
              <el-descriptions-item label="总体状态">
                <el-tag :type="diagnostics.status === 'ok' ? 'success' : 'warning'">
                  {{ diagnostics.status || '未知' }}
                </el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="服务器时间">
                <span class="mono">{{ diagnostics.server_time || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="运行环境">
                <span class="mono">{{ diagnostics.environment || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="后端时区">
                <span class="mono">{{ diagnostics.backend_timezone || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="数据库状态">
                <el-tag :type="diagnostics.database_status === 'ok' ? 'success' : 'danger'">
                  {{ diagnostics.database_status || '未知' }}
                </el-tag>
                <div v-if="diagnostics.database_error" class="diag-error">
                  {{ diagnostics.database_error }}
                </div>
              </el-descriptions-item>

              <el-descriptions-item label="Redis 状态">
                <el-tag :type="diagnostics.redis_status === 'ok' ? 'success' : 'danger'">
                  {{ diagnostics.redis_status || '未知' }}
                </el-tag>
                <div v-if="diagnostics.redis_error" class="diag-error">
                  {{ diagnostics.redis_error }}
                </div>
              </el-descriptions-item>

              <el-descriptions-item label="部署模式">
                {{ deploymentModeLabel(diagnostics.deployment_mode) }}
              </el-descriptions-item>

              <el-descriptions-item label="网络设置已加载">
                {{ diagnostics.network_settings_loaded ? '是' : '否' }}
              </el-descriptions-item>

              <el-descriptions-item label="公网 API 地址">
                <span class="mono">{{ diagnostics.public_api_base_url || '未配置' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="管理后台地址">
                <span class="mono">{{ diagnostics.public_admin_base_url || '未配置' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="热更新地址">
                <span class="mono">{{ diagnostics.public_update_base_url || '未配置' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="中转模式">
                {{ diagnostics.relay_enabled ? '启用' : '关闭' }} / {{ diagnostics.relay_mode || '—' }}
              </el-descriptions-item>

              <el-descriptions-item label="中转地址">
                <span class="mono">{{ diagnostics.relay_url || '未配置' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="中转健康检查">
                <span class="mono">{{ diagnostics.relay_health_url || '未配置' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="D 路由策略">
                <span class="mono">{{ diagnostics.route_strategy || 'relay_only' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="D 优先线路">
                <span class="mono">{{ diagnostics.preferred_route || 'relay' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="直连候选启用">
                {{ diagnostics.direct_enabled ? '启用' : '关闭' }}
              </el-descriptions-item>

              <el-descriptions-item label="直连健康检查">
                <span class="mono">{{ diagnostics.direct_health_url || '未配置' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="直连候选地址" :span="2">
                <span class="mono">
                  {{ Array.isArray(diagnostics.direct_candidate_urls) && diagnostics.direct_candidate_urls.length ? diagnostics.direct_candidate_urls.join('，') : '未配置' }}
                </span>
              </el-descriptions-item>

              <el-descriptions-item label="反向代理">
                {{ diagnostics.reverse_proxy_enabled ? '启用' : '关闭' }}
                <span class="mono">{{ diagnostics.reverse_proxy_url || '' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="真实 IP Header">
                <span class="mono">{{ diagnostics.real_ip_header || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="请求来源 IP">
                <span class="mono">{{ diagnostics.request_remote_addr || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="当前选中的真实 IP">
                <span class="mono">{{ diagnostics.selected_real_ip_value || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="X-Forwarded-For">
                <span class="mono">{{ diagnostics.x_forwarded_for || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="X-Real-IP">
                <span class="mono">{{ diagnostics.x_real_ip || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="CF-Connecting-IP">
                <span class="mono">{{ diagnostics.cf_connecting_ip || '—' }}</span>
              </el-descriptions-item>

              <el-descriptions-item label="可信代理校验">
                {{ diagnostics.trusted_proxy_enabled ? '启用' : '关闭' }}
              </el-descriptions-item>
            </el-descriptions>

            <el-alert
              title="注意：Header 展示用于诊断真实 IP 传递情况。是否真正信任这些 Header，还需要配合可信代理 IP 规则。"
              type="warning"
              show-icon
              :closable="false"
              class="inner-alert diagnostics-tip"
            />
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
                <span class="about-label">当前生效模式</span>
                <span>{{ deploymentModeLabel(savedMode) }}</span>
              </div>

              <div class="about-row">
                <span class="about-label">D 模式策略</span>
                <span class="mono">{{ networkForm.route_strategy || 'relay_only' }}</span>
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
 * 时间: 2026-05-01
 * 版本: V2.3.0
 * 功能说明:
 *   平台级系统设置入口。
 *
 * 本版重点:
 *   1. D 模式连接策略字段前端落地。
 *   2. route_strategy / direct_enabled / direct_candidate_urls / preferred_route 可展示和保存。
 *   3. 运行诊断展示 D 模式路由策略。
 */

import { computed, defineComponent, h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { systemSettingsApi } from '@/api/systemSettings'

const UrlTestResult = defineComponent({
  name: 'UrlTestResult',
  props: {
    result: {
      type: Object,
      default: null,
    },
    compact: {
      type: Boolean,
      default: false,
    },
  },
  setup(props) {
    return () => {
      if (!props.result) return null

      const cls = [
        'url-test-result',
        props.result.success ? 'success' : 'fail',
        props.compact ? 'compact' : '',
      ]

      const text = props.result.success
        ? `连通 · HTTP ${props.result.status_code} · ${props.result.elapsed_ms}ms`
        : `失败 · ${props.result.error || props.result.status_code || '未知错误'} · ${props.result.elapsed_ms ?? '-'}ms`

      return h('div', { class: cls }, text)
    }
  },
})

const settings = useSettingsStore()
const authStore = useAuthStore()

const activeTab = ref('network')
const backendTimezone = ref('Asia/Shanghai')

const networkLoading = ref(false)
const savingNetwork = ref(false)
const diagnosticsLoading = ref(false)

const loadingAny = computed(() => networkLoading.value || savingNetwork.value || diagnosticsLoading.value)

const savedMode = ref('relay_tunnel')
const editingMode = ref('relay_tunnel')

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

  route_strategy: 'relay_only',
  direct_enabled: false,
  direct_candidate_urls: [],
  direct_health_url: '',
  direct_min_success_count: 2,
  direct_failback_threshold: 2,
  relay_keepalive_after_direct: true,
  preferred_route: 'relay',

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
  environment: '',
  backend_timezone: '',

  database_status: '',
  database_error: '',
  redis_status: '',
  redis_error: '',

  network_settings_loaded: false,
  deployment_mode: '',
  public_api_base_url: '',
  public_admin_base_url: '',
  public_update_base_url: '',

  relay_enabled: false,
  relay_mode: '',
  relay_url: '',
  relay_health_url: '',

  route_strategy: '',
  direct_enabled: false,
  direct_candidate_urls: [],
  direct_health_url: '',
  preferred_route: '',

  reverse_proxy_enabled: false,
  reverse_proxy_url: '',
  real_ip_header: '',
  trusted_proxy_enabled: false,

  request_remote_addr: '',
  x_forwarded_for: '',
  x_real_ip: '',
  cf_connecting_ip: '',
  selected_real_ip_value: '',
})

const backupApiUrlsText = ref('')
const trustedProxyIpsText = ref('')
const directCandidateUrlsText = ref('')

const urlTestLoading = reactive({})
const urlTestResults = reactive({})

const now = ref(new Date())
let timer = null

const modeOptions = [
  {
    value: 'cloud_direct',
    code: 'A',
    name: '云服务器直接部署',
    desc: 'Verify、数据库、Redis 部署在云服务器。支持有域名或仅公网 IP 两种入口。',
  },
  {
    value: 'home_direct',
    code: 'B',
    name: '家庭宽带直连',
    desc: '家庭宽带必须有公网 IP / IPv6，并完成端口映射或 DDNS。',
  },
  {
    value: 'reverse_proxy',
    code: 'C',
    name: '公网服务器反向代理',
    desc: '客户端访问云服务器，云服务器主动访问家庭源站。不能单独穿透 CGNAT。',
  },
  {
    value: 'relay_tunnel',
    code: 'D',
    name: '公网中转 / 隧道',
    desc: '家庭无公网 IP 时的主线方案。家庭服务器主动连出，公网云服务器作为入口。',
  },
]

const modeChanged = computed(() => savedMode.value !== editingMode.value)

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

const normalizeDModeForRelayOnly = () => {
  if (networkForm.route_strategy === 'relay_only') {
    networkForm.direct_enabled = false
    networkForm.preferred_route = 'relay'
  }
}

const loadNetworkSettings = async () => {
  networkLoading.value = true

  try {
    const res = await systemSettingsApi.getNetworkSettings()
    Object.assign(networkForm, res.data || {})

    savedMode.value = networkForm.deployment_mode || 'relay_tunnel'
    editingMode.value = savedMode.value

    backupApiUrlsText.value = joinLines(networkForm.backup_api_urls)
    trustedProxyIpsText.value = joinLines(networkForm.trusted_proxy_ips)
    directCandidateUrlsText.value = joinLines(networkForm.direct_candidate_urls)

    normalizeDModeForRelayOnly()
  } finally {
    networkLoading.value = false
  }
}

const buildNetworkPayload = () => {
  normalizeDModeForRelayOnly()

  return {
    ...networkForm,
    deployment_mode: editingMode.value,
    backup_api_urls: splitLines(backupApiUrlsText.value),
    trusted_proxy_ips: splitLines(trustedProxyIpsText.value),
    direct_candidate_urls: splitLines(directCandidateUrlsText.value),
  }
}

const saveNetworkSettings = async () => {
  const message = modeChanged.value
    ? `确认保存网络设置，并将当前生效模式从「${deploymentModeLabel(savedMode.value)}」切换为「${deploymentModeLabel(editingMode.value)}」？`
    : '确认保存系统网络设置？保存后会更新客户端网络配置版本，但不会立即改变当前后台浏览器的请求地址。'

  await ElMessageBox.confirm(
    message,
    '保存网络设置',
    { type: modeChanged.value ? 'warning' : 'info' },
  )

  savingNetwork.value = true

  try {
    const payload = buildNetworkPayload()
    const res = await systemSettingsApi.updateNetworkSettings(payload)

    Object.assign(networkForm, res.data || {})

    savedMode.value = networkForm.deployment_mode || editingMode.value
    editingMode.value = savedMode.value

    backupApiUrlsText.value = joinLines(networkForm.backup_api_urls)
    trustedProxyIpsText.value = joinLines(networkForm.trusted_proxy_ips)
    directCandidateUrlsText.value = joinLines(networkForm.direct_candidate_urls)

    normalizeDModeForRelayOnly()

    ElMessage.success(`网络设置已保存，配置版本 v${networkForm.config_version}`)
  } finally {
    savingNetwork.value = false
  }
}

const resetEditingMode = () => {
  editingMode.value = savedMode.value
  ElMessage.info('已回到当前生效模式的编辑页面')
}

const testUrl = async (targetName, url, resultKey) => {
  const finalUrl = String(url || '').trim()

  if (!finalUrl) {
    ElMessage.warning('请先填写要测试的地址')
    return
  }

  urlTestLoading[resultKey] = true

  try {
    const res = await systemSettingsApi.testUrl({
      target_name: targetName,
      url: finalUrl,
      timeout_seconds: networkForm.client_timeout_seconds || 15,
    })

    urlTestResults[resultKey] = res.data

    if (res.data.success) {
      ElMessage.success(`${targetName} 连通成功`)
    } else {
      ElMessage.warning(`${targetName} 连通失败`)
    }
  } catch (error) {
    console.error(error)
    ElMessage.error(`${targetName} 测试失败`)
  } finally {
    urlTestLoading[resultKey] = false
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

.diagnostics-tip {
  margin-top: 16px;
}

.settings-form {
  max-width: 760px;
  padding-top: 8px;
}

.settings-form.wide {
  max-width: 980px;
}

.input-with-action {
  display: flex;
  align-items: center;
  gap: 8px;
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

.mode-status-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.status-label {
  color: #64748b;
  font-size: 12px;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.mode-card {
  position: relative;
  text-align: left;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 12px;
  padding: 14px 14px 16px;
  cursor: pointer;
  transition: all .15s ease;
  min-height: 130px;
}

.mode-card:hover {
  border-color: #93c5fd;
  box-shadow: 0 4px 14px rgba(37, 99, 235, .08);
}

.mode-card.active {
  border-color: #2563eb;
  background: #eff6ff;
  box-shadow: 0 4px 14px rgba(37, 99, 235, .12);
}

.mode-code {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #2563eb;
  color: #fff;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 8px;
}

.mode-name {
  color: #1e293b;
  font-size: 14px;
  font-weight: 800;
  margin-bottom: 6px;
}

.mode-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.mode-tag {
  margin-top: 8px;
  margin-right: 6px;
}

.mode-panel {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 16px;
}

.mode-panel-title {
  font-size: 16px;
  font-weight: 800;
  color: #1e293b;
  margin-bottom: 10px;
}

.mode-flow {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 10px;
  padding: 12px 14px;
  font-family: 'Cascadia Code', monospace;
  font-size: 12px;
  line-height: 1.7;
  margin-bottom: 14px;
}

.mode-flow span {
  color: #93c5fd;
}

.mode-text {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

.mode-text p {
  margin: 6px 0;
}

.mode-two-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0;
}

.mode-info-box {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  border-radius: 10px;
  padding: 12px 14px;
}

.mode-info-box.warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.mode-info-box.danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.mode-info-box h4 {
  margin: 0 0 8px;
  color: #1e293b;
  font-size: 13px;
  font-weight: 800;
}

.mode-info-box p {
  margin: 4px 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.mode-risk {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 12px;
  color: #78350f;
  font-size: 12px;
  line-height: 1.7;
  border-radius: 8px;
}

.network-save-footer {
  position: sticky;
  bottom: 0;
  z-index: 10;
  margin-top: 22px;
  background: rgba(255, 255, 255, .96);
  backdrop-filter: blur(8px);
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 -4px 16px rgba(15, 23, 42, .08);
  padding: 14px 16px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.save-footer-info {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 22px;
  color: #334155;
  font-size: 13px;
}

.save-footer-info .changed {
  color: #d97706;
}

.save-footer-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.url-test-result {
  margin-top: 5px;
  font-size: 12px;
  font-family: 'Cascadia Code', monospace;
}

.url-test-result.success {
  color: #059669;
}

.url-test-result.fail {
  color: #dc2626;
}

.url-test-result.compact {
  margin-top: 0;
  min-width: 220px;
}

.backup-test-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.backup-test-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #475569;
  font-size: 12px;
}

.diag-error {
  margin-top: 4px;
  color: #dc2626;
  font-size: 12px;
  word-break: break-all;
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
  word-break: break-all;
}

:deep(.el-divider__text) {
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

@media (max-width: 1200px) {
  .mode-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mode-two-cols {
    grid-template-columns: 1fr;
  }

  .network-save-footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>