<template>
  <div class="side-menu">
    <!-- Logo 区域 -->
    <div class="logo" :class="{ collapsed: appStore.sidebarCollapsed }">
      <span class="logo-icon">🐝</span>
      <span v-if="!appStore.sidebarCollapsed" class="logo-text">蜂巢·大圣</span>
    </div>

    <!-- 导航菜单 -->
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
 * 名称: 左侧导航菜单
 * 作者: 蜂巢·大圣 (Hive-GreatSage)
 * 时间: 2026-04-29
 * 版本: V1.1.0
 * 功能及相关说明:
 *   根据当前登录角色渲染侧边栏菜单。
 *   Admin 显示平台管理菜单。
 *   Agent 显示代理工作台菜单，包括项目目录与我的余额。
 *
 * 改进内容:
 *   V1.1.0 - 新增代理侧「项目目录」「我的余额」入口，补齐代理端价格/余额能力链路
 *   V1.0.0 - 初始侧边栏菜单
 *
 * 调试信息:
 *   若菜单不显示，先检查 Pinia auth.role 是否为 admin / agent。
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore }  from '@/stores/app'
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
  Coin,
  Tickets,
  Wallet,
} from '@element-plus/icons-vue'

const route    = useRoute()
const auth     = useAuthStore()
const appStore = useAppStore()

const currentPath = computed(() => '/' + route.path.split('/')[1])

const menuItems = computed(() => {
  // ── Agent 专属菜单 ───────────────────────────────────────
  if (auth.isAgent) {
    return [
      { label: '个人主页', path: '/profile', icon: Avatar },
      { label: '总览',     path: '/dashboard', icon: Odometer },
      { label: '用户管理', path: '/users', icon: User },
      { label: '设备监控', path: '/devices', icon: Monitor },
      { label: '项目目录', path: '/catalog', icon: Tickets },
      { label: '我的余额', path: '/balance', icon: Wallet },
    ]
  }

  // ── Admin 专属菜单 ───────────────────────────────────────
  if (auth.isAdmin) {
    return [
      { label: '总览',     path: '/dashboard',  icon: Odometer },
      { label: '用户管理', path: '/users',      icon: User },
      { label: '代理管理', path: '/agents',     icon: Share },
      { label: '项目管理', path: '/projects',   icon: Grid },
      { label: '项目定价', path: '/pricing',    icon: Coin },
      { label: '热更新',   path: '/updates',    icon: Upload },
      { label: '设备监控', path: '/devices',    icon: Monitor },
      { label: '登录日志', path: '/login-logs', icon: Document },
      { label: '系统设置', path: '/settings',   icon: Setting },
      { label: '使用指南', path: '/guide',      icon: QuestionFilled },
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

/* 激活项背景 */
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