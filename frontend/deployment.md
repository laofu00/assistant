# 前端部署指南

## 概述

智能助手前端是一个基于 Vue.js 3 的单页应用，使用 CDN 引入依赖，无需构建即可直接运行。本文档提供两种部署方式：开发环境部署和生产环境部署。

## 项目结构

```
frontend/
├── public/              # 静态资源目录
│   └── index.html      # 主HTML文件（包含CDN依赖）
├── src/                # 源代码目录
│   ├── main.js         # 应用入口
│   ├── App.vue         # 根组件
│   ├── router/         # 路由配置
│   ├── store/          # 状态管理
│   ├── api/            # API封装
│   └── views/          # 页面组件
└── deployment.md       # 本部署文档
```

## 部署方式

### 方式一：开发环境部署（推荐）

1. **本地服务器运行**
   ```bash
   # 使用任何静态文件服务器
   cd frontend
   # Python3
   python -m http.server 8000
   # 或使用Node.js的http-server
   npx http-server -p 8000
   ```

2. **配置后端API地址**
   - 默认API地址：`http://localhost:80/api`
   - 如需修改，编辑 `src/api/index.js` 中的 `baseURL`
   - 或通过环境变量 `VITE_API_BASE_URL` 配置（如果使用Vite构建）

3. **访问应用**
   - 打开浏览器访问 `http://localhost:8000`

### 方式二：生产环境部署（静态资源）

#### 方案A：集成到后端网关（Nginx）

1. **准备静态文件**
   ```bash
   # 复制整个frontend目录到服务器
   scp -r frontend user@server:/var/www/smart-assistant/
   ```

2. **Nginx配置示例**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       # 前端静态文件
       location / {
           root /var/www/smart-assistant;
           index index.html;
           try_files $uri $uri/ /index.html;
       }

       # 后端API代理
       location /api {
           proxy_pass http://localhost:80;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

           # 支持WebSocket（如有需要）
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```

3. **配置API地址**
   - 修改 `src/api/index.js` 中的 `baseURL` 为相对路径 `/api`
   - 或使用环境特定的配置文件

#### 方案B：独立部署（与后端分离）

1. **修改API配置**
   ```javascript
   // src/api/index.js
   const api = axios.create({
     baseURL: 'https://api.your-domain.com/api', // 后端公网地址
     timeout: 20000
   })
   ```

2. **解决跨域问题**
   - 后端网关需要配置CORS，允许前端域名访问
   - 或使用Nginx反向代理统一域名

3. **HTTPS配置（推荐）**
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;

       # ... 其他配置同上
   }
   ```

## 构建优化（可选）

### 使用Vite构建

虽然当前项目使用CDN引入依赖，但可以迁移到构建工具以获得更好的性能：

1. **初始化Vite项目**
   ```bash
   npm create vite@latest smart-assistant-fe -- --template vue
   ```

2. **迁移现有代码**
   - 复制 `src/` 目录到新项目
   - 配置 `vite.config.js`
   - 安装依赖：`npm install`

3. **构建生产版本**
   ```bash
   npm run build
   # 输出到 dist/ 目录
   ```

4. **部署dist目录**
   ```bash
   # 复制dist目录到服务器
   scp -r dist user@server:/var/www/smart-assistant/
   ```

### 环境变量配置

创建 `.env` 文件：
```env
VITE_API_BASE_URL=http://localhost:80/api
```

在代码中使用：
```javascript
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:80/api'
})
```

## 运维注意事项

### 1. 缓存控制
- HTML文件：不缓存或短时间缓存
- 静态资源（JS/CSS）：长期缓存，使用文件hash

### 2. 性能优化
- 开启Gzip压缩
- 启用HTTP/2
- 配置合适的缓存头

### 3. 监控与日志
- 配置访问日志
- 监控页面加载性能
- 错误追踪（如Sentry）

### 4. 安全建议
- 使用HTTPS
- 配置CSP（内容安全策略）
- 防止XSS攻击

## 故障排除

### 常见问题

1. **跨域错误**
   - 检查后端CORS配置
   - 确保API地址正确

2. **404路由问题**
   - SPA需要配置服务器支持history模式
   - Nginx中添加 `try_files $uri $uri/ /index.html`

3. **API连接失败**
   - 检查网络连通性
   - 确认后端服务运行状态
   - 查看浏览器控制台错误信息

4. **静态资源加载失败**
   - 检查文件路径
   - 确认文件权限
   - 查看服务器日志

### 调试建议

1. 浏览器开发者工具查看Network和Console
2. 检查服务器访问日志
3. 验证API接口可用性
4. 清除浏览器缓存测试

## 更新维护

### 版本更新流程
1. 备份当前版本
2. 部署新版本到临时目录
3. 验证功能正常
4. 切换符号链接或重启服务
5. 回滚计划准备

### 日常维护
- 定期检查日志
- 监控系统资源使用
- 更新安全补丁
- 备份配置文件

---

*最后更新：2026-03-27*
*部署状态：支持独立部署和集成部署*