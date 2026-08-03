import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { formatDateTime } from '../utils/dateUtils.js'
import axios from 'axios'

function makeSessionId() {
  return 'session_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 7)
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

function getAuthHeaders() {
  const token = localStorage.getItem('token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ==================== localStorage 操作（不依赖 auth，页面刷新瞬间可用） ====================

function loadSessionList() {
  try {
    const saved = localStorage.getItem('chat_sessions')
    return saved ? JSON.parse(saved) : []
  } catch { return [] }
}

function saveSessionList(sessions) {
  localStorage.setItem('chat_sessions', JSON.stringify(sessions))
}

function getCurrentSessionId() {
  return localStorage.getItem('chat_current_session') || ''
}

function setCurrentSessionId(id) {
  localStorage.setItem('chat_current_session', id)
}

function loadMessages(sessionId) {
  if (!sessionId) return []
  try {
    const saved = localStorage.getItem('chat_msgs_' + sessionId)
    return saved ? JSON.parse(saved) : []
  } catch { return [] }
}

function saveMessages(sessionId, msgs) {
  if (!sessionId) return
  localStorage.setItem('chat_msgs_' + sessionId, JSON.stringify(msgs))
}

// ==================== store ====================

export const useChatStore = defineStore('chat', () => {
  // 当前会话 ID（纯 localStorage，不依赖后端）
  const currentSessionId = ref(getCurrentSessionId())

  // 会话列表（localStorage 为默认，Redis 异步更新）
  const sessionList = ref(loadSessionList())

  // 消息列表
  const messages = ref(loadMessages(currentSessionId.value))

  const loading = ref(false)
  const streamingMessageIndex = ref(-1)
  const inputMessage = ref('')

  // ==================== 消息持久化 ====================

  function saveMessagesToStorage() {
    saveMessages(currentSessionId.value, messages.value)
  }

  // ==================== 会话同步（Redis → localStorage，页面加载时执行一次） ====================

  async function syncSessionsFromBackend() {
    try {
      const resp = await axios.get(`${API_BASE}/memory/sessions`, { headers: getAuthHeaders() })
      const backendSessions = resp.data?.data || []
      if (backendSessions.length === 0) return  // Redis 空，保留本地

      const localMap = Object.fromEntries(sessionList.value.map(s => [s.id, s]))

      // Redis 为主，保留本地标题
      const merged = backendSessions.map(bs => ({
        id: bs.session_id,
        title: (localMap[bs.session_id]?.title && !localMap[bs.session_id]?.title.startsWith('新会话'))
          ? localMap[bs.session_id].title : (bs.title || '新会话'),
        time: localMap[bs.session_id]?.time || bs.created_at || new Date().toISOString(),
        messageCount: bs.message_count || 0,
      }))

      // 保底：当前会话必须在列表中（Redis 可能已过期但 local 还在）
      if (currentSessionId.value && !merged.find(s => s.id === currentSessionId.value)) {
        const local = localMap[currentSessionId.value]
        if (local) {
          merged.unshift(local)
        }
      }

      sessionList.value = merged
      saveSessionList(merged)
    } catch (e) {
      console.warn('会话同步失败，保留本地列表:', e.message)
    }
  }

  // ==================== 会话操作 ====================

  let _sessionCounter = sessionList.value.length

  const createSession = () => {
    _sessionCounter++
    const id = makeSessionId()
    const now = new Date().toISOString()
    const session = { id, title: `新会话 ${_sessionCounter}`, time: now, messageCount: 0 }
    sessionList.value.unshift(session)
    saveSessionList(sessionList.value)
    switchSession(id)
  }

  const switchSession = (sessionId) => {
    // 保存当前消息
    if (currentSessionId.value) {
      saveMessages(currentSessionId.value, messages.value)
    }
    // 切换
    currentSessionId.value = sessionId
    setCurrentSessionId(sessionId)
    messages.value = loadMessages(sessionId)
    streamingMessageIndex.value = -1
    if (messages.value.length === 0) initWelcomeMessage()
  }

  const deleteSession = (sessionId) => {
    sessionList.value = sessionList.value.filter(s => s.id !== sessionId)
    saveSessionList(sessionList.value)
    localStorage.removeItem('chat_msgs_' + sessionId)
    if (currentSessionId.value === sessionId) {
      if (sessionList.value.length > 0) {
        switchSession(sessionList.value[0].id)
      } else {
        createSession()
      }
    }
  }

  const renameSession = (sessionId, newTitle) => {
    const idx = sessionList.value.findIndex(s => s.id === sessionId)
    if (idx >= 0 && newTitle.trim()) {
      sessionList.value[idx].title = newTitle.trim().substring(0, 30)
      saveSessionList(sessionList.value)
    }
  }

  // ==================== 消息操作 ====================

  const getCurrentTime = () => formatDateTime(new Date())

  const initWelcomeMessage = () => {
    if (messages.value.length === 0) {
      messages.value = [{
        role: 'assistant',
        content: '您好，我是您的智能助手 Smart Assistant，可以帮您做以下事情：\n'
          + '1. 创建、查询、更新或删除备忘录（AI 自动分类）\n'
          + '2. 从知识库中检索信息、上传和管理文档\n'
          + '3. 简历与 JD 匹配评估（支持招聘方/求职者双视角）\n'
          + '4. 整理信息并通过邮件发送\n'
          + '5. 日期查询与计算\n'
          + '\n请告诉我您需要什么帮助？',
        time: getCurrentTime(),
        intent: 'GENERAL',
        references: [],
        thinkingSteps: []
      }]
    }
  }

  const addUserMessage = (content) => {
    messages.value.push({
      role: 'user',
      content,
      time: formatDateTime(new Date())
    })
    updateSessionMeta()
    saveMessagesToStorage()
  }

  const addAiMessage = (content, intent = 'GENERAL') => {
    const index = messages.value.push({
      role: 'ai',
      content,
      time: formatDateTime(new Date()),
      intent,
      references: [],
      thinkingSteps: []
    })
    saveMessagesToStorage()
    return index - 1
  }

  const addErrorMessage = (errorMsg) => {
    messages.value.push({
      role: 'assistant',
      content: errorMsg,
      time: formatDateTime(new Date()),
      intent: 'ERROR',
      references: [],
      thinkingSteps: []
    })
    saveMessagesToStorage()
  }

  const updateSessionMeta = () => {
    const idx = sessionList.value.findIndex(s => s.id === currentSessionId.value)
    if (idx >= 0) {
      const userMsgs = messages.value.filter(m => m.role === 'user')
      sessionList.value[idx].messageCount = messages.value.length
      sessionList.value[idx].time = new Date().toISOString()
      if (userMsgs.length === 1 && sessionList.value[idx].title === '新会话') {
        sessionList.value[idx].title = (userMsgs[0].content || '').substring(0, 20)
      }
      saveSessionList(sessionList.value)
    }
  }

  // ==================== 清空 ====================

  const clearMessages = () => {
    // 清除当前会话的消息和 localStorage
    const sid = currentSessionId.value
    localStorage.removeItem('chat_msgs_' + sid)
    messages.value = []
    // 从会话列表中移除
    sessionList.value = sessionList.value.filter(s => s.id !== sid)
    currentSessionId.value = ''
    localStorage.removeItem('chat_current_session')
    saveSessionList(sessionList.value)
  }

  // ==================== 流式内容操作 ====================

  const startStreamAiMessage = () => {
    const index = messages.value.push({
      role: 'assistant',
      content: '',
      time: formatDateTime(new Date()),
      intent: 'GENERAL',
      references: [],
      thinkingSteps: []
    }) - 1
    streamingMessageIndex.value = index
    saveMessagesToStorage()
  }

  const addThinkingStep = (tool, label) => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      const msg = newMessages[streamingMessageIndex.value]
      const steps = [...(msg.thinkingSteps || [])]
      steps.push({ tool, label, status: 'running', time: formatDateTime(new Date()) })
      newMessages[streamingMessageIndex.value] = { ...msg, thinkingSteps: steps }
      messages.value = newMessages
    }
  }

  const _autoCompleteThinking = () => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const msg = messages.value[streamingMessageIndex.value]
      const steps = msg.thinkingSteps || []
      if (steps.some(s => s.status === 'running')) {
        const newMessages = [...messages.value]
        const completed = steps.map(s => s.status === 'running' ? { ...s, status: 'done' } : s)
        newMessages[streamingMessageIndex.value] = { ...msg, thinkingSteps: completed }
        messages.value = newMessages
        return true
      }
    }
    return false
  }

  const truncateStreamContent = (n) => {
    if (n <= 0) return
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      const msg = newMessages[streamingMessageIndex.value]
      const content = msg.content || ''
      if (content.length >= n) {
        newMessages[streamingMessageIndex.value] = { ...msg, content: content.slice(0, -n) }
        messages.value = newMessages
      }
    }
  }

  const completeThinkingStep = () => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      const msg = newMessages[streamingMessageIndex.value]
      const steps = [...(msg.thinkingSteps || [])]
      if (steps.length > 0) {
        steps[steps.length - 1] = { ...steps[steps.length - 1], status: 'done' }
        newMessages[streamingMessageIndex.value] = { ...msg, thinkingSteps: steps }
        messages.value = newMessages
      }
    }
  }

  const appendStreamContent = (content) => {
    _autoCompleteThinking()

    if (typeof content === 'string') {
      try {
        const decoded = JSON.parse(content)
        if (typeof decoded === 'string') content = decoded
      } catch (e) { /* 非 JSON */ }
    }

    // 元数据事件（JSON 包含 intent 字段）
    let metadata = null
    if (content.startsWith('__METADATA__')) {
      try { metadata = JSON.parse(content.substring('__METADATA__'.length)) } catch (e) { /* ignore */ }
    } else if (typeof content === 'string' && content.startsWith('{') && content.includes('"intent"')) {
      try {
        const parsed = JSON.parse(content)
        if (parsed.intent) metadata = parsed
      } catch (e) { /* ignore */ }
    }

    if (metadata) {
      if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
        const newMessages = [...messages.value]
        newMessages[streamingMessageIndex.value] = {
          ...newMessages[streamingMessageIndex.value],
          intent: metadata.intent || 'GENERAL',
          references: metadata.references || []
        }
        messages.value = newMessages
        saveMessagesToStorage()
      }
      return
    }

    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      const oldContent = newMessages[streamingMessageIndex.value].content
      newMessages[streamingMessageIndex.value] = {
        ...newMessages[streamingMessageIndex.value],
        content: oldContent + (typeof content === 'string' ? content : '')
      }
      messages.value = newMessages
      saveMessagesToStorage()
    }
  }

  const completeStreamMessage = (intent = 'GENERAL', references = []) => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      const currentMessage = newMessages[streamingMessageIndex.value]
      const finalIntent = (!intent || intent === '' || intent === 'GENERAL') && currentMessage.intent
        ? currentMessage.intent : (intent || 'GENERAL')
      const finalReferences = currentMessage.references && currentMessage.references.length > 0
        ? currentMessage.references : references

      newMessages[streamingMessageIndex.value] = {
        ...currentMessage, intent: finalIntent, references: finalReferences
      }
      messages.value = newMessages
      streamingMessageIndex.value = -1
      saveMessagesToStorage()
    }
  }

  const abortStreamMessage = () => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      if (newMessages[streamingMessageIndex.value].content === '') {
        newMessages.splice(streamingMessageIndex.value, 1)
        messages.value = newMessages
      } else {
        newMessages[streamingMessageIndex.value] = {
          ...newMessages[streamingMessageIndex.value], intent: 'GENERAL', references: []
        }
        messages.value = newMessages
      }
      streamingMessageIndex.value = -1
      saveMessagesToStorage()
    }
  }

  // ==================== computed ====================

  const messageList = computed(() => messages.value)
  const isLoading = computed(() => loading.value)
  const currentInputMessage = computed(() => inputMessage.value)
  const currentStreamingMessageIndex = computed(() => streamingMessageIndex.value)

  const setLoading = (isLoading) => { loading.value = isLoading }
  const setInputMessage = (msg) => { inputMessage.value = msg }

  return {
    messages: messageList,
    loading: isLoading,
    inputMessage: currentInputMessage,
    streamingMessageIndex: currentStreamingMessageIndex,
    currentSessionId,
    sessionList,
    // 会话
    syncSessionsFromBackend,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
    // 消息
    getCurrentTime,
    initWelcomeMessage,
    addUserMessage,
    addAiMessage,
    addErrorMessage,
    clearMessages,
    setLoading,
    setInputMessage,
    updateSessionMeta,
    // 流式
    startStreamAiMessage,
    addThinkingStep,
    completeThinkingStep,
    truncateStreamContent,
    appendStreamContent,
    completeStreamMessage,
    abortStreamMessage,
  }
})
