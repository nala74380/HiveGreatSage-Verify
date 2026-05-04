<template>
  <div class="side-menu">
    <div class="logo" :class="{ collapsed: appStore.sidebarCollapsed }">
      <span class="logo-icon">🐝</span>
      <span v-if="!appStore.sidebarCollapsed" class="logo-text">蜂巢·大圣</span>
    </div>

    <el-menu
      :default-active="currentPath"
      :collapse="appStore.sidebarCollapsed"
      :collapse-transition="false"
      router
      background-color="#1a1f2e"
      text-color="#a0aec0"
      active-text-color="#ffffff"
      class="menu"
    >
      <el-menu-item
        v-for="item in menuItems"
        :key="item.path"
        :index="item.path"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <template #title>{{ item.label }}</template>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup>
/**
 * 文件位置: src/components/layout/SideMenu.vue
 * 名称: 左侧菜单
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-30
 * 版本: V1.5.0
 * 功能说明:
 *   根据管理员 / 代理身份显示不同菜单。
 *
 * 当前业务口径:
 *   - 项目管理是项目相关能力统一入口。
 *   - 项目定价、项目准入、授权申请已收敛到项目详情页。
 *   - 账务中心是平台内部点数资产治理统一入口。
 *   - 旧“点数流水”不再作为菜单名出现。
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import {
  Odometer,
  User,
  Share,
  Monitor,
  Grid,
  Setting,
  Document,
  Upload,
  Avatar,
  QuestionFilled,
  Tickets,
  Wallet,
  List,
} from '@element-plus/icons-vue'

const route = useRoute()
const auth = useAuthStore()
const appStore = useAppStore()

const currentPath = computed(() => '/' + route.path.split('/')[1])

const menuItems = computed(() => {
  if (auth.isAgent) {
    return [
      { label: '总览', path: '/dashboard', icon: Odometer },
      { label: '个人主页', path: '/profile', icon: Avatar },
      { label: '用户管理', path: '/users', icon: User },
      { label: '设备监控', path: '/devices', icon: Monitor },
      { label: '项目目录', path: '/catalog', icon: Tickets },
      { label: '我的余额', path: '/balance', icon: Wallet },
    ]
  }

  if (auth.isAdmin) {
    return [
      { label: '总览', path: '/dashboard', icon: Odometer },
      { label: '用户管理', path: '/users', icon: User },
      { label: '代理管理', path: '/agents', icon: Share },
      { label: '项目管理', path: '/projects', icon: Grid },
      { label: '账务中心', path: '/accounting', icon: List },
      { label: '热更新', path: '/updates', icon: Upload },
      { label: '设备监控', path: '/devices', icon: Monitor },
      { label: '登录日志', path: '/login-logs', icon: Document },
      { label: '系统设置', path: '/settings', icon: Setting },
      { label: '使用指南', path: '/guide', icon: QuestionFilled },
    ]
  }

  return []
})
</script>

<style scoped>
.side-menu {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  border-bottom: 1px solid #2d3748;
  white-space: nowrap;
  overflow: hidden;
  transition: padding 0.25s;
}

.logo.collapsed {
  padding: 0;
  justify-content: center;
}

.logo-icon {
  font-size: 22px;
  flex-shrink: 0;
}

.logo-text {
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.menu {
  flex: 1;
  border-right: none;
}

:deep(.el-menu-item.is-active) {
  background-color: #2563eb !important;
  border-radius: 6px;
  margin: 0 8px;
  width: calc(100% - 16px);
}

:deep(.el-menu-item:hover) {
  background-color: #2d3748 !important;
  border-radius: 6px;
  margin: 0 8px;
  width: calc(100% - 16px);
}
</style>