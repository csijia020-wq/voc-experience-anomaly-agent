"""
LLM服务 - 封装DeepSeek API调用
"""
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
import json
import logging
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """用户安全的LLM错误，detail仅写日志，不返回前端。"""

    def __init__(self, code: str, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.detail = detail


class LLMService:
    """LLM服务，封装DeepSeek API调用"""

    def __init__(self):
        timeout = httpx.Timeout(
            connect=settings.LLM_CONNECT_TIMEOUT_SECONDS,
            read=settings.LLM_READ_TIMEOUT_SECONDS,
            write=settings.LLM_CONNECT_TIMEOUT_SECONDS,
            pool=settings.LLM_CONNECT_TIMEOUT_SECONDS,
        )
        self.http_client = httpx.Client(
            timeout=timeout,
            trust_env=settings.DEEPSEEK_USE_ENV_PROXY,
        )
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            max_retries=settings.LLM_MAX_RETRIES,
            http_client=self.http_client,
        )
        self.model = settings.MODEL_NAME

    def get_status(self) -> Dict[str, Any]:
        """只返回配置状态，不发起收费模型调用。"""
        key = settings.DEEPSEEK_API_KEY or ""
        proxy_configured = any(os.getenv(name) for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"))
        return {
            "configured": bool(key and "your_" not in key),
            "key_suffix": f"****{key[-4:]}" if len(key) >= 4 and "your_" not in key else "",
            "base_url": settings.DEEPSEEK_BASE_URL,
            "model": self.model,
            "env_proxy_enabled": settings.DEEPSEEK_USE_ENV_PROXY,
            "proxy_configured": proxy_configured,
            "fallback_available": True,
        }

    def _to_service_error(self, exc: Exception) -> LLMServiceError:
        detail = f"{type(exc).__name__}: {exc}"
        code = "LLM_API_ERROR"
        user_message = "实时模型暂时不可用，系统已使用结构化计算结果生成降级报告。"

        if isinstance(exc, APITimeoutError):
            code = "LLM_TIMEOUT"
        elif isinstance(exc, APIConnectionError):
            text = str(exc).lower()
            if "tls" in text or "ssl" in text or "eof" in text:
                code = "LLM_TLS_ERROR"
            elif "name resolution" in text or "dns" in text:
                code = "LLM_DNS_ERROR"
            else:
                code = "LLM_CONNECTION_ERROR"
        elif isinstance(exc, AuthenticationError):
            code = "LLM_AUTH_ERROR"
        elif isinstance(exc, PermissionDeniedError):
            code = "LLM_PERMISSION_ERROR"
        elif isinstance(exc, RateLimitError):
            code = "LLM_RATE_LIMIT"
        elif isinstance(exc, NotFoundError):
            code = "LLM_NOT_FOUND"
        elif isinstance(exc, BadRequestError):
            code = "LLM_BAD_REQUEST"
        elif isinstance(exc, APIStatusError):
            if exc.status_code == 402:
                code = "LLM_QUOTA_ERROR"
            elif exc.status_code == 404:
                code = "LLM_NOT_FOUND"
            elif exc.status_code == 429:
                code = "LLM_RATE_LIMIT"
            else:
                code = f"LLM_HTTP_{exc.status_code}"
        elif isinstance(exc, APIError):
            code = "LLM_API_ERROR"

        logger.warning("DeepSeek call failed [%s]: %s", code, detail)
        return LLMServiceError(code=code, user_message=user_message, detail=detail)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None
    ) -> str:
        """
        同步调用LLM

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            LLM响应内容
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or settings.TEMPERATURE,
                max_tokens=max_tokens or settings.MAX_TOKENS
            )
            return response.choices[0].message.content
        except Exception as exc:
            raise self._to_service_error(exc) from exc

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None
    ) -> AsyncGenerator[str, None]:
        """
        流式调用LLM

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Yields:
            LLM响应内容块
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or settings.TEMPERATURE,
                max_tokens=max_tokens or settings.MAX_TOKENS,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise self._to_service_error(exc) from exc

    def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        tool_choice: str = "auto"
    ) -> Dict[str, Any]:
        """
        带工具调用的LLM

        Args:
            messages: 消息列表
            tools: 工具定义列表
            tool_choice: 工具选择策略

        Returns:
            包含工具调用的响应
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=settings.TEMPERATURE
            )
        except Exception as exc:
            raise self._to_service_error(exc) from exc

        message = response.choices[0].message

        result = {
            "content": message.content,
            "tool_calls": []
        }

        if message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_calls"].append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments)
                })

        return result

    def analyze_data(self, data: Dict[str, Any], prompt_template: str) -> str:
        """
        分析数据并生成报告

        Args:
            data: 数据字典
            prompt_template: 提示词模板

        Returns:
            分析结果
        """
        messages = [
            {"role": "system", "content": "你是一个专业的数据分析助手，擅长分析客户服务数据并生成洞察报告。"},
            {"role": "user", "content": prompt_template.format(data=json.dumps(data, ensure_ascii=False, indent=2))}
        ]
        return self.chat(messages)


# 单例实例
llm_service = LLMService()
