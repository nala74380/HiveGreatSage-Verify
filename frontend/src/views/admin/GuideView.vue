<template>
  <div class="guide-page">
    <div class="guide-header">
      <div>
        <h2>网络验证系统使用指南</h2>
        <p>面向后台维护、PC 中控、Android 脚本和后续接手开发者的部署与对接说明。</p>
      </div>
      <span class="version-badge">Verify v0.1.0</span>
    </div>

    <el-tabs v-model="activeTab" class="guide-tabs" type="border-card">
      <el-tab-pane label="系统定位" name="overview">
        <section class="section">
          <h3>核心边界</h3>
          <el-table :data="conceptRows" size="small" class="info-table">
            <el-table-column prop="name" label="对象" width="180" />
            <el-table-column prop="meaning" label="含义" min-width="260" />
            <el-table-column prop="note" label="开发注意" min-width="320" />
          </el-table>
        </section>

        <section class="section">
          <h3>业务主流程</h3>
          <div class="flow-line">
            <span>管理员创建项目</span>
            <span>创建代理</span>
            <span>授予代理项目权限</span>
            <span>代理创建用户</span>
            <span>授予用户项目授权</span>
            <span>终端登录验证</span>
            <span>设备心跳与热更新</span>
          </div>
        </section>

        <section class="section">
          <h3>项目标识</h3>
          <el-table :data="projectIdRows" size="small" class="info-table">
            <el-table-column prop="field" label="字段" width="180" />
            <el-table-column prop="where" label="使用位置" />
            <el-table-column prop="rule" label="规则" />
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="部署启动" name="deploy">
        <section class="section">
          <h3>环境要求</h3>
          <el-table :data="requirementsData" size="small" class="info-table">
            <el-table-column prop="item" label="组件" width="160" />
            <el-table-column prop="requirement" label="要求" />
            <el-table-column prop="note" label="备注" />
          </el-table>
        </section>

        <section class="section">
          <h3>首次部署步骤</h3>
          <el-steps direction="vertical" :active="99" class="deploy-steps">
            <el-step v-for="step in deploySteps" :key="step.title" :title="step.title">
              <template #description>
                <div class="step-desc">
                  <p>{{ step.desc }}</p>
                  <CodeBlock v-if="step.code" :code="step.code" :lang="step.lang || 'bash'" />
                </div>
              </template>
            </el-step>
          </el-steps>
        </section>

        <section class="section">
          <h3>.env 关键配置</h3>
          <CodeBlock :code="envConfig" lang="bash" />
        </section>

        <section class="section">
          <h3>服务启动命令</h3>
          <CodeBlock :code="startCmds" lang="bash" />
        </section>
      </el-tab-pane>

      <el-tab-pane label="初始化流程" name="bootstrap">
        <section class="section">
          <h3>后台初始化顺序</h3>
          <el-table :data="bootstrapRows" size="small" class="info-table">
            <el-table-column prop="step" label="顺序" width="80" />
            <el-table-column prop="action" label="操作" min-width="220" />
            <el-table-column prop="api" label="接口或页面" min-width="240" />
            <el-table-column prop="note" label="注意事项" min-width="360" />
          </el-table>
        </section>

        <section class="section">
          <h3>创建用户与项目授权示例</h3>
          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <p class="sub-label">创建用户主体</p>
              <CodeBlock :code="createUserExample" lang="json" />
            </el-col>
            <el-col :xs="24" :md="12">
              <p class="sub-label">授予项目授权</p>
              <CodeBlock :code="grantAuthExample" lang="json" />
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3>新版授权口径</h3>
          <el-alert type="warning" show-icon :closable="false">
            <template #default>
              用户等级、授权设备数、到期时间不再属于 User 表。所有终端登录、刷新、设备限额判断均以 Authorization 为事实源。
            </template>
          </el-alert>
        </section>
      </el-tab-pane>

      <el-tab-pane label="接口契约" name="apis">
        <section class="section">
          <el-alert type="info" show-icon :closable="false" class="notice">
            <template #default>
              基础地址开发环境通常为 <code>http://127.0.0.1:8000</code>。除登录和健康检查外，业务接口使用
              <code>Authorization: Bearer &lt;token&gt;</code>。
            </template>
          </el-alert>
          <el-table :data="apiList" size="small" class="api-table" :row-class-name="apiRowClass">
            <el-table-column label="方法" width="82">
              <template #default="{ row }">
                <el-tag :type="methodType(row.method)" size="small" effect="dark">{{ row.method }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="路径" min-width="270">
              <template #default="{ row }">
                <code class="path-code">{{ row.path }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="desc" label="说明" min-width="260" />
            <el-table-column label="鉴权" width="150">
              <template #default="{ row }">
                <el-tag
                  v-for="t in row.auth"
                  :key="t"
                  size="small"
                  effect="plain"
                  :type="authType(t)"
                  class="auth-tag"
                >
                  {{ t }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="终端接入" name="client">
        <section class="section">
          <h3>登录验证</h3>
          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <p class="sub-label">请求体</p>
              <CodeBlock :code="loginRequest" lang="json" />
            </el-col>
            <el-col :xs="24" :md="12">
              <p class="sub-label">成功响应</p>
              <CodeBlock :code="loginResponse" lang="json" />
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3>PC 中控接入示例</h3>
          <CodeBlock :code="pcPythonCode" lang="python" />
        </section>

        <section class="section">
          <h3>Android 脚本接入示例</h3>
          <CodeBlock :code="androidCode" lang="javascript" />
        </section>

        <section class="section">
          <h3>设备绑定规则</h3>
          <el-table :data="bindingLogic" size="small" class="info-table">
            <el-table-column prop="condition" label="条件" min-width="320" />
            <el-table-column prop="result" label="结果" width="140" />
            <el-table-column prop="action" label="后续动作" min-width="320" />
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="心跳与热更新" name="runtime">
        <section class="section">
          <h3>心跳上报</h3>
          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <p class="sub-label">请求体</p>
              <CodeBlock :code="heartbeatRequest" lang="json" />
            </el-col>
            <el-col :xs="24" :md="12">
              <p class="sub-label">game_data 建议结构</p>
              <CodeBlock :code="gameDataExample" lang="json" />
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3>热更新检查与下载</h3>
          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <p class="sub-label">检查版本</p>
              <CodeBlock :code="updateCheckReq" lang="bash" />
            </el-col>
            <el-col :xs="24" :md="12">
              <p class="sub-label">获取下载地址</p>
              <CodeBlock :code="updateDownloadReq" lang="bash" />
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3>客户端更新伪代码</h3>
          <CodeBlock :code="updateClientCode" lang="python" />
        </section>
      </el-tab-pane>

      <el-tab-pane label="排障清单" name="troubleshooting">
        <section class="section">
          <h3>常见失败原因</h3>
          <el-table :data="failReasons" size="small" class="info-table">
            <el-table-column prop="http" label="HTTP" width="90" />
            <el-table-column prop="reason" label="原因" min-width="240" />
            <el-table-column prop="check" label="排查点" min-width="360" />
          </el-table>
        </section>

        <section class="section">
          <h3>上线前检查</h3>
          <el-table :data="releaseChecklist" size="small" class="info-table">
            <el-table-column prop="item" label="项目" width="220" />
            <el-table-column prop="check" label="检查内容" min-width="420" />
            <el-table-column prop="command" label="命令或入口" min-width="280" />
          </el-table>
        </section>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { h, ref } from 'vue'
import { ElMessage } from 'element-plus'

const activeTab = ref('overview')

const CodeBlock = (props) => {
  const copy = () => {
    navigator.clipboard.writeText(props.code)
    ElMessage.success('已复制')
  }
  return h('div', { class: 'code-block' }, [
    h('button', { class: 'copy-btn', onClick: copy }, '复制'),
    h('pre', h('code', { class: `lang-${props.lang}` }, props.code)),
  ])
}

const requirementsData = [
  { item: 'Python', requirement: '3.11+', note: '后端、Celery、Alembic 迁移使用' },
  { item: 'PostgreSQL', requirement: '14+', note: '主库 hive_platform；按项目可扩展游戏库' },
  { item: 'Redis', requirement: '7.0+', note: 'Refresh Token、Access Token 黑名单、心跳缓存、热更新缓存' },
  { item: 'Node.js', requirement: '18+', note: '前端开发和构建使用' },
  { item: '存储', requirement: 'local 或对象存储', note: '热更新包通过 Storage 抽象保存并生成下载地址' },
  { item: '反向代理', requirement: 'nginx 或同类网关', note: '生产环境建议统一 TLS、静态资源、上传包下载路径' },
]

const conceptRows = [
  {
    name: 'User',
    meaning: '账号主体，只保存用户名、密码、创建者、账号状态。',
    note: '不要在 User 上读取等级、设备数、到期时间，这些字段已迁移到 Authorization。',
  },
  {
    name: 'Authorization',
    meaning: '用户在某个项目下的授权记录。',
    note: '登录响应的 authorization_level、设备上限、到期时间都来自这里。',
  },
  {
    name: 'DeviceBinding',
    meaning: '用户、项目、设备指纹三元绑定。',
    note: 'Android 登录会创建绑定并占用设备名额；PC 登录不占用 Android 设备名额。',
  },
  {
    name: 'AgentProjectAuth',
    meaning: '代理能销售或开通哪些项目。',
    note: '代理给用户授权前，自己必须先拥有该项目的 active 授权。',
  },
  {
    name: 'VersionRecord',
    meaning: '热更新版本记录。',
    note: '客户端 check/download 读取主库 VersionRecord，按 project + client_type 区分。',
  },
]

const projectIdRows = [
  { field: 'project_uuid', where: 'PC/Android 登录请求', rule: '终端配置必须和后台项目 UUID 完全一致。' },
  { field: 'project_id', where: '后台管理、授权、热更新上传', rule: '数据库主键，仅后台和服务端内部使用。' },
  { field: 'code_name', where: 'Token、设备、热更新缓存、展示', rule: '项目代码名应稳定，不建议上线后变更。' },
]

const deploySteps = [
  {
    title: '1. 安装后端依赖',
    desc: '建议使用独立虚拟环境，避免覆盖全局 Python 依赖。',
    code: `cd HiveGreatSage-Verify
python -m venv .venv
.venv\\Scripts\\activate
python -m pip install -r requirements.txt`,
  },
  {
    title: '2. 准备 PostgreSQL 与 Redis',
    desc: '主库用于账号、代理、授权、设备绑定、热更新、账务；Redis 用于短时状态和 Token 状态。',
    code: `# 示例库名
hive_platform

# Redis 示例
redis://127.0.0.1:6379/0`,
  },
  {
    title: '3. 配置 .env',
    desc: '复制模板后填写数据库、Redis、密钥、存储和跨域配置。',
    code: `copy .env.example .env
# 修改 DATABASE_MAIN_URL / REDIS_URL / SECRET_KEY / CORS_ORIGINS`,
  },
  {
    title: '4. 执行迁移',
    desc: '迁移会创建或升级主库结构。当前 User 旧授权字段应由 0016 迁移清理。',
    code: `alembic current
alembic upgrade head`,
  },
  {
    title: '5. 初始化数据',
    desc: '创建管理员、默认项目、测试数据时优先使用项目脚本或后台页面，不直接手写业务数据。',
    code: `python scripts/init_data.py
# 如需创建游戏库，按项目脚本执行 setup_game_db / setup_real_env`,
  },
  {
    title: '6. 构建前端',
    desc: '开发环境用 Vite，生产环境将 dist 交给 nginx 或静态资源服务。',
    code: `cd frontend
npm install
npm run build`,
  },
]

const envConfig = `SECRET_KEY=<至少 32 字节随机密钥>
DATABASE_MAIN_URL=postgresql+asyncpg://hive_user:password@127.0.0.1:5432/hive_platform
REDIS_URL=redis://127.0.0.1:6379/0

ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

STORAGE_MODE=local
STORAGE_LOCAL_ROOT=storage/updates
S3_URL_EXPIRE_SECONDS=600`

const startCmds = `# 后端 API
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Celery Worker，负责心跳异步落库等任务
celery -A app.core.celery_app worker --loglevel=info

# Celery Beat，如启用周期任务
celery -A app.core.celery_app beat --loglevel=info

# 前端开发服务
cd frontend
npm run dev`

const bootstrapRows = [
  { step: '1', action: '管理员登录', api: 'POST /admin/api/auth/login', note: '拿到 admin token 后才能创建项目、代理、上传热更新包。' },
  { step: '2', action: '创建项目', api: 'POST /admin/api/projects/', note: '记录 project_uuid；终端登录必须使用该 UUID。' },
  { step: '3', action: '创建代理', api: 'POST /api/agents/', note: '管理员创建顶级代理；代理状态必须 active。' },
  { step: '4', action: '代理项目授权', api: 'POST /admin/api/agents/{id}/project-auths/', note: '代理只能给用户开通自己已授权的项目。' },
  { step: '5', action: '创建用户主体', api: 'POST /api/users/', note: '只传 username/password；不要传 user_level/max_devices/expired_at。' },
  { step: '6', action: '授予用户项目授权', api: 'POST /api/users/{id}/authorizations', note: '设置 user_level、authorized_devices、valid_until。' },
  { step: '7', action: '终端登录', api: 'POST /api/auth/login', note: 'Android 登录会创建 DeviceBinding；PC 登录只作为中控入口。' },
]

const createUserExample = `POST /api/users/
Authorization: Bearer <admin_or_agent_token>

{
  "username": "user_001",
  "password": "User@2026!"
}`

const grantAuthExample = `POST /api/users/1/authorizations
Authorization: Bearer <admin_or_agent_token>

{
  "game_project_id": 1,
  "user_level": "normal",
  "authorized_devices": 20,
  "valid_until": "2026-12-31T23:59:59+08:00"
}`

const apiList = [
  { method: 'POST', path: '/admin/api/auth/login', desc: '管理员登录', auth: ['Public'] },
  { method: 'POST', path: '/api/agents/auth/login', desc: '代理登录', auth: ['Public'] },
  { method: 'POST', path: '/api/auth/login', desc: '终端用户登录，校验项目授权并按设备规则绑定', auth: ['Public'] },
  { method: 'POST', path: '/api/auth/refresh', desc: '使用 Refresh Token 换取新的 Access Token', auth: ['Public'] },
  { method: 'POST', path: '/api/auth/logout', desc: '注销当前 Access Token 并删除对应 Refresh Token', auth: ['User'] },
  { method: 'GET', path: '/api/auth/me', desc: '读取当前项目上下文下的授权摘要', auth: ['User'] },
  { method: 'GET', path: '/api/agents/me', desc: '代理个人主页与余额摘要', auth: ['Agent'] },
  { method: 'GET', path: '/api/agents/my-projects', desc: '代理可销售项目列表', auth: ['Agent'] },
  { method: 'POST', path: '/api/users/', desc: '创建用户主体', auth: ['Admin', 'Agent'] },
  { method: 'GET', path: '/api/users/', desc: '用户列表，支持状态、等级、项目、创建代理过滤', auth: ['Admin', 'Agent'] },
  { method: 'POST', path: '/api/users/{id}/authorizations', desc: '给用户授予项目授权', auth: ['Admin', 'Agent'] },
  { method: 'PATCH', path: '/api/users/{id}/authorizations/{auth_id}', desc: '修改项目授权，当前仅管理员可改', auth: ['Admin'] },
  { method: 'GET', path: '/api/device/list', desc: '当前用户当前项目下设备列表', auth: ['User'] },
  { method: 'POST', path: '/api/device/heartbeat', desc: 'Android 心跳上报，写入 Redis 并更新绑定时间', auth: ['User'] },
  { method: 'POST', path: '/api/device/imsi', desc: '可选 IMSI 上报，设备必须已绑定', auth: ['User'] },
  { method: 'GET', path: '/api/update/check', desc: '检查当前项目当前客户端是否需要热更新', auth: ['User'] },
  { method: 'GET', path: '/api/update/download', desc: '获取当前项目当前客户端最新包下载地址', auth: ['User'] },
  { method: 'POST', path: '/admin/api/updates/{project_id}/{client_type}', desc: '管理员上传热更新包', auth: ['Admin'] },
  { method: 'GET', path: '/admin/api/devices/', desc: '后台设备监控总览', auth: ['Admin', 'Agent'] },
  { method: 'GET', path: '/health', desc: '服务健康检查', auth: ['Public'] },
]

const loginRequest = `{
  "username": "user_001",
  "password": "User@2026!",
  "project_uuid": "00000000-0000-0000-0000-000000000001",
  "device_fingerprint": "android_device_hash_001",
  "client_type": "android"
}`

const loginResponse = `{
  "access_token": "eyJ...",
  "refresh_token": "rt_...",
  "token_type": "bearer",
  "expires_in": 900,
  "user_id": 1,
  "username": "user_001",
  "authorization_level": "normal",
  "game_project_code": "game_001"
}`

const pcPythonCode = `import requests

BASE_URL = "http://127.0.0.1:8000"
PROJECT_UUID = "00000000-0000-0000-0000-000000000001"

class VerifyClient:
    def __init__(self):
        self.access_token = None
        self.refresh_token = None

    def login(self, username, password, device_fingerprint):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": username,
            "password": password,
            "project_uuid": PROJECT_UUID,
            "device_fingerprint": device_fingerprint,
            "client_type": "pc",
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        return data

    def headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_devices(self):
        resp = requests.get(f"{BASE_URL}/api/device/list", headers=self.headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()["devices"]

    def check_update(self, current_version):
        resp = requests.get(
            f"{BASE_URL}/api/update/check",
            params={"client_type": "pc", "current_version": current_version},
            headers=self.headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

client = VerifyClient()
login_info = client.login("user_001", "User@2026!", "pc_controller_hash")
print(login_info["authorization_level"])
print(client.get_devices())`

const androidCode = `const BASE_URL = "http://127.0.0.1:8000";
const PROJECT_UUID = "00000000-0000-0000-0000-000000000001";
let accessToken = null;
let refreshToken = null;

function login(username, password, deviceId) {
  const resp = httpRequest(BASE_URL + "/api/auth/login", "POST", JSON.stringify({
    username: username,
    password: password,
    project_uuid: PROJECT_UUID,
    device_fingerprint: deviceId,
    client_type: "android"
  }), { "Content-Type": "application/json" });

  if (resp.statusCode !== 200) {
    const err = JSON.parse(resp.body || "{}");
    throw new Error(err.detail || "登录失败");
  }

  const data = JSON.parse(resp.body);
  accessToken = data.access_token;
  refreshToken = data.refresh_token;
  return data;
}

function heartbeat(deviceId, gameData) {
  httpRequest(BASE_URL + "/api/device/heartbeat", "POST", JSON.stringify({
    device_fingerprint: deviceId,
    status: "running",
    game_data: gameData || {}
  }), {
    "Content-Type": "application/json",
    "Authorization": "Bearer " + accessToken
  });
}

function main() {
  const deviceId = getDeviceId();
  login("user_001", "User@2026!", deviceId);
  setInterval(function () {
    heartbeat(deviceId, { current_task: "idle", progress: 0 });
  }, 30000);
}`

const bindingLogic = [
  { condition: 'client_type=pc', result: '通过', action: '不创建 DeviceBinding，不占用 Android 授权设备数。' },
  { condition: 'Android 设备已在当前用户 + 当前项目下 active 绑定', result: '通过', action: '更新 last_seen_at，签发 Access Token 和 Refresh Token。' },
  { condition: 'Android 新设备，当前绑定数小于 authorized_devices', result: '通过', action: '创建 DeviceBinding 后签发 Token。' },
  { condition: 'authorized_devices=0', result: '通过', action: '表示该授权设备数无限制。' },
  { condition: 'Android 新设备，绑定数已达上限', result: '拒绝', action: '返回 403，提示设备绑定数量已达上限。' },
]

const heartbeatRequest = `POST /api/device/heartbeat
Authorization: Bearer <user_access_token>

{
  "device_fingerprint": "android_device_hash_001",
  "status": "running",
  "game_data": {
    "current_task": "daily",
    "progress": 75,
    "error_msg": null
  }
}`

const gameDataExample = `{
  "current_task": "当前任务名",
  "progress": 75,
  "error_msg": null,
  "extra": {
    "gold": 9999,
    "stamina": 100
  }
}`

const updateCheckReq = `GET /api/update/check?client_type=android&current_version=1.0.0
Authorization: Bearer <user_access_token>`

const updateDownloadReq = `GET /api/update/download?client_type=android
Authorization: Bearer <user_access_token>`

const updateClientCode = `def update_flow(client_type, current_version):
    check = GET("/api/update/check", {
        "client_type": client_type,
        "current_version": current_version,
    })

    if not check["need_update"]:
        return "continue"

    if check["force_update"]:
        block_old_version_runtime()

    download = GET("/api/update/download", {"client_type": client_type})
    file_bytes = download_file(download["download_url"])
    assert sha256(file_bytes) == download["checksum_sha256"]
    install_package(file_bytes)
    restart_client()`

const failReasons = [
  { http: '401', reason: '用户名或密码错误', check: '检查账号是否存在、密码是否正确、用户是否被软删除。' },
  { http: '401', reason: 'Access Token 无效或过期', check: '调用 /api/auth/refresh 刷新；刷新失败则重新登录。' },
  { http: '403', reason: '用户状态不是 active', check: '后台用户详情查看账号状态。' },
  { http: '403', reason: '用户没有该项目授权', check: '检查 Authorization 是否存在且 status=active。' },
  { http: '403', reason: '项目授权已过期', check: '检查 Authorization.valid_until。' },
  { http: '403', reason: '设备数量达到上限', check: '检查 Authorization.authorized_devices 与 DeviceBinding active 数量。' },
  { http: '404', reason: 'project_uuid 不存在或项目停用', check: '后台项目详情核对 UUID、is_active、终端配置。' },
  { http: '422', reason: '请求字段不符合契约', check: '检查字段名，例如登录必须使用 device_fingerprint，不是 hardware_serial。' },
  { http: '429', reason: '登录或心跳过于频繁', check: '心跳建议 30 秒一次；登录失败不要高频重试。' },
]

const releaseChecklist = [
  { item: '数据库迁移', check: '确认主库迁移到最新 head，User 旧授权字段已清理。', command: 'alembic current && alembic upgrade head' },
  { item: '后端测试', check: '认证、用户授权、设备、热更新测试通过。', command: 'pytest tests/test_auth.py tests/test_update.py -q' },
  { item: '前端构建', check: '管理后台能成功生产构建。', command: 'cd frontend && npm run build' },
  { item: '热更新包', check: 'VersionRecord 有 active 记录，包路径可被 Storage 读取。', command: '后台热更新页面' },
  { item: '项目 UUID', check: 'PCControl 与 AndroidScript 的 project_uuid 和后台项目一致。', command: '后台项目详情' },
  { item: 'Redis', check: 'Token、心跳、热更新缓存可读写。', command: 'redis-cli ping' },
  { item: 'Celery', check: 'Worker 与 Beat 正常运行，心跳落库任务无堆积。', command: 'celery -A app.core.celery_app worker --loglevel=info' },
]

const methodType = (method) => ({
  GET: 'success',
  POST: 'primary',
  PATCH: 'warning',
  DELETE: 'danger',
}[method] || 'info')

const authType = (auth) => ({
  Admin: 'danger',
  Agent: 'warning',
  User: 'success',
  Public: 'info',
}[auth] || 'info')

const apiRowClass = ({ row }) => (row.auth.includes('Public') ? 'row-public' : '')
</script>

<style scoped>
.guide-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.guide-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 0 0 16px;
}

.guide-header h2 {
  margin: 0;
  font-size: 22px;
  color: #1f2937;
}

.guide-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.version-badge {
  flex: 0 0 auto;
  background: #e0f2fe;
  color: #0369a1;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.guide-tabs {
  border-radius: 8px;
}

.section {
  margin-bottom: 28px;
}

.section h3 {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 12px;
}

.sub-label {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 6px;
  font-weight: 600;
}

.notice {
  margin-bottom: 16px;
}

.info-table,
.api-table {
  width: 100%;
}

.auth-tag {
  margin-right: 4px;
}

code {
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  color: #be123c;
}

.path-code {
  color: #2563eb;
  background: #eff6ff;
  padding: 2px 6px;
  border-radius: 4px;
}

.code-block {
  position: relative;
  background: #111827;
  border-radius: 8px;
  overflow: hidden;
}

.code-block pre {
  margin: 0;
  padding: 16px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.6;
  color: #e5e7eb;
  font-family: "Cascadia Code", Consolas, monospace;
  white-space: pre;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 10px;
  background: #374151;
  color: #d1d5db;
  border: none;
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
}

.copy-btn:hover {
  background: #4b5563;
  color: #fff;
}

.deploy-steps {
  padding: 8px 0;
}

.step-desc {
  padding: 4px 0 12px;
}

.step-desc p {
  margin: 0 0 8px;
  font-size: 13px;
  color: #475569;
}

.flow-line {
  display: grid;
  grid-template-columns: repeat(7, minmax(110px, 1fr));
  gap: 8px;
}

.flow-line span {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  padding: 8px;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  background: #eff6ff;
  color: #1e3a8a;
  font-size: 12px;
  text-align: center;
}

:deep(.row-public td) {
  background: #f8fafc !important;
}

@media (max-width: 960px) {
  .guide-header {
    flex-direction: column;
  }

  .flow-line {
    grid-template-columns: 1fr;
  }
}
</style>
