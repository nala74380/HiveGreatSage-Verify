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
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore }  from '@/stores/app'
import {
  Odometer, User, Share, Monitor, Grid, Setting, Document, Upload, Avatar, QuestionFilled, Coin,
} from '@element-plus/icons-vue'

const route    = useRoute()
const auth     = useAuthStore()
const appStore = useAppStore()

const currentPath = computed(() => '/' + route.path.split('/')[1])

/**
 * 菜单项：Admin 额外看到「游戏项目」。
 * 代理管理目前仅 Admin 可见（Phase 1：代理只能管理员创建）。
 */
const menuItems = computed(() => {
  const base = [
    { label: '总览',     path: '/dashboard',  icon: Odometer },
    { label: '用户管理', path: '/users',      icon: User },
    { label: '设备监控', path: '/devices',    icon: Monitor },
  ]

  // Agent 专属：个人主页
  if (auth.isAgent) {
    base.unshift({ label: '个人主页', path: '/profile', icon: Avatar })
  }

  if (auth.isAdmin) {
    // Admin 专属菜单项
    base.splice(2, 0,
      { label: '代理管理', path: '/agents',      icon: Share },
      { label: '项目管理', path: '/projects',    icon: Grid },
      { label: '项目定价', path: '/pricing',    icon: Coin },
      { label: '热更新',   path: '/updates',     icon: Upload },
    )
    base.push(
      { label: '登录日志', path: '/login-logs', icon: Document },
      { label: '系统设置', path: '/settings',   icon: Setting },
      { label: '使用指南', path: '/guide',      icon: QuestionFilled },
    )
  }

  return base
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
