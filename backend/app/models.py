"""
数据模型定义
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ChatMessage(BaseModel):
    """对话消息"""
    role: str = Field(..., description="角色: user/assistant")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., description="用户消息")
    business: Optional[str] = Field(None, description="业务类型")
    period: Optional[str] = Field(None, description="时间周期")
    history: List[ChatMessage] = Field(default=[], description="历史消息")


class ChatResponse(BaseModel):
    """对话响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    report: Optional[Dict[str, Any]] = Field(None, description="报告数据")
    intent: Optional[str] = Field(None, description="识别的意图")