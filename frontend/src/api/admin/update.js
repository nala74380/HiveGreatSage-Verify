/**
 * 文件位置: src/api/admin/update.js
 * 名称: 管理员热更新 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-05-17
 * 版本: V1.0.0
 * 功能及相关说明:
 *   管理端热更新 latest / history 统一 API。
 *   UploadVersionForm.vue 继续负责 upload；本文件负责读取当前版本与历史。
 */

import http from '../http'

const normalizeLatestVersion = (payload = null) => {
  if (!payload) return null

  return {
    version: payload.version || '',
    force_update: Boolean(payload.force_update),
    released_at: payload.released_at || null,
    checksum_sha256: payload.checksum_sha256 || '',
    release_notes: payload.release_notes || '',
    is_active: Boolean(payload.is_active),
    client_type: payload.client_type || '',
    game_project_code: payload.game_project_code || '',
  }
}

const normalizeVersionHistory = (items = []) =>
  (items || []).map((item) => ({
    version: item.version || '',
    force_update: Boolean(item.force_update),
    release_notes: item.release_notes || '',
    released_at: item.released_at || null,
    is_active: Boolean(item.is_active),
    client_type: item.client_type || '',
    game_project_code: item.game_project_code || '',
  }))

export const adminUpdateApi = {
  async latest(projectId, clientType) {
    const res = await http.get(`/admin/api/updates/${projectId}/${clientType}/latest`)
    return normalizeLatestVersion(res.data)
  },

  async latestPair(projectId) {
    const [pcRes, androidRes] = await Promise.allSettled([
      this.latest(projectId, 'pc'),
      this.latest(projectId, 'android'),
    ])

    return {
      pc: pcRes.status === 'fulfilled' ? pcRes.value : null,
      android: androidRes.status === 'fulfilled' ? androidRes.value : null,
    }
  },

  async history(projectId, clientType) {
    const res = await http.get(`/admin/api/updates/${projectId}/${clientType}/history`)
    return normalizeVersionHistory(res.data.versions)
  },
}
