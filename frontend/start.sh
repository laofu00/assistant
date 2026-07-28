#!/bin/bash

echo "智能助手前端启动脚本"
echo ""

# 检查Node.js是否安装
if ! command -v node &> /dev/null; then
    echo "错误: 未找到Node.js"
    echo "请安装Node.js 16或更高版本"
    echo "下载地址: https://nodejs.org/"
    exit 1
fi

# 检查npm是否安装
if ! command -v npm &> /dev/null; then
    echo "错误: 未找到npm"
    exit 1
fi

# 检查是否已安装依赖
if [ ! -d "node_modules" ]; then
    echo "正在安装依赖..."
    npm install
    if [ $? -ne 0 ]; then
        echo "错误: 依赖安装失败"
        exit 1
    fi
fi

echo "启动开发服务器..."
echo "前端将在浏览器中打开: http://localhost:8000"
echo "按 Ctrl+C 停止服务器"
echo ""

npm run dev