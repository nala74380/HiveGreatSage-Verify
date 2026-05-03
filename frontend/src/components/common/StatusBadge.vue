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
  status: { type: String, required: true },
  type:   { type: String, default: 'user' },
  isOnline: { type: Boolean, default: false },
  /** 用户对象（用于判断是否所有授权已过期） */
  user: { type: Object, default: null },
})

const info = computed(() => {
  if (props.type === 'agent')  return formatAgentStatus(props.status)
  if (props.type === 'device') return formatDeviceStatus(props.status, props.isOnline)
  return formatUserStatus(props.status, props.user)
})
</script>
