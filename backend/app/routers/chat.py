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
from agent.core import analysis_agent, has_pending_schedule
from app.agent.tools.anomaly_calc import anomaly_calc
from app.agent.tools.query_friday_data import query_friday_data

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse_frame(event: str, data):
    """Serialize one standard SSE frame as data: {json}\n\n."""
    payload = {"event": event, "type": event, "data": data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


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

        # 确认类回复优先处理（定时任务确认词，先于意图识别/缺参追问判断）
        if analysis_agent._is_confirmation(request.message) and has_pending_schedule():
            result = analysis_agent.process_with_tools(request.message, request.history)
            inner = result.get("result", {})
            if inner.get("schedule_created"):
                task = inner["schedule_created"]
                return ChatResponse(
                    success=True,
                    message=f"已创建定时任务「{task['name']}」（业务={task['business']}，cron={task['cron']}，Demo Mock 本地配置，非真实调度）。",
                    intent="schedule_task",
                    report={"schedule_created": task},
                )
            return ChatResponse(
                success=True,
                message=inner.get("message", "已处理确认请求。"),
                intent="schedule_task",
                report=inner,
            )

        intent_result = analysis_agent.recognize_intent(request.message, request.history)
        print(f"Intent result: {intent_result}")

        # 缺参追问：LLM 判定参数不完整时，直接返回追问，不生成报告
        if intent_result.get("needs_clarification"):
            return ChatResponse(
                success=False,
                message=intent_result.get("llm_response") or "请补充业务范围和对比周期。",
                intent=intent_result.get("intent"),
            )

        # 不支持的业务：明确拒绝，不生成虚假报告
        if intent_result.get("unsupported_reason"):
            return ChatResponse(
                success=False,
                message=intent_result.get("unsupported_reason"),
                intent=intent_result.get("intent"),
            )

        intent = intent_result.get("intent", "general_chat")
        business = intent_result.get("business", "")
        period = intent_result.get("period", "")

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
            query_result = query_friday_data(business=business, period=period, granularity="weekly")
            if "error" in query_result:
                raise HTTPException(status_code=400, detail=query_result["error"])
            calc_result = anomaly_calc(
                current_data=query_result["current_data"],
                compare_data=query_result["compare_data"],
                daily_current=query_result["daily_current"],
                daily_compare=query_result["daily_compare"],
                dimension_availability=query_result["dimension_availability"],
                overall_base=query_result["overall"],
            )

            return ChatResponse(
                success=True,
                message=f"已查询{business}的数据",
                intent=intent,
                report={
                    "business": business,
                    "period": period,
                    "meta": query_result["meta"],
                    "overall_base": query_result["overall"],
                    "calc_result": calc_result,
                }
            )
        elif intent == "schedule_task":
            result = analysis_agent.process_with_tools(request.message, request.history)
            inner = result.get("result", {})
            return ChatResponse(
                success=True,
                message=inner.get("message", "已生成定时任务确认信息"),
                intent=intent,
                report=inner,
            )
        else:
            # chat 或「确认」类回复（确认 pending 定时任务）
            result = analysis_agent.process_with_tools(request.message, request.history)
            inner = result.get("result", {})
            message = inner.get("message")
            if message is None and inner.get("schedule_created"):
                message = f"已创建定时任务「{inner['schedule_created']['name']}」"
            if message is None:
                message = analysis_agent.chat(request.message, request.history)
            return ChatResponse(
                success=True,
                message=message,
                intent=intent,
                report=inner if inner.get("schedule_created") else None
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
            # 确认类回复优先处理：定时任务确认词必须先于意图识别/缺参追问处理，
            # 否则「确认」会被误判为缺少周期而进入澄清，导致确认流程中断。
            if analysis_agent._is_confirmation(request.message) and has_pending_schedule():
                result = analysis_agent.process_with_tools(request.message, request.history)
                inner = result.get("result", {})
                if inner.get("schedule_created"):
                    task = inner["schedule_created"]
                    yield _sse_frame("text", f"已创建定时任务「{task['name']}」（业务={task['business']}，cron={task['cron']}，Demo Mock 本地配置，非真实调度）。")
                elif inner.get("needs_confirmation"):
                    yield _sse_frame("text", inner.get("message", "请回复「确认」以创建定时任务"))
                elif inner.get("message"):
                    yield _sse_frame("text", inner["message"])
                else:
                    yield _sse_frame("text", "已处理确认请求。")
                yield _sse_frame("done", {"message": "完成"})
                return

            # 识别意图（支持多轮澄清槽位继承）
            intent_result = analysis_agent.recognize_intent(request.message, request.history)
            intent = intent_result.get("intent", "generate_report")
            business = intent_result.get("business", "")
            period = intent_result.get("period", "")

            # 缺参追问：LLM 判定参数不完整时，发送追问并终止后续取数/计算
            if intent_result.get("needs_clarification"):
                question = intent_result.get("llm_response") or "请补充业务范围和对比周期。"
                yield _sse_frame("thinking", {"step": "intent_recognition", "content": question})
                yield _sse_frame("done", {"message": "需要补充信息"})
                return

            # 不支持的业务：明确拒绝，不生成虚假报告
            if intent_result.get("unsupported_reason"):
                yield _sse_frame("thinking", {"step": "intent_recognition", "content": intent_result["unsupported_reason"]})
                yield _sse_frame("error", {"message": intent_result["unsupported_reason"]})
                return

            if intent == "generate_report":
                # 流式生成报告（携带 task_id 状态机）
                async for chunk in analysis_agent.generate_report_stream(business, period):
                    event = chunk.get("event") or chunk.get("type") or "text"
                    yield _sse_frame(event, chunk.get("data", {}))
            else:
                # schedule_task / query_data / chat / 确认类回复，统一走 process_with_tools
                result = analysis_agent.process_with_tools(request.message, request.history)
                inner = result.get("result", {})
                if inner.get("schedule_created"):
                    task = inner["schedule_created"]
                    yield _sse_frame("text", f"已创建定时任务「{task['name']}」（业务={task['business']}，cron={task['cron']}，Demo Mock 本地配置，非真实调度）。")
                elif inner.get("needs_confirmation"):
                    yield _sse_frame("text", inner.get("message", "请回复「确认」以创建定时任务"))
                elif inner.get("message"):
                    yield _sse_frame("text", inner["message"])
                else:
                    yield _sse_frame("text", analysis_agent.chat(request.message, request.history))
                yield _sse_frame("done", {"message": "完成"})

        except Exception as e:
            import traceback
            print(f"[STREAM ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
            yield _sse_frame("error", {"message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
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
        result = analysis_agent.recognize_intent(request.message, request.history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 定时任务配置管理（Demo Mock，本地 JSON 持久化，非真实调度） ----

from app.services.scheduled_tasks import scheduled_task_store


@router.post("/schedule/create")
async def create_scheduled_task(business: str = "到餐客服", cron: str = "0 9 * * 1", name: str = ""):
    """直接创建本地定时任务配置（供前端表单使用；自然语言路径走确认流程）。"""
    task = scheduled_task_store.create(
        name=name or f"{business}周报",
        business=business,
        cron=cron,
    )
    return {"task": task, "demo_mock": True}


@router.get("/schedule/list")
async def list_scheduled_tasks():
    """查看本地定时任务列表（Demo Mock）。"""
    return {"tasks": scheduled_task_store.list(), "demo_mock": True}


@router.post("/schedule/pause/{task_id}")
async def pause_scheduled_task(task_id: str):
    """暂停本地定时任务。"""
    task = scheduled_task_store.pause(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")
    return {"task": task}


@router.post("/schedule/resume/{task_id}")
async def resume_scheduled_task(task_id: str):
    """恢复本地定时任务。"""
    task = scheduled_task_store.resume(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")
    return {"task": task}


@router.post("/schedule/delete/{task_id}")
async def delete_scheduled_task(task_id: str):
    """删除本地定时任务。"""
    existed = scheduled_task_store.delete(task_id)
    if not existed:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")
    return {"deleted": True, "task_id": task_id}
