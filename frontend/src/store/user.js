import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userId = ref(localStorage.getItem('userId') || '')
  const username = ref(localStorage.getItem('username') || '')
  const nickname = ref(localStorage.getItem('nickname') || '')

  const displayName = computed(() => nickname.value || username.value || '用户')

  console.log('User store initialized:', { token: token.value, userId: userId.value, username: username.value })

  const isLoggedIn = computed(() => !!token.value)

  const login = async (credentials) => {
    try {
      const response = await authApi.login(credentials)
      const data = response.data
      token.value = data.token
      userId.value = data.userId
      username.value = data.username
      nickname.value = data.nickname || data.username

      localStorage.setItem('token', token.value)
      localStorage.setItem('userId', userId.value)
      localStorage.setItem('username', username.value)
      localStorage.setItem('nickname', nickname.value)

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
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('username')
    localStorage.removeItem('nickname')
    console.log('Logout completed')
  }

  return {
    token,
    userId,
    username,
    nickname,
    displayName,
    isLoggedIn,
    login,
    register,
    logout
  }
})