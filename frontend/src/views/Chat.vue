<template>
  <div class="chat-page">
    <!-- 会话侧边栏 -->
    <aside class="session-sidebar">
      <div class="session-sidebar-header">
        <span>对话</span>
        <el-button size="small" text @click="handleNewSession" title="新建会话">
          <el-icon><Plus /></el-icon>
        </el-button>
      </div>
      <div class="session-sidebar-list">
        <div
          v-for="s in sessionList"
          :key="s.id"
          :class="['session-sidebar-item', { active: chatStore.currentSessionId === s.id }]"
          @click="handleSessionClick(s.id)"
        >
          <span class="session-sidebar-title" :title="s.title">{{ s.title }}</span>
          <el-dropdown trigger="click" @command="(cmd) => handleSessionCmd(cmd, s)">
            <el-icon class="session-more-icon"><MoreFilled /></el-icon>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </aside>

    <!-- 网络断开提示 -->
    <div v-if="!online" class="connection-banner">
      <span>⚠ 网络连接已断开</span>
      <button class="reconnect-btn" @click="retryConnection">重试连接</button>
    </div>

    <div class="chat-container">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="messagesContainer">
        <!-- 历史消息加载提示 -->
        <div v-if="visibleStart > 0" class="load-more-bar">
          <el-button size="small" text @click="loadMoreMessages" :loading="loadingMore">
            查看更早的消息（已隐藏 {{ visibleStart }} 条）
          </el-button>
        </div>
        <div
          v-for="(message, index) in visibleMessages"
          :key="messages.indexOf(message)"
          :class="['message-row', message.role === 'user' ? 'row-user' : 'row-ai']"
        >
          <div v-if="message.role === 'assistant'" class="avatar avatar-ai">✦</div>
          <div
            :class="['message-bubble', message.role === 'user' ? 'bubble-user' : 'bubble-ai']"
          >
            <!-- 用户消息 -->
            <template v-if="message.role === 'user'">
              <div class="message-content">{{ message.content }}</div>
            </template>

            <!-- AI 消息 -->
            <template v-else>
              <!-- 思考过程卡片 -->
              <div v-if="message.thinkingSteps && message.thinkingSteps.length > 0" class="thinking-steps">
                <!-- 运行中的步骤：始终展开 -->
                <div
                  v-for="step in message.thinkingSteps.filter(s => s.status === 'running')"
                  :key="step.tool"
                  class="thinking-step running"
                >
                  <div class="thinking-step-header">
                    <span class="thinking-dot running"></span>
                    <span class="thinking-label">{{ step.label }}</span>
                  </div>
                </div>
                <!-- 已完成的步骤：折叠为一行摘要，点击展开/收起 -->
                <div
                  v-if="doneCount(message) > 0"
                  :class="['thinking-step', 'done', { collapsed: collapsedSteps[index] }]"
                >
                  <div class="thinking-step-header" @click="toggleStep(index)">
                    <span class="thinking-dot done">✓</span>
                    <span class="thinking-label">
                      {{ collapsedSteps[index] ? `已完成 ${doneCount(message)} 个步骤` : '' }}
                    </span>
                    <span class="thinking-arrow">{{ collapsedSteps[index] ? '▸' : '▾' }}</span>
                  </div>
                  <div v-if="!collapsedSteps[index]" class="thinking-step-detail">
                    <div
                      v-for="step in message.thinkingSteps.filter(s => s.status === 'done')"
                      :key="step.tool"
                      class="thinking-detail-item"
                    >
                      <span class="thinking-done-icon">✓</span>
                      {{ step.label }}
                    </div>
                  </div>
                </div>
              </div>

              <div class="message-content ai-content" v-html="renderMarkdown(message.content)"></div>

            <!-- 意图标签 -->
            <div v-if="message.intent" class="intent-tag">
              {{ getIntentDescription(message.intent) }}
            </div>

            <!-- 引用来源 -->
            <div v-if="message.references && message.references.length > 0" class="references">
              <div class="references-title">引用来源:</div>
              <ul class="references-list">
                <li v-for="(ref, refIndex) in message.references" :key="refIndex">{{ ref }}</li>
              </ul>
            </div>

            <!-- 操作按钮 -->
            <div class="message-actions">
              <el-tooltip content="复制" placement="top">
                <el-button size="small" circle @click="copyContent(message.content)">
                  <el-icon><DocumentCopy /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </template>

          <div class="message-time">{{ message.time }}</div>
          </div>
          <div v-if="message.role === 'user'" class="avatar avatar-user">{{ userStore.displayName?.charAt(0)?.toUpperCase() }}</div>
        </div>
        <!-- 空状态 -->
      <div v-if="!loading && messages.length === 0 && !welcomeShown" class="empty-chat">
        <div class="empty-chat-icon">💬</div>
        <div class="empty-chat-text">开始新的对话</div>
        <div class="empty-chat-hint">输入消息或点击下方快捷操作</div>
      </div>

      <div v-if="loading" class="loading-indicator">
          <el-icon class="is-loading"><Loading /></el-icon>
          {{ thinkingText }}
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="3"
          placeholder="请输入问题（如：知识库查询、查看我的备忘录、整理信息并发送邮件）"
          @keyup.enter.exact.prevent="sendMessage"
        />
        <el-button
          type="primary"
          :loading="loading"
          @click="sendMessage"
          class="send-btn"
        >
          发送
        </el-button>
      </div>

      <!-- 快速操作 -->
      <div class="quick-actions">
        <span class="quick-label">快捷操作:</span>
        <el-button-group>
          <el-button size="small" @click="quickAction('查看我的备忘录')">查看备忘录</el-button>
          <el-button size="small" @click="quickAction('知识库里有什么')">知识库查询</el-button>
          <el-button size="small" @click="clearChat">清空对话</el-button>
        </el-button-group>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed, reactive } from 'vue'
import { chatApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, DocumentCopy, Plus, MoreFilled } from '@element-plus/icons-vue'
import { useChatStore } from '../store/chat'
import { useUserStore } from '../store/user'
import { listSessions, setSessionTitle, clearSession } from '../api/toolManagement'
import router from '../router'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css'

// 配置 marked 使用 highlight.js
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (_) { /* fallthrough */ }
    }
    return hljs.highlightAuto(code).value
  }
})

const chatStore = useChatStore()
const userStore = useUserStore()
const messagesContainer = ref(null)
const thinkingText = ref('正在思考...')
const collapsedSteps = reactive({})

// 网络状态监控
const online = ref(navigator.onLine)
const handleOnline = () => { online.value = true }
const handleOffline = () => { online.value = false }
const retryConnection = () => { online.value = navigator.onLine; if (online.value) ElMessage.success('网络已恢复') }

// 虚拟滚动：控制可见消息数量
const VISIBLE_BATCH = 50
const visibleStart = ref(0)
const loadingMore = ref(false)
const welcomeShown = ref(true)

const loadMoreMessages = () => {
  loadingMore.value = true
  setTimeout(() => {
    visibleStart.value = Math.max(0, visibleStart.value - VISIBLE_BATCH)
    loadingMore.value = false
  }, 200)
}

// 会话管理
const sessionList = computed(() => chatStore.sessionList)
const handleNewSession = () => chatStore.createSession()
const handleSessionClick = (id) => chatStore.switchSession(id)
const handleSessionCmd = async (cmd, session) => {
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm('删除会话将清除所有对话记录，不可恢复。', '确认删除', { type: 'warning' })
      chatStore.deleteSession(session.id)
      clearSession(session.id).catch(e => console.warn('Redis 会话清理失败:', e))
    } catch { /* cancelled */ }
  } else if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('请输入新名称', '重命名', {
        inputValue: session.title,
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空'
      })
      if (value) {
        chatStore.renameSession(session.id, value)
        setSessionTitle(session.id, value).catch(() => {})  // 同步到服务端
      }
    } catch { /* cancelled */ }
  }
}

// 从服务端恢复会话列表（防止 localStorage 清缓存丢失）
async function restoreFromServer() {
  try {
    const res = await listSessions({})
    if (res.code === 0 && res.data?.length > 0) {
      for (const s of res.data) {
        const existing = chatStore.sessionList.find(l => l.id === s.session_id)
        if (!existing) {
          chatStore.sessionList.push({
            id: s.session_id,
            title: s.title || '新会话',
            time: s.created_at || new Date().toISOString(),
            messageCount: s.message_count || 0,
          })
        } else if (s.title && existing.title === '新会话') {
          existing.title = s.title  // 用服务端标题覆盖默认标题
        }
      }
      // 持久化
      localStorage.setItem('chat_sessions', JSON.stringify(chatStore.sessionList))
    }
  } catch { /* 服务端不可用时使用本地数据 */ }
}

const toggleStep = (msgIdx) => {
  collapsedSteps[msgIdx] = !collapsedSteps[msgIdx]
}

const doneCount = (msg) => {
  return (msg.thinkingSteps || []).filter(s => s.status === 'done').length
}

// 工具名称中文映射
const toolNameMap = {
  'add_memo': '创建备忘录',
  'list_memos': '查询备忘录',
  'update_memo': '更新备忘录',
  'delete_memo': '删除备忘录',
  'complete_memo': '完成备忘录',
  'list_memos_by_date': '按日期查询备忘录',
  'search_knowledge': '检索知识库',
  'upload_knowledge': '上传文档到知识库',
  'get_document_content': '获取文档内容',
  'list_knowledge': '列出知识库文件',
  'delete_knowledge': '删除知识库文档',
  'preview_email': '生成邮件预览',
  'do_send_email': '发送邮件',
  'do_send_formatted_email': '发送格式化邮件',
  'get_current_date': '获取当前日期',
  'get_date_after_days': '计算日期',
  'get_current_datetime': '获取当前时间',
  'parse_date_range': '解析日期范围',
  'get_current_user_email': '获取用户邮箱',
}

const messages = computed(() => chatStore.messages)
// 虚拟滚动可见窗口
const visibleMessages = computed(() => {
  const all = messages.value
  if (all.length <= VISIBLE_BATCH || visibleStart.value === 0) return all
  return all.slice(-Math.min(all.length, VISIBLE_BATCH))
})
const hasHiddenMessages = computed(() => messages.value.length > VISIBLE_BATCH && visibleStart.value > 0)
const loading = computed(() => chatStore.loading)
const inputMessage = computed({
  get: () => chatStore.inputMessage,
  set: (value) => chatStore.setInputMessage(value)
})

// Markdown 渲染（带代码高亮和链接新窗口打开）
const renderMarkdown = (content) => {
  if (!content) return ''
  const html = marked.parse(content)
  // 链接在新窗口打开
  return html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ')
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 复制内容
const copyContent = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 认证错误处理
const handleAuthError = (error) => {
  if (error && (error.isAuthError || (error.message && error.message.includes('401')))) {
    ElMessage.error('登录已过期，请重新登录')
    userStore.logout()
    router.push('/login')
    return true
  }
  return false
}

const sendMessage = async () => {
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }

  const message = inputMessage.value.trim()
  if (!message) {
    ElMessage.warning('请输入消息')
    return
  }

  chatStore.addUserMessage(message)
  chatStore.setInputMessage('')
  scrollToBottom()

  chatStore.startStreamAiMessage()
  chatStore.setLoading(true)
  thinkingText.value = '正在思考...'
  scrollToBottom()

  try {
    const sid = chatStore.currentSessionId

    await chatApi.sendMessageStream(
      message,
      sid,
      // 流式块回调
      (chunk) => {
        thinkingText.value = '正在输出...'
        chatStore.appendStreamContent(chunk)
        scrollToBottom()
      },
      // 完成回调
      () => {
        chatStore.completeStreamMessage('', [])
        chatStore.setLoading(false)
        scrollToBottom()
      },
      // 错误回调
      (error) => {
        console.error('流式请求错误:', error)
        chatStore.abortStreamMessage()
        chatStore.setLoading(false)
        thinkingText.value = '正在思考...'
        if (!handleAuthError(error)) {
          ElMessage.error('发送消息失败: ' + error.message)
        }
        scrollToBottom()
      },
      // 思考过程回调
      (thinking) => {
        if (thinking.status === 'start') {
          const name = toolNameMap[thinking.tool] || thinking.tool
          chatStore.addThinkingStep(thinking.tool, name)
          thinkingText.value = `正在执行：${name}...`
        } else if (thinking.status === 'done') {
          chatStore.completeThinkingStep()
          thinkingText.value = '正在思考...'
        }
      },
      // 回退推理文字回调
      (n) => {
        chatStore.truncateStreamContent(n)
      }
    )
  } catch (error) {
    console.error('发送消息失败:', error)
    chatStore.abortStreamMessage()
    chatStore.setLoading(false)
    if (!handleAuthError(error)) {
      ElMessage.error('发送消息失败: ' + error.message)
    }
    scrollToBottom()
  }
}

const quickAction = (action) => {
  inputMessage.value = action
  sendMessage()
}

const getIntentDescription = (intent) => {
  const map = { MEMO: '备忘录', KNOWLEDGE: '知识库', GENERAL: '一般聊天', WORKFLOW: '工作流' }
  return map[intent] || intent
}

const clearChat = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要清空对话历史吗？此操作将清除当前所有聊天记录，不可恢复。',
      '清空确认',
      { confirmButtonText: '确定清空', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' }
    )
    chatStore.clearMessages()
    chatStore.initWelcomeMessage()
    ElMessage.success('对话已清空')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.success('已取消')
    }
  }
}

onMounted(async () => {
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)

  // 只在 localStorage 无数据时才从服务端恢复
  if (chatStore.sessionList.length === 0) {
    await restoreFromServer()
  }
  if (!chatStore.currentSessionId || chatStore.sessionList.length === 0) {
    chatStore.createSession()
  }
  if (chatStore.messages.length === 0) {
    chatStore.initWelcomeMessage()
  }
  welcomeShown.value = false
  scrollToBottom()
})
</script>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
}

/* 会话侧边栏 */
.session-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  transition: background var(--transition);
}

.session-sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 14px 10px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}

.session-sidebar-header .el-button {
  color: #909399;
  padding: 4px;
}

.session-sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
}

.session-sidebar-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text-regular);
  font-size: 13px;
  margin-bottom: 2px;
}

.session-sidebar-item:hover { background: var(--border-light); }
.session-sidebar-item.active { background: rgba(64,158,255,0.1); color: var(--text-primary); font-weight: 500; }
html.dark .session-sidebar-item:hover { background: var(--bg-sidebar-hover); }
html.dark .session-sidebar-item.active { background: rgba(64,158,255,0.15); }

.session-sidebar-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-more-icon {
  flex-shrink: 0;
  opacity: 0;
  font-size: 14px;
  color: #909399;
}
.session-sidebar-item:hover .session-more-icon { opacity: 0.7; }

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ─── 消息列表 ─── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 16px;
  padding: 24px;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  transition: background var(--transition);
}

.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  align-items: flex-start;
  content-visibility: auto;
  contain-intrinsic-size: auto 80px;
}

/* 黑暗模式额外覆盖 */
html.dark .session-sidebar { background: var(--bg-sidebar); }
html.dark .bubble-ai { background: var(--bg-chat-ai); border-color: var(--border); }
html.dark .session-sidebar-item:hover { background: var(--bg-sidebar-hover); }
html.dark .session-sidebar-item.active { background: var(--bg-sidebar-hover); }
html.dark .thinking-step { background: rgba(64,158,255,0.08); border-color: rgba(64,158,255,0.15); }
html.dark .thinking-step.done { background: rgba(255,255,255,0.03); border-color: var(--border); }

.row-user { justify-content: flex-end; }
.row-ai { justify-content: flex-start; }

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}

.avatar-ai {
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
}

.avatar-user {
  background: linear-gradient(135deg, #67c23a, #529b2e);
  color: #fff;
}

.message-bubble {
  max-width: 72%;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  position: relative;
  line-height: 1.6;
  word-break: break-word;
}

.bubble-user {
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  color: #fff;
}

.bubble-ai {
  background: #fff;
  color: var(--text-primary);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-sm);
}

.message-content {
  line-height: 1.6;
  white-space: pre-wrap;
}

/* Markdown 渲染样式 */
.ai-content :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  margin: 8px 0;
}

.ai-content :deep(code) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
}

.ai-content :deep(p code) {
  background: #e8e8e8;
  padding: 2px 6px;
  border-radius: 3px;
  color: #d63384;
}

.ai-content :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.ai-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}

.ai-content :deep(th), .ai-content :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
}

.ai-content :deep(th) {
  background: #ebeef5;
  font-weight: bold;
}

.ai-content :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.ai-content :deep(a:hover) {
  text-decoration: underline;
}

.ai-content :deep(blockquote) {
  border-left: 3px solid #409eff;
  margin: 8px 0;
  padding: 4px 12px;
  color: #606266;
  background: #f8f9fa;
  border-radius: 0 4px 4px 0;
}

.ai-content :deep(ul), .ai-content :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.ai-content :deep(h1), .ai-content :deep(h2), .ai-content :deep(h3), .ai-content :deep(h4) {
  margin: 12px 0 6px;
  color: #303133;
}

.ai-content :deep(h1) { font-size: 18px; }
.ai-content :deep(h2) { font-size: 16px; }
.ai-content :deep(h3) { font-size: 15px; }

/* ─── 思考过程卡片 ─── */
.thinking-steps {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.thinking-step {
  background: #f0f6ff;
  border: 1px solid #c6ddf7;
  border-radius: 6px;
  overflow: hidden;
  font-size: 13px;
  transition: all 0.2s;
}

.thinking-step.done {
  background: #f6f8fa;
  border-color: #dfe3e8;
}

.thinking-step.done.collapsed {
  background: #f8f9fa;
  border-color: #e8eaed;
}

.thinking-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  user-select: none;
}

.thinking-step.done .thinking-step-header {
  cursor: pointer;
}

.thinking-step.done .thinking-step-header:hover {
  background: #e8f0fe;
}

.thinking-step.running .thinking-step-header {
  cursor: default;
}

.thinking-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  flex-shrink: 0;
}

.thinking-dot.running {
  background: #409eff;
  animation: pulse 1.5s ease-in-out infinite;
}

.thinking-dot.done {
  background: #67c23a;
  color: #fff;
}

.thinking-label {
  flex: 1;
  color: #303133;
}

.thinking-step.done .thinking-label {
  color: #909399;
  font-size: 12px;
}

.thinking-arrow {
  font-size: 10px;
  color: #909399;
  flex-shrink: 0;
}

/* 已完成步骤的展开详情 */
.thinking-step-detail {
  border-top: 1px solid #e8eaed;
  padding: 6px 0;
}

.thinking-detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 10px;
  font-size: 12px;
  color: #909399;
}

.thinking-done-icon {
  color: #67c23a;
  font-size: 10px;
  flex-shrink: 0;
  width: 16px;
  text-align: center;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ─── 消息元数据 ─── */
.intent-tag {
  display: inline-block;
  background: #e6f7ff;
  color: #1890ff;
  padding: 2px 8px;
  border-radius: 10px;
  margin-top: 8px;
  font-size: 12px;
  border: 1px solid #91d5ff;
}

.references {
  margin-top: 8px;
  border-top: 1px dashed #e8e8e8;
  padding-top: 8px;
  font-size: 12px;
}

.references-title {
  font-weight: bold;
  margin-bottom: 4px;
  color: #666;
}

.references-list {
  margin: 0;
  padding-left: 20px;
  color: #888;
}

.references-list li {
  margin-bottom: 2px;
  line-height: 1.4;
}

/* ─── 消息操作按钮 ─── */
.message-actions {
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.15s;
}

.row-ai:hover .message-actions {
  opacity: 1;
}

.message-actions .el-button {
  width: 28px;
  height: 28px;
}

.message-time {
  font-size: 12px;
  opacity: 0.6;
  margin-top: 4px;
  text-align: right;
}

/* ─── 空状态 ─── */
.empty-chat {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 60px 20px; color: var(--text-secondary);
}
.empty-chat-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.5; }
.empty-chat-text { font-size: 16px; font-weight: 500; color: var(--text-regular); margin-bottom: 8px; }
.empty-chat-hint { font-size: 13px; }

/* ─── 加载更多 ─── */
.load-more-bar { text-align: center; padding: 8px; }

/* ─── 加载状态 ─── */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  padding: 10px 16px;
  font-size: 14px;
}

/* ─── 输入区域 ─── */
.chat-input-area {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.chat-input-area .el-textarea {
  flex: 1;
}

.send-btn {
  height: auto;
  align-self: flex-end;
}

html.dark .chat-input-area .el-textarea__inner {
  background: var(--bg-input) !important;
  color: var(--text-primary) !important;
}

/* ─── 快捷操作 ─── */
.quick-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.quick-label {
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}

/* ─── 响应式 ─── */
@media (max-width: 768px) {
  .chat-messages { padding: 12px; }
  .message-bubble { max-width: 90%; }
  .message-row { gap: 6px; }
  .chat-input-area { flex-direction: column; }
  .chat-input-area .el-textarea { width: 100%; }
  .send-btn { width: 100%; height: 40px; }
  .quick-actions { flex-wrap: wrap; }
  .quick-actions .el-button-group { flex-wrap: wrap; justify-content: center; }
  .quick-actions .el-button { font-size: 12px; padding: 6px 10px; }
}
</style>
