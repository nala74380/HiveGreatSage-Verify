/**
 * 文件位置: src/router/index.js
 * 名称: Vue Router 主入口
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-30
 * 版本: V1.8.0
 * 功能说明:
 *   Vue Router 实例 + 全局路由守卫。
 *
 * 当前业务口径:
 *   - 项目管理是项目相关能力统一入口。
 *   - 项目详情页承载定价、准入、授权申请、热更新等项目能力。
 *   - 账务中心是平台内部点数资产治理统一入口。
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import AuthLayout from '@/layouts/AuthLayout.vue'
import LoginView from '@/views/auth/LoginView.vue'
import NotFound from '@/views/error/NotFound.vue'
import Forbidden from '@/views/error/Forbidden.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: DashboardLayout,
      children: [
        { path: '', redirect: '/dashboard' },

        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/shared/DashboardView.vue'),
          meta: { requiresAuth: true, title: '总览' },
        },
        {
          path: 'profile',
          name: 'AgentProfile',
          component: () => import('@/views/shared/AgentProfile.vue'),
          meta: { requiresAgent: true, title: '个人主页' },
        },
        {
          path: 'users',
          name: 'UserList',
          component: () => import('@/views/shared/UserList.vue'),
          meta: { requiresAuth: true, title: '用户管理' },
        },
        {
          path: 'users/:id',
          name: 'UserDetail',
          component: () => import('@/views/shared/UserDetail.vue'),
          meta: { requiresAuth: true, title: '用户详情' },
        },
        {
          path: 'devices',
          name: 'DeviceList',
          component: () => import('@/views/shared/DeviceList.vue'),
          meta: { requiresAuth: true, title: '设备监控' },
        },

        // Agent
        {
          path: 'catalog',
          name: 'AgentCatalog',
          component: () => import('@/views/agent/AgentCatalog.vue'),
          meta: { requiresAgent: true, title: '项目目录' },
        },
        {
          path: 'balance',
          name: 'AgentBalance',
          component: () => import('@/views/agent/AgentBalance.vue'),
          meta: { requiresAgent: true, title: '我的余额' },
        },

        // Admin shared / Agent Lv.2+
        {
          path: 'agents',
          name: 'AgentList',
          component: () => import('@/views/shared/AgentList.vue'),
          meta: { requiresAuth: true, title: '代理管理' },
        },
        {
          path: 'agents/:id',
          name: 'AgentDetail',
          component: () => import('@/views/shared/AgentDetail.vue'),
          meta: { requiresAdmin: true, title: '代理详情' },
        },
        {
          path: 'login-logs',
          name: 'LoginLogs',
          component: () => import('@/views/shared/LoginLogView.vue'),
          meta: { requiresAdmin: true, title: '登录日志' },
        },

        // Admin: Project
        {
          path: 'projects',
          name: 'GameProjectList',
          component: () => import('@/views/admin/GameProjectList.vue'),
          meta: { requiresAdmin: true, title: '项目管理' },
        },
        {
          path: 'projects/:id',
          name: 'GameProjectDetail',
          component: () => import('@/views/admin/GameProjectDetail.vue'),
          meta: { requiresAdmin: true, title: '项目详情' },
        },

        // Admin: Project legacy transition pages
        {
          path: 'pricing',
          name: 'ProjectPricing',
          component: () => import('@/views/admin/ProjectPricing.vue'),
          meta: { requiresAdmin: true, title: '项目定价' },
        },
        {
          path: 'project-access-policies',
          name: 'ProjectAccessPolicies',
          component: () => import('@/views/admin/ProjectAccessPolicies.vue'),
          meta: { requiresAdmin: true, title: '项目准入' },
        },
        {
          path: 'project-auth-requests',
          name: 'AgentProjectAuthRequests',
          component: () => import('@/views/admin/AgentProjectAuthRequests.vue'),
          meta: { requiresAdmin: true, title: '授权申请' },
        },

        // Admin: Accounting
        {
          path: 'accounting',
          name: 'AccountingCenter',
          component: () => import('@/views/admin/AccountingCenter.vue'),
          meta: { requiresAdmin: true, title: '账务中心' },
        },
        // Admin: Other
        {
          path: 'updates',
          name: 'UpdateManage',
          component: () => import('@/views/admin/UpdateManage.vue'),
          meta: { requiresAdmin: true, title: '热更新' },
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/admin/SettingsView.vue'),
          meta: { requiresAdmin: true, title: '系统设置' },
        },
        {
          path: 'guide',
          name: 'Guide',
          component: () => import('@/views/admin/GuideView.vue'),
          meta: { requiresAdmin: true, title: '使用指南' },
        },
      ],
    },

    {
      path: '/login',
      component: AuthLayout,
      children: [
        { path: '', name: 'Login', component: LoginView },
      ],
    },
    { path: '/403', name: 'Forbidden', component: Forbidden },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if ((to.meta.requiresAuth || to.meta.requiresAdmin || to.meta.requiresAgent) && !auth.isLoggedIn) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'Login' && auth.isLoggedIn) {
    return auth.isAgent ? { name: 'AgentProfile' } : { name: 'Dashboard' }
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'Forbidden' }
  }

  if (to.meta.requiresAgent && !auth.isAgent) {
    return { name: 'Forbidden' }
  }

  return true
})

export default router
