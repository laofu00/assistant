<template>
  <div class="home-page">
    <div class="hero">
      <div class="hero-icon">✦</div>
      <h1>Smart Assistant</h1>
      <p class="hero-desc">智能助手，一站式管理你的备忘录、知识库，通过自然语言对话高效完成工作</p>
      <div class="hero-actions">
        <el-button type="primary" size="large" @click="goToLogin">立即登录</el-button>
        <el-button size="large" @click="goToRegister">创建账号</el-button>
      </div>
    </div>
    <div class="features-row">
      <div class="feature-card">
        <div class="feature-icon">💬</div>
        <h3>智能对话</h3>
        <p>通过自然语言与 AI 交互，支持多工具协同调用</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📚</div>
        <h3>知识库检索</h3>
        <p>上传文档自动分块索引，RAG 增强生成精准回答</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📝</div>
        <h3>备忘录管理</h3>
        <p>创建、查询、分类管理，支持按日期范围和关键词检索</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📊</div>
        <h3>用量统计</h3>
        <p>Token 消耗实时监控，成本可视化图表分析</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
const goToLogin = () => router.push('/login')
const goToRegister = () => router.push('/register')
</script>

<style scoped>
.home-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}

.hero {
  text-align: center;
  max-width: 560px;
  margin-bottom: 48px;
}

.hero-icon {
  font-size: 56px;
  color: var(--primary);
  margin-bottom: 16px;
}

.hero h1 {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.hero-desc {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 28px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.features-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  max-width: 900px;
  width: 100%;
}

.feature-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 24px 20px;
  text-align: center;
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition), box-shadow var(--transition);
}

.feature-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.feature-icon {
  font-size: 32px;
  margin-bottom: 12px;
}

.feature-card h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.feature-card p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

@media (max-width: 768px) {
  .features-row { grid-template-columns: repeat(2, 1fr); }
  .hero h1 { font-size: 24px; }
}

@media (max-width: 480px) {
  .features-row { grid-template-columns: 1fr; }
}
</style>
