/**
 * 文件位置: src/api/agent/projectAccess.js
 * 名称: 代理端项目准入 API
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.0.0
 * 功能说明:
 *   代理端项目目录、项目开通申请、自动开通、取消申请接口。
 *
 * 后端接口:
 *   GET  /api/agents/my/project-access/catalog
 *   POST /api/agents/my/project-access/requests
 *   GET  /api/agents/my/project-access/requests
 *   POST /api/agents/my/project-access/requests/{request_id}/cancel
 */

import http from '../http'

export const agentProjectAccessApi = {
  catalog() {
    return http.get('/api/agents/my/project-access/catalog', {
      _skipAuthRedirect: true,
    })
  },

  createRequest(data) {
    return http.post('/api/agents/my/project-access/requests', data, {
      _skipAuthRedirect: true,
    })
  },

  myRequests(params = {}) {
    return http.get('/api/agents/my/project-access/requests', {
      params,
      _skipAuthRedirect: true,
    })
  },

  cancelRequest(requestId) {
    return http.post(`/api/agents/my/project-access/requests/${requestId}/cancel`, {}, {
      _skipAuthRedirect: true,
    })
  },
}