<template>
  <!-- 用户/代理状态标签，对齐后端枚举 -->
  <el-tag :type="info.type" effect="light" size="small">
    {{ info.label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'
import { formatUserStatus, formatAgentStatus, formatDeviceStatus } from '@/utils/format'

const props = defineProps({
  /** 状态值，如 'active' | 'suspended' | 'expired' | 'running' | 'offline' 等 */
  status: { type: String, required: true },
  /** 类型：'user' | 'agent' | 'device' */
  type:   { type: String, default: 'user' },
  /** 设备专用：是否在线 */
  isOnline: { type: Boolean, default: false },
})

const info = computed(() => {
  if (props.type === 'agent')  return formatAgentStatus(props.status)
  if (props.type === 'device') return formatDeviceStatus(props.status, props.isOnline)
  return formatUserStatus(props.status)
})
</script>
