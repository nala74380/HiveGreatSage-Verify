import http from './http'

export const auditApi = {
  list(params = {}) {
    return http.get('/admin/api/audit-logs/', { params })
  },

  detail(auditLogId) {
    return http.get(`/admin/api/audit-logs/${auditLogId}`)
  },
}
