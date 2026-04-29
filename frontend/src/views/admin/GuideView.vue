<template>
  <div class="guide-page">
    <!-- 顶部标题 -->
    <div class="guide-header">
      <h2>🐝 蜂巢·大圣接入使用指南</h2>
      <span class="version-badge">v0.1.0</span>
    </div>

    <!-- 导航标签 -->
    <el-tabs v-model="activeTab" class="guide-tabs" type="border-card">

      <!-- ─────────────── 1. 快速部署 ─────────────── -->
      <el-tab-pane label="🚀 快速部署" name="deploy">
        <div class="section">
          <h3>系统要求</h3>
          <el-table :data="requirementsData" size="small" class="info-table">
            <el-table-column prop="item" label="组件" width="160" />
            <el-table-column prop="requirement" label="要求" />
            <el-table-column prop="note" label="备注" />
          </el-table>
        </div>

        <div class="section">
          <h3>部署步骤</h3>
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
        </div>

        <div class="section">
          <h3>.env 关键配置项</h3>
          <CodeBlock :code="envConfig" lang="bash" />
        </div>

        <div class="section">
          <h3>启动命令</h3>
          <CodeBlock :code="startCmds" lang="bash" />
        </div>
      </el-tab-pane>

      <!-- ─────────────── 2. API 接口列表 ─────────────── -->
      <el-tab-pane label="📋 基础 API" name="apis">
        <div class="section">
          <el-alert type="info" show-icon :closable="false" style="margin-bottom:16px">
            <template #default>
              所有 API 使用 <code>Authorization: Bearer &lt;access_token&gt;</code> 鉴权。<br/>
              基础地址：<code>https://your-domain.com</code>（或开发时 <code>http://127.0.0.1:8000</code>）
            </template>
          </el-alert>
          <el-table :data="apiList" size="small" class="api-table" :row-class-name="apiRowClass">
            <el-table-column label="方法" width="80">
              <template #default="{ row }">
                <el-tag :type="methodType(row.method)" size="small" effect="dark">{{ row.method }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="路径" min-width="240">
              <template #default="{ row }">
                <code class="path-code">{{ row.path }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="desc" label="说明" min-width="160" />
            <el-table-column label="鉴权" width="120">
              <template #default="{ row }">
                <el-tag v-for="t in row.auth" :key="t" size="small" effect="plain"
                  :type="t === 'Admin' ? 'danger' : t === 'Agent' ? 'warning' : t === 'User' ? 'success' : 'info'"
                  style="margin-right:3px">{{ t }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- ─────────────── 3. 相关函数 API ─────────────── -->
      <el-tab-pane label="⚙️ 相关函数 API" name="funcs">
        <div class="section">
          <h3>PC 中控 — Python 接入示例</h3>
          <CodeBlock :code="pcPythonCode" lang="python" />
        </div>
        <div class="section">
          <h3>安卓脚本 — 懒人精灵接入示例</h3>
          <CodeBlock :code="androidLrpCode" lang="javascript" />
        </div>
        <div class="section">
          <h3>心跳上报函数</h3>
          <CodeBlock :code="heartbeatCode" lang="python" />
        </div>
        <div class="section">
          <h3>热更新检查函数</h3>
          <CodeBlock :code="updateCheckCode" lang="python" />
        </div>
      </el-tab-pane>

      <!-- ─────────────── 4. 用户 API 对接例子 ─────────────── -->
      <el-tab-pane label="👤 用户 API 对接" name="user-api">
        <div class="section">
          <h3>登录验证（完整请求/响应）</h3>
          <el-row :gutter="16">
            <el-col :span="12">
              <p class="sub-label">请求体</p>
              <CodeBlock :code="loginRequest" lang="json" />
            </el-col>
            <el-col :span="12">
              <p class="sub-label">成功响应</p>
              <CodeBlock :code="loginResponse" lang="json" />
            </el-col>
          </el-row>
        </div>
        <div class="section">
          <h3>常见失败原因</h3>
          <el-table :data="failReasons" size="small" class="info-table">
            <el-table-column prop="code" label="fail_reason" width="180">
              <template #default="{ row }"><code>{{ row.code }}</code></template>
            </el-table-column>
            <el-table-column prop="desc" label="说明" />
            <el-table-column prop="action" label="客户端处理建议" min-width="200" />
          </el-table>
        </div>
        <div class="section">
          <h3>心跳上报（安卓脚本，每 30 秒）</h3>
          <el-row :gutter="16">
            <el-col :span="12">
              <p class="sub-label">请求体</p>
              <CodeBlock :code="heartbeatRequest" lang="json" />
            </el-col>
            <el-col :span="12">
              <p class="sub-label">game_data 字段结构（游戏自定义）</p>
              <CodeBlock :code="gameDataExample" lang="json" />
            </el-col>
          </el-row>
        </div>
        <div class="section">
          <h3>热更新检查</h3>
          <el-row :gutter="16">
            <el-col :span="12">
              <p class="sub-label">请求</p>
              <CodeBlock :code="updateCheckReq" lang="bash" />
            </el-col>
            <el-col :span="12">
              <p class="sub-label">响应</p>
              <CodeBlock :code="updateCheckResp" lang="json" />
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ─────────────── 5. 对接流程图 ─────────────── -->
      <el-tab-pane label="🔄 对接流程图" name="flow">
        <div class="section">
          <h3>PC 中控完整对接流程</h3>
          <div class="flow-container">
            <div class="flow-box flow-start">启动 PC 中控</div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">检查本地版本<br/><code>GET /api/update/check</code></div>
            <div class="flow-branch">
              <div class="branch-item">
                <div class="branch-label need-update">有新版本</div>
                <div class="flow-arrow">↓</div>
                <div class="flow-box small">下载更新包<br/><code>GET /api/update/download</code></div>
                <div class="flow-arrow">↓</div>
                <div class="flow-box small">重启生效</div>
              </div>
              <div class="branch-item">
                <div class="branch-label no-update">无更新</div>
                <div class="flow-arrow">↓</div>
                <div class="flow-box small">继续</div>
              </div>
            </div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">用户登录验证<br/><code>POST /api/auth/login</code></div>
            <div class="flow-branch">
              <div class="branch-item">
                <div class="branch-label fail">验证失败</div>
                <div class="flow-arrow">↓</div>
                <div class="flow-box small error">展示错误<br/>（账号/密码/过期/超设备）</div>
              </div>
              <div class="branch-item">
                <div class="branch-label success">验证成功</div>
                <div class="flow-arrow">↓</div>
                <div class="flow-box small">保存 Access Token</div>
              </div>
            </div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">拉取脚本参数<br/><code>GET /api/params/get</code></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">展示设备列表<br/><code>GET /api/device/list</code>（每 10s）</div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box flow-end">用户修改参数<br/><code>POST /api/params/set</code></div>
          </div>
        </div>

        <div class="section">
          <h3>安卓脚本完整对接流程</h3>
          <div class="flow-container">
            <div class="flow-box flow-start">脚本启动</div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">检查脚本更新<br/><code>GET /api/update/check?type=android</code></div>
            <div class="flow-arrow">↓ 版本一致则跳过</div>
            <div class="flow-box">登录验证 + 设备绑定<br/><code>POST /api/auth/login</code></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">上报 IMSI（首次绑定后）<br/><code>POST /api/device/imsi</code></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box">拉取脚本参数<br/><code>GET /api/params/get</code></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box flow-loop">脚本运行循环<br/>每 30s 上报心跳<br/><code>POST /api/device/heartbeat</code></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-box flow-end">Token 过期 → 自动刷新<br/><code>POST /api/auth/refresh</code></div>
          </div>
        </div>

        <div class="section">
          <h3>设备绑定判断逻辑</h3>
          <div class="logic-table">
            <div class="logic-row header">
              <span>条件</span><span>结果</span><span>后续操作</span>
            </div>
            <div class="logic-row" v-for="r in bindingLogic" :key="r.cond">
              <span>{{ r.cond }}</span>
              <span :class="r.result === '✅ 通过' ? 'ok' : 'fail'">{{ r.result }}</span>
              <span>{{ r.action }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>
  </div>
</template>

<script setup>
import { ref, h } from 'vue'
import { ElMessage } from 'element-plus'

const activeTab = ref('deploy')

// ── 代码高亮组件（基于 pre/code，无需额外库）───────────────
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

// ── 数据 ─────────────────────────────────────────────────────

const requirementsData = [
  { item: 'Python',      requirement: '3.11+',                note: '使用 zoneinfo 标准库' },
  { item: 'PostgreSQL',  requirement: '14+',                  note: '支持 INET 类型 + gen_random_uuid()' },
  { item: 'Redis',       requirement: '7.0+',                 note: '心跳缓冲 + Token 黑名单' },
  { item: 'Node.js',     requirement: '18+',                  note: '前端构建用，生产可不安装' },
  { item: '操作系统',    requirement: 'Linux / Windows',      note: '推荐 Ubuntu 22.04 LTS' },
  { item: '内存',        requirement: '≥ 2GB',                note: '小规模部署（< 1000 设备）' },
]

const deploySteps = [
  {
    title: '1. 克隆仓库 & 创建虚拟环境',
    desc: '从 Git 仓库拉取代码，建立 Python 虚拟环境。',
    code: `git clone <仓库地址> HiveGreatSage-Verify
cd HiveGreatSage-Verify
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt`,
  },
  {
    title: '2. 配置环境变量',
    desc: '复制模板并填写实际配置。',
    code: `cp .env.example .env
# 用文本编辑器修改 .env，至少填写：
# SECRET_KEY / DATABASE_MAIN_URL / REDIS_URL`,
  },
  {
    title: '3. 初始化数据库',
    desc: '运行 Alembic 迁移，创建所有表结构。',
    code: `alembic upgrade head
# 然后初始化默认数据（管理员账号）
python scripts/init_data.py`,
  },
  {
    title: '4. 启动后端服务',
    desc: '开发环境使用 --reload，生产环境去掉。',
    code: `# 开发
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 生产（多 worker）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`,
  },
  {
    title: '5. 构建前端（可选）',
    desc: '生产部署时构建前端静态资源，交给 nginx 托管。',
    code: `cd frontend
npm install
npm run build
# 产物在 frontend/dist/`,
  },
]

const envConfig = `# 必填
SECRET_KEY=<随机32字节密钥>
DATABASE_MAIN_URL=postgresql+asyncpg://user:pass@localhost:5432/hive_platform
REDIS_URL=redis://localhost:6379/0

# 时区（默认 UTC+8）
TIMEZONE=Asia/Shanghai

# 存储模式
STORAGE_MODE=local
STORAGE_LOCAL_ROOT=/var/www/hive-updates

# 可选（生产环境）
ENVIRONMENT=production
SENTRY_DSN=https://xxx@sentry.io/xxx`

const startCmds = `# 后端（开发）
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Celery Worker（心跳落库）
celery -A app.core.celery_app worker --loglevel=info

# 前端开发服务
cd frontend && npm run dev
# 访问 http://localhost:5173`

// ── API 列表 ──────────────────────────────────────────────
const apiList = [
  { method: 'POST',   path: '/api/auth/login',              desc: '用户登录验证',         auth: ['User'] },
  { method: 'POST',   path: '/api/auth/refresh',            desc: '刷新 Access Token',   auth: ['User'] },
  { method: 'POST',   path: '/api/auth/logout',             desc: '登出（吊销 Token）',   auth: ['User'] },
  { method: 'POST',   path: '/api/device/heartbeat',        desc: '安卓设备心跳上报',     auth: ['User'] },
  { method: 'GET',    path: '/api/device/list',             desc: '拉取用户名下设备列表', auth: ['User'] },
  { method: 'GET',    path: '/api/device/data',             desc: '拉取指定设备实时数据', auth: ['User'] },
  { method: 'POST',   path: '/api/device/imsi',             desc: '上报设备 IMSI',        auth: ['User'] },
  { method: 'GET',    path: '/api/params/get',              desc: '拉取脚本参数',         auth: ['User'] },
  { method: 'POST',   path: '/api/params/set',              desc: '保存脚本参数',         auth: ['User'] },
  { method: 'GET',    path: '/api/update/check',            desc: '检查热更新版本',       auth: ['User'] },
  { method: 'GET',    path: '/api/update/download',         desc: '获取带签名下载链接',   auth: ['User'] },
  { method: 'POST',   path: '/admin/api/auth/login',        desc: '管理员登录',           auth: ['公开'] },
  { method: 'POST',   path: '/api/agents/auth/login',       desc: '代理登录',             auth: ['公开'] },
  { method: 'GET',    path: '/api/agents/me',               desc: '代理个人主页信息',     auth: ['Agent'] },
  { method: 'GET',    path: '/api/agents/my-projects',      desc: '代理已授权项目列表',   auth: ['Agent'] },
  { method: 'GET',    path: '/admin/api/users/',            desc: '用户列表（含项目过滤）',auth: ['Admin', 'Agent'] },
  { method: 'POST',   path: '/admin/api/users/',            desc: '创建用户',             auth: ['Admin', 'Agent'] },
  { method: 'GET',    path: '/admin/api/devices/',          desc: '全平台设备总览',       auth: ['Admin', 'Agent'] },
  { method: 'GET',    path: '/admin/api/login-logs/',       desc: '登录日志',             auth: ['Admin'] },
  { method: 'GET',    path: '/admin/api/projects/',         desc: '项目列表',             auth: ['Admin'] },
  { method: 'POST',   path: '/admin/api/updates/{id}/{type}',desc:'发布热更新包',         auth: ['Admin'] },
  { method: 'GET',    path: '/health',                       desc: '健康检查',            auth: ['公开'] },
]

const methodType = (m) => ({ GET: 'success', POST: 'primary', PATCH: 'warning', DELETE: 'danger' }[m] || 'info')
const apiRowClass = ({ row }) => row.auth.includes('公开') ? 'row-public' : ''

// ── 函数 API ──────────────────────────────────────────────
const pcPythonCode = `import requests

BASE_URL = "https://your-domain.com"

class HiveVerifyClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.token = None

    def login(self, username: str, password: str,
              project_uuid: str, device_fingerprint: str) -> dict:
        """
        登录验证。
        device_fingerprint 建议使用 CPU ID + 主板序列号 的 MD5 哈希。
        """
        resp = requests.post(f"{self.base_url}/api/auth/login", json={
            "username": username,
            "password": password,
            "project_uuid": project_uuid,
            "hardware_serial": device_fingerprint,
            "client_type": "pc",
        })
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        return data

    def get_device_list(self) -> list:
        """拉取当前用户所有设备实时状态（PC 中控每 10 秒调用）。"""
        resp = requests.get(
            f"{self.base_url}/api/device/list",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        resp.raise_for_status()
        return resp.json()["devices"]

    def get_params(self, project_uuid: str) -> dict:
        """拉取脚本参数。"""
        resp = requests.get(
            f"{self.base_url}/api/params/get",
            params={"project_uuid": project_uuid},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        resp.raise_for_status()
        return resp.json()

    def set_params(self, project_uuid: str, params: dict) -> None:
        """保存脚本参数（PC 中控写入）。"""
        requests.post(
            f"{self.base_url}/api/params/set",
            json={"project_uuid": project_uuid, "params": params},
            headers={"Authorization": f"Bearer {self.token}"}
        ).raise_for_status()

    def check_update(self, project_uuid: str, current_version: str,
                     client_type: str = "pc") -> dict:
        """检查热更新。返回 {need_update, version, force_update, download_url}。"""
        resp = requests.get(
            f"{self.base_url}/api/update/check",
            params={"project_uuid": project_uuid,
                    "current_version": current_version,
                    "client_type": client_type},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        resp.raise_for_status()
        return resp.json()


# 使用示例
if __name__ == "__main__":
    client = HiveVerifyClient()
    result = client.login(
        username="user001",
        password="UserPass123",
        project_uuid="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        device_fingerprint="a1b2c3d4e5f6..."
    )
    print("登录成功，用户级别：", result["level"])
    devices = client.get_device_list()
    print("在线设备数：", sum(1 for d in devices if d["is_online"]))`

const androidLrpCode = `// 懒人精灵脚本接入示例（JavaScript）
// 请将 BASE_URL / PROJECT_UUID 替换为实际值

const BASE_URL = "https://your-domain.com";
const PROJECT_UUID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx";

// 全局 token
let g_token = null;

/**
 * 登录验证
 * deviceId: 设备唯一标识（建议使用 IMEI 或硬件 ID）
 */
function verifyLogin(username, password, deviceId) {
  const resp = httpRequest(BASE_URL + "/api/auth/login", "POST", JSON.stringify({
    username: username,
    password: password,
    project_uuid: PROJECT_UUID,
    hardware_serial: deviceId,
    client_type: "android"
  }), { "Content-Type": "application/json" });

  if (resp.statusCode !== 200) {
    const err = JSON.parse(resp.body);
    throw new Error("登录失败: " + (err.detail || resp.statusCode));
  }

  const data = JSON.parse(resp.body);
  g_token = data.access_token;
  log("登录成功，级别: " + data.level);
  return data;
}

/**
 * 心跳上报（每 30 秒调用一次）
 * gameData: 游戏自定义数据对象
 */
function sendHeartbeat(deviceId, status, gameData) {
  httpRequest(BASE_URL + "/api/device/heartbeat", "POST",
    JSON.stringify({
      device_fingerprint: deviceId,
      status: status,          // "running" | "idle" | "error"
      game_data: gameData || {}
    }),
    {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + g_token
    }
  );
}

/**
 * 拉取脚本参数
 */
function getParams() {
  const resp = httpRequest(
    BASE_URL + "/api/params/get?project_uuid=" + PROJECT_UUID,
    "GET", null,
    { "Authorization": "Bearer " + g_token }
  );
  return JSON.parse(resp.body);
}

// ─── 主流程 ───────────────────────────────────────────────
function main() {
  const deviceId = getDeviceId();  // 获取设备唯一标识

  // 1. 登录
  verifyLogin("user001", "密码", deviceId);

  // 2. 拉取参数
  const params = getParams();
  log("脚本参数: " + JSON.stringify(params));

  // 3. 定时心跳
  setInterval(function() {
    sendHeartbeat(deviceId, "running", {
      "current_task": "挂机中",
      "gold": 1234
    });
  }, 30000);
}`

const heartbeatCode = `import requests
import time
import threading

def start_heartbeat(token: str, device_fp: str, base_url: str,
                    get_game_data_fn=None, interval: int = 30):
    """
    启动后台心跳线程。
    get_game_data_fn: 可选，返回当前游戏状态的函数，每次心跳调用一次。
    """
    def _beat():
        while True:
            try:
                game_data = get_game_data_fn() if get_game_data_fn else {}
                requests.post(
                    f"{base_url}/api/device/heartbeat",
                    json={
                        "device_fingerprint": device_fp,
                        "status": "running",
                        "game_data": game_data,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
            except Exception as e:
                print(f"[heartbeat] 上报失败: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_beat, daemon=True)
    t.start()
    return t

# 使用
# start_heartbeat(token, device_fp, BASE_URL, lambda: {"gold": 999})`

const updateCheckCode = `import requests
import zipfile
import hashlib

def check_and_update(token: str, base_url: str,
                     project_uuid: str, current_version: str,
                     client_type: str = "pc",
                     install_dir: str = "./") -> bool:
    """
    检查并下载热更新包。返回 True 表示有更新并已安装。
    """
    # 1. 检查版本
    resp = requests.get(
        f"{base_url}/api/update/check",
        params={
            "project_uuid": project_uuid,
            "current_version": current_version,
            "client_type": client_type,
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    if not resp.get("need_update"):
        return False

    print(f"发现新版本 {resp['version']}，正在下载...")

    # 2. 获取签名下载链接
    dl_resp = requests.get(
        f"{base_url}/api/update/download",
        params={
            "project_uuid": project_uuid,
            "version": resp["version"],
            "client_type": client_type,
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # 3. 下载并校验
    data = requests.get(dl_resp["download_url"]).content
    sha256 = hashlib.sha256(data).hexdigest()
    assert sha256 == resp["checksum_sha256"], "校验失败！"

    # 4. 解压（PC 端 .zip）
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(install_dir)

    print(f"更新完成，请重启程序")
    return True`

// ── 请求/响应示例 ─────────────────────────────────────────
const loginRequest = `{
  "username": "user001",
  "password": "UserPass123",
  "project_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "hardware_serial": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "client_type": "pc"
}`

const loginResponse = `{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
  "token_type": "bearer",
  "expires_in": 900,
  "user_id": 42,
  "username": "user001",
  "level": "vip",
  "project_code": "game_001"
}`

const failReasons = [
  { code: 'wrong_password',    desc: '密码错误',               action: '提示用户重新输入' },
  { code: 'user_not_found',    desc: '用户名不存在',           action: '提示账号不存在' },
  { code: 'user_suspended',    desc: '账号已被停用',           action: '提示联系代理' },
  { code: 'user_expired',      desc: '账号已过期',             action: '提示续费' },
  { code: 'auth_not_found',    desc: '未授权该项目',           action: '提示联系代理授权' },
  { code: 'auth_expired',      desc: '项目授权已过期',         action: '提示授权过期' },
  { code: 'device_limit',      desc: '已达设备绑定上限',       action: '提示设备数量上限' },
  { code: 'project_not_found', desc: '项目 UUID 不存在',       action: '检查 project_uuid 配置' },
]

const heartbeatRequest = `{
  "device_fingerprint": "a1b2c3d4e5f6...",
  "status": "running",
  "game_data": {
    "current_task": "副本挂机",
    "gold": 12345,
    "level": 88
  }
}`

const gameDataExample = `// game_data 完全自定义，建议字段：
{
  "current_task": "当前任务名",
  "progress": 75,          // 进度百分比
  "error_msg": null,        // 有错误时填写
  "extra": {               // 扩展字段
    "gold": 9999,
    "stamina": 100
  }
}`

const updateCheckReq = `GET /api/update/check
  ?project_uuid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  &current_version=1.0.0
  &client_type=android
Authorization: Bearer <access_token>`

const updateCheckResp = `{
  "need_update": true,
  "version": "1.0.3",
  "force_update": false,
  "checksum_sha256": "abc123...",
  "release_notes": "修复找图精度问题",
  "package_size_bytes": 2048000
}`

const bindingLogic = [
  { cond: '设备指纹在 device_binding 中存在且 active', result: '✅ 通过', action: '更新 last_seen_at，直接签发 Token' },
  { cond: '设备指纹不存在 + 已绑数量 < max_devices',   result: '✅ 通过', action: '插入新绑定记录，签发 Token' },
  { cond: '设备指纹不存在 + 已绑数量 ≥ max_devices',   result: '❌ 拒绝', action: 'fail_reason = device_limit' },
  { cond: 'SVIP / tester 级别用户',                     result: '✅ 通过', action: '跳过设备数量检查，直接绑定' },
]
</script>

<style scoped>
.guide-page { display: flex; flex-direction: column; gap: 0; min-height: 100%; }

.guide-header {
  display: flex; align-items: center; gap: 12px;
  padding: 0 0 16px;
}
.guide-header h2 { margin: 0; font-size: 20px; color: #1e293b; }
.version-badge {
  background: #e0f2fe; color: #0369a1; padding: 2px 10px;
  border-radius: 20px; font-size: 12px; font-weight: 600;
}

.guide-tabs { border-radius: 10px; }
.section { margin-bottom: 32px; }
.section h3 { font-size: 15px; font-weight: 700; color: #1e293b; margin: 0 0 12px; }
.sub-label { font-size: 12px; color: #64748b; margin: 0 0 6px; font-weight: 600; }

/* 代码块 */
.code-block {
  position: relative;
  background: #0f172a; border-radius: 8px;
  overflow: hidden;
}
.code-block pre {
  margin: 0; padding: 16px;
  overflow-x: auto; font-size: 12.5px; line-height: 1.6;
  color: #e2e8f0; font-family: 'Cascadia Code', 'Consolas', monospace;
  white-space: pre;
}
.copy-btn {
  position: absolute; top: 8px; right: 10px;
  background: #334155; color: #94a3b8; border: none;
  border-radius: 4px; padding: 3px 10px; font-size: 11px;
  cursor: pointer; transition: all 0.2s;
}
.copy-btn:hover { background: #475569; color: #fff; }

/* 表格 */
.info-table, .api-table { width: 100%; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 12px; color: #e11d48; }
.path-code { color: #2563eb; font-size: 12px; background: #eff6ff; padding: 2px 6px; border-radius: 4px; }

:deep(.row-public td) { background: #f8fafc !important; color: #94a3b8 !important; }

/* 部署步骤 */
.deploy-steps { padding: 8px 0; }
.step-desc { padding: 4px 0 12px; }
.step-desc p { margin: 0 0 8px; font-size: 13px; color: #475569; }

/* 流程图 */
.flow-container {
  display: flex; flex-direction: column; align-items: center;
  gap: 0; padding: 16px;
  background: #f8fafc; border-radius: 10px;
}
.flow-box {
  background: #fff; border: 2px solid #bfdbfe;
  border-radius: 8px; padding: 10px 24px;
  text-align: center; font-size: 13px; color: #1e293b;
  min-width: 260px; line-height: 1.6;
}
.flow-box code { font-size: 11px; }
.flow-box.flow-start { background: #2563eb; border-color: #2563eb; color: #fff; font-weight: 600; }
.flow-box.flow-end   { background: #10b981; border-color: #10b981; color: #fff; font-weight: 600; }
.flow-box.flow-loop  { background: #7c3aed; border-color: #7c3aed; color: #fff; }
.flow-box.small      { min-width: 180px; padding: 7px 16px; font-size: 12px; }
.flow-box.error      { border-color: #ef4444; background: #fef2f2; color: #ef4444; }
.flow-arrow { font-size: 18px; color: #94a3b8; padding: 4px 0; line-height: 1; }

.flow-branch {
  display: flex; gap: 32px; align-items: flex-start;
}
.branch-item { display: flex; flex-direction: column; align-items: center; gap: 0; }
.branch-label {
  font-size: 11px; font-weight: 600; padding: 2px 10px;
  border-radius: 10px; margin-bottom: 4px;
}
.branch-label.success   { background: #d1fae5; color: #065f46; }
.branch-label.fail      { background: #fee2e2; color: #991b1b; }
.branch-label.need-update { background: #fef3c7; color: #92400e; }
.branch-label.no-update { background: #f0f9ff; color: #0369a1; }

/* 绑定逻辑表 */
.logic-table { border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; }
.logic-row {
  display: grid; grid-template-columns: 2fr 1fr 2fr;
  padding: 10px 16px; border-bottom: 1px solid #f1f5f9;
  font-size: 13px; gap: 12px; align-items: center;
}
.logic-row.header {
  background: #f8fafc; font-weight: 600; color: #64748b;
  font-size: 12px;
}
.logic-row .ok   { color: #10b981; font-weight: 600; }
.logic-row .fail { color: #ef4444; font-weight: 600; }
</style>
