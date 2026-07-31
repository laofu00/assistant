<template>
  <div id="app" :class="{ 'no-sidebar': !userStore.isLoggedIn }">
    <header class="header">
      <div class="logo" @click="router.push('/chat')">
        <span class="logo-icon">✦</span>
        <span class="logo-text">Smart Assistant</span>
      </div>
      <div v-if="userStore.isLoggedIn" class="user-info">
        <el-dropdown @command="handleUserCommand" trigger="click">
          <span class="user-dropdown">
            <span class="user-avatar">{{ userStore.displayName?.charAt(0)?.toUpperCase() }}</span>
            <span class="user-name">{{ userStore.displayName }}</span>
            <el-icon><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">
                <el-icon><User /></el-icon> 个人资料
              </el-dropdown-item>
              <el-dropdown-item command="logout" divided>
                <el-icon><SwitchButton /></el-icon> 退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>
    <div class="main-container">
      <aside v-if="userStore.isLoggedIn" class="sidebar">
        <el-menu
          :default-active="activeMenu"
          router
          background-color="var(--bg-sidebar)"
          text-color="#a0a3b1"
          active-text-color="#fff"
        >
          <el-menu-item index="/chat">
            <el-icon><chat-line-round /></el-icon>
            <span>智能助手</span>
          </el-menu-item>
          <el-menu-item index="/knowledge">
            <el-icon><document /></el-icon>
            <span>个人知识库</span>
          </el-menu-item>
          <el-menu-item index="/memo">
            <el-icon><notebook /></el-icon>
            <span>备忘录</span>
          </el-menu-item>
          <el-menu-item index="/token-statistics">
            <el-icon><pie-chart /></el-icon>
            <span>Token 统计</span>
          </el-menu-item>
          <el-menu-item index="/tool-management">
            <el-icon><tools /></el-icon>
            <span>工具管理</span>
          </el-menu-item>
          <el-menu-item index="/audit-logs">
            <el-icon><list /></el-icon>
            <span>审计日志</span>
          </el-menu-item>
        </el-menu>
      </aside>
      <main class="content">
        <router-view></router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './store/user'
import { useChatStore } from './store/chat'
import { ElMessageBox } from 'element-plus'
import {
  Document, Notebook, ChatLineRound, ArrowDown, PieChart, Tools, List, User, SwitchButton
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const chatStore = useChatStore()

const activeMenu = computed(() => route.path)

const handleUserCommand = async (command) => {
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '退出确认', {
        confirmButtonText: '确定退出',
        cancelButtonText: '取消',
        type: 'warning'
      })
      userStore.logout()
      chatStore.clearMessages()
      router.push('/')
    } catch (e) { /* cancelled */ }
  } else if (command === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped>
#app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ===== Header ===== */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  z-index: 100;
  flex-shrink: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.logo-icon {
  font-size: 24px;
  color: var(--primary);
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background var(--transition);
}

.user-dropdown:hover {
  background: var(--bg-page);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

.user-name {
  font-size: 14px;
  color: var(--text-regular);
}

/* ===== Layout ===== */
.main-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.sidebar {
  width: 220px;
  flex-shrink: 0;
  overflow-y: auto;
}

.sidebar :deep(.el-menu) {
  border-right: none;
  height: 100%;
  padding-top: 8px;
}

.sidebar :deep(.el-menu-item) {
  margin: 2px 8px;
  border-radius: var(--radius-sm);
  height: 44px;
  line-height: 44px;
  transition: all var(--transition);
}

.sidebar :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark)) !important;
}

.sidebar :deep(.el-menu-item:hover) {
  background: var(--bg-sidebar-hover);
}

.content {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-page);
}

/* 无侧边栏时全宽 */
#app.no-sidebar .content {
  background: var(--bg-page);
}

#app.no-sidebar .header {
  box-shadow: none;
  border-bottom: 1px solid var(--border);
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .header { padding: 0 16px; }
  .logo-text { font-size: 16px; }
  .sidebar { width: 64px; }
  .sidebar :deep(.el-menu-item span) { display: none; }
  .sidebar :deep(.el-menu-item) { justify-content: center; padding: 0 !important; }
}

@media (max-width: 480px) {
  .sidebar { display: none; }
  .user-name { display: none; }
}
</style>
