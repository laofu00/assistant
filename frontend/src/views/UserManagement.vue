<template>
  <div class="user-management-page">
    <h2>用户管理</h2>

    <!-- 搜索 -->
    <div class="filter-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名或昵称"
        clearable
        style="width: 260px"
        @keyup.enter="search"
        @clear="search"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="search" style="margin-left: 12px">搜索</el-button>
    </div>

    <!-- 用户列表 -->
    <el-card shadow="hover">
      <el-table :data="users" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="昵称" min-width="120">
          <template #default="{ row }">
            {{ row.nickname || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="160">
          <template #default="{ row }">
            {{ row.email || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="roles" label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.roles || '').includes('admin')" type="danger" size="small">管理员</el-tag>
            <el-tag v-else type="info" size="small">普通用户</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">
              {{ row.status === 1 ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="disabledToolCount" label="已禁用工具" width="110" align="center">
          <template #default="{ row }">
            <span :style="{ color: row.disabledToolCount > 0 ? '#f56c6c' : '#909399' }">
              {{ row.disabledToolCount }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="openToolConfig(row)">
              <el-icon><Setting /></el-icon>
              工具配置
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadUsers"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <!-- 工具配置弹窗 -->
    <el-dialog
      v-model="toolDialogVisible"
      :title="`用户 [${selectedUser?.nickname || selectedUser?.username}] 工具权限配置`"
      width="695px"
      destroy-on-close
    >
      <el-table :data="toolConfigs" max-height="400" size="small">
        <el-table-column prop="name" label="工具名称" width="150" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="80" align="center" />
        <el-table-column prop="permission" label="权限级别" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="permTagType(row.permission)" size="small">{{ row.permission }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="全局状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.globalEnabled ? 'success' : 'danger'" size="small">
              {{ row.globalEnabled ? '启用' : '禁用' }}
            </el-tag>
            <el-tooltip v-if="!row.globalEnabled" content="全局已禁用，用户无法使用" placement="top">
              <el-icon style="margin-left:4px;color:#f56c6c;font-size:14px"><WarningFilled /></el-icon>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="用户状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.userEnabled ? 'success' : 'danger'" size="small">
              {{ row.userEnabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.userEnabled"
              :disabled="!row.globalEnabled || row.toggling"
              :loading="row.toggling"
              @change="(val) => toggleUserTool(row, val)"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Setting, WarningFilled } from '@element-plus/icons-vue'
import {
  listUsers,
  listTools,
  getUserDisabledTools,
  disableToolForUser,
  enableToolForUser,
} from '../api/toolManagement'

const keyword = ref('')
const users = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const toolDialogVisible = ref(false)
const selectedUser = ref(null)
const toolConfigs = ref([])

function permTagType(perm) {
  return perm === 'ADMIN' ? 'danger' : perm === 'READ_WRITE' ? 'warning' : 'info'
}

async function loadUsers() {
  loading.value = true
  try {
    const res = await listUsers({ keyword: keyword.value, page: page.value, size: pageSize.value })
    if (res.code === 0) {
      const data = res.data
      users.value = data.items || []
      total.value = data.total || 0
    }
  } catch (e) {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  loadUsers()
}

async function openToolConfig(user) {
  selectedUser.value = user
  toolDialogVisible.value = true

  try {
    const [toolsRes, disabledRes] = await Promise.all([
      listTools(),
      getUserDisabledTools(user.userId),
    ])
    const allTools = toolsRes.code === 0 ? (toolsRes.data || []) : []
    const disabledTools = disabledRes.code === 0 ? (disabledRes.data || []) : []

    const disabledSet = new Set(disabledTools)
    toolConfigs.value = allTools.map(t => ({
      ...t,
      globalEnabled: t.enabled,
      userEnabled: t.enabled && !disabledSet.has(t.name),
      toggling: false,
    }))
  } catch (e) {
    ElMessage.error('加载工具配置失败')
  }
}

async function toggleUserTool(row, enabled) {
  row.toggling = true
  const userId = selectedUser.value.userId
  try {
    if (enabled) {
      await enableToolForUser(userId, row.name)
      row.userEnabled = true
      ElMessage.success(`已启用 [${row.name}]`)
    } else {
      await disableToolForUser(userId, row.name)
      row.userEnabled = false
      ElMessage.success(`已禁用 [${row.name}]`)
    }
    // 更新用户列表中的禁用工具数
    const u = users.value.find(u => u.userId === userId)
    if (u) {
      u.disabledToolCount = toolConfigs.value.filter(t => !t.userEnabled).length
    }
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    row.toggling = false
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.user-management-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.user-management-page h2 {
  margin-bottom: 20px;
  font-size: 20px;
  color: var(--text-primary);
}

.filter-bar {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
