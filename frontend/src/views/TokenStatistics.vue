<template>
  <div class="token-statistics-page">
    <h2>大模型Token使用统计</h2>

    <!-- 筛选条件 -->
    <div class="filter-section">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            @change="handleDateRangeChange"
          />
        </el-form-item>
<!--        <el-form-item label="意图">
          <el-select v-model="filterForm.intentType" placeholder="全部意图" clearable style="width:130px">
            <el-option label="全部意图" value="" />
            <el-option label="通用对话" value="GENERAL" />
            <el-option label="知识库查询" value="KNOWLEDGE" />
            <el-option label="备忘录操作" value="MEMO" />
            <el-option label="工作流" value="WORKFLOW" />
          </el-select>
        </el-form-item>-->
        <el-form-item label="模型">
          <el-select v-model="filterForm.modelName" placeholder="全部模型" clearable style="width:130px">
            <el-option label="全部模型" value="" />
            <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData" :loading="loading">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
          <el-button @click="loadData" :loading="loading" icon="Refresh">刷新</el-button>
          <span v-if="lastUpdated" class="last-updated">最后更新: {{ formatDateTime(lastUpdated) }}</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- 统计概览卡片 -->
    <div class="statistics-cards">
      <el-card class="stat-card" shadow="hover">
        <div class="card-body">
          <div class="card-label">总Token消耗</div>
          <div class="stat-value">{{ formatNumber(statistics.totalTokens || 0) }}</div>
          <div class="stat-sub">
            <span>输入 {{ formatNumber(statistics.totalInputTokens || 0) }}</span>
            <span class="sub-sep">|</span>
            <span>输出 {{ formatNumber(statistics.totalOutputTokens || 0) }}</span>
          </div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="card-body">
          <div class="card-label">请求次数</div>
          <div class="stat-value">{{ formatNumber(statistics.requestCount || 0) }}</div>
          <div class="stat-sub">平均 {{ formatNumber(statistics.avgTokensPerRequest || 0) }} Token/次</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="card-body">
          <div class="card-label">总成本</div>
          <div class="stat-value cost-color">¥{{ formatCurrency(statistics.totalCost || 0) }}</div>
          <div class="stat-sub">平均 ¥{{ formatCurrency(statistics.avgCostPerRequest || 0) }}/次</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="card-body">
          <div class="card-label">工具调用</div>
          <div class="stat-value tool-color">{{ statistics.toolCallCount || 0 }}</div>
          <div class="stat-sub">调用率 {{ toolCallRate }}%</div>
        </div>
      </el-card>
    </div>

    <!-- ECharts 图表 -->
    <div class="chart-row">
      <el-card class="chart-card" shadow="hover">
        <template #header><span class="card-label">按模型统计 (Token占比)</span></template>
        <div v-if="statisticsByModel.length > 0" ref="pieChartRef" class="chart-container"></div>
        <div v-else class="empty-data">暂无数据</div>
      </el-card>

      <el-card class="chart-card" shadow="hover">
        <template #header><span class="card-label">每日Token趋势</span></template>
        <div v-if="statisticsByDate.length > 0" ref="lineChartRef" class="chart-container"></div>
        <div v-else class="empty-data">暂无数据</div>
      </el-card>
    </div>

    <!-- 使用记录表格 -->
    <el-card class="table-card" shadow="hover">
      <template #header>
        <div class="table-header">
          <span class="card-label">使用记录</span>
          <div class="table-actions">
            <el-button size="small" @click="toggleTableExpanded">
              {{ tableExpanded ? '收起' : '展开' }}
            </el-button>
            <el-button size="small" type="primary" @click="exportToCSV" :loading="exporting">导出CSV</el-button>
          </div>
        </div>
      </template>
      <div v-if="tableExpanded">
        <el-table
          :data="usageRecords"
          stripe
          style="width: 100%"
          :loading="tableLoading"
          max-height="450"
          size="small"
        >
          <el-table-column prop="createTime" label="时间" width="140">
            <template #default="{ row }">
              <span class="cell-text">{{ formatDateTime(row.createTime) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="modelName" label="模型" width="100">
            <template #default="{ row }">
              <el-tooltip :content="row.modelName || 'qwen-plus'" placement="top">
                <span class="cell-ellipsis">{{ truncateText(row.modelName || 'qwen-plus', 20) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="intentType" label="意图" width="140">
            <template #default="{ row }">
              <el-tooltip :content="getIntentDescription(row.intentType)" placement="top">
                <el-tag size="small" :type="getIntentTagType(row.intentType)" class="cell-ellipsis">
                  {{ getIntentDescription(row.intentType) }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="callPurpose" label="目的" width="120">
            <template #default="{ row }">
              <el-tooltip :content="getCallPurposeDescription(row.callPurpose)" placement="top">
                <el-tag size="small" type="info" class="cell-ellipsis">
                  {{ getCallPurposeDescription(row.callPurpose) }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="inputTokens" label="输入" width="60" align="right" />
          <el-table-column prop="outputTokens" label="输出" width="60" align="right" />
          <el-table-column prop="totalTokens" label="总计" width="65" align="right" />
          <el-table-column prop="costAmount" label="成本" width="80" align="right">
            <template #default="{ row }">
              <span class="cell-text">¥{{ formatCurrency(row.costAmount || 0) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="toolNames" label="工具" width="160">
            <template #default="{ row }">
              <el-tooltip v-if="row.toolCalled && row.toolNames" :content="row.toolNames" placement="top">
                <span class="cell-ellipsis">{{ truncateText(row.toolNames, 15) }}</span>
              </el-tooltip>
              <span v-else-if="row.toolCalled" class="cell-text">已调用</span>
              <span v-else class="cell-text no-tool">无</span>
            </template>
          </el-table-column>
          <el-table-column prop="queryText" label="查询内容" min-width="100">
            <template #default="{ row }">
              <el-tooltip v-if="row.queryText" :content="row.queryText" placement="top">
                <span class="cell-ellipsis">{{ truncateText(row.queryText, 30) }}</span>
              </el-tooltip>
              <span v-else class="cell-text no-tool">空</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination">
          <el-pagination
            v-model:current-page="pagination.pageNum"
            v-model:page-size="pagination.pageSize"
            :total="pagination.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          />
        </div>
      </div>
    </el-card>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, nextTick, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { getTokenUsageRecords, getTokenUsageStatistics, getTokenUsageByModel, getTokenUsageByDate } from '../api/tokenUsage.js'
import { useUserStore } from '../store/user'

const filterForm = reactive({
  dateRange: null,
  startTime: null,
  endTime: null,
  modelName: null,
  intentType: null
})

const userStore = useUserStore()

const statistics = ref({})
const statisticsByModel = ref([])
const statisticsByDate = ref([])
const modelOptions = ref([])
const usageRecords = ref([])
const loading = ref(false)
const tableLoading = ref(false)
const tableExpanded = ref(true)
const exporting = ref(false)
const lastUpdated = ref(null)

const pieChartRef = ref(null)
const lineChartRef = ref(null)
let pieChartInstance = null
let lineChartInstance = null

const pagination = reactive({
  pageNum: 1,
  pageSize: 20,
  total: 0
})

const toolCallRate = computed(() => {
  const total = statistics.value.requestCount || 0
  const toolCalls = statistics.value.toolCallCount || 0
  if (total === 0) return '0.0'
  return (toolCalls / total * 100).toFixed(1)
})

const getDefaultDateRange = () => {
  const now = new Date()
  const startDate = new Date(now.getFullYear(), now.getMonth(), 1)
  const endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  const fmt = (d) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }
  return [fmt(startDate), fmt(endDate)]
}

onMounted(() => {
  filterForm.dateRange = getDefaultDateRange()
  loadData()
})

onUnmounted(() => {
  pieChartInstance?.dispose()
  lineChartInstance?.dispose()
})

watch([statisticsByModel, statisticsByDate], () => {
  nextTick(() => {
    renderPieChart()
    renderLineChart()
  })
})

const getFilterParams = () => {
  const params = {}
  if (filterForm.intentType) params.intentType = filterForm.intentType
  if (filterForm.modelName) params.modelName = filterForm.modelName
  return params
}

const loadData = async () => {
  try {
    loading.value = true
    tableLoading.value = true

    if (filterForm.dateRange && filterForm.dateRange.length === 2) {
      filterForm.startTime = filterForm.dateRange[0] + ' 00:00:00'
      filterForm.endTime = filterForm.dateRange[1] + ' 23:59:59'
    }

    const userId = userStore.userId || 'demo-user'
    const { intentType, modelName } = getFilterParams()

    const [statsRes, modelRes, dateRes] = await Promise.all([
      getTokenUsageStatistics(userId, filterForm.startTime, filterForm.endTime, intentType, modelName),
      getTokenUsageByModel(userId, filterForm.startTime, filterForm.endTime, intentType, modelName),
      getTokenUsageByDate(userId, filterForm.startTime, filterForm.endTime, intentType, modelName)
    ])

    if (statsRes.code === 0) {
      statistics.value = statsRes.data
    }

    if (modelRes.code === 0) {
      statisticsByModel.value = modelRes.data || []
      const models = [...new Set((modelRes.data || []).map(m => m.model_name || m.model).filter(Boolean))]
      modelOptions.value = models
    }

    if (dateRes.code === 0) {
      statisticsByDate.value = dateRes.data || []
    }

    await loadRecords()
  } catch (error) {
    console.error('加载数据失败:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
    tableLoading.value = false
    lastUpdated.value = new Date()
  }
}

const loadRecords = async () => {
  try {
    const userId = userStore.userId || 'demo-user'
    const recordsRes = await getTokenUsageRecords(userId, filterForm.startTime, filterForm.endTime, pagination.pageNum, pagination.pageSize)
    if (recordsRes.code === 0) {
      const data = recordsRes.data || {}
      let records = data.records || []
      // 前端过滤（后端暂不支持分页场景下的意图/模型筛选）
      if (filterForm.intentType) records = records.filter(r => r.intentType === filterForm.intentType)
      if (filterForm.modelName) records = records.filter(r => r.modelName === filterForm.modelName)
      usageRecords.value = records
      pagination.total = data.total || 0
      if (data.pageNum) pagination.pageNum = data.pageNum
      if (data.pageSize) pagination.pageSize = data.pageSize
    }
  } catch (e) {
    console.error('加载记录失败:', e)
  }
}

// ─── ECharts ───────────────────────────────────────────────

const renderPieChart = () => {
  if (!pieChartRef.value || statisticsByModel.value.length === 0) return
  if (pieChartInstance) { pieChartInstance.dispose(); pieChartInstance = null }
  pieChartInstance = echarts.init(pieChartRef.value)

  const data = statisticsByModel.value.map(item => ({
    name: item.model_name || 'qwen-plus',
    value: item.total_tokens || 0
  }))
  const total = data.reduce((s, i) => s + i.value, 0)

  pieChartInstance.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}<br/>Token: ${formatNumber(p.value)} (${((p.value / total) * 100).toFixed(1)}%)`
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '50%'],
      padAngle: 2,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: {
        show: true,
        formatter: (p) => `${p.name}\n${((p.value / total) * 100).toFixed(1)}%`,
        fontSize: 11
      },
      data
    }]
  })
  pieChartInstance.resize()
}

const renderLineChart = () => {
  if (!lineChartRef.value || statisticsByDate.value.length === 0) return
  if (lineChartInstance) { lineChartInstance.dispose(); lineChartInstance = null }
  lineChartInstance = echarts.init(lineChartRef.value)

  const sorted = [...statisticsByDate.value].sort((a, b) => ((a.usage_date || '') > (b.usage_date || '') ? 1 : -1))
  const dates = sorted.map(i => {
    const d = i.usage_date || ''
    return d.length > 10 ? d.substring(5, 10) : d.substring(5)
  })
  const tokens = sorted.map(i => i.total_tokens || 0)
  const costs = sorted.map(i => parseFloat(i.total_cost || 0))

  lineChartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        let html = `<strong>${params[0]?.axisValue || ''}</strong><br/>`
        params.forEach(p => {
          html += `${p.marker} ${p.seriesName}: ${p.seriesName === 'Token数' ? formatNumber(p.value) : '¥' + p.value}<br/>`
        })
        return html
      }
    },
    legend: { data: ['Token数', '成本'], top: 0, right: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: [
      { type: 'value', name: 'Token', axisLabel: { formatter: (v) => v >= 1000 ? (v / 1000) + 'k' : v } },
      { type: 'value', name: '成本(元)', axisLabel: { formatter: (v) => '¥' + v.toFixed(2) } }
    ],
    series: [
      {
        name: 'Token数', type: 'line', data: tokens, smooth: true,
        lineStyle: { color: '#409eff', width: 2 },
        itemStyle: { color: '#409eff' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.3)' }, { offset: 1, color: 'rgba(64,158,255,0.05)' }
        ]) }
      },
      {
        name: '成本', type: 'line', yAxisIndex: 1, data: costs, smooth: true,
        lineStyle: { color: '#f56c6c', width: 2 },
        itemStyle: { color: '#f56c6c' }
      }
    ]
  })
  lineChartInstance.resize()
}

const onWindowResize = () => { pieChartInstance?.resize(); lineChartInstance?.resize() }
window.addEventListener('resize', onWindowResize)

// ─── 操作 ──────────────────────────────────────────────────

const exportToCSV = () => {
  if (!usageRecords.value || usageRecords.value.length === 0) {
    ElMessage.warning('没有数据可以导出')
    return
  }
  try {
    exporting.value = true
    const headers = ['时间', '追踪ID', '模型', '意图', '调用目的', '输入Token', '输出Token', '总Token', '成本(元)', '工具', '查询内容']
    const rows = usageRecords.value.map(r => [
      formatDateTime(r.createTime), r.traceId || '', r.modelName || '',
      getIntentDescription(r.intentType), getCallPurposeDescription(r.callPurpose),
      r.inputTokens || 0, r.outputTokens || 0, r.totalTokens || 0, r.costAmount || 0,
      r.toolCalled ? (r.toolNames || '已调用') : '无',
      `"${(r.queryText || '').replace(/"/g, '""')}"`
    ])
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `token_usage_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// ─── 事件处理 ──────────────────────────────────────────────

const handleSizeChange = (size) => { pagination.pageSize = size; pagination.pageNum = 1; loadRecords() }
const handleCurrentChange = (page) => { pagination.pageNum = page; loadRecords() }
const handleDateRangeChange = (range) => {
  if (range && range.length === 2) {
    filterForm.startTime = range[0] + ' 00:00:00'
    filterForm.endTime = range[1] + ' 23:59:59'
  } else {
    filterForm.startTime = null
    filterForm.endTime = null
  }
}
const resetFilter = () => {
  filterForm.dateRange = getDefaultDateRange()
  filterForm.startTime = null
  filterForm.endTime = null
  filterForm.modelName = null
  filterForm.intentType = null
  pagination.pageNum = 1
  loadData()
}
const toggleTableExpanded = () => { tableExpanded.value = !tableExpanded.value }

// ─── 格式化 ────────────────────────────────────────────────

const formatNumber = (num) => (num === null || num === undefined) ? '0' : new Intl.NumberFormat('zh-CN').format(num)
const formatCurrency = (amount) => {
  if (!amount) return '0.00'
  return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(amount)
}
const formatDateTime = (d) => d ? new Date(d).toLocaleString('zh-CN') : ''
const truncateText = (text, max) => (text && text.length > max) ? text.substring(0, max) + '...' : (text || '')

const getIntentDescription = (t) => ({ GENERAL: '通用对话', KNOWLEDGE: '知识库查询', MEMO: '备忘录操作', WORKFLOW: '工作流', UNKNOWN: '未知' })[t] || t
const getIntentTagType = (t) => ({ GENERAL: 'info', KNOWLEDGE: 'success', MEMO: 'warning', WORKFLOW: 'danger' })[t] || ''
const getCallPurposeDescription = (p) => ({
  intent_classification: '意图分类', knowledge_agent: '知识库问答', memo_agent: '备忘录操作',
  workflow_date_parsing: '日期解析', workflow_email_format: '邮件排版',
  knowledge_rewrite_query: '查询改写', knowledge_rerank: '重排序', knowledge_rag: 'RAG检索'
})[p] || p || '通用'
</script>

<style scoped>
.token-statistics-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

/* ─── 筛选区 ─── */
.filter-section {
  margin-bottom: 20px;
  background: var(--bg-card);
  padding: 16px 20px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

/* ─── 统计卡片 ─── */
.statistics-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.card-body {
  text-align: center;
  padding: 4px 0;
}

.card-label {
  font-weight: bold;
  font-size: 14px;
  color: #606266;
}

.stat-value {
  font-size: 26px;
  font-weight: bold;
  margin: 8px 0;
  color: #409eff;
}

.cost-color { color: #f56c6c; }
.tool-color { color: #67c23a; }

.stat-sub {
  font-size: 13px;
  color: #909399;
}

.sub-sep {
  margin: 0 6px;
  color: #dcdfe6;
}

/* ─── 图表 ─── */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

.chart-card :deep(.el-card__body) {
  padding: 12px;
}

.chart-container {
  width: 100%;
  height: 340px;
}

/* ─── 表格 ─── */
.table-card {
  min-height: 400px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-actions {
  display: flex;
  gap: 8px;
}

.empty-data {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 280px;
  color: #999;
  font-size: 16px;
}

.no-tool {
  color: #999;
  font-style: italic;
}

.cell-ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.cell-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}

.last-updated {
  margin-left: 15px;
  font-size: 12px;
  color: #909399;
}

@media (max-width: 1200px) {
  .statistics-cards { grid-template-columns: repeat(2, 1fr); }
  .chart-row { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .statistics-cards { grid-template-columns: 1fr; }
}
</style>
