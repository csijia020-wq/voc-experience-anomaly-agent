"""SSE thinking-message builders."""

from typing import Any, Dict


def build_intent_thinking(business: str, period: str) -> str:
    return (
        f"用户请求生成{business}在{period}的报告。我将按照体验异动分析流程进行处理："
        "首先查询数据，然后计算异动指标，最后生成分析报告。"
    )


def build_data_query_thinking(business: str, period: str) -> str:
    return (
        f"调用魔数平台查询{business}在{period}的数据。需要获取本期和对比期的周粒度数据，"
        "以及日粒度数据用于趋势分析。查询维度包括城市等级、品类、事件类别、进线渠道、战区和FAQ。"
    )


def build_anomaly_calc_thinking(overall: Dict[str, Any] = None, calc_result: Dict[str, Any] = None) -> str:
    if not overall:
        return (
            "数据查询完成，现在进行异动计算。计算逻辑包括：1) 整体万服计算（本期vs去年同期）；"
            "2) 各维度服务量变化占比分析（识别推高/压低因素）；3) 日趋势生成；4) 异动打标和告警。"
        )

    calc_result = calc_result or {}
    return (
        f"计算结果：本期万服{overall.get('current', 0)}，对比期{overall.get('compare', 0)}，"
        f"同比{overall.get('yoy', 0)}%。推高因素有{len(calc_result.get('dim', {}).get('top_up', []))}个，"
        f"压低因素有{len(calc_result.get('dim', {}).get('top_down', []))}个。"
    )


def build_report_generation_thinking() -> str:
    return (
        "基于计算结果，我将调用LLM生成结构化报告。报告将包含核心指标、综合分析、"
        "日万服趋势、各维度分析和告警解读等模块。"
    )
