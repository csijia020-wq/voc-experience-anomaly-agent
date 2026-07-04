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

router = APIRouter(prefix="/api/report", tags=["report"])


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
        data = analysis_agent.data_service.query_data(business, dimension_type, period)
        return data
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
        trend = analysis_agent.data_service.get_daily_trend(business, period)
        return trend
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factors")
async def get_factors(
    business: str = "到餐客服",
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
        factors = analysis_agent.data_service.get_top_factors(business, top_n)
        return factors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))