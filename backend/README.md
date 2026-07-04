# VoC 体验异动分析 Agent

基于LLM大模型的智能体验分析助手，自动完成数据查询、指标计算、报告生成全流程。

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI入口
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型
│   ├── agent/
│   │   ├── core.py          # Agent核心逻辑
│   │   ├── tools.py         # 工具函数
│   │   └── prompts.py       # Prompt模板
│   ├── services/
│   │   ├── llm.py           # LLM服务(DeepSeek)
│   │   └── mock_data.py     # Mock数据服务
│   └── routers/
│       ├── chat.py          # 对话接口
│       └── report.py        # 报告接口
├── requirements.txt
├── .env.example
├── start.bat                # Windows启动脚本
└── start.sh                 # Linux/Mac启动脚本
```

## 快速启动

### 1. 配置API Key

编辑 `backend/.env` 文件，填入你的DeepSeek API Key：

```env
DEEPSEEK_API_KEY=your_api_key_here
```

### 2. 启动后端服务

**Windows:**
```bash
cd backend
start.bat
```

**Linux/Mac:**
```bash
cd backend
chmod +x start.sh
./start.sh
```

或手动启动：
```bash
cd backend
pip install -r requirements.txt
python -m app.main
```

### 3. 启动前端服务

前端页面位于 `project_delivery/vibe_coding_prototype.html`

使用任意HTTP服务器启动：
```bash
cd project_delivery
npx serve -l 8080 .
```

访问地址：http://localhost:8080/vibe_coding_prototype.html

## API接口

### 对话接口

**POST /api/chat/stream** - 流式对话（推荐）
```json
{
  "message": "生成到餐客服上周周报",
  "history": []
}
```

**POST /api/chat/message** - 同步对话
```json
{
  "message": "生成到餐客服上周周报",
  "business": "到餐客服",
  "period": "上周"
}
```

### 报告接口

**GET /api/report/generate** - 生成报告
```
?business=到餐客服&period=上周
```

**GET /api/report/data** - 查询数据
```
?business=到餐客服&dimension_type=城市等级
```

**GET /api/report/trend** - 获取日趋势
```
?business=到餐客服
```

**GET /api/report/factors** - 获取主要因素
```
?business=到餐客服&top_n=3
```

## Agent工作流程

```
用户输入 → 意图识别 → 数据查询 → LLM分析 → 报告生成 → 返回前端
```

1. **意图识别**: 使用LLM识别用户意图（生成报告/查询数据/定时任务/普通对话）
2. **数据查询**: 调用工具函数查询Mock数据（可替换为真实数据库）
3. **LLM分析**: 将数据输入LLM进行智能分析
4. **报告生成**: 生成结构化的分析报告
5. **流式返回**: 通过SSE逐步返回分析过程

## 扩展指南

### 连接真实数据源

修改 `app/services/mock_data.py`，替换为真实数据库查询：

```python
def query_data(self, business, dimension_type, period):
    # 替换为真实数据库查询
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ...")
    return cursor.fetchall()
```

### 添加新工具

在 `app/agent/tools.py` 中添加新工具：

```python
def new_tool(param1, param2):
    """工具描述"""
    # 工具逻辑
    return result

# 在TOOLS_DEFINITION中添加工具定义
```

### 自定义Prompt

修改 `app/agent/prompts.py` 中的Prompt模板，调整分析逻辑和输出格式。

## 技术栈

- **后端**: Python FastAPI
- **LLM**: DeepSeek API
- **前端**: HTML + TailwindCSS + ECharts
- **数据**: Mock数据（可扩展为真实数据库）

## 注意事项

1. 确保DeepSeek API Key正确配置
2. 后端服务默认端口8000，前端默认端口8080
3. 如需生产部署，建议使用Nginx反向代理
4. 流式响应需要前端支持SSE（已实现）

## API文档

启动后端服务后访问：http://localhost:8000/docs
