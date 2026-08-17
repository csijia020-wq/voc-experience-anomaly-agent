"""
工具定义与执行模块

整合skill定义的工具：query_friday_data 和 anomaly_calc
"""
import sys
import os
import json
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.tools import anomaly_calc, ANOMALY_CALC_TOOL
from agent.tools import query_friday_data, QUERY_FRIDAY_TOOL

logger = logging.getLogger(__name__)


# 扩展TOOLS_DEFINITION，包含skill定义的工具
TOOLS_DEFINITION = [
    # Skill工具：数据查询
    {
        "type": "function",
        "function": {
            **QUERY_FRIDAY_TOOL
        }
    },
    # Skill工具：异动计算
    {
        "type": "function",
        "function": {
            **ANOMALY_CALC_TOOL
        }
    },
    # 原有工具：业务数据查询
    {
        "type": "function",
        "function": {
            "name": "query_business_data",
            "description": "查询业务核心数据，包括万服、服务量、同比等",
            "parameters": {
                "type": "object",
                "properties": {
                    "business": {
                        "type": "string",
                        "description": "业务名称，如：到餐客服、闪购客服、企客业务"
                    },
                    "period": {
                        "type": "string",
                        "description": "时间周期，如：上周、本周、上月"
                    }
                },
                "required": ["business"]
            }
        }
    },
    # 原有工具：日趋势
    {
        "type": "function",
        "function": {
            "name": "get_daily_trend",
            "description": "获取业务日趋势数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "business": {
                        "type": "string",
                        "description": "业务名称"
                    },
                    "period": {
                        "type": "string",
                        "description": "时间周期"
                    }
                },
                "required": ["business"]
            }
        }
    },
    # 原有工具：维度因素
    {
        "type": "function",
        "function": {
            "name": "get_dimension_factors",
            "description": "获取各维度影响因素（推高/压低万服的因素）",
            "parameters": {
                "type": "object",
                "properties": {
                    "business": {
                        "type": "string",
                        "description": "业务名称"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "返回前N个因素"
                    }
                },
                "required": ["business"]
            }
        }
    }
]


def execute_tool(tool_name: str, arguments: dict) -> dict:
    """
    执行工具

    Args:
        tool_name: 工具名称
        arguments: 工具参数

    Returns:
        工具执行结果
    """
    try:
        if not isinstance(arguments, dict):
            arguments = {}

        business = arguments.get("business", "到餐客服")
        period = arguments.get("period", "上周")

        # Skill工具：query_friday_data
        if tool_name == "query_friday_data":
            result = query_friday_data(
                business=arguments.get("business", business),
                period=arguments.get("period", period),
                granularity=arguments.get("granularity", "weekly")
            )
            return result

        # Skill工具：anomaly_calc
        elif tool_name == "anomaly_calc":
            current_data = arguments.get("current_data", [])
            compare_data = arguments.get("compare_data", [])
            daily_current = arguments.get("daily_current")
            daily_compare = arguments.get("daily_compare")
            dimension_availability = arguments.get("dimension_availability")
            overall_base = arguments.get("overall_base") or arguments.get("overall")

            result = anomaly_calc(
                current_data=current_data,
                compare_data=compare_data,
                daily_current=daily_current,
                daily_compare=daily_compare,
                dimension_availability=dimension_availability,
                overall_base=overall_base
            )
            return result

        # 原有工具：query_business_data
        elif tool_name == "query_business_data":
            query_result = query_friday_data(business=business, period=period, granularity="weekly")
            if "error" in query_result:
                return query_result
            calc_result = anomaly_calc(
                current_data=query_result["current_data"],
                compare_data=query_result["compare_data"],
                daily_current=query_result["daily_current"],
                daily_compare=query_result["daily_compare"],
                dimension_availability=query_result["dimension_availability"],
                overall_base=query_result["overall"],
            )
            return {
                "business": business,
                "period": period,
                "meta": query_result["meta"],
                "overall_base": query_result["overall"],
                "calc_result": calc_result,
            }

        # 原有工具：get_daily_trend
        elif tool_name == "get_daily_trend":
            query_result = query_friday_data(business=business, period=period, granularity="weekly")
            if "error" in query_result:
                return query_result
            calc_result = anomaly_calc(
                current_data=query_result["current_data"],
                compare_data=query_result["compare_data"],
                daily_current=query_result["daily_current"],
                daily_compare=query_result["daily_compare"],
                dimension_availability=query_result["dimension_availability"],
                overall_base=query_result["overall"],
            )
            return {"trend": calc_result["daily_trend"]}

        # 原有工具：get_dimension_factors
        elif tool_name == "get_dimension_factors":
            top_n = arguments.get("top_n", 3)
            query_result = query_friday_data(business=business, period=period, granularity="weekly")
            if "error" in query_result:
                return query_result
            calc_result = anomaly_calc(
                current_data=query_result["current_data"],
                compare_data=query_result["compare_data"],
                daily_current=query_result["daily_current"],
                daily_compare=query_result["daily_compare"],
                dimension_availability=query_result["dimension_availability"],
                overall_base=query_result["overall"],
            )
            return {
                "top_up": calc_result["dim"]["top_up"][:top_n],
                "top_down": calc_result["dim"]["top_down"][:top_n],
            }

        else:
            return {"error": f"未知工具: {tool_name}"}
    except Exception as e:
        # 工具执行异常统一转化为 {"error": ...}，交由上层（generate_report_stream）检查并阻断下游，
        # 不再打印误导性的成功日志；异常细节仅写日志，避免把内部信息暴露给前端。
        logger.warning("execute_tool(%s) 执行异常: %s: %s", tool_name, type(e).__name__, e)
        return {"error": str(e)}
