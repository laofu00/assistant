<template>
  <div class="page-container">
    <div class="page-header">
      <h2>个人知识库</h2>
      <el-button type="primary" @click="showUploadDialog = true">
        上传文件
      </el-button>
    </div>

    <!-- 文件上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传文件" width="400px">
      <el-upload
        class="upload-demo"
        drag
        :action="uploadUrl"
        :headers="uploadHeaders"
        :on-success="handleUploadSuccess"
        :on-error="handleUploadError"
        :before-upload="beforeUpload"
        :show-file-list="false"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          将文件拖到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .txt|.xlsx|.pdf 格式，文件大小不超过20MB
          </div>
        </template>
      </el-upload>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showUploadDialog = false">取消</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 文件列表 -->
    <div class="file-list">
      <el-table :data="files" v-loading="loading">
        <el-table-column prop="fileName" label="文件名" width="250" />
        <el-table-column prop="fileType" label="类型" width="150" />
        <el-table-column prop="chunkCount" label="分块数" width="150" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag
              :type="getStatusType(scope.row.status)"
              :class="{ 'pulse-animation': scope.row.status === 'PROCESSING' }"
            >
              {{ getStatusText(scope.row.status) }}
            </el-tag>
            <div v-if="scope.row.status === 'FAILED' && scope.row.errorMessage" class="error-tip">
              <el-tooltip :content="scope.row.errorMessage" placement="top">
                <el-icon><warning /></el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="createTime" label="上传时间" width="220">
          <template #default="scope">
            {{ formatDateTime(scope.row.createTime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(scope.row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[5, 10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchFiles"
          @current-change="fetchFiles"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useUserStore } from '../store/user'
import { knowledgeApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Warning } from '@element-plus/icons-vue'
import { formatDateTime } from '../utils/dateUtils'

const userStore = useUserStore()
const files = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const showUploadDialog = ref(false)

const uploadUrl = computed(() => {
  return `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/knowledge/upload`
})

const uploadHeaders = computed(() => {
  const headers = {}
  if (userStore.token) {
    headers.Authorization = `Bearer ${userStore.token}`
  }
  if (userStore.userId) {
    headers['X-User-Id'] = userStore.userId
  }
  return headers
})

const fetchFiles = async () => {
  loading.value = true
  try {
    const response = await knowledgeApi.getFiles(currentPage.value, pageSize.value)
    files.value = response.data.records || []
    total.value = response.data.total || 0

    // 检查是否有需要轮询的文件
    checkAndStartPolling()
  } catch (error) {
    ElMessage.error('获取文件列表失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

// 状态轮询相关
const pollingIntervals = ref({})
const pollingFiles = ref(new Set())

// 状态映射
const getStatusType = (status) => {
  switch (status) {
    case 'COMPLETED': return 'success'
    case 'PROCESSING': return 'primary'
    case 'PENDING': return 'info'
    case 'FAILED': return 'danger'
    default: return 'info'
  }
}

const getStatusText = (status) => {
  switch (status) {
    case 'COMPLETED': return '已完成'
    case 'PROCESSING': return '处理中'
    case 'PENDING': return '等待中'
    case 'FAILED': return '失败'
    default: return status || '未知'
  }
}

// 检查并启动轮询
const checkAndStartPolling = () => {
  // 清除旧的轮询
  Object.values(pollingIntervals.value).forEach(interval => clearInterval(interval))
  pollingIntervals.value = {}
  pollingFiles.value.clear()

  // 查找需要轮询的文件
  files.value.forEach(file => {
    if (file.status === 'PENDING' || file.status === 'PROCESSING') {
      startPollingFile(file.id)
    }
  })
}

// 启动文件状态轮询
const startPollingFile = (fileId) => {
  if (pollingFiles.value.has(fileId)) {
    return
  }

  pollingFiles.value.add(fileId)

  const interval = setInterval(async () => {
    try {
      const response = await knowledgeApi.getFileStatus(fileId)
      const updatedFile = response.data

      // 更新文件状态
      const index = files.value.findIndex(f => f.id === fileId)
      if (index !== -1) {
        files.value[index] = { ...files.value[index], ...updatedFile }
      }

      // 如果状态变为完成或失败，停止轮询
      if (updatedFile.status === 'COMPLETED' || updatedFile.status === 'FAILED') {
        stopPollingFile(fileId)

        // 如果是失败状态，显示提示
        if (updatedFile.status === 'FAILED' && updatedFile.errorMessage) {
          ElMessage.warning(`文件处理失败: ${updatedFile.errorMessage}`)
        }
      }
    } catch (error) {
      console.error(`轮询文件状态失败，文件ID: ${fileId}`, error)
      // 发生错误时停止轮询
      stopPollingFile(fileId)
    }
  }, 3000) // 每3秒轮询一次

  pollingIntervals.value[fileId] = interval
}

// 停止文件状态轮询
const stopPollingFile = (fileId) => {
  if (pollingIntervals.value[fileId]) {
    clearInterval(pollingIntervals.value[fileId])
    delete pollingIntervals.value[fileId]
  }
  pollingFiles.value.delete(fileId)
}

// 组件卸载时清除所有轮询
onUnmounted(() => {
  Object.values(pollingIntervals.value).forEach(interval => clearInterval(interval))
  pollingIntervals.value = {}
  pollingFiles.value.clear()
})

const handleUploadSuccess = (response) => {
  if (response.code === 0) {
    ElMessage.success('文件上传成功')
    showUploadDialog.value = false
    fetchFiles()
  } else {
    ElMessage.error('上传失败: ' + (response.msg || '未知错误'))
  }
}

const handleUploadError = (error) => {
  ElMessage.error('文件上传失败: ' + error.message)
}

const beforeUpload = (file) => {
  const allowedTypes = ['.txt', '.xlsx', '.pdf']
  const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()

  if (!allowedTypes.includes(fileExtension)) {
    ElMessage.error('只支持 .txt|.xlsx|.pdf 格式的文件')
    return false
  }

  const isLt10M = file.size / 1024 / 1024 < 20
  if (!isLt10M) {
    ElMessage.error('文件大小不能超过20MB')
    return false
  }

  return true
}

const handleDelete = async (file) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件 "${file.fileName}" 吗？\n\n此操作将永久删除该文件及其所有分块数据，不可恢复。`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    await knowledgeApi.deleteFile(file.id)
    ElMessage.success('文件删除成功')
    fetchFiles()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + error.message)
    }
  }
}

onMounted(() => {
  fetchFiles()
})
</script>

<style scoped>
.knowledge-page {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.file-list {
  background-color: white;
  border-radius: 8px;
  padding: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }

  .page-header h2 {
    font-size: 20px;
    margin: 0;
  }

  .file-list {
    padding: 15px;
  }

  .el-table {
    font-size: 14px;
  }

  .el-table-column {
    min-width: 60px;
  }

  .el-table .el-button {
    font-size: 12px;
    padding: 5px 8px;
  }

  .pagination {
    justify-content: center;
  }

  .el-pagination {
    flex-wrap: wrap;
  }

  .el-dialog {
    width: 90% !important;
    max-width: 400px;
  }
}

@media (max-width: 480px) {
  .page-header h2 {
    font-size: 18px;
  }

  .file-list {
    padding: 10px;
  }

  .el-table {
    font-size: 12px;
  }

  .el-table-column {
    min-width: 50px;
  }

  .el-table .el-button {
    font-size: 11px;
    padding: 4px 6px;
  }

  .el-pagination .el-pagination__total,
  .el-pagination .el-pagination__sizes,
  .el-pagination .el-pagination__jump {
    margin-bottom: 10px;
  }
}

/* 状态标签动画 */
.pulse-animation {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
  100% {
    opacity: 1;
  }
}

.error-tip {
  display: inline-block;
  margin-left: 5px;
  color: #f56c6c;
  cursor: help;
}
</style>