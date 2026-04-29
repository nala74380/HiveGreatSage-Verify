<template>
  <!-- 用户级别标签：trial/normal/vip/svip/tester -->
  <el-tag
    effect="dark"
    size="small"
    :style="{ backgroundColor: info.color, borderColor: info.color }"
  >
    {{ info.label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'
import { formatUserLevel } from '@/utils/format'

const props = defineProps({
  level: { type: String, required: true },
})

const info = computed(() => formatUserLevel(props.level))
</script>
