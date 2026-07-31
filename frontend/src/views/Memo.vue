<template>
  <div class="page-container">
    <div class="page-header">
      <h2>备忘录</h2>
      <div class="header-actions">
        <el-select
          v-model="searchCategory"
          placeholder="按分类筛选"
          style="width: 200px; margin-right: 10px;"
          clearable
          filterable
          allow-create
          default-first-option
          @change="fetchMemos"
        >
          <el-option
            v-for="cat in categoryOptions"
            :key="cat"
            :label="cat"
            :value="cat"
          />
        </el-select>
        <el-button type="default" @click="fetchMemos" style="margin-right: 10px;">
          搜索
        </el-button>
        <el-button type="primary" @click="createNewMemo">
          新建备忘录
        </el-button>
      </div>
    </div>

    <!-- 创建/编辑备忘录对话框 -->
    <el-dialog
      v-model="showEditDialog"
      :title="editingMemo.id ? '编辑备忘录' : '新建备忘录'"
      width="500px"
    >
      <el-form :model="editingMemo" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="editingMemo.title" placeholder="请输入标题" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="editingMemo.content"
            type="textarea"
            :rows="4"
            placeholder="请输入内容"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select
            v-model="editingMemo.category"
            placeholder="留空则由AI自动分类"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
            clearable
          >
            <el-option
              v-for="cat in categoryOptions"
              :key="cat"
              :label="cat"
              :value="cat"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="到期日期">
          <el-date-picker
            v-model="editingMemo.due_date"
            type="date"
            placeholder="选择到期日期（可选）"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" @click="saveMemo">
            保存
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 备忘录列表 -->
    <div class="memo-list">
      <el-table :data="memos" v-loading="loading">
        <el-table-column prop="title" label="标题" width="200" />
        <el-table-column prop="content" label="内容">
          <template #default="scope">
            <div class="content-preview">{{ scope.row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="due_date" label="到期日期" width="120">
          <template #default="scope">
            {{ scope.row.due_date || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="createTime" label="创建时间" width="170">
          <template #default="scope">
            {{ formatDateTime(scope.row.createTime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="scope">
            <el-button
              type="primary"
              size="small"
              @click="editMemo(scope.row)"
            >
              编辑
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="deleteMemo(scope.row)"
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
          @size-change="fetchMemos"
          @current-change="fetchMemos"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { memoApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime, convertRelativeDates } from '../utils/dateUtils'

const memos = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const searchCategory = ref('')
const showEditDialog = ref(false)

// 预设分类选项（用户可输入自定义分类）
const categoryOptions = ['工作', '生活', '待办', '学习', '重要']

const editingMemo = reactive({
  id: null,
  title: '',
  content: '',
  category: '',
  due_date: null
})

const fetchMemos = async () => {
  loading.value = true
  try {
    const response = await memoApi.getMemos(
      searchCategory.value || null,
      currentPage.value,
      pageSize.value
    )
    memos.value = response.data.records || []
    total.value = response.data.total || 0
  } catch (error) {
    ElMessage.error('获取备忘录列表失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const editMemo = (memo) => {
  Object.assign(editingMemo, memo)
  showEditDialog.value = true
}

const createNewMemo = () => {
  editingMemo.id = null
  editingMemo.title = ''
  editingMemo.content = ''
  editingMemo.category = ''
  editingMemo.due_date = null
  showEditDialog.value = true
}

const saveMemo = async () => {
  if (!editingMemo.title.trim()) {
    ElMessage.warning('请输入标题')
    return
  }

  // 转换内容中的相对日期时间词为具体日期
  if (editingMemo.content) {
    editingMemo.content = convertRelativeDates(editingMemo.content)
  }

  try {
    if (editingMemo.id) {
      await memoApi.updateMemo(editingMemo.id, editingMemo)
      ElMessage.success('备忘录更新成功')
    } else {
      await memoApi.createMemo(editingMemo)
      ElMessage.success('备忘录创建成功')
    }
    showEditDialog.value = false
    fetchMemos()
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

const deleteMemo = async (memo) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除备忘录 "${memo.title}" 吗？\n\n此操作将永久删除该备忘录，不可恢复。`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    await memoApi.deleteMemo(memo.id)
    ElMessage.success('备忘录删除成功')
    fetchMemos()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + error.message)
    }
  }
}

onMounted(() => {
  fetchMemos()
})

defineExpose({
  showCreateDialog: showEditDialog,
  createNewMemo
})
</script>

<style scoped>
.memo-page {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  align-items: center;
}

.memo-list {
  background-color: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 20px;
}

.content-preview {
  max-height: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
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

  .header-actions {
    width: 100%;
    flex-direction: column;
    gap: 10px;
  }

  .header-actions .el-input {
    width: 100%;
    margin-right: 0;
  }

  .header-actions .el-button {
    width: 100%;
  }

  .memo-list {
    padding: 15px;
  }

  .el-table {
    font-size: 14px;
  }

  .el-table-column {
    min-width: 60px;
  }

  .content-preview {
    -webkit-line-clamp: 2;
    max-height: 40px;
  }

  .el-table .el-button {
    font-size: 12px;
    padding: 5px 8px;
    margin-bottom: 5px;
  }

  .pagination {
    justify-content: center;
  }

  .el-pagination {
    flex-wrap: wrap;
  }

  .el-dialog {
    width: 90% !important;
    max-width: 500px;
  }
}

@media (max-width: 480px) {
  .page-header h2 {
    font-size: 18px;
  }

  .memo-list {
    padding: 10px;
  }

  .el-table {
    font-size: 12px;
  }

  .el-table-column {
    min-width: 50px;
  }

  .content-preview {
    -webkit-line-clamp: 2;
    font-size: 11px;
  }

  .el-table .el-button {
    font-size: 11px;
    padding: 4px 6px;
    margin-bottom: 3px;
  }

  .el-pagination .el-pagination__total,
  .el-pagination .el-pagination__sizes,
  .el-pagination .el-pagination__jump {
    margin-bottom: 10px;
  }
}
</style>