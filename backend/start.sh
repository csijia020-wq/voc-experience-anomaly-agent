#!/bin/bash
echo "========================================"
echo "VoC回声系统 - 体验异动分析Agent"
echo "========================================"
echo ""

echo "[1] 检查Python环境..."
python3 --version || { echo "错误: 未找到Python，请先安装Python 3.8+"; exit 1; }

echo ""
echo "[2] 进入后端目录..."
cd backend

echo ""
echo "[3] 安装依赖..."
pip3 install -r requirements.txt || { echo "错误: 依赖安装失败"; exit 1; }

echo ""
echo "[4] 检查.env配置..."
if [ ! -f .env ]; then
    echo "提示: 未找到.env文件，正在从.env.example复制..."
    cp .env.example .env
    echo "请编辑.env文件，填入你的DeepSeek API Key"
    read -p "按回车继续..."
fi

echo ""
echo "[5] 启动后端服务..."
echo "后端服务将在 http://localhost:8000 启动"
echo "API文档地址: http://localhost:8000/docs"
echo ""
python3 -m app.main