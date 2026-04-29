<template>
  <div class="login-wrap">
    <div class="login-card">
      <!-- 品牌标志 -->
      <div class="brand">
        <span class="brand-icon">🐝</span>
        <div>
          <div class="brand-name">蜂巢·大圣</div>
          <div class="brand-sub">管理后台</div>
        </div>
      </div>

      <!-- 登录表单 -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            autocomplete="username"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            style="width: 100%"
            @click="handleLogin"
          >
            {{ loading ? '登录中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 错误提示 -->
      <el-alert
        v-if="errorMsg"
        :title="errorMsg"
        type="error"
        show-icon
        :closable="false"
        style="margin-top: -8px"
      />

      <div class="hint">管理员 · 代理 均可登录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route  = useRoute()
const auth   = useAuthStore()

const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({ username: '', password: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码',   trigger: 'blur' }],
}

const handleLogin = async () => {
  if (!await formRef.value?.validate().catch(() => false)) return

  loading.value  = true
  errorMsg.value = ''

  try {
    await auth.login({ username: form.username, password: form.password })
    // 登录成功，跳转到来源页或总览
    const redirect = route.query.redirect || '/dashboard'
    router.push(redirect)
  } catch (err) {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401 || status === 403) {
      errorMsg.value = typeof detail === 'string' ? detail : '用户名或密码错误'
    } else {
      errorMsg.value = '登录失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.login-card {
  width: 380px;
  background: #1e293b;
  border: 1px solid #2d3748;
  border-radius: 16px;
  padding: 40px 36px;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 36px;
}

.brand-icon {
  font-size: 40px;
}

.brand-name {
  font-size: 20px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: 0.04em;
}

.brand-sub {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.hint {
  text-align: center;
  color: #475569;
  font-size: 12px;
  margin-top: 16px;
}

/* 覆盖 Element Plus 输入框在深色卡片上的样式 */
:deep(.el-input__wrapper) {
  background: #0f172a;
  border-color: #2d3748;
  box-shadow: none;
}

:deep(.el-input__wrapper:hover),
:deep(.el-input__wrapper.is-focus) {
  border-color: #2563eb !important;
  box-shadow: none !important;
}

:deep(.el-input__inner) {
  color: #f1f5f9;
}

:deep(.el-input__prefix-icon),
:deep(.el-input__suffix-icon) {
  color: #64748b;
}
</style>
