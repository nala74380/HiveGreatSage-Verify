<template>
  <el-card shadow="never" class="health-card">
    <template #header>
      <span class="card-title">系统健康</span>
    </template>
    <div class="health-grid">
      <div class="health-item">
        <span class="health-dot" :class="props.health?.api"></span>
        <span class="health-label">API</span>
      </div>
      <div class="health-item">
        <span class="health-dot" :class="props.health?.database || 'error'"></span>
        <span class="health-label">数据库</span>
      </div>
      <div class="health-item">
        <span class="health-dot" :class="props.health?.redis || 'error'"></span>
        <span class="health-label">Redis</span>
      </div>
      <div class="health-item">
        <span class="health-dot" :class="props.health?.celery || 'unknown'"></span>
        <span class="health-label">Celery</span>
      </div>
    </div>
    <div class="health-footer">
      <span v-if="allOk" class="health-ok">所有服务正常</span>
      <span v-else class="health-warn">部分服务异常</span>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  health: { type: Object, default: () => ({}) },
})

const allOk = computed(() =>
  props.health?.api === 'ok' &&
  props.health?.database === 'ok' &&
  props.health?.redis === 'ok' &&
  props.health?.celery === 'ok'
)
</script>

<style scoped>
.health-card { height: 100%; }
.health-grid { display: flex; gap: 16px; flex-wrap: wrap; padding: 4px 0 8px; }
.health-item { display: flex; align-items: center; gap: 6px; }
.health-dot {
  width: 10px; height: 10px; border-radius: 50%; background: #909399;
}
.health-dot.ok      { background: #10b981; }
.health-dot.error   { background: #ef4444; }
.health-dot.unknown { background: #f59e0b; }
.health-dot.no_recent_flush { background: #f59e0b; }
.health-label { font-size: 13px; color: #606266; }
.health-footer { font-size: 12px; color: #909399; padding-top: 4px; }
.health-ok { color: #10b981; }
.health-warn { color: #ef4444; }
</style>
