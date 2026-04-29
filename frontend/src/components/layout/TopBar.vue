<template>
  <div class="top-bar">
    <!-- 左侧：折叠按钮 + 当前页标题 -->
    <div class="left">
      <el-button
        text
        :icon="appStore.sidebarCollapsed ? Expand : Fold"
        @click="appStore.toggleSidebar()"
        class="collapse-btn"
      />
      <span class="page-title">{{ pageTitle }}</span>
    </div>

    <!-- 右侧：角色标签 + 用户名 + 登出 -->
    <div class="right">
      <el-tag
        :type="auth.isAdmin ? 'danger' : 'warning'"
        effect="light"
        size="small"
        class="role-tag"
      >
        {{ auth.isAdmin ? '管理员' : `代理 Lv.${auth.userInfo?.level ?? '?'}` }}
      </el-tag>

      <el-dropdown @command="handleCommand" trigger="click">
        <span class="user-info">
          <el-avatar :size="28" :style="{ background: '#2563eb' }">
            {{ auth.displayName.charAt(0).toUpperCase() }}
          </el-avatar>
          <span class="username">{{ auth.displayName }}</span>
          <el-icon class="arrow"><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon> 退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Fold, Expand, ArrowDown, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore }  from '@/stores/app'

const auth     = useAuthStore()
const appStore = useAppStore()
const route    = useRoute()
const router   = useRouter()

const pageTitle = computed(() => route.meta?.title || '蜂巢·大圣')

const handleCommand = async (cmd) => {
  if (cmd === 'logout') {
    await ElMessageBox.confirm('确认退出登录？', '提示', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.top-bar {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.collapse-btn {
  font-size: 18px;
  color: #606266;
}

.page-title {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.role-tag {
  font-size: 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}

.user-info:hover {
  background: #f4f6f9;
}

.username {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
}

.arrow {
  font-size: 12px;
  color: #909399;
}
</style>
