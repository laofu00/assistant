import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { formatDateTime } from '../utils/dateUtils.js'

function makeSessionId() {
  return 'session_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 7)
}

export const useChatStore = defineStore('chat', () => {
  // 当前会话 ID
  const currentSessionId = ref(localStorage.getItem('chat_current_session') || '')

  // 会话列表 [{id, title, time, messageCount}]
  const sessionList = ref(loadSessionList())

  // 从 localStorage 加载会话列表
  function loadSessionList() {
    try {
      const saved = localStorage.getItem('chat_sessions')
      return saved ? JSON.parse(saved) : []
    } catch { return [] }
  }

  function saveSessionList() {
    localStorage.setItem('chat_sessions', JSON.stringify(sessionList.value))
  }

  // 从 localStorage 加载当前会话的消息
  function loadCurrentMessages() {
    if (!currentSessionId.value) return []
    try {
      const saved = localStorage.getItem('chat_msgs_' + currentSessionId.value)
      if (saved) return JSON.parse(saved)
    } catch { return [] }
    return []
  }

  // 消息列表（会话隔离）
  const messages = ref(loadCurrentMessages())

  // 是否正在加载
  const loading = ref(false)

  // 当前流式消息的索引（-1表示无）
  const streamingMessageIndex = ref(-1)

  // 输入框内容
  const inputMessage = ref('')

  // 获取当前时间
  const getCurrentTime = () => {
    return formatDateTime(new Date())
  }

  // 初始化默认欢迎消息（如果没有消息）
  const initWelcomeMessage = () => {
    if (messages.value.length === 0) {
      messages.value = [
        {
          role: 'ai',
          content: '您好，我是您的智能助手 Smart Assistant，可以帮您做以下事情：\n'
              + '1. 创建、查询、更新或删除备忘录（AI 自动分类）\n'
              + '2. 从知识库中检索信息、上传和管理文档\n'
              + '3. 简历与 JD 匹配评估（支持招聘方/求职者双视角）\n'
              + '4. 整理信息并通过邮件发送\n'
              + '5. 日期查询与计算\n'
              + '\n请告诉我您需要什么帮助？',
          time: getCurrentTime(),
          intent: 'GENERAL',
          references: []
        }
      ]
      saveMessagesToStorage()
    }
  }

  // 保存消息到 localStorage（按会话隔离）
  const saveMessagesToStorage = () => {
    if (!currentSessionId.value) return
    try {
      localStorage.setItem('chat_msgs_' + currentSessionId.value, JSON.stringify(messages.value))
      // 更新会话列表的标题和消息数
      updateSessionMeta()
    } catch { /* ignore */ }
  }

  // 更新会话列表中的元信息
  function updateSessionMeta() {
    const idx = sessionList.value.findIndex(s => s.id === currentSessionId.value)
    if (idx >= 0) {
      const userMsgs = messages.value.filter(m => m.role === 'user')
      sessionList.value[idx].messageCount = messages.value.length
      sessionList.value[idx].time = new Date().toISOString()
      // 首次有用户消息时自动命名，已有名称不变
      if (userMsgs.length === 1 && sessionList.value[idx].title === '新会话') {
        sessionList.value[idx].title = (userMsgs[0].content || '').substring(0, 20)
      }
      saveSessionList()
    }
  }

  // 创建新会话
  let _sessionCounter = sessionList.value.length
  const createSession = () => {
    _sessionCounter++
    const id = makeSessionId()
    const title = `新会话 ${_sessionCounter}`
    sessionList.value.unshift({ id, title, time: new Date().toISOString(), messageCount: 0 })
    saveSessionList()
    switchSession(id)
  }

  // 重命名会话
  const renameSession = (sessionId, newTitle) => {
    const idx = sessionList.value.findIndex(s => s.id === sessionId)
    if (idx >= 0 && newTitle.trim()) {
      sessionList.value[idx].title = newTitle.trim().substring(0, 30)
      saveSessionList()
    }
  }

  // 切换会话
  const switchSession = (sessionId) => {
    // 保存当前会话消息
    if (currentSessionId.value) {
      localStorage.setItem('chat_msgs_' + currentSessionId.value, JSON.stringify(messages.value))
    }
    // 切换到新会话
    currentSessionId.value = sessionId
    localStorage.setItem('chat_current_session', sessionId)
    // 加载新会话消息
    const saved = localStorage.getItem('chat_msgs_' + sessionId)
    messages.value = saved ? JSON.parse(saved) : []
    if (messages.value.length === 0) initWelcomeMessage()
  }

  // 删除会话
  const deleteSession = (sessionId) => {
    sessionList.value = sessionList.value.filter(s => s.id !== sessionId)
    saveSessionList()
    localStorage.removeItem('chat_msgs_' + sessionId)
    if (currentSessionId.value === sessionId) {
      if (sessionList.value.length > 0) {
        switchSession(sessionList.value[0].id)
      } else {
        createSession()
      }
    }
  }

  // 添加用户消息
  const addUserMessage = (content) => {
    // 创建新数组以确保响应式更新
    const newMessages = [...messages.value]
    newMessages.push({
      role: 'user',
      content,
      time: getCurrentTime(),
      intent: null,
      references: []
    })
    messages.value = newMessages
    saveMessagesToStorage()
  }

  // 添加AI消息
  const addAiMessage = (content, intent = 'GENERAL', references = []) => {
    // 创建新数组以确保响应式更新
    const newMessages = [...messages.value]
    newMessages.push({
      role: 'ai',
      content,
      time: getCurrentTime(),
      intent,
      references
    })
    messages.value = newMessages
    saveMessagesToStorage()
  }

  // 添加错误消息
  const addErrorMessage = (errorMsg) => {
    // 创建新数组以确保响应式更新
    const newMessages = [...messages.value]
    newMessages.push({
      role: 'ai',
      content: errorMsg || '抱歉，我暂时无法处理您的请求，请稍后再试。',
      time: getCurrentTime(),
      intent: 'GENERAL',
      references: []
    })
    messages.value = newMessages
    saveMessagesToStorage()
  }

  // 开始流式AI消息，返回消息索引
  const startStreamAiMessage = () => {
    const index = messages.value.length
    // 创建新数组以确保响应式更新
    const newMessages = [...messages.value]
    newMessages.push({
      role: 'ai',
      content: '',
      time: getCurrentTime(),
      intent: 'GENERAL',
      references: [],
      thinkingSteps: []
    })
    messages.value = newMessages
    streamingMessageIndex.value = index
    saveMessagesToStorage()
    return index
  }

  // 添加思考步骤
  const addThinkingStep = (tool, label) => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      const newMessages = [...messages.value]
      const msg = newMessages[streamingMessageIndex.value]
      const steps = [...(msg.thinkingSteps || [])]
      steps.push({ tool, label, status: 'running', time: getCurrentTime() })
      newMessages[streamingMessageIndex.value] = { ...msg, thinkingSteps: steps }
      messages.value = newMessages
    }
  }

  // 正文开始输出时，自动把所有运行的思考步骤标记为完成
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

  // 回退流式内容（去掉推理文字）
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

  // 完成最后一个思考步骤
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

  // 追加流式内容到当前流式消息
  const appendStreamContent = (content) => {
    // 首次收到正文时，标记所有运行中的思考步骤为完成
    _autoCompleteThinking()

    // 检测 JSON 编码的文本（后端对多行内容使用 json.dumps 保护换行格式）
    if (content.length > 0 && content[0] === '"') {
      try {
        const decoded = JSON.parse(content)
        if (typeof decoded === 'string') {
          content = decoded
        }
      } catch (e) { /* 非 JSON 编码文本，保持原样 */ }
    }

    console.log('🔵 appendStreamContent called:', {
      contentLength: content.length,
      contentPreview: content.length > 50 ? content.substring(0, 50) + '...' : content,
      streamingMessageIndex: streamingMessageIndex.value,
      messagesLength: messages.value.length,
      currentContent: streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length
        ? messages.value[streamingMessageIndex.value].content
        : 'N/A'
    })

    // 检查是否为元数据事件（支持 __METADATA__ 前缀或纯 JSON）
    let metadata = null
    if (content.startsWith('__METADATA__')) {
      try {
        metadata = JSON.parse(content.substring('__METADATA__'.length))
      } catch (e) { /* ignore */ }
    } else if (content.startsWith('{') && content.includes('"intent"')) {
      try {
        const parsed = JSON.parse(content)
        if (parsed.intent) {
          metadata = parsed
        }
      } catch (e) { /* ignore */ }
    }

    if (metadata) {
      console.log('📦 收到元数据:', metadata)
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
      // 创建新数组以确保响应式更新
      const newMessages = [...messages.value]
      const oldContent = newMessages[streamingMessageIndex.value].content
      newMessages[streamingMessageIndex.value] = {
        ...newMessages[streamingMessageIndex.value],
        content: oldContent + content
      }
      console.log('🟢 Updating message content:', {
        oldContentLength: oldContent.length,
        newContentLength: newMessages[streamingMessageIndex.value].content.length,
        newContentPreview: newMessages[streamingMessageIndex.value].content.length > 100
          ? newMessages[streamingMessageIndex.value].content.substring(0, 100) + '...'
          : newMessages[streamingMessageIndex.value].content
      })
      messages.value = newMessages
      saveMessagesToStorage()
    } else {
      console.warn('⚠️ Invalid streamingMessageIndex or messages array:', {
        streamingMessageIndex: streamingMessageIndex.value,
        messagesLength: messages.value.length
      })
    }
  }

  // 完成流式消息，设置意图和引用
  const completeStreamMessage = (intent = 'GENERAL', references = []) => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      // 创建新数组以确保响应式更新
      const newMessages = [...messages.value]
      const currentMessage = newMessages[streamingMessageIndex.value]

      console.log('🔵 completeStreamMessage called:', {
        streamingMessageIndex: streamingMessageIndex.value,
        incomingIntent: intent,
        incomingReferences: references,
        currentMessageIntent: currentMessage.intent,
        currentMessageReferences: currentMessage.references
      })

      // 如果消息已经有意图（通过元数据设置），或者传入的意图为空，则保留已有意图
      const finalIntent = (!intent || intent === '' || intent === 'GENERAL') && currentMessage.intent
        ? currentMessage.intent
        : (intent || 'GENERAL')
      const finalReferences = currentMessage.references && currentMessage.references.length > 0 ? currentMessage.references : references

      console.log('🟢 Final values:', {
        finalIntent,
        finalReferences
      })

      newMessages[streamingMessageIndex.value] = {
        ...currentMessage,
        intent: finalIntent,
        references: finalReferences
      }
      messages.value = newMessages
      streamingMessageIndex.value = -1
      saveMessagesToStorage()
    }
  }

  // 中止流式消息（出错时）
  const abortStreamMessage = () => {
    if (streamingMessageIndex.value >= 0 && streamingMessageIndex.value < messages.value.length) {
      // 创建新数组以确保响应式更新
      const newMessages = [...messages.value]

      // 如果内容为空，移除该消息
      if (newMessages[streamingMessageIndex.value].content === '') {
        newMessages.splice(streamingMessageIndex.value, 1)
        messages.value = newMessages
      } else {
        // 否则保留已接收内容，但标记为一般意图
        newMessages[streamingMessageIndex.value] = {
          ...newMessages[streamingMessageIndex.value],
          intent: 'GENERAL',
          references: []
        }
        messages.value = newMessages
      }
      streamingMessageIndex.value = -1
      saveMessagesToStorage()
    }
  }

  // 清空当前会话
  const clearMessages = () => {
    messages.value = []
    saveMessagesToStorage()
  }

  // 设置加载状态
  const setLoading = (isLoading) => {
    loading.value = isLoading
  }

  // 设置输入消息
  const setInputMessage = (msg) => {
    inputMessage.value = msg
  }

  // 获取消息列表（只读）
  const messageList = computed(() => messages.value)

  // 获取加载状态
  const isLoading = computed(() => loading.value)

  // 获取输入消息
  const currentInputMessage = computed(() => inputMessage.value)

  // 获取当前流式消息索引（调试用）
  const currentStreamingMessageIndex = computed(() => streamingMessageIndex.value)

  return {
    messages: messageList,
    loading: isLoading,
    inputMessage: currentInputMessage,
    streamingMessageIndex: currentStreamingMessageIndex,
    currentSessionId,
    sessionList,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
    initWelcomeMessage,
    addUserMessage,
    addAiMessage,
    addErrorMessage,
    startStreamAiMessage,
    appendStreamContent,
    completeStreamMessage,
    abortStreamMessage,
    addThinkingStep,
    completeThinkingStep,
    truncateStreamContent,
    clearMessages,
    setLoading,
    setInputMessage,
    getCurrentTime,
    saveMessagesToStorage
  }
})