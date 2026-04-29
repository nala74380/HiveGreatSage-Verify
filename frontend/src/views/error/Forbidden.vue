<template>
  <div class="error-page">
    <div class="code">403</div>
    <div class="title">无访问权限</div>
    <div class="desc">您的账号没有访问该页面的权限</div>
    <el-button type="primary" @click="router.push('/dashboard')">返回总览</el-button>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<style scoped>
.error-page {
  min-height: 100vh;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; background: #f4f6f9;
}
.code  { font-size: 96px; font-weight: 800; color: #fecdd3; line-height: 1; }
.title { font-size: 22px; font-weight: 600; color: #1e293b; }
.desc  { font-size: 14px; color: #64748b; margin-bottom: 8px; }
</style>
