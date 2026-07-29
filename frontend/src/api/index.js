import axios from 'axios'
import { useUserStore } from '../store/user'
import router from '../router'

// 创建axios实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 60000
})

// 请求拦截器：添加用户ID（Python 版简化认证，不需要 JWT）
api.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    // 传递用户ID到后端（Python 版通过 X-User-ID 头识别用户）
    const userId = userStore.userId || localStorage.getItem('userId') || 'test'
    config.headers['X-User-ID'] = userId
    // 传递 token（兼容旧版，Python 版可选）
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理错误
api.interceptors.response.use(
  (response) => {
    // Python 版返回格式 { code: 0, data: ..., msg: "success" }
    // code=0 表示成功
    if (response.data.code === 0 || response.data.code === 200) {
      return response.data
    } else {
      const errorMessage = response.data.msg || response.data.message || '请求失败'

      if (response.data.code === 401) {
        const userStore = useUserStore()
        userStore.logout()
        router.push('/login')
        return
      }

      return Promise.reject(new Error(errorMessage))
    }
  },
  (error) => {
    console.error('API请求错误:', error)

    if (error.response) {
      const { status } = error.response

      if (status === 401) {
        const userStore = useUserStore()
        userStore.logout()
        router.push('/login')
        return Promise.reject(new Error('登录已过期，请重新登录'))
      }

      const errorMessage = error.response.data?.msg || error.response.data?.detail || `请求失败 (${status})`
      return Promise.reject(new Error(errorMessage))
    }

    if (error.message === 'Network Error') {
      return Promise.reject(new Error('网络连接失败，请检查网络设置'))
    }

    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('请求超时，请稍后重试'))
    }

    return Promise.reject(error)
  }
)

// 知识库相关API
export const knowledgeApi = {
  uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  getFiles(page = 1, size = 10) {
    return api.get('/knowledge/files', { params: { page, size } })
  },

  deleteFile(fileId) {
    return api.delete(`/knowledge/files/${fileId}`)
  },

  getFileStatus(fileId) {
    return api.get(`/knowledge/files/${fileId}/status`)
  },

  retrieveKnowledge(query, topK = 5) {
    return api.get('/knowledge/retrieve', { params: { query, topK } })
  }
}

// 备忘录相关API
export const memoApi = {
  createMemo(memo) {
    return api.post('/memo', memo)
  },

  updateMemo(id, memo) {
    return api.put(`/memo/${id}`, memo)
  },

  deleteMemo(id) {
    return api.delete(`/memo/${id}`)
  },

  getMemos(category = null, page = 1, size = 10) {
    const params = { page, size }
    if (category) params.category = category
    return api.get('/memo/list', { params })
  },

  searchMemos(keyword, page = 1, size = 10) {
    return api.get('/memo/search', { params: { keyword, page, size } })
  }
}

// 对话相关API
export const chatApi = {
  sendMessage(message) {
    return api.post('/chat', { message })
  },

  // 流式发送消息（Python 版：POST + SSE）
  async sendMessageStream(message, onChunk, onComplete, onError, onThinking, onUndo) {
    try {
      const userId = localStorage.getItem('userId') || 'test'
      const token = localStorage.getItem('token') || ''
      const url = `${api.defaults.baseURL}/chat`

      console.log('sendMessageStream - POST', url)

      const headers = {
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json',
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message, user_id: userId })
      })

      console.log('sendMessageStream - Response status:', response.status)

      if (!response.ok) {
        if (response.status === 401) {
          console.warn('Authentication failed (401)')
          localStorage.removeItem('token')
          localStorage.removeItem('userId')
          const error = new Error('Authentication failed - Please login again')
          error.isAuthError = true
          error.status = 401
          throw error
        }
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEventType = 'message'
      let currentEventData = ''  // 累积同一个 SSE 事件的多行 data
      let lastDataTime = Date.now()
      const timeoutMs = 120000
      const timeoutTimer = setInterval(() => {
        if (Date.now() - lastDataTime > timeoutMs) {
          console.error('SSE流超时')
          clearInterval(timeoutTimer)
          if (onError) onError(new Error('SSE流超时，请重试'))
          reader.cancel()
        }
      }, 5000)

      const flushEvent = () => {
        if (!currentEventData || currentEventData === '[DONE]') return
        if (currentEventType === 'thinking' && onThinking) {
          try { onThinking(JSON.parse(currentEventData)) } catch { onThinking({ raw: currentEventData }) }
        } else if (currentEventType === 'undo' && onUndo) {
          onUndo(parseInt(currentEventData, 10) || 0)
        } else {
          onChunk(currentEventData)
        }
      }

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            if (buffer.trim()) {
              currentEventType = 'message'
              currentEventData = ''
              for (const line of buffer.split('\n')) {
                if (line.startsWith('event:')) {
                  currentEventType = line.substring(6).trim()
                } else if (line.startsWith('data:')) {
                  currentEventData += (currentEventData ? '\n' : '') + line.substring(5).trim()
                } else if (line.trim() === '') {
                  flushEvent()
                  currentEventType = 'message'
                  currentEventData = ''
                }
              }
              flushEvent()
            }
            if (onComplete) onComplete()
            break
          }
          lastDataTime = Date.now()
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = ''
          for (const line of lines) {
            if (line.startsWith('event:')) {
              const eventType = line.substring(6).trim()
              if (eventType === 'done') {
                if (onComplete) onComplete()
                return
              }
              currentEventType = eventType
            } else if (line.startsWith('data:')) {
              currentEventData += (currentEventData ? '\n' : '') + line.substring(5).trim()
            } else if (line.trim() === '') {
              flushEvent()
              currentEventType = 'message'
              currentEventData = ''
            } else {
              buffer += line + '\n'
            }
          }
        }
      } finally {
        clearInterval(timeoutTimer)
      }
    } catch (error) {
      if (onError) onError(error)
    }
  },

  // 流式发送消息（Flux端点，保留兼容）
  async sendMessageStreamFlux(message, onChunk, onComplete, onError) {
    return this.sendMessageStream(message, onChunk, onComplete, onError)
  }
}

// 用户认证相关API
export const authApi = {
  login(credentials) {
    return api.post('/auth/login', credentials)
  },

  register(userData) {
    return api.post('/auth/register', userData)
  },

  getCurrentUser() {
    return api.get('/auth/current')
  },

  updateProfile(profileData) {
    return api.put('/auth/profile', profileData)
  },

  changePassword(passwordData) {
    return api.post('/auth/change-password', passwordData)
  }
}

export default api
