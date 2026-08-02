<template>
  <div class="memory-page">
    <h2>记忆管理</h2>

    <!-- 统计概览 -->
    <div class="stats-row">
      <el-card class="stat-card">
        <div class="stat-label">活跃会话</div>
        <div class="stat-value">{{ sessions.length }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">长期事实</div>
        <div class="stat-value">{{ ltFacts.length }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">用户偏好</div>
        <div class="stat-value">{{ prefsCount }}</div>
      </el-card>
    </div>

    <!-- 标签切换 -->
    <el-tabs v-model="activeTab" class="memory-tabs">
      <el-tab-pane label="会话记忆" name="session">
        <div class="split-layout">
          <!-- 左侧：会话列表 -->
          <div class="session-panel">
            <div class="panel-header">
              <span>会话列表</span>
              <el-button size="small" @click="refreshSessions" :loading="loading">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
            <div class="session-list" v-loading="loading">
              <div
                v-for="s in sessions"
                :key="s.session_id"
                :class="['session-item', { active: selectedId === s.session_id }]"
                @click="selectSession(s)"
              >
                <div class="session-id">{{ s.title || s.session_id }}</div>
                <div class="session-meta">
                  <el-tag v-if="s.user_id" size="small" type="warning">{{ s.user_id }}</el-tag>
                  <span>{{ s.message_count }} 条消息</span>
                  <el-tag v-if="s.ttl_seconds > 0" size="small" type="info">{{ formatTTL(s.ttl_seconds) }}</el-tag>
                </div>
                <div class="session-preview">{{ s.first_message }}</div>
              </div>
              <el-empty v-if="!loading && sessions.length === 0" description="暂无活跃会话" />
            </div>
          </div>

          <!-- 右侧：详情 -->
          <div class="detail-panel">
            <template v-if="selectedId">
              <div class="panel-header">
                <span>会话详情 — {{ selectedId }}</span>
                <el-button type="danger" size="small" @click="handleClear" :loading="clearing">
                  <el-icon><Delete /></el-icon> 清除记忆
                </el-button>
              </div>
              <div class="section">
                <div class="section-title"><el-icon><DataAnalysis /></el-icon> 结构化事实摘要（{{ currentFacts.length }} 条）</div>
                <div v-if="currentFacts.length === 0" class="empty-hint">暂无摘要，消息量较少时直接保留原文</div>
                <div v-for="(f, i) in currentFacts" :key="i" :class="['fact-item', f.importance]">
                  <span class="fact-marker">{{ importanceIcon(f.importance) }}</span>
                  <span class="fact-action">[{{ f.action }}]</span>
                  <span class="fact-entity">{{ f.entity }}</span>
                  <span v-if="f.detail" class="fact-detail">— {{ f.detail }}</span>
                  <el-tag :type="importanceTag(f.importance)" size="small" class="fact-tag">{{ f.importance }}</el-tag>
                </div>
              </div>
              <div class="section">
                <div class="section-title"><el-icon><ChatLineRound /></el-icon> 消息记录（{{ currentMessages.length }} 条）</div>
                <div v-if="currentMessages.length === 0" class="empty-hint">暂无消息记录</div>
                <div v-for="(m, i) in currentMessages" :key="i" :class="['message-item', m.role === '用户' ? 'user' : 'assistant']">
                  <span class="msg-role">{{ m.role === '用户' ? '👤' : '🤖' }}</span>
                  <span class="msg-content">{{ truncate(m.content, 300) }}</span>
                </div>
              </div>
            </template>
            <el-empty v-else description="选择左侧会话查看详情" />
          </div>
        </div>
      </el-tab-pane>

      <!-- 长期记忆 -->
      <el-tab-pane label="长期记忆" name="longterm">
        <div class="ltm-layout" v-loading="ltLoading">
          <!-- 用户画像 -->
          <div class="ltm-panel">
            <div class="panel-header">
              <span>用户画像</span>
              <el-button size="small" @click="refreshLongTerm">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
            <div class="profile-section" v-if="profile && (profile.preferences || profile.key_facts)">
              <div v-if="profile.preferences && Object.keys(profile.preferences).length" class="pref-group">
                <div class="ltm-section-title">偏好设置</div>
                <el-tag v-for="(v, k) in profile.preferences" :key="k" class="pref-tag" type="success">
                  {{ k }}: {{ v }}
                </el-tag>
              </div>
              <div v-if="profile.key_facts && Object.keys(profile.key_facts).length" class="pref-group">
                <div class="ltm-section-title">关键事实</div>
                <div v-for="(v, k) in profile.key_facts" :key="k" class="key-fact">
                  <span class="key-label">{{ k }}</span>: {{ v }}
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无用户画像" :image-size="60" />
          </div>

          <!-- 事实列表 -->
          <div class="ltm-panel ltm-facts">
            <div class="panel-header">
              <span>长期事实（{{ ltFacts.length }} 条）</span>
            </div>
            <div class="ltm-fact-list">
              <div v-for="(f, i) in ltFacts" :key="i" :class="['ltm-fact-item', f.importance]">
                <span class="fact-marker">{{ importanceIcon2(f.importance) }}</span>
                <div class="ltm-fact-body">
                  <div class="ltm-fact-text">{{ f.fact }}</div>
                  <div class="ltm-fact-meta">
                    <el-tag :type="importanceTag2(f.importance)" size="small">{{ f.importance }}</el-tag>
                    <el-tag size="small" type="info">{{ f.type }}</el-tag>
                    <span class="ltm-source">{{ f.session_id?.substring(0, 16) }}...</span>
                  </div>
                </div>
                <el-button type="danger" link size="small" @click="handleDeleteFact(f.fact)">删除</el-button>
              </div>
              <el-empty v-if="ltFacts.length === 0" description="暂无长期记忆" :image-size="60" />
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Delete, DataAnalysis, ChatLineRound } from '@element-plus/icons-vue'
import {
  listSessions, getSessionDetail, clearSession,
  getLongTermMemory, deleteLongTermFact,
} from '../api/toolManagement'

const activeTab = ref('session')
const sessions = ref([])
const loading = ref(false)
const clearing = ref(false)
const selectedId = ref('')
const selectedUserId = ref('')
const currentMessages = ref([])
const currentFacts = ref([])

// 长期记忆
const ltFacts = ref([])
const profile = ref(null)
const ltLoading = ref(false)

const prefsCount = computed(() => {
  if (!profile.value?.preferences) return 0
  return Object.keys(profile.value.preferences).length
})

function importanceIcon(imp) { return imp === 'critical' ? '★' : imp === 'important' ? '●' : '·' }
function importanceIcon2(imp) { return imp === 'high' ? '★' : imp === 'medium' ? '●' : '·' }
function importanceTag(imp) { return imp === 'critical' ? 'danger' : imp === 'important' ? 'warning' : 'info' }
function importanceTag2(imp) { return imp === 'high' ? 'danger' : imp === 'medium' ? 'warning' : 'info' }
function truncate(text, max) { if (!text) return ''; return text.length > max ? text.substring(0, max) + '...' : text }
function formatTTL(seconds) {
  if (seconds <= 0) return '已过期'
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}时${m}分` : `${m}分钟`
}

async function refreshSessions() {
  loading.value = true
  try {
    const res = await listSessions({})
    if (res.code === 0) sessions.value = res.data || []
  } catch { ElMessage.error('加载会话列表失败') } finally { loading.value = false }
}

async function selectSession(session) {
  selectedId.value = session.session_id
  selectedUserId.value = session.user_id || ''
  try {
    const res = await getSessionDetail(session.session_id, session.user_id)
    if (res.code === 0) {
      currentMessages.value = res.data.messages || []
      currentFacts.value = res.data.summary_facts || []
    }
  } catch { currentMessages.value = []; currentFacts.value = [] }
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清除该会话记忆？', '确认', { type: 'warning' })
    clearing.value = true
    await clearSession(selectedId.value, selectedUserId.value)
    ElMessage.success('会话记忆已清除')
    selectedId.value = ''; selectedUserId.value = ''; currentMessages.value = []; currentFacts.value = []
    await refreshSessions()
  } catch (e) { if (e !== 'cancel') ElMessage.error('操作失败') } finally { clearing.value = false }
}

async function refreshLongTerm() {
  ltLoading.value = true
  try {
    const res = await getLongTermMemory()
    if (res.code === 0) {
      ltFacts.value = res.data.facts || []
      profile.value = res.data.profile || {}
    }
  } catch { ElMessage.error('加载长期记忆失败') } finally { ltLoading.value = false }
}

async function handleDeleteFact(factText) {
  try {
    await ElMessageBox.confirm('确定删除该条长期记忆？', '确认', { type: 'warning' })
    await deleteLongTermFact(factText)
    ElMessage.success('已删除')
    await refreshLongTerm()
  } catch (e) { if (e !== 'cancel') ElMessage.error('操作失败') }
}

onMounted(() => { refreshSessions(); refreshLongTerm() })
</script>

<style scoped>
.memory-page { padding: 20px; max-width: 1400px; margin: 0 auto; height: 100%; display: flex; flex-direction: column; }
.memory-page h2 { margin-bottom: 20px; font-size: 20px; color: var(--text-primary); flex-shrink: 0; }

.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px; flex-shrink: 0; }
.stat-card { text-align: center; }
.stat-label { font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }
.stat-value { font-size: 26px; font-weight: 600; color: var(--primary); }

.memory-tabs { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
.memory-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }
.memory-tabs :deep(.el-tabs__active-bar) { display: none; }
.memory-tabs :deep(.el-tabs__content) { flex: 1; overflow: hidden; }
.memory-tabs :deep(.el-tab-pane) { height: 100%; }

.split-layout { display: grid; grid-template-columns: 360px 1fr; gap: 16px; height: 100%; }

.session-panel, .detail-panel {
  background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden; transition: background var(--transition);
}
.panel-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; flex-shrink: 0; color: var(--text-primary); }
.session-list { flex: 1; overflow-y: auto; padding: 8px; }
.session-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; transition: background 0.2s; }
.session-item:hover { background: var(--bg-page); }
.session-item.active { background: rgba(64,158,255,0.08); border-left: 3px solid var(--primary); }
.session-id { font-family: monospace; font-size: 13px; color: var(--text-primary); margin-bottom: 4px; }
.session-meta { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.session-preview { font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.detail-panel { overflow-y: auto; }

.section { padding: 16px; }
.section-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; display: flex; align-items: center; gap: 6px; }
.empty-hint { color: var(--text-secondary); font-size: 13px; text-align: center; padding: 20px; }

.fact-item { display: flex; align-items: center; gap: 6px; padding: 8px 12px; margin-bottom: 6px; background: var(--bg-page); border-radius: 6px; font-size: 13px; flex-wrap: wrap; }
.fact-item.critical { background: rgba(245,108,108,0.08); border-left: 3px solid var(--danger); }
.fact-item.important { background: rgba(230,162,60,0.08); border-left: 3px solid var(--warning); }
.fact-marker { font-size: 14px; }
.fact-action { color: var(--primary); font-weight: 600; }
.fact-entity { color: var(--text-primary); }
.fact-detail { color: var(--text-regular); }
.fact-tag { margin-left: auto; }

.message-item { display: flex; gap: 10px; padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; font-size: 13px; line-height: 1.6; }
.message-item.user { background: rgba(103,194,58,0.06); }
.message-item.assistant { background: var(--bg-page); }
.msg-role { flex-shrink: 0; font-size: 16px; }
.msg-content { color: var(--text-regular); word-break: break-all; }

/* 长期记忆 */
.ltm-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; height: 100%; }
.ltm-panel { background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; transition: background var(--transition); }
.ltm-facts { overflow: hidden; }
.ltm-fact-list { flex: 1; overflow-y: auto; padding: 12px; }
.ltm-section-title { font-size: 13px; font-weight: 600; color: var(--text-regular); margin-bottom: 8px; }
.profile-section { padding: 16px; overflow-y: auto; }
.pref-group { margin-bottom: 16px; }
.pref-tag { margin-right: 6px; margin-bottom: 6px; }
.key-fact { padding: 6px 0; font-size: 13px; color: var(--text-regular); border-bottom: 1px solid var(--border); }
.key-label { color: var(--primary); font-weight: 600; }

.ltm-fact-item { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; margin-bottom: 6px; border-radius: 6px; font-size: 13px; }
.ltm-fact-item.high { background: rgba(245,108,108,0.08); border-left: 3px solid var(--danger); }
.ltm-fact-item.medium { background: rgba(230,162,60,0.08); border-left: 3px solid var(--warning); }
.ltm-fact-item.low { background: var(--bg-page); }
.ltm-fact-body { flex: 1; }
.ltm-fact-text { color: var(--text-primary); margin-bottom: 4px; line-height: 1.5; }
.ltm-fact-meta { display: flex; align-items: center; gap: 6px; }
.ltm-source { font-size: 11px; color: var(--text-secondary); font-family: monospace; }

@media (max-width: 768px) {
  .split-layout, .ltm-layout { grid-template-columns: 1fr; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
