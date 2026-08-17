"""
报告接口路由
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.core import analysis_agent
from app.agent.tools.anomaly_calc import anomaly_calc
from app.agent.tools.query_friday_data import query_friday_data

router = APIRouter(prefix="/api/report", tags=["report"])


def _query_and_calculate(business: str, period: str):
    query_result = query_friday_data(
        business=business,
        period=period,
        granularity="weekly",
    )
    if "error" in query_result:
        raise ValueError(query_result["error"])

    calc_result = anomaly_calc(
        current_data=query_result["current_data"],
        compare_data=query_result["compare_data"],
        daily_current=query_result["daily_current"],
        daily_compare=query_result["daily_compare"],
        dimension_availability=query_result["dimension_availability"],
        overall_base=query_result["overall"],
    )
    return query_result, calc_result


@router.get("/generate")
async def generate_report(
    business: str = "到餐客服",
    period: str = "上周"
):
    """
    生成报告

    Args:
        business: 业务名称
        period: 时间周期

    Returns:
        报告数据
    """
    try:
        report = analysis_agent.generate_report(business, period)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data")
async def get_data(
    business: str = "到餐客服",
    dimension_type: Optional[str] = None,
    period: str = "上周"
):
    """
    查询数据

    Args:
        business: 业务名称
        dimension_type: 维度类型
        period: 时间周期

    Returns:
        数据查询结果
    """
    try:
        query_result, calc_result = _query_and_calculate(business, period)
        response = {
            "business": business,
            "period": period,
            "meta": query_result["meta"],
            "overall_base": query_result["overall"],
            "overall": calc_result["overall"],
            "dimensions": calc_result["dim"]["detail"],
            "top_up_factors": calc_result["dim"]["top_up"],
            "top_down_factors": calc_result["dim"]["top_down"],
            "daily_trend": calc_result["daily_trend"],
            "alerts": calc_result["alerts"],
            "dimension_availability": calc_result["dimension_availability"],
            "calc_result": calc_result,
        }
        if dimension_type:
            response["dimension"] = {
                "dimension_type": dimension_type,
                "items": calc_result["dim"]["detail"].get(dimension_type, []),
            }
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend")
async def get_daily_trend(
    business: str = "到餐客服",
    period: str = "上周"
):
    """
    获取日趋势

    Args:
        business: 业务名称
        period: 时间周期

    Returns:
        日趋势数据
    """
    try:
        _, calc_result = _query_and_calculate(business, period)
        return calc_result["daily_trend"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factors")
async def get_factors(
    business: str = "到餐客服",
    period: str = "上周",
    top_n: int = 3
):
    """
    获取主要因素

    Args:
        business: 业务名称
        top_n: 返回数量

    Returns:
        推高/压低因素
    """
    try:
        _, calc_result = _query_and_calculate(business, period)
        return {
            "top_up": calc_result["dim"]["top_up"][:top_n],
            "top_down": calc_result["dim"]["top_down"][:top_n],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 任务状态与失败恢复（Demo Mock） ----

from app.agent.task_state import task_store


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    """查看任务状态（含失败节点与可重试动作）。"""
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return record


@router.get("/tasks")
async def list_tasks():
    """查看全部任务状态。"""
    return {"tasks": task_store.list_tasks()}


@router.post("/retry/{task_id}")
async def retry_task(task_id: str):
    """从失败节点恢复（Demo Mock）：保留前序产物，不重新取数/计算。"""
    result = analysis_agent.retry_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
