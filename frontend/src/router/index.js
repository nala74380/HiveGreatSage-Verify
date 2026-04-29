/**
 * 文件位置: src/router/index.js
 * 功能说明: Vue Router 实例 + 全局路由守卫
 */

import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import AuthLayout      from '@/layouts/AuthLayout.vue'
import LoginView       from '@/views/auth/LoginView.vue'
import NotFound        from '@/views/error/NotFound.vue'
import Forbidden       from '@/views/error/Forbidden.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: DashboardLayout,
      children: [
        { path: '', redirect: '/dashboard' },

        // ── 所有角色共用 ────────────────────────────────────
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
          meta: { requiresAuth: true, title: '个人主页' },
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
          path: 'agents',
          name: 'AgentList',
          component: () => import('@/views/shared/AgentList.vue'),
          meta: { requiresAuth: true, title: '代理管理' },
        },
        {
          path: 'devices',
          name: 'DeviceList',
          component: () => import('@/views/shared/DeviceList.vue'),
          meta: { requiresAuth: true, title: '设备监控' },
        },
        {
          path: 'login-logs',
          name: 'LoginLogs',
          component: () => import('@/views/shared/LoginLogView.vue'),
          meta: { requiresAdmin: true, title: '登录日志' },
        },

        // ── Admin 专属 ──────────────────────────────────────
        {
          path: 'projects',
          name: 'GameProjectList',
          component: () => import('@/views/admin/GameProjectList.vue'),
          meta: { requiresAdmin: true, title: '项目管理' },
        },
        {
          path: 'pricing',
          name: 'ProjectPricing',
          component: () => import('@/views/admin/ProjectPricing.vue'),
          meta: { requiresAdmin: true, title: '项目定价' },
        },
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

    { path: '/login', component: AuthLayout, children: [{ path: '', name: 'Login', component: LoginView }] },
    { path: '/403', name: 'Forbidden', component: Forbidden },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound },
  ],
})

router.beforeEach((to, from) => {
  const auth = useAuthStore()
  if ((to.meta.requiresAuth || to.meta.requiresAdmin) && !auth.isLoggedIn)
    return { name: 'Login', query: { redirect: to.fullPath } }
  if (to.name === 'Login' && auth.isLoggedIn)
    return auth.isAgent ? { name: 'AgentProfile' } : { name: 'Dashboard' }
  if (to.meta.requiresAdmin && !auth.isAdmin)
    return { name: 'Forbidden' }
})

export default router
