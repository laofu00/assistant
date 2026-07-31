import api from './index'

// 列出所有工具
export function listTools(params) {
  return api.get('/tools', { params })
}

// 获取单个工具详情
export function getTool(toolName) {
  return api.get(`/tools/${toolName}`)
}

// 启用工具
export function enableTool(toolName) {
  return api.put(`/tools/${toolName}/enable`)
}

// 禁用工具
export function disableTool(toolName) {
  return api.put(`/tools/${toolName}/disable`)
}

// 查询审计日志
export function getAuditLogs(params) {
  return api.get('/chat/audit-logs', { params })
}

// 记忆管理
export function listSessions(params) {
  return api.get('/memory/sessions', { params })
}
export function getSessionDetail(sessionId) {
  return api.get(`/memory/sessions/${sessionId}`)
}
export function clearSession(sessionId) {
  return api.delete(`/memory/sessions/${sessionId}`)
}
export function getLongTermMemory() {
  return api.get('/memory/long-term')
}
export function deleteLongTermFact(factText) {
  return api.delete('/memory/long-term', { data: { fact_text: factText } })
}
export function getProfile() {
  return api.get('/memory/profile')
}
export function updateProfile(preferences) {
  return api.put('/memory/profile', preferences)
}
export function setSessionTitle(sessionId, title) {
  return api.put(`/memory/sessions/${sessionId}/title`, { title })
}
