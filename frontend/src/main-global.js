// 使用全局变量而不是ES6导入
const { createApp } = Vue;
const { createPinia } = Pinia;
const ElementPlus = ElementPlus;
const { createRouter, createWebHashHistory } = VueRouter;

// 导入组件（需要先定义）
// 注意：这里我们需要等待组件定义
// 首先定义App组件
const App = {
  template: '<div>Loading...</div>'
};

// 创建路由
const routes = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => Promise.resolve({ template: '<div>知识库</div>' })
  },
  {
    path: '/memo',
    name: 'Memo',
    component: () => Promise.resolve({ template: '<div>备忘录</div>' })
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => Promise.resolve({ template: '<div>聊天</div>' })
  },
  {
    path: '/login',
    name: 'Login',
    component: () => Promise.resolve({ template: '<div>登录</div>' })
  },
  {
    path: '/register',
    name: 'Register',
    component: () => Promise.resolve({ template: '<div>注册</div>' })
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => Promise.resolve({ template: '<div>个人资料</div>' })
  }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes
});

// 创建Pinia store
const pinia = createPinia();

// 创建Vue应用
const app = createApp(App);

app.use(router);
app.use(pinia);
app.use(ElementPlus);

app.mount('#app');