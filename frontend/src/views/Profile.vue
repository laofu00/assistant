<template>
  <div class="page-container">
    <div class="page-header">
      <h2>个人资料</h2>
    </div>
    <div class="profile-layout">
      <div class="profile-avatar-section">
        <div class="avatar-preview">
          <img v-if="form.avatar" :src="form.avatar" class="avatar-img" />
          <span v-else class="avatar-placeholder">{{ form.username?.charAt(0)?.toUpperCase() || '?' }}</span>
        </div>
        <p class="avatar-hint">{{ form.avatar ? '头像预览' : '设置头像 URL后预览' }}</p>
      </div>
      <el-card class="profile-card">
        <el-form :model="form" :rules="rules" ref="formRef" label-width="80px" @submit.prevent="handleSave">
          <el-form-item label="用户ID"><el-input v-model="form.userId" disabled /></el-form-item>
          <el-form-item label="用户名"><el-input v-model="form.username" disabled /></el-form-item>
          <el-form-item label="昵称" prop="nickname">
            <el-input v-model="form.nickname" placeholder="请输入昵称" />
          </el-form-item>
          <el-form-item label="头像URL" prop="avatar">
            <el-input v-model="form.avatar" placeholder="请输入头像URL" />
          </el-form-item>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="form.phone" placeholder="请输入手机号" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="form.email" placeholder="请输入邮箱" />
          </el-form-item>
          <el-form-item label="性别" prop="gender">
            <el-select v-model="form.gender" placeholder="请选择性别">
              <el-option label="未知" :value="0" />
              <el-option label="男" :value="1" />
              <el-option label="女" :value="2" />
            </el-select>
          </el-form-item>
          <el-divider content-position="left">修改密码（留空则不修改）</el-divider>
          <el-form-item label="旧密码" prop="oldPassword">
            <el-input v-model="form.oldPassword" type="password" placeholder="请输入当前密码" show-password />
          </el-form-item>
          <el-form-item label="新密码" prop="newPassword">
            <el-input v-model="form.newPassword" type="password" placeholder="需包含大写、小写字母和数字，至少8位" show-password />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirmPassword">
            <el-input v-model="form.confirmPassword" type="password" placeholder="再次输入新密码" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSave" :loading="loading">保存修改</el-button>
            <el-button @click="router.push('/chat')">返回首页</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { authApi } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ userId: '', username: '', nickname: '', avatar: '', phone: '', email: '', gender: 0, oldPassword: '', newPassword: '', confirmPassword: '' })

const validatePassword = (rule, value, callback) => {
  if (form.newPassword && value === '') callback(new Error('请再次输入密码'))
  else if (value !== form.newPassword) callback(new Error('两次输入密码不一致'))
  else callback()
}

const rules = {
  nickname: [{ min: 1, max: 30, message: '昵称长度在 1 到 30 个字符', trigger: 'blur' }],
  avatar: [{ type: 'url', message: '请输入正确的URL地址', trigger: 'blur' }],
  phone: [{ validator: (rule, value, callback) => { if (!value) callback(); else if (!/^1[3-9]\d{9}$/.test(value)) callback(new Error('请输入正确的手机号码')); else callback() }, trigger: 'blur' }],
  email: [{ validator: (rule, value, callback) => { if (!value) callback(); else if (!/^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value)) callback(new Error('请输入正确的邮箱地址')); else callback() }, trigger: 'blur' }],
  gender: [{ type: 'number', message: '请选择性别', trigger: 'change' }],
  newPassword: [
    { pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/, message: '密码需包含大写、小写字母和数字，至少8位', trigger: 'blur' }
  ],
  confirmPassword: [{ validator: validatePassword, trigger: 'blur' }]
}

const loadProfile = async () => {
  try {
    const response = await authApi.getCurrentUser()
    const userData = response.data
    form.userId = userData.userId || ''
    form.username = userData.username || ''
    form.nickname = userData.nickname || ''
    form.avatar = userData.avatar || ''
    form.phone = userData.phone || ''
    form.email = userData.email || ''
    form.gender = userData.gender || 0
    if (userData.nickname) { userStore.username = userData.nickname; localStorage.setItem('username', userData.nickname) }
  } catch (error) {
    form.userId = userStore.userId || ''
    form.username = userStore.username || ''
    ElMessage.error('加载用户信息失败')
  }
}

const handleSave = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      // 更新个人资料
      await authApi.updateProfile({ nickname: form.nickname, avatar: form.avatar, phone: form.phone, email: form.email, gender: form.gender })
      userStore.nickname = form.nickname || form.username
      localStorage.setItem('nickname', userStore.nickname)

      // 如果填写了密码，单独调用改密接口
      if (form.oldPassword || form.newPassword) {
        if (!form.oldPassword) { ElMessage.warning('请输入旧密码'); loading.value = false; return }
        if (!form.newPassword) { ElMessage.warning('请输入新密码'); loading.value = false; return }
        await authApi.changePassword({ old_password: form.oldPassword, new_password: form.newPassword })
        ElMessage.success('密码修改成功，请重新登录')
        userStore.logout()
        router.push('/login')
        return
      }

      ElMessage.success('个人资料更新成功')
      form.oldPassword = ''; form.newPassword = ''; form.confirmPassword = ''
    } catch (error) {
      ElMessage.error('更新失败: ' + error.message)
    } finally { loading.value = false }
  })
}

onMounted(loadProfile)
</script>

<style scoped>
.profile-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.profile-avatar-section {
  width: 180px;
  flex-shrink: 0;
  text-align: center;
}

.avatar-preview {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  margin: 0 auto 12px;
  overflow: hidden;
  background: linear-gradient(135deg, var(--bg-page), var(--border-light));
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  font-size: 40px;
  font-weight: 600;
  color: var(--primary);
}

.avatar-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.profile-card {
  flex: 1;
  max-width: 640px;
}

@media (max-width: 768px) {
  .profile-layout { flex-direction: column; }
  .profile-avatar-section { width: 100%; }
}
</style>
