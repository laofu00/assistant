import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '../store/user'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { guestOnly: true }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('../views/Knowledge.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/memo',
    name: 'Memo',
    component: () => import('../views/Memo.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/Chat.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { guestOnly: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { guestOnly: true }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/Profile.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/token-statistics',
    name: 'TokenStatistics',
    component: () => import('../views/TokenStatistics.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/user-management',
    name: 'UserManagement',
    component: () => import('../views/UserManagement.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/tool-management',
    name: 'ToolManagement',
    component: () => import('../views/ToolManagement.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/audit-logs',
    name: 'AuditLogs',
    component: () => import('../views/AuditLogs.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/memory',
    name: 'Memory',
    component: () => import('../views/Memory.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 全局前置守卫
router.beforeEach((to, from, next) => {
  console.log('Router navigation:', { from: from.path, to: to.path })
  
  try {
    const userStore = useUserStore()
    const isLoggedIn = userStore.isLoggedIn
    console.log('User login status:', isLoggedIn)
    console.log('Route meta:', to.meta)

    // 检查路由是否需要认证
    if (to.meta.requiresAuth && !isLoggedIn) {
      console.log('Redirecting to login - authentication required')
      // 重定向到登录页面
      next('/login')
      return
    }

    // 检查路由是否需要管理员权限
    if (to.meta.requiresAdmin && !userStore.isAdmin) {
      console.log('Redirecting to chat - admin required')
      next('/chat')
      return
    }

    // 检查是否只允许未登录用户访问（如登录、注册页面）
    if (to.meta.guestOnly && isLoggedIn) {
      console.log('Redirecting to chat - already logged in')
      // 如果已登录，重定向到聊天页面（避免重定向到根路径造成死循环）
      next('/chat')
      return
    }

    console.log('Navigation allowed for route:', to.path)
    next()
  } catch (error) {
    console.error('Router guard error:', error)
    console.log('Allowing navigation due to error')
    next() // 允许导航以防store未初始化
  }
})

export default router