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

// 修改工具权限
export function setToolPermission(toolName, permission) {
  return api.put(`/tools/${toolName}/permission`, null, { params: { permission } })
}

// 查询审计日志
export function getAuditLogs(params) {
  return api.get('/chat/audit-logs', { params })
}

// 记忆管理
export function listSessions(params) {
  return api.get('/memory/sessions', { params })
}
export function getSessionDetail(sessionId, ownerUserId) {
  const params = ownerUserId ? { owner_user_id: ownerUserId } : {}
  return api.get(`/memory/sessions/${sessionId}`, { params })
}
export function clearSession(sessionId, ownerUserId) {
  const params = ownerUserId ? { owner_user_id: ownerUserId } : {}
  return api.delete(`/memory/sessions/${sessionId}`, { params })
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

// ==================== 用户管理 ====================

// 管理员获取用户列表
export function listUsers(params) {
  return api.get('/admin/users', { params })
}

// 查询某用户被禁用的工具
export function getUserDisabledTools(userId) {
  return api.get(`/tools/users/${userId}/disabled`)
}

// 对某用户禁用工具
export function disableToolForUser(userId, toolName) {
  return api.post(`/tools/users/${userId}/disable`, { tool_name: toolName })
}

// 取消某用户的工具禁用
export function enableToolForUser(userId, toolName) {
  return api.post(`/tools/users/${userId}/enable`, { tool_name: toolName })
}
