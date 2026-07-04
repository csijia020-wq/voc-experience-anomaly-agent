"""Report generation prompts."""

from typing import Any, Dict, List
import json


REPORT_SYSTEM_PROMPT = (
    "你是一个专业的体验异动分析助手。"
    "请严格基于输入的结构化计算结果生成报告，不要编造业务事件。"
)


def format_ratio_percent(value: Any) -> str:
    """Format a ratio value as percentage text."""
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def format_factors_for_prompt(factors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only report-safe fields for LLM report generation."""
    formatted = []
    for rank, item in enumerate(factors[:5], start=1):
        ratio = item.get("service_change_ratio", item.get("contrib_wanfu", 0))
        formatted.append({
            "rank": rank,
            "name": item.get("name", ""),
            "dim_type": item.get("dim_type", ""),
            "service_delta": item.get("service_delta", 0),
            "curr_service": item.get("curr_service", 0),
            "prev_service": item.get("prev_service", 0),
            "yoy": item.get("yoy", 0),
            "service_change_ratio": ratio,
            "service_change_ratio_percent": format_ratio_percent(ratio),
        })
    return formatted


def build_report_prompt(
    business: str,
    period: str,
    calc_result: Dict[str, Any],
    meta: Dict[str, Any],
) -> str:
    """Build the report-generation prompt from calculated metrics."""
    overall = calc_result.get("overall", {})
    dim = calc_result.get("dim", {})
    daily_trend = calc_result.get("daily_trend", [])
    alerts = calc_result.get("alerts", [])
    dim_avail = calc_result.get("dimension_availability", {})
    prompt_top_up = format_factors_for_prompt(dim.get("top_up", []))
    prompt_top_down = format_factors_for_prompt(dim.get("top_down", []))

    return f"""基于以下计算结果，生成体验异动分析报告。

## 基本信息
- 业务：{business}
- 周期：{period}
- 日期范围：{meta.get('current_date_range', '')} vs {meta.get('compare_date_range', '')}
- 数据声明：本报告基于模拟 VoC 数据生成，仅用于求职作品集和产品方案演示，不代表真实生产数据或业务经营结果。

## 核心指标
- 本期人工万服：{overall.get('current', 0)}
- 去年同期万服：{overall.get('compare', 0)}
- 万服同比：{overall.get('yoy', 0)}%（差 {overall.get('delta', 0)}）
- 服务量：{overall.get('service_cnt', 0)}（同比 {overall.get('service_yoy', 0)}%）
- 订单量：{overall.get('order_cnt', 0)}（同比 {overall.get('order_yoy', 0)}%）

## 推高因素 Top5（服务量增加、对整体体验指标形成向上压力的主要因素；字段 service_change_ratio 为服务量变化占比）
{json.dumps(prompt_top_up, ensure_ascii=False, indent=2)}

## 压低因素 Top5（服务量减少、对整体体验指标形成向下作用的主要因素；字段 service_change_ratio 为服务量变化占比）
{json.dumps(prompt_top_down, ensure_ascii=False, indent=2)}

## 日趋势
{json.dumps(daily_trend, ensure_ascii=False, indent=2)}

## 告警
{json.dumps(alerts, ensure_ascii=False, indent=2)}

## 维度可用性
{json.dumps(dim_avail, ensure_ascii=False, indent=2)}

## 严格约束
- 所有数字必须来自上述计算结果，不得自行重算、补算或编造。
- 所有业务原因只能基于上述维度名称和指标进行谨慎表述，不得编造外部活动、系统故障、政策变化等不存在的信息。
- 报告必须明确说明使用模拟数据。
- 服务量变化占比 = 某因素服务量变化 / 本期整体服务量。
- 报告中展示服务量变化占比时必须使用 service_change_ratio_percent，例如 0.0048 展示为 0.48%，不能写成 0.0048% 或 0.52。
- 该指标用于近似衡量因素变化与整体异动之间的相对关联，不能证明因果关系。
- 请不要使用“贡献度”“万服贡献度”“贡献了”这类旧口径，不要把相关影响写成确定因果。
- Top推高因素和Top压低因素必须严格按上述JSON数组的rank顺序输出，不要按绝对值或自行判断重新排序。
- 如果描述“第一/最大/主要”因素，只能使用rank=1的因素：推高第一名为{prompt_top_up[0].get('name') if prompt_top_up else '无'}，压低第一名为{prompt_top_down[0].get('name') if prompt_top_down else '无'}。

请按以下模块生成报告：
1. 【核心指标】- 列出关键数字
2. 【综合分析】- 总结+主要推高因素+主要压低因素
3. 【日万服趋势】- 表格形式
4. 【各维度分析】- 对各维度简要分析
5. 【告警解读】- 说明告警含义

请用中文回复。"""
