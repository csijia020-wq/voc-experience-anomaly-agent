"""
FastAPI主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import sys
import os

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from services.llm import llm_service
from routers.chat import router as chat_router
from routers.report import router as report_router

# 创建FastAPI应用
app = FastAPI(
    title="VoC 体验异动分析 Agent",
    description="基于LLM的智能体验分析助手API",
    version="1.0.0"
)

# 挂载前端静态文件（存在时才挂载：云端 API-only 部署可无 docs 目录）
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
frontend_dir = os.path.join(project_root, "docs")
frontend_index = os.path.join(frontend_dir, "index.html")
output_dir = os.path.join(project_root, "output")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# 挂载本地 HTML 报告目录（s3plus-upload 本地落地产物，可通过 http://host/reports/xxx.html 访问，
# 供前端 iframe 正常加载；不接真实 S3/CDN）
os.makedirs(output_dir, exist_ok=True)
app.mount("/reports", StaticFiles(directory=output_dir), name="reports")

# CORS 配置：显式允许 GitHub Pages 线上前端、本地开发与同源部署访问。
# 说明：allow_origins=["*"] 与 allow_credentials=True 在浏览器中不兼容（凭据模式不允许通配符），
# 因此显式列出前端来源；后端不依赖 Cookie 鉴权。
# 部署平台可通过 CORS_ORIGINS 环境变量（逗号分隔）覆盖默认列表。
_default_cors_origins = [
    "https://csijia020-wq.github.io",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080",
]
_env_cors = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _env_cors.split(",") if o.strip()] if _env_cors else _default_cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat_router)
app.include_router(report_router)


@app.get("/", include_in_schema=False)
async def root():
    """Serve the browser demo as the public entry point (docs 存在时) 或 API 说明。"""
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    return {"service": "VoC 体验异动分析 Agent API", "health": "/health"}


@app.get("/index.html", include_in_schema=False)
async def frontend_page():
    """Serve the demo page on the same path used by local static hosting."""
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    return {"service": "VoC 体验异动分析 Agent API", "health": "/health"}


@app.get("/vibe_coding_prototype.html", include_in_schema=False)
async def legacy_frontend_page():
    """Backward-compatible alias for the old prototype filename."""
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    return {"service": "VoC 体验异动分析 Agent API", "health": "/health"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "agent": "ready",
        "llm": llm_service.get_status()
    }


@app.get("/config")
async def get_config():
    """获取配置信息"""
    return {
        "model": settings.MODEL_NAME,
        "debug": settings.DEBUG
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
