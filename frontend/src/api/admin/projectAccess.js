/**
 * 文件位置: src/api/admin/projectAccess.js
 * 名称: 管理员项目准入 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能说明:
 *   管理员项目准入策略配置、代理项目申请审核接口。
 *
 * 后端接口:
 *   GET   /admin/api/project-access/policies
 *   PATCH /admin/api/project-access/policies/{project_id}
 *   GET   /admin/api/project-access/requests
 *   POST  /admin/api/project-access/requests/{request_id}/approve
 *   POST  /admin/api/project-access/requests/{request_id}/reject
 */

import http from '../http'

export const adminProjectAccessApi = {
  policies(params = {}) {
    return http.get('/admin/api/project-access/policies', { params })
  },

  updatePolicy(projectId, data) {
    return http.patch(`/admin/api/project-access/policies/${projectId}`, data)
  },

  requests(params = {}) {
    return http.get('/admin/api/project-access/requests', { params })
  },

  approveRequest(requestId, data) {
    return http.post(`/admin/api/project-access/requests/${requestId}/approve`, data)
  },

  rejectRequest(requestId, data) {
    return http.post(`/admin/api/project-access/requests/${requestId}/reject`, data)
  },
}