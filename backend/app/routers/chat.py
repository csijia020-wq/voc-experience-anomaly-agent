"""
对话接口路由
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List
import json
import asyncio
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import ChatRequest, ChatResponse, ChatMessage
from agent.core import analysis_agent

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    发送对话消息

    Args:
        request: 对话请求

    Returns:
        对话响应
    """
    try:
        print(f"Received request: message={request.message}, history={request.history}")
        
        intent_result = analysis_agent.recognize_intent(request.message)
        print(f"Intent result: {intent_result}")

        intent = intent_result.get("intent", "general_chat")
        business = intent_result.get("business", "到餐客服")
        period = intent_result.get("period", "上周")

        if intent == "generate_report":
            report = analysis_agent.generate_report(business, period)
            print(f"Report generated successfully for {business} {period}")

            return ChatResponse(
                success=True,
                message=f"已生成{business}{period}的体验异动分析报告",
                intent=intent,
                report=report
            )
        elif intent == "query_data":
            data = analysis_agent.data_service.query_data(business)

            return ChatResponse(
                success=True,
                message=f"已查询{business}的数据",
                intent=intent,
                report=None
            )
        else:
            response = analysis_agent.chat(request.message, request.history)

            return ChatResponse(
                success=True,
                message=response,
                intent=intent
            )

    except Exception as e:
        print(f"Error in send_message: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_message(request: ChatRequest):
    """
    流式对话消息，逐步返回分析过程

    Args:
        request: 对话请求

    Returns:
        流式响应
    """
    async def generate():
        try:
            # 识别意图
            intent_result = analysis_agent.recognize_intent(request.message)
            intent = intent_result.get("intent", "generate_report")
            business = intent_result.get("business", "到餐客服")
            period = intent_result.get("period", "上周")

            if intent == "generate_report":
                # 流式生成报告
                async for chunk in analysis_agent.generate_report_stream(business, period):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            else:
                # 普通对话，直接返回
                response = analysis_agent.chat(request.message, request.history)
                yield f"data: {json.dumps({'type': 'text', 'data': response}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'data': {'message': '完成'}})}\n\n"

        except Exception as e:
            import traceback
            print(f"[STREAM ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/intent")
async def recognize_intent(request: ChatRequest):
    """
    识别用户意图

    Args:
        request: 对话请求

    Returns:
        意图识别结果
    """
    try:
        result = analysis_agent.recognize_intent(request.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))