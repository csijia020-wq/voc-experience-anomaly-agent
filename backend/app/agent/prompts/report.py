"""Report generation prompts.

报告生成严格遵循：LLM 只基于上游确定性计算结果撰写文字，不得重算、补数或编造
外部原因；报告按固定 5 模块组织（文档 0.5 / F05）。
"""

from typing import Any, Dict, List
import json


REPORT_SYSTEM_PROMPT = (
    "你是一个专业的体验异动分析助手。"
    "请严格基于输入的结构化计算结果生成报告，不要编造业务事件。"
    "所有数字必须引用计算结果，不得自行重算、补算或改写。"
)

DIMENSION_DISPLAY_NAMES = {
    "city_level": "城市等级",
    "event_category": "事件类别",
    "faq_level_6": "六级FAQ",
    "store_category_level_1": "一级门店品类",
    "incoming_channel": "进线渠道",
    "warzone_level_1": "一级战区",
}


def format_ratio_percent(value: Any) -> str:
    """Format a ratio value as percentage text."""
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def format_factors_for_prompt(factors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only report-safe fields for LLM report generation."""
    formatted = []
    for rank, item in enumerate(factors[:3], start=1):
        ratio = item.get("service_change_ratio", 0)
        wanfu_contribution = item.get("wanfu_contribution", item.get("contrib_wanfu", 0))
        formatted.append({
            "rank": rank,
            "name": item.get("name", ""),
            "dim_type": item.get("dim_type", ""),
            "dim_label": DIMENSION_DISPLAY_NAMES.get(item.get("dim_type", ""), item.get("dim_type", "")),
            "service_delta": item.get("service_delta", 0),
            "curr_service": item.get("curr_service", 0),
            "prev_service": item.get("prev_service", 0),
            "yoy": item.get("yoy", 0),
            "wanfu_contribution": wanfu_contribution,
            "service_change_ratio": ratio,
            "service_change_ratio_percent": format_ratio_percent(ratio),
        })
    return formatted


def _format_dimension_tops(dimension_tops: Dict[str, Any]) -> str:
    """把每个维度的 Top3 推高/压低项序列化为 prompt 友好的 JSON，用于「6 维度拆解」模块。"""
    if not dimension_tops:
        return "{}"
    safe = {}
    for dim_key, tops in dimension_tops.items():
        label = DIMENSION_DISPLAY_NAMES.get(dim_key, dim_key)
        safe[label] = {
            "top_up": format_factors_for_prompt((tops or {}).get("top_up", [])),
            "top_down": format_factors_for_prompt((tops or {}).get("top_down", [])),
        }
    return json.dumps(safe, ensure_ascii=False, indent=2)


def build_report_prompt(
    business: str,
    period: str,
    calc_result: Dict[str, Any],
    meta: Dict[str, Any],
) -> str:
    """Build the report-generation prompt from calculated metrics."""
    overall = calc_result.get("overall", {})
    dim = calc_result.get("dim", {})
    # 标准字段优先（文档 5.7 数据契约）
    detail = calc_result.get("dimensions") or dim.get("detail", {})
    dimension_tops = calc_result.get("dimension_tops", {})
    daily_trend = calc_result.get("daily_trend", [])
    alerts = calc_result.get("alerts", [])
    dim_avail = calc_result.get("dimension_availability", {})
    prompt_top_up = format_factors_for_prompt(dim.get("top_up", []))
    prompt_top_down = format_factors_for_prompt(dim.get("top_down", []))
    dimension_tops_text = _format_dimension_tops(dimension_tops)

    return f"""基于以下计算结果，生成体验异动分析报告。你只负责撰写文字，所有数字必须原样引用，不得自行重算、补算、补数或编造外部原因。

## 基本信息
- 业务：{business}
- 周期：{period}
- 日期范围：{meta.get('current_date_range', '')} vs {meta.get('compare_date_range', '')}
- 数据声明：本项目使用模拟数据，仅用于作品集演示，不代表真实生产数据或真实业务结果。

## 核心指标（来自确定性计算）
- 本期万服：{overall.get('current', 0)}
- 对比期万服：{overall.get('compare', 0)}
- 万服同比：{overall.get('yoy', 0)}%（差 {overall.get('delta', 0)}）
- 服务量：{overall.get('service_cnt', 0)}（同比 {overall.get('service_yoy', 0)}%）
- 订单量：{overall.get('order_cnt', 0)}（同比 {overall.get('order_yoy', 0)}%）

## 全局推高因素 Top3（按 wanfu_contribution 排序；正值表示推高万服）
{json.dumps(prompt_top_up, ensure_ascii=False, indent=2)}

## 全局压低因素 Top3（按 wanfu_contribution 排序；负值表示压低万服）
{json.dumps(prompt_top_down, ensure_ascii=False, indent=2)}

## 6 维度拆解（每个维度的 Top3 推高/压低项，key 为维度中文名）
{dimension_tops_text}

## 日度趋势
{json.dumps(daily_trend, ensure_ascii=False, indent=2)}

## 告警与明细
{json.dumps(alerts, ensure_ascii=False, indent=2)}

## 维度可用性
{json.dumps(dim_avail, ensure_ascii=False, indent=2)}

## 严格约束
- 所有数字必须来自上述计算结果，不得自行重算、补算或编造。
- 所有业务原因只能基于上述维度名称和指标进行谨慎表述，不得编造外部活动、系统故障、政策变化等不存在的信息。
- 表达必须谨慎：可以说「关联」「可能反映」「建议关注」，不得无证据使用「导致」「证明」「必然」等确定因果措辞。
- 报告必须明确说明使用模拟数据。
- 归因排序必须使用 wanfu_contribution（万服波动贡献，单位：次/万单），不得使用 service_change_ratio 排序或替代归因。
- 万服波动贡献 = 维度项本期服务量 / 本期整体订单量 * 10000 - 维度项对比期服务量 / 对比期整体订单量 * 10000。
- 服务量变化占比 = 某因素服务量变化 / 本期整体服务量。
- service_change_ratio 只用于辅助说明服务量规模变化，不能当作万服归因，不能证明因果关系，不要使用「服务量变化占比贡献了」这类旧口径。
- 报告中展示服务量变化占比时必须使用 service_change_ratio_percent（例如 0.0048 展示为 0.48%）。
- Top 推高因素和 Top 压低因素必须严格按上述 JSON 数组的 rank 顺序输出，不要按绝对值或自行判断重新排序。
- 如果描述「第一/最大/主要」因素，只能使用 rank=1 的因素：推高第一名为{prompt_top_up[0].get('name') if prompt_top_up else '无'}，压低第一名为{prompt_top_down[0].get('name') if prompt_top_down else '无'}。
- 不同维度存在重复归因，不得跨维度简单加总。

请严格按以下 5 个模块生成报告：
1. 【核心指标】- 列出关键数字（本期/对比期万服、服务量、订单量及同比）
2. 【综合结论】- 整体变化方向、主要推高因素、主要压低因素及注意事项
3. 【日度趋势】- 本期与对比期日万服趋势及异常日期
4. 【6 维度拆解】- 逐维度展示主要波动项、变化方向和业务解释（参考上方「6 维度拆解」数据）
5. 【明细与告警】- 维度明细、不可用维度、新增/消失项、极端值和口径风险

请用中文回复。"""
