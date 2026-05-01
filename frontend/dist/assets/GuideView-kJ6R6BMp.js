import{_ as G,b as u,c as f,l as e,d as s,e as a,r as B,j as l,F as g,k as b,t as c,g as y,h as q,p as n,q as z,T as h,E as L}from"./index-Dryp5BTV.js";const N={class:"guide-page"},D={class:"section"},J={class:"section"},V={class:"step-desc"},M={class:"section"},H={class:"section"},F={class:"section"},W={class:"path-code"},Z={class:"section"},Y={class:"section"},K={class:"section"},Q={class:"section"},X={class:"section"},$={class:"section"},ee={class:"section"},te={class:"section"},se={class:"section"},ae={class:"logic-table"},oe=`# 必填
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
SENTRY_DSN=https://xxx@sentry.io/xxx`,ne=`# 后端（开发）
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Celery Worker（心跳落库）
celery -A app.core.celery_app worker --loglevel=info

# 前端开发服务
cd frontend && npm run dev
# 访问 http://localhost:5173`,ie=`import requests

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
    print("在线设备数：", sum(1 for d in devices if d["is_online"]))`,re=`// 懒人精灵脚本接入示例（JavaScript）
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
}`,le=`import requests
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
# start_heartbeat(token, device_fp, BASE_URL, lambda: {"gold": 999})`,de=`import requests
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
    return True`,ce=`{
  "username": "user001",
  "password": "UserPass123",
  "project_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "hardware_serial": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "client_type": "pc"
}`,pe=`{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
  "token_type": "bearer",
  "expires_in": 900,
  "user_id": 42,
  "username": "user001",
  "level": "vip",
  "project_code": "game_001"
}`,ue=`{
  "device_fingerprint": "a1b2c3d4e5f6...",
  "status": "running",
  "game_data": {
    "current_task": "副本挂机",
    "gold": 12345,
    "level": 88
  }
}`,_e=`// game_data 完全自定义，建议字段：
{
  "current_task": "当前任务名",
  "progress": 75,          // 进度百分比
  "error_msg": null,        // 有错误时填写
  "extra": {               // 扩展字段
    "gold": 9999,
    "stamina": 100
  }
}`,me=`GET /api/update/check
  ?project_uuid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  &current_version=1.0.0
  &client_type=android
Authorization: Bearer <access_token>`,fe=`{
  "need_update": true,
  "version": "1.0.3",
  "force_update": false,
  "checksum_sha256": "abc123...",
  "release_notes": "修复找图精度问题",
  "package_size_bytes": 2048000
}`,he={__name:"GuideView",setup(xe){const w=B("deploy"),i=d=>h("div",{class:"code-block"},[h("button",{class:"copy-btn",onClick:()=>{navigator.clipboard.writeText(d.code),L.success("已复制")}},"复制"),h("pre",h("code",{class:`lang-${d.lang}`},d.code))]),k=[{item:"Python",requirement:"3.11+",note:"使用 zoneinfo 标准库"},{item:"PostgreSQL",requirement:"14+",note:"支持 INET 类型 + gen_random_uuid()"},{item:"Redis",requirement:"7.0+",note:"心跳缓冲 + Token 黑名单"},{item:"Node.js",requirement:"18+",note:"前端构建用，生产可不安装"},{item:"操作系统",requirement:"Linux / Windows",note:"推荐 Ubuntu 22.04 LTS"},{item:"内存",requirement:"≥ 2GB",note:"小规模部署（< 1000 设备）"}],E=[{title:"1. 克隆仓库 & 创建虚拟环境",desc:"从 Git 仓库拉取代码，建立 Python 虚拟环境。",code:`git clone <仓库地址> HiveGreatSage-Verify
cd HiveGreatSage-Verify
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt`},{title:"2. 配置环境变量",desc:"复制模板并填写实际配置。",code:`cp .env.example .env
# 用文本编辑器修改 .env，至少填写：
# SECRET_KEY / DATABASE_MAIN_URL / REDIS_URL`},{title:"3. 初始化数据库",desc:"运行 Alembic 迁移，创建所有表结构。",code:`alembic upgrade head
# 然后初始化默认数据（管理员账号）
python scripts/init_data.py`},{title:"4. 启动后端服务",desc:"开发环境使用 --reload，生产环境去掉。",code:`# 开发
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 生产（多 worker）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`},{title:"5. 构建前端（可选）",desc:"生产部署时构建前端静态资源，交给 nginx 托管。",code:`cd frontend
npm install
npm run build
# 产物在 frontend/dist/`}],S=[{method:"POST",path:"/api/auth/login",desc:"用户登录验证",auth:["User"]},{method:"POST",path:"/api/auth/refresh",desc:"刷新 Access Token",auth:["User"]},{method:"POST",path:"/api/auth/logout",desc:"登出（吊销 Token）",auth:["User"]},{method:"POST",path:"/api/device/heartbeat",desc:"安卓设备心跳上报",auth:["User"]},{method:"GET",path:"/api/device/list",desc:"拉取用户名下设备列表",auth:["User"]},{method:"GET",path:"/api/device/data",desc:"拉取指定设备实时数据",auth:["User"]},{method:"POST",path:"/api/device/imsi",desc:"上报设备 IMSI",auth:["User"]},{method:"GET",path:"/api/params/get",desc:"拉取脚本参数",auth:["User"]},{method:"POST",path:"/api/params/set",desc:"保存脚本参数",auth:["User"]},{method:"GET",path:"/api/update/check",desc:"检查热更新版本",auth:["User"]},{method:"GET",path:"/api/update/download",desc:"获取带签名下载链接",auth:["User"]},{method:"POST",path:"/admin/api/auth/login",desc:"管理员登录",auth:["公开"]},{method:"POST",path:"/api/agents/auth/login",desc:"代理登录",auth:["公开"]},{method:"GET",path:"/api/agents/me",desc:"代理个人主页信息",auth:["Agent"]},{method:"GET",path:"/api/agents/my-projects",desc:"代理已授权项目列表",auth:["Agent"]},{method:"GET",path:"/admin/api/users/",desc:"用户列表（含项目过滤）",auth:["Admin","Agent"]},{method:"POST",path:"/admin/api/users/",desc:"创建用户",auth:["Admin","Agent"]},{method:"GET",path:"/admin/api/devices/",desc:"全平台设备总览",auth:["Admin","Agent"]},{method:"GET",path:"/admin/api/login-logs/",desc:"登录日志",auth:["Admin"]},{method:"GET",path:"/admin/api/projects/",desc:"项目列表",auth:["Admin"]},{method:"POST",path:"/admin/api/updates/{id}/{type}",desc:"发布热更新包",auth:["Admin"]},{method:"GET",path:"/health",desc:"健康检查",auth:["公开"]}],A=d=>({GET:"success",POST:"primary",PATCH:"warning",DELETE:"danger"})[d]||"info",j=({row:d})=>d.auth.includes("公开")?"row-public":"",P=[{code:"wrong_password",desc:"密码错误",action:"提示用户重新输入"},{code:"user_not_found",desc:"用户名不存在",action:"提示账号不存在"},{code:"user_suspended",desc:"账号已被停用",action:"提示联系代理"},{code:"user_expired",desc:"账号已过期",action:"提示续费"},{code:"auth_not_found",desc:"未授权该项目",action:"提示联系代理授权"},{code:"auth_expired",desc:"项目授权已过期",action:"提示授权过期"},{code:"device_limit",desc:"已达设备绑定上限",action:"提示设备数量上限"},{code:"project_not_found",desc:"项目 UUID 不存在",action:"检查 project_uuid 配置"}],I=[{cond:"设备指纹在 device_binding 中存在且 active",result:"✅ 通过",action:"更新 last_seen_at，直接签发 Token"},{cond:"设备指纹不存在 + 已绑数量 < max_devices",result:"✅ 通过",action:"插入新绑定记录，签发 Token"},{cond:"设备指纹不存在 + 已绑数量 ≥ max_devices",result:"❌ 拒绝",action:"fail_reason = device_limit"},{cond:"SVIP / tester 级别用户",result:"✅ 通过",action:"跳过设备数量检查，直接绑定"}];return(d,t)=>{const r=l("el-table-column"),x=l("el-table"),C=l("el-step"),U=l("el-steps"),_=l("el-tab-pane"),O=l("el-alert"),T=l("el-tag"),p=l("el-col"),v=l("el-row"),R=l("el-tabs");return u(),f("div",N,[t[24]||(t[24]=e("div",{class:"guide-header"},[e("h2",null,"🐝 蜂巢·大圣接入使用指南"),e("span",{class:"version-badge"},"v0.1.0")],-1)),s(R,{modelValue:w.value,"onUpdate:modelValue":t[0]||(t[0]=o=>w.value=o),class:"guide-tabs",type:"border-card"},{default:a(()=>[s(_,{label:"🚀 快速部署",name:"deploy"},{default:a(()=>[e("div",D,[t[1]||(t[1]=e("h3",null,"系统要求",-1)),s(x,{data:k,size:"small",class:"info-table"},{default:a(()=>[s(r,{prop:"item",label:"组件",width:"160"}),s(r,{prop:"requirement",label:"要求"}),s(r,{prop:"note",label:"备注"})]),_:1})]),e("div",J,[t[2]||(t[2]=e("h3",null,"部署步骤",-1)),s(U,{direction:"vertical",active:99,class:"deploy-steps"},{default:a(()=>[(u(),f(g,null,b(E,o=>s(C,{key:o.title,title:o.title},{description:a(()=>[e("div",V,[e("p",null,c(o.desc),1),o.code?(u(),y(i,{key:0,code:o.code,lang:o.lang||"bash"},null,8,["code","lang"])):q("",!0)])]),_:2},1032,["title"])),64))]),_:1})]),e("div",M,[t[3]||(t[3]=e("h3",null,".env 关键配置项",-1)),s(i,{code:oe,lang:"bash"})]),e("div",H,[t[4]||(t[4]=e("h3",null,"启动命令",-1)),s(i,{code:ne,lang:"bash"})])]),_:1}),s(_,{label:"📋 基础 API",name:"apis"},{default:a(()=>[e("div",F,[s(O,{type:"info","show-icon":"",closable:!1,style:{"margin-bottom":"16px"}},{default:a(()=>[...t[5]||(t[5]=[n(" 所有 API 使用 ",-1),e("code",null,"Authorization: Bearer <access_token>",-1),n(" 鉴权。",-1),e("br",null,null,-1),n(" 基础地址：",-1),e("code",null,"https://your-domain.com",-1),n("（或开发时 ",-1),e("code",null,"http://127.0.0.1:8000",-1),n("） ",-1)])]),_:1}),s(x,{data:S,size:"small",class:"api-table","row-class-name":j},{default:a(()=>[s(r,{label:"方法",width:"80"},{default:a(({row:o})=>[s(T,{type:A(o.method),size:"small",effect:"dark"},{default:a(()=>[n(c(o.method),1)]),_:2},1032,["type"])]),_:1}),s(r,{label:"路径","min-width":"240"},{default:a(({row:o})=>[e("code",W,c(o.path),1)]),_:1}),s(r,{prop:"desc",label:"说明","min-width":"160"}),s(r,{label:"鉴权",width:"120"},{default:a(({row:o})=>[(u(!0),f(g,null,b(o.auth,m=>(u(),y(T,{key:m,size:"small",effect:"plain",type:m==="Admin"?"danger":m==="Agent"?"warning":m==="User"?"success":"info",style:{"margin-right":"3px"}},{default:a(()=>[n(c(m),1)]),_:2},1032,["type"]))),128))]),_:1})]),_:1})])]),_:1}),s(_,{label:"⚙️ 相关函数 API",name:"funcs"},{default:a(()=>[e("div",Z,[t[6]||(t[6]=e("h3",null,"PC 中控 — Python 接入示例",-1)),s(i,{code:ie,lang:"python"})]),e("div",Y,[t[7]||(t[7]=e("h3",null,"安卓脚本 — 懒人精灵接入示例",-1)),s(i,{code:re,lang:"javascript"})]),e("div",K,[t[8]||(t[8]=e("h3",null,"心跳上报函数",-1)),s(i,{code:le,lang:"python"})]),e("div",Q,[t[9]||(t[9]=e("h3",null,"热更新检查函数",-1)),s(i,{code:de,lang:"python"})])]),_:1}),s(_,{label:"👤 用户 API 对接",name:"user-api"},{default:a(()=>[e("div",X,[t[12]||(t[12]=e("h3",null,"登录验证（完整请求/响应）",-1)),s(v,{gutter:16},{default:a(()=>[s(p,{span:12},{default:a(()=>[t[10]||(t[10]=e("p",{class:"sub-label"},"请求体",-1)),s(i,{code:ce,lang:"json"})]),_:1}),s(p,{span:12},{default:a(()=>[t[11]||(t[11]=e("p",{class:"sub-label"},"成功响应",-1)),s(i,{code:pe,lang:"json"})]),_:1})]),_:1})]),e("div",$,[t[13]||(t[13]=e("h3",null,"常见失败原因",-1)),s(x,{data:P,size:"small",class:"info-table"},{default:a(()=>[s(r,{prop:"code",label:"fail_reason",width:"180"},{default:a(({row:o})=>[e("code",null,c(o.code),1)]),_:1}),s(r,{prop:"desc",label:"说明"}),s(r,{prop:"action",label:"客户端处理建议","min-width":"200"})]),_:1})]),e("div",ee,[t[16]||(t[16]=e("h3",null,"心跳上报（安卓脚本，每 30 秒）",-1)),s(v,{gutter:16},{default:a(()=>[s(p,{span:12},{default:a(()=>[t[14]||(t[14]=e("p",{class:"sub-label"},"请求体",-1)),s(i,{code:ue,lang:"json"})]),_:1}),s(p,{span:12},{default:a(()=>[t[15]||(t[15]=e("p",{class:"sub-label"},"game_data 字段结构（游戏自定义）",-1)),s(i,{code:_e,lang:"json"})]),_:1})]),_:1})]),e("div",te,[t[19]||(t[19]=e("h3",null,"热更新检查",-1)),s(v,{gutter:16},{default:a(()=>[s(p,{span:12},{default:a(()=>[t[17]||(t[17]=e("p",{class:"sub-label"},"请求",-1)),s(i,{code:me,lang:"bash"})]),_:1}),s(p,{span:12},{default:a(()=>[t[18]||(t[18]=e("p",{class:"sub-label"},"响应",-1)),s(i,{code:fe,lang:"json"})]),_:1})]),_:1})])]),_:1}),s(_,{label:"🔄 对接流程图",name:"flow"},{default:a(()=>[t[22]||(t[22]=e("div",{class:"section"},[e("h3",null,"PC 中控完整对接流程"),e("div",{class:"flow-container"},[e("div",{class:"flow-box flow-start"},"启动 PC 中控"),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("检查本地版本"),e("br"),e("code",null,"GET /api/update/check")]),e("div",{class:"flow-branch"},[e("div",{class:"branch-item"},[e("div",{class:"branch-label need-update"},"有新版本"),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box small"},[n("下载更新包"),e("br"),e("code",null,"GET /api/update/download")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box small"},"重启生效")]),e("div",{class:"branch-item"},[e("div",{class:"branch-label no-update"},"无更新"),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box small"},"继续")])]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("用户登录验证"),e("br"),e("code",null,"POST /api/auth/login")]),e("div",{class:"flow-branch"},[e("div",{class:"branch-item"},[e("div",{class:"branch-label fail"},"验证失败"),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box small error"},[n("展示错误"),e("br"),n("（账号/密码/过期/超设备）")])]),e("div",{class:"branch-item"},[e("div",{class:"branch-label success"},"验证成功"),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box small"},"保存 Access Token")])]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("拉取脚本参数"),e("br"),e("code",null,"GET /api/params/get")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("展示设备列表"),e("br"),e("code",null,"GET /api/device/list"),n("（每 10s）")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box flow-end"},[n("用户修改参数"),e("br"),e("code",null,"POST /api/params/set")])])],-1)),t[23]||(t[23]=e("div",{class:"section"},[e("h3",null,"安卓脚本完整对接流程"),e("div",{class:"flow-container"},[e("div",{class:"flow-box flow-start"},"脚本启动"),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("检查脚本更新"),e("br"),e("code",null,"GET /api/update/check?type=android")]),e("div",{class:"flow-arrow"},"↓ 版本一致则跳过"),e("div",{class:"flow-box"},[n("登录验证 + 设备绑定"),e("br"),e("code",null,"POST /api/auth/login")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("上报 IMSI（首次绑定后）"),e("br"),e("code",null,"POST /api/device/imsi")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box"},[n("拉取脚本参数"),e("br"),e("code",null,"GET /api/params/get")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box flow-loop"},[n("脚本运行循环"),e("br"),n("每 30s 上报心跳"),e("br"),e("code",null,"POST /api/device/heartbeat")]),e("div",{class:"flow-arrow"},"↓"),e("div",{class:"flow-box flow-end"},[n("Token 过期 → 自动刷新"),e("br"),e("code",null,"POST /api/auth/refresh")])])],-1)),e("div",se,[t[21]||(t[21]=e("h3",null,"设备绑定判断逻辑",-1)),e("div",ae,[t[20]||(t[20]=e("div",{class:"logic-row header"},[e("span",null,"条件"),e("span",null,"结果"),e("span",null,"后续操作")],-1)),(u(),f(g,null,b(I,o=>e("div",{class:"logic-row",key:o.cond},[e("span",null,c(o.cond),1),e("span",{class:z(o.result==="✅ 通过"?"ok":"fail")},c(o.result),3),e("span",null,c(o.action),1)])),64))])])]),_:1})]),_:1},8,["modelValue"])])}}},ge=G(he,[["__scopeId","data-v-2f43de58"]]);export{ge as default};
