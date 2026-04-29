/**
 * 文件位置: src/router/routes/common.js
 * 功能说明: 公共路由（登录页、403、404）
 */

import AuthLayout    from '@/layouts/AuthLayout.vue'
import LoginView     from '@/views/auth/LoginView.vue'
import NotFound      from '@/views/error/NotFound.vue'
import Forbidden     from '@/views/error/Forbidden.vue'

export const commonRoutes = [
  {
    path: '/login',
    component: AuthLayout,
    children: [
      { path: '', name: 'Login', component: LoginView },
    ],
  },
  { path: '/403', name: 'Forbidden', component: Forbidden },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound },
]
