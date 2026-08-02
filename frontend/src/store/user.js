import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userId = ref(localStorage.getItem('userId') || '')
  const username = ref(localStorage.getItem('username') || '')
  const nickname = ref(localStorage.getItem('nickname') || '')
  const roles = ref(localStorage.getItem('roles') || '')

  const displayName = computed(() => nickname.value || username.value || '用户')
  const isAdmin = computed(() => {
    const roleList = (roles.value || '').split(',').map(r => r.trim().toLowerCase())
    return roleList.some(r => r === 'admin' || r === 'role_admin')
  })

  console.log('User store initialized:', { token: token.value, userId: userId.value, username: username.value, roles: roles.value, isAdmin: isAdmin.value })

  const isLoggedIn = computed(() => !!token.value)

  const login = async (credentials) => {
    try {
      const response = await authApi.login(credentials)
      const data = response.data
      const prevUserId = localStorage.getItem('userId')

      token.value = data.token
      userId.value = data.userId
      username.value = data.username
      nickname.value = data.nickname || data.username
      roles.value = data.roles || 'READ_WRITE'

      localStorage.setItem('token', token.value)
      localStorage.setItem('userId', userId.value)
      localStorage.setItem('username', username.value)
      localStorage.setItem('nickname', nickname.value)
      localStorage.setItem('roles', roles.value)

      // 切换用户时清空上一个用户的会话缓存
      if (prevUserId && prevUserId !== data.userId) {
        Object.keys(localStorage).forEach(key => {
          if (key.startsWith('chat_')) localStorage.removeItem(key)
        })
      }

      return { success: true }
    } catch (error) {
      console.error('登录失败:', error)
      return { success: false, message: error.message || '登录失败' }
    }
  }

  const register = async (userData) => {
    try {
      await authApi.register(userData)
      return { success: true }
    } catch (error) {
      console.error('注册失败:', error)
      return { success: false, message: error.message || '注册失败' }
    }
  }

  const logout = () => {
    console.log('Logging out...')
    token.value = ''
    userId.value = ''
    username.value = ''
    nickname.value = ''
    roles.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('username')
    localStorage.removeItem('nickname')
    localStorage.removeItem('roles')
    console.log('Logout completed')
  }

  const syncRoles = async () => {
    if (!token.value) return
    try {
      const res = await authApi.getCurrentUser()
      if (res.code === 0 && res.data?.roles) {
        roles.value = res.data.roles
        localStorage.setItem('roles', roles.value)
        console.log('Roles synced:', roles.value, 'isAdmin:', isAdmin.value)
      }
    } catch (e) {
      console.warn('同步角色失败, 将使用本地缓存:', e)
    }
  }

  return {
    token,
    userId,
    username,
    nickname,
    roles,
    displayName,
    isLoggedIn,
    isAdmin,
    login,
    register,
    logout,
    syncRoles,
  }
})