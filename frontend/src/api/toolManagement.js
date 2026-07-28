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
