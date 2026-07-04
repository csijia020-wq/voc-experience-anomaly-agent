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

# 挂载前端静态文件
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
frontend_dir = os.path.join(project_root, "project_delivery")
frontend_index = os.path.join(frontend_dir, "vibe_coding_prototype.html")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

# 注册路由
app.include_router(chat_router)
app.include_router(report_router)


@app.get("/", include_in_schema=False)
async def root():
    """Serve the browser demo as the public entry point."""
    return FileResponse(frontend_index)


@app.get("/vibe_coding_prototype.html", include_in_schema=False)
async def frontend_page():
    """Serve the demo page on the same path used by local static hosting."""
    return FileResponse(frontend_index)


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
