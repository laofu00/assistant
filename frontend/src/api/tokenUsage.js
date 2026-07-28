import api from './index'

/**
 * Token使用记录API
 * 参数名对齐 Python 后端（user_id, page, size）
 */

export function getTokenUsageRecords(userId, startTime, endTime, page = 1, size = 20) {
  return api.get('/token/records', {
    params: {
      user_id: userId,
      start_time: startTime,
      end_time: endTime,
      page,
      size
    }
  })
}

export function getTokenUsageStatistics(userId, startTime, endTime) {
  return api.get('/token/statistics', {
    params: { user_id: userId, start_time: startTime, end_time: endTime }
  })
}

export function getTokenUsageByModel(userId, startTime, endTime) {
  return api.get('/token/by-model', {
    params: { user_id: userId, start_time: startTime, end_time: endTime }
  })
}

export function getTokenUsageByDate(userId, startTime, endTime) {
  return api.get('/token/by-date', {
    params: { user_id: userId, start_time: startTime, end_time: endTime }
  })
}
