"""
配置管理模块
"""
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 加载.env文件
load_dotenv()


class Settings(BaseSettings):
    """应用配置"""
    # DeepSeek API配置
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_USE_ENV_PROXY: bool = os.getenv("DEEPSEEK_USE_ENV_PROXY", "false").lower() == "true"
    LLM_CONNECT_TIMEOUT_SECONDS: float = float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", 10))
    LLM_READ_TIMEOUT_SECONDS: float = float(os.getenv("LLM_READ_TIMEOUT_SECONDS", 60))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", 1))

    # 服务配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # 数据配置
    DATA_PATH: str = os.getenv("DATA_PATH", "../mock_data_weekly_dimension_full.csv")
    DEMO_SEED: str = os.getenv("DEMO_SEED", "20260702")
    DEMO_DETERMINISTIC: bool = os.getenv("DEMO_DETERMINISTIC", "true").lower() != "false"

    # 模型配置
    MODEL_NAME: str = DEEPSEEK_MODEL
    MAX_TOKENS: int = 4096
    TEMPERATURE: float = 0.7

    class Config:
        env_file = ".env"


settings = Settings()
