# 智能助手前端

## 项目概述
基于Vue 3 + Element Plus + Vite的前端项目，与后端微服务网关通信。

## 快速开始

### 前提条件
- Node.js 16+
- npm 或 yarn

### 安装依赖
```bash
npm install
```

### 开发模式
```bash
npm run dev
```
访问 http://localhost:8000

### 构建生产版本
```bash
npm run build
```
构建产物在 `dist/` 目录

### 预览生产构建
```bash
npm run preview
```

## 项目结构
```
frontend/
├── index.html          # 主HTML文件
├── vite.config.js      # Vite配置
├── package.json        # 依赖配置
├── public/             # 静态资源
│   └── index.html      # 原CDN版本HTML（已备份）
└── src/                # 源代码
    ├── main.js         # 应用入口
    ├── App.vue         # 根组件
    ├── router/         # 路由配置
    ├── store/          # 状态管理
    ├── api/            # API封装
    └── views/          # 页面组件
```

## 功能模块
1. **用户管理**: 登录、注册、个人资料
2. **个人知识库**: 文件上传、管理、检索
3. **备忘录**: 创建、编辑、删除、分类筛选
4. **智能助手**: 聊天界面，支持知识库查询、备忘录查看等

## 接口配置
默认API基础URL: `http://localhost:80/api`

### 配置方式
1. **环境变量（推荐）**: 创建 `.env` 文件，设置 `VITE_API_BASE_URL=http://your-api-domain/api`
   - 示例: `.env.example` 提供了模板
   - 开发环境: `VITE_API_BASE_URL=http://localhost:80/api`
   - 生产环境: `VITE_API_BASE_URL=https://your-domain.com/api`

2. **直接修改代码**: 在 `src/api/index.js` 中修改 `baseURL` 默认值

### 注意
- 流式聊天接口（SSE）现在使用与普通API相同的配置，确保前后端地址一致
- 生产部署时务必设置正确的API地址，避免使用前端IP地址访问后端服务

## 技术栈
- Vue 3 (Composition API)
- Vue Router 4
- Pinia (状态管理)
- Element Plus (UI组件库)
- Axios (HTTP客户端)
- Vite (构建工具)

## 注意事项
1. 需要后端服务运行在 http://localhost:80
2. 开发时使用Vite代理解决CORS问题
3. 生产部署时需配置正确的API地址