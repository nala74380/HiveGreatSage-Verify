/**
 * 文件位置: src/api/http.js
 * 功能说明: axios 实例 + 请求/响应拦截器
 *
 * 鉴权说明：
 *   管理后台使用 Admin Token 或 Agent Token，均无 refresh_token。
 *   Token 过期（401）时直接清除本地存储并跳转到登录页，不做静默刷新。
 *
 * _skipAuthRedirect 选项：
 *   请求配置中加入 { _skipAuthRedirect: true } 可跳过 401 自动跳登录逻辑。
 *   用于「有 Token 但无权限调用的端点」（如 Admin Token 调用 User 专属接口），
 *   此时 401 代表权限不足，不代表 Token 失效，不应强制登出。
 *
 * 错误处理：
 *   401（无 _skipAuthRedirect）→ 清除登录状态，跳转 /login
 *   401（有 _skipAuthRedirect）→ 静默，由调用方自行处理
 *   403 → ElMessage 提示无权限
 *   422 → ElMessage 提示参数错误（FastAPI Validation Error）
 *   429 → ElMessage 提示请求过于频繁
 *   5xx → ElMessage 提示服务器异常
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import { storage } from '@/utils/storage'

const instance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求拦截器：自动挂载 Token ─────────────────────────────────
instance.interceptors.request.use(
  (config) => {
    const token = storage.getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ── 响应拦截器：统一错误处理 ───────────────────────────────────
instance.interceptors.response.use(
  (res) => res,
  (error) => {
    const status  = error.response?.status
    const config  = error.config || {}
    const detail  = error.response?.data?.detail

    // 提取后端错误消息（FastAPI detail 可能是字符串或数组）
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((e) => e.msg).join('；')
        : '请求失败'

    if (status === 401) {
      if (config._skipAuthRedirect) {
        // 调用方主动声明跳过跳转（权限不足，而非 Token 失效）
        // 静默处理，由调用方的 catch 决定如何展示
      } else {
        // Token 真正失效 → 清除状态并跳登录页
        storage.clearAll()
        if (window.location.pathname !== '/login') {
          ElMessage.error('登录已过期，请重新登录')
          window.location.href = '/login'
        }
      }
    } else if (status === 403) {
      ElMessage.error(`无权限：${message}`)
    } else if (status === 422) {
      ElMessage.error(`参数错误：${message}`)
    } else if (status === 429) {
      ElMessage.warning('请求过于频繁，请稍后再试')
    } else if (status >= 500) {
      ElMessage.error(`服务器异常（${status}），请联系管理员`)
    } else if (status && !config._skipAuthRedirect) {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  },
)

export default instance
