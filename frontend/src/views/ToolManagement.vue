<template>
  <div class="tool-management-page">
    <h2>工具管理</h2>

    <!-- 统计概览 -->
    <div class="stats-row">
      <el-card class="stat-card">
        <div class="stat-label">工具总数</div>
        <div class="stat-value">{{ tools.length }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">已启用</div>
        <div class="stat-value" style="color: #67c23a">{{ enabledCount }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">已禁用</div>
        <div class="stat-value" style="color: #f56c6c">{{ disabledCount }}</div>
      </el-card>
    </div>

    <!-- 权限筛选 -->
    <div class="filter-bar">
      <el-radio-group v-model="filterPermission" @change="applyFilter">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="READ_ONLY">只读</el-radio-button>
        <el-radio-button value="READ_WRITE">读写</el-radio-button>
        <el-radio-button value="ADMIN">管理员</el-radio-button>
      </el-radio-group>
      <el-button type="primary" @click="refresh" style="margin-left: 16px">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 工具列表 -->
    <el-table :data="filteredTools" stripe v-loading="loading" style="width: 100%; margin-top: 16px">
      <el-table-column prop="name" label="工具名称" min-width="200" />
      <el-table-column prop="description" label="描述" min-width="300" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ truncate(row.description, 60) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="permission" label="权限级别" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="permTagType(row.permission)" size="small">
            {{ row.permission }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="100" align="center" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'danger'" size="small">
            {{ row.enabled ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.enabled"
            type="warning"
            size="small"
            @click="handleDisable(row)"
          >
            禁用
          </el-button>
          <el-button
            v-else
            type="success"
            size="small"
            @click="handleEnable(row)"
          >
            启用
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listTools, enableTool, disableTool } from '../api/toolManagement'

const tools = ref([])
const loading = ref(false)
const filterPermission = ref('')

const enabledCount = computed(() => tools.value.filter(t => t.enabled).length)
const disabledCount = computed(() => tools.value.filter(t => !t.enabled).length)

const filteredTools = computed(() => {
  if (!filterPermission.value) return tools.value
  return tools.value.filter(t => t.permission === filterPermission.value)
})

function applyFilter() {
  // computed 自动响应
}

function permTagType(perm) {
  return perm === 'ADMIN' ? 'danger' : perm === 'READ_WRITE' ? 'warning' : 'info'
}

function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? text.substring(0, max) + '...' : text
}

async function refresh() {
  loading.value = true
  try {
    const params = {}
    if (filterPermission.value) {
      params.permission = filterPermission.value
    }
    const res = await listTools(params)
    if (res.code === 0) {
      tools.value = res.data || []
    }
  } catch (e) {
    ElMessage.error('加载工具列表失败')
  } finally {
    loading.value = false
  }
}

async function handleEnable(row) {
  try {
    await enableTool(row.name)
    ElMessage.success(`工具 ${row.name} 已启用`)
    row.enabled = true
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function handleDisable(row) {
  try {
    await ElMessageBox.confirm(`确定要禁用工具 "${row.name}" 吗？禁用后 Agent 将无法调用该工具。`, '确认', {
      type: 'warning'
    })
    await disableTool(row.name)
    ElMessage.success(`工具 ${row.name} 已禁用`)
    row.enabled = false
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('操作失败')
  }
}

onMounted(refresh)
</script>

<style scoped>
.tool-management-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.tool-management-page h2 {
  margin-bottom: 20px;
  font-size: 20px;
  color: #303133;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
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
}
</style>
