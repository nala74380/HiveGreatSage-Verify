<template>
  <el-container class="dashboard-layout">
    <!-- 侧边栏 -->
    <el-aside :width="appStore.sidebarCollapsed ? '64px' : '220px'" class="aside">
      <SideMenu />
    </el-aside>

    <!-- 主区域 -->
    <el-container direction="vertical">
      <!-- 顶栏 -->
      <el-header height="56px" class="header">
        <TopBar />
      </el-header>

      <!-- 内容区 -->
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useAppStore } from '@/stores/app'
import SideMenu from '@/components/layout/SideMenu.vue'
import TopBar   from '@/components/layout/TopBar.vue'

const appStore = useAppStore()
</script>

<style scoped>
.dashboard-layout {
  height: 100vh;
  overflow: hidden;
}

.aside {
  background: #1a1f2e;
  transition: width 0.25s ease;
  overflow: hidden;
}

.header {
  background: #ffffff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  padding: 0;
}

.main {
  background: #f4f6f9;
  overflow-y: auto;
  padding: 20px;
}

/* 页面切换过渡 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
