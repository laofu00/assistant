<template>
  <div class="auth-page">
    <div class="auth-brand">
      <div class="brand-content">
        <div class="brand-logo">✦</div>
        <h1>Smart Assistant</h1>
        <p class="brand-desc">加入智能助手，开启高效工作新体验</p>
        <div class="brand-features">
          <div class="feature-item"><span class="feature-icon">💬</span> 智能对话 · 多工具协同</div>
          <div class="feature-item"><span class="feature-icon">📚</span> 知识库 · RAG 精准检索</div>
          <div class="feature-item"><span class="feature-icon">📝</span> 备忘录 · 智能分类管理</div>
        </div>
        <div class="brand-footer">© 2026 Smart Assistant</div>
      </div>
    </div>
    <div class="auth-form-side">
      <div class="auth-card">
        <h2>创建账号</h2>
        <p class="auth-subtitle">注册后即可使用全部功能</p>
        <el-form :model="form" :rules="rules" ref="formRef" @submit.prevent="handleRegister">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名（3-20个字符）" size="large" prefix-icon="User" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="需包含大写、小写字母和数字，至少8位" size="large" show-password prefix-icon="Lock" />
          </el-form-item>
          <el-form-item prop="confirmPassword">
            <el-input v-model="form.confirmPassword" type="password" placeholder="确认密码" size="large" show-password prefix-icon="Lock" />
          </el-form-item>
          <el-form-item prop="email">
            <el-input v-model="form.email" placeholder="邮箱（可选）" size="large" prefix-icon="Message" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" @click="handleRegister" :loading="loading" style="width: 100%">
              注 册
            </el-button>
          </el-form-item>
        </el-form>
        <div class="auth-footer">
          已有账号？<span class="link" @click="goToLogin">去登录</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: '', password: '', confirmPassword: '', email: '' })

const validatePassword = (rule, value, callback) => {
  if (value === '') callback(new Error('请再次输入密码'))
  else if (value !== form.password) callback(new Error('两次输入密码不一致'))
  else callback()
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度在 3 到 20 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 30, message: '密码长度在 8 到 30 个字符', trigger: 'blur' },
    { pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/, message: '密码需包含大写字母、小写字母和数字', trigger: 'blur' }
  ],
  confirmPassword: [{ required: true, validator: validatePassword, trigger: 'blur' }],
  email: [{ type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }]
}

const handleRegister = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    const result = await userStore.register(form)
    loading.value = false
    if (result.success) {
      ElMessage.success('注册成功，请登录')
      router.push('/login')
    } else {
      ElMessage.error(result.message || '注册失败，请检查输入信息')
    }
  })
}

const goToLogin = () => router.push('/login')
</script>

<style scoped>
.auth-page { display: flex; height: 100%; }

.auth-brand {
  flex: 1;
  background: linear-gradient(135deg, #2b3a67 0%, #1a2332 50%, #0d1b2a 100%);
  display: flex; align-items: center; justify-content: center;
  position: relative; overflow: hidden;
}
.auth-brand::before {
  content: ''; position: absolute;
  width: 400px; height: 400px; border-radius: 50%;
  background: radial-gradient(circle, rgba(64,158,255,.15) 0%, transparent 70%);
  top: -100px; right: -100px;
}
.auth-brand::after {
  content: ''; position: absolute;
  width: 300px; height: 300px; border-radius: 50%;
  background: radial-gradient(circle, rgba(64,158,255,.1) 0%, transparent 70%);
  bottom: -80px; left: -80px;
}

.brand-content { position: relative; z-index: 1; text-align: center; padding: 40px; max-width: 380px; }
.brand-logo { font-size: 48px; color: #409eff; margin-bottom: 16px; }
.brand-content h1 { color: #fff; font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.brand-desc { color: rgba(255,255,255,.6); font-size: 14px; margin-bottom: 40px; }
.brand-features { text-align: left; margin-bottom: 60px; }
.feature-item { color: rgba(255,255,255,.75); font-size: 14px; padding: 8px 0; }
.feature-icon { margin-right: 8px; }
.brand-footer { color: rgba(255,255,255,.35); font-size: 12px; }

.auth-form-side { width: 460px; display: flex; align-items: center; justify-content: center; background: var(--bg-page); padding: 40px; }
.auth-card { width: 100%; max-width: 380px; }
.auth-card h2 { font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.auth-subtitle { color: var(--text-secondary); font-size: 14px; margin-bottom: 32px; }
.auth-footer { text-align: center; font-size: 14px; color: var(--text-secondary); margin-top: 16px; }
.link { color: var(--primary); cursor: pointer; }
.link:hover { text-decoration: underline; }

@media (max-width: 768px) {
  .auth-brand { display: none; }
  .auth-form-side { width: 100%; }
}
</style>
