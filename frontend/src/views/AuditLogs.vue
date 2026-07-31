<template>
  <div class="audit-logs-page">
    <h2>工具审计日志</h2>

    <!-- 统计概览 -->
    <div class="stats-row">
      <el-card class="stat-card">
        <div class="stat-label">总调用次数</div>
        <div class="stat-value">{{ total }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">成功率</div>
        <div class="stat-value" :style="{ color: successRateColor }">{{ successRate }}%</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">平均耗时</div>
        <div class="stat-value">{{ avgDuration }}ms</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">当前页记录</div>
        <div class="stat-value">{{ filteredLogs.length }}</div>
      </el-card>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filterToolName"
        placeholder="工具名称"
        clearable
        style="width: 180px"
        @clear="search"
        @keyup.enter="search"
      />
      <el-select
        v-model="filterResult"
        placeholder="执行结果"
        clearable
        style="width: 140px"
        @change="search"
      >
        <el-option label="成功" value="SUCCESS" />
        <el-option label="失败" value="FAILED" />
        <el-option label="超时" value="TIMEOUT" />
      </el-select>
      <el-button type="primary" @click="search">
        <el-icon><Search /></el-icon>
        查询
      </el-button>
      <el-button @click="reset">
        <el-icon><Refresh /></el-icon>
        重置
      </el-button>
    </div>

    <!-- 日志表格 -->
    <el-table :data="filteredLogs" stripe v-loading="loading" style="width: 100%; margin-top: 16px">
      <el-table-column prop="tool_name" label="工具名称" width="180" />
      <el-table-column prop="user_id" label="用户" width="100" />
      <el-table-column prop="tool_input" label="输入参数" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="mono-text">{{ truncate(row.tool_input, 80) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="tool_output" label="输出结果" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="mono-text">{{ truncate(row.tool_output, 80) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时" width="80" align="right">
        <template #default="{ row }">
          <span :style="{ color: row.duration_ms > 5000 ? '#f56c6c' : '' }">{{ row.duration_ms }}ms</span>
        </template>
      </el-table-column>
      <el-table-column prop="result" label="结果" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="resultTagType(row.result)" size="small">{{ resultLabel(row.result) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{ row }">
          <span class="time-text">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="详情" width="70" align="center">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="showDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @size-change="search"
        @current-change="search"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="调用详情" width="720px" class="detail-dialog">
      <template v-if="currentLog">
        <el-descriptions :column="2" border size="small" label-width="70px">
          <el-descriptions-item label="Trace ID" :span="2">
            <code>{{ currentLog.trace_id }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="工具名称">{{ currentLog.tool_name }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ currentLog.user_id }}</el-descriptions-item>
          <el-descriptions-item label="结果">
            <el-tag :type="resultTagType(currentLog.result)" size="small">{{ resultLabel(currentLog.result) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="耗时">{{ currentLog.duration_ms }}ms</el-descriptions-item>
          <el-descriptions-item label="时间" :span="2">{{ formatTime(currentLog.created_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="currentLog.error_msg" label="错误信息" :span="2">
            <span style="color: #f56c6c">{{ currentLog.error_msg }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="输入参数" :span="2">
            <pre class="detail-pre">{{ currentLog.tool_input || '(空)' }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="输出结果" :span="2">
            <pre class="detail-pre">{{ currentLog.tool_output || '(空)' }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import { getAuditLogs } from '../api/toolManagement'

const logs = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)

const filterToolName = ref('')
const filterResult = ref('')

const currentLog = ref(null)
const detailVisible = ref(false)

const filteredLogs = computed(() => {
  if (!filterResult.value) return logs.value
  return logs.value.filter(l => l.result === filterResult.value)
})

const successCount = computed(() => filteredLogs.value.filter(l => l.result === 'SUCCESS').length)
const totalCount = computed(() => filteredLogs.value.length)
const successRate = computed(() => {
  if (totalCount.value === 0) return '—'
  return ((successCount.value / totalCount.value) * 100).toFixed(1)
})
const successRateColor = computed(() => {
  const rate = parseFloat(successRate.value)
  if (rate >= 90) return '#67c23a'
  if (rate >= 70) return '#e6a23c'
  return '#f56c6c'
})
const avgDuration = computed(() => {
  if (filteredLogs.value.length === 0) return '—'
  const total = filteredLogs.value.reduce((s, l) => s + (l.duration_ms || 0), 0)
  return Math.round(total / filteredLogs.value.length)
})

function resultTagType(result) {
  return result === 'SUCCESS' ? 'success' : result === 'TIMEOUT' ? 'warning' : 'danger'
}
function resultLabel(result) {
  return result === 'SUCCESS' ? '成功' : result === 'TIMEOUT' ? '超时' : '失败'
}
function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? text.substring(0, max) + '...' : text
}
function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function search() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filterToolName.value) params.tool_name = filterToolName.value
    const res = await getAuditLogs(params)
    if (res.code === 0) {
      const data = res.data || {}
      logs.value = data.records || []
      total.value = data.total || 0
    }
  } catch (e) {
    ElMessage.error('加载审计日志失败')
  } finally {
    loading.value = false
  }
}

function reset() {
  filterToolName.value = ''
  filterResult.value = ''
  page.value = 1
  search()
}

function showDetail(row) {
  currentLog.value = row
  detailVisible.value = true
}

onMounted(search)
</script>

<style scoped>
.audit-logs-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.audit-logs-page h2 {
  margin-bottom: 20px;
  font-size: 20px;
  color: #303133;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 26px;
  font-weight: 600;
  color: #409eff;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-start;
}

.mono-text {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  color: #606266;
}

.time-text {
  font-size: 13px;
  color: #909399;
}

.detail-dialog :deep(.el-descriptions__label) {
  width: 80px;
  white-space: nowrap;
}

.detail-pre {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.pagination-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .filter-bar { flex-wrap: wrap; }
}
</style>
