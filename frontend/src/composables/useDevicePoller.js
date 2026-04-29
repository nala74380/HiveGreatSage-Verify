/**
 * 文件位置: src/composables/useDevicePoller.js
 * 功能说明: 设备列表 10 秒轮询封装
 */

import { ref, watch, onMounted, onUnmounted } from 'vue'
import { deviceApi } from '@/api/device'
import http from '@/api/http'

const POLL_INTERVAL = 10_000

export function useDevicePoller(userIdRef = null) {
  const devices      = ref([])
  const summary      = ref({ total: 0, online_count: 0 })
  const loading      = ref(false)
  const error        = ref(null)
  const notSupported = ref(false)
  let   timer        = null

  const fetchDevices = async () => {
    loading.value = true
    error.value   = null

    try {
      const uid = userIdRef?.value ?? null

      if (uid) {
        // ── 管理员查看指定用户的设备绑定列表 ───────────────────
        const res = await http.get(`/admin/api/users/${uid}/devices`, {
          _skipAuthRedirect: true,   // 防止 Token 过期时跳转登录页破坏轮询
        })
        const list = res.data.devices ?? []
        console.log(`[DevicePoller] uid=${uid} 设备数=${list.length}`, list)
        devices.value = list.map(d => ({
          device_id:  d.device_fingerprint,
          is_online:  d.is_online ?? false,
          status:     d.is_online ? (d.status === 'active' ? 'idle' : d.status) : 'offline',
          last_seen:  d.last_seen_at,
          game_data:  null,
        }))
        summary.value = {
          total:        list.length,
          online_count: list.filter(d => d.is_online).length,
        }

      } else {
        // ── 全局视角：Admin/Agent Token 调全局端点 ─────────────
        try {
          const res = await http.get('/admin/api/devices/', {
            params:            { page: 1, page_size: 200 },
            _skipAuthRedirect: true,
          })
          const list = res.data.devices ?? []
          console.log(`[DevicePoller] global 设备数=${list.length}`, res.data)
          devices.value = list
          summary.value = {
            total:        res.data.total        ?? list.length,
            online_count: res.data.online_count ?? 0,
          }
        } catch (innerErr) {
          const s = innerErr.response?.status
          console.warn(`[DevicePoller] global 端点失败 status=${s}`, innerErr.message)
          if (s === 401 || s === undefined) {
            // 终端用户 Token（PC 中控场景），回落到 User Token 端点
            const res2 = await deviceApi.list()
            const list2 = res2.data.devices ?? []
            console.log(`[DevicePoller] fallback 设备数=${list2.length}`)
            devices.value = list2
            summary.value = {
              total:        res2.data.total        ?? list2.length,
              online_count: res2.data.online_count ?? 0,
            }
          } else {
            // 记录错误但不 throw，保持之前的设备列表不变
            console.error(`[DevicePoller] global 端点非预期错误:`, innerErr)
            error.value = `设备数据加载失败 (${s ?? '网络错误'})`
          }
        }
      }
    } catch (err) {
      console.error('[DevicePoller] fetchDevices 异常:', err)
      error.value = err.message || '加载失败'
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    fetchDevices()
    timer = setInterval(fetchDevices, POLL_INTERVAL)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  if (userIdRef) {
    watch(userIdRef, () => {
      fetchDevices()
    })
  }

  return { devices, summary, loading, error, notSupported, refresh: fetchDevices }
}
