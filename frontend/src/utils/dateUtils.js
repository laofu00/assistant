/**
 * 日期格式化工具函数
 */

/**
 * 格式化日期为 YYYY-mm-dd HH:mm:ss 格式
 * @param {Date|string} date - 日期对象或日期字符串
 * @returns {string} 格式化后的日期字符串
 */
export const formatDateTime = (date) => {
  if (!date) return ''

  const d = new Date(date)
  if (isNaN(d.getTime())) return ''

  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hours = String(d.getHours()).padStart(2, '0')
  const minutes = String(d.getMinutes()).padStart(2, '0')
  const seconds = String(d.getSeconds()).padStart(2, '0')

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

/**
 * 格式化日期为 YYYY-mm-dd 格式
 * @param {Date|string} date - 日期对象或日期字符串
 * @returns {string} 格式化后的日期字符串
 */
export const formatDate = (date) => {
  if (!date) return ''

  const d = new Date(date)
  if (isNaN(d.getTime())) return ''

  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

/**
 * 获取某一天的下一个指定星期几的日期
 * @param {Date} from - 起始日期
 * @param {number} dayOfWeek - 星期几 (0=周日, 1=周一, ..., 6=周六)
 * @returns {Date}
 */
const nextDayOfWeek = (from, dayOfWeek) => {
  const d = new Date(from)
  const currentDay = d.getDay()
  const daysUntil = (dayOfWeek - currentDay + 7) % 7
  // 如果是同一天，取下周的
  const offset = daysUntil === 0 ? 7 : daysUntil
  d.setDate(d.getDate() + offset)
  return d
}

const df = (d) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * 将文本中的相对时间词替换为具体日期
 * @param {string} text - 原始文本
 * @returns {string} 替换后的文本
 */
export const convertRelativeDates = (text) => {
  if (!text) return text

  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const replacements = {}

  // 相对日期
  replacements['今天'] = df(today)
  replacements['昨天'] = df(new Date(today.getTime() - 86400000))
  replacements['明天'] = df(new Date(today.getTime() + 86400000))
  replacements['后天'] = df(new Date(today.getTime() + 172800000))
  replacements['前天'] = df(new Date(today.getTime() - 172800000))

  // 星期转换
  const dayMap = { '周日': 0, '星期天': 0, '星期日': 0, '周一': 1, '星期一': 1, '周二': 2, '星期二': 2,
                   '周三': 3, '星期三': 3, '周四': 4, '星期四': 4, '周五': 5, '星期五': 5,
                   '周六': 6, '星期六': 6 }
  for (const [name, dow] of Object.entries(dayMap)) {
    replacements[name] = df(nextDayOfWeek(today, dow))
  }

  // 周
  const currentDay = today.getDay()
  const mon = new Date(today.getTime() - (currentDay === 0 ? 6 : currentDay - 1) * 86400000)
  const sun = new Date(mon.getTime() + 6 * 86400000)
  replacements['本周'] = `本周(${df(mon)}~${df(sun)})`

  const nextMon = new Date(mon.getTime() + 7 * 86400000)
  const nextSun = new Date(sun.getTime() + 7 * 86400000)
  replacements['下周'] = `下周(${df(nextMon)}~${df(nextSun)})`

  const prevMon = new Date(mon.getTime() - 7 * 86400000)
  const prevSun = new Date(sun.getTime() - 7 * 86400000)
  replacements['上周'] = `上周(${df(prevMon)}~${df(prevSun)})`

  // 月
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  replacements['本月'] = `本月(${df(firstDay)}~${df(lastDay)})`

  const nextFirst = new Date(today.getFullYear(), today.getMonth() + 1, 1)
  const nextLast = new Date(today.getFullYear(), today.getMonth() + 2, 0)
  replacements['下月'] = `下月(${df(nextFirst)}~${df(nextLast)})`

  const prevFirst = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const prevLast = new Date(today.getFullYear(), today.getMonth(), 0)
  replacements['上月'] = `上月(${df(prevFirst)}~${df(prevLast)})`

  let result = text
  for (const [key, value] of Object.entries(replacements)) {
    result = result.replaceAll(key, value)
  }
  return result
}
