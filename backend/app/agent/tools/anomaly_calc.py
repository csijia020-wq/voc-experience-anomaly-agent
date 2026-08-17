"""
anomaly_calc - 体验异动分析核心计算工具

基于experience-anomaly-report.md第一层规范实现
"""
from typing import Dict, List, Any, Optional
import random


STANDARD_DIMENSIONS = (
    "city_level",
    "event_category",
    "faq_level_6",
    "store_category_level_1",
    "incoming_channel",
    "warzone_level_1",
)

LEGACY_DIMENSION_ALIASES = {
    "城市等级": "city_level",
    "事件类别": "event_category",
    "FAQ": "faq_level_6",
    "六级FAQ": "faq_level_6",
    "品类": "store_category_level_1",
    "一级门店品类": "store_category_level_1",
    "进线渠道": "incoming_channel",
    "战区": "warzone_level_1",
    "一级战区": "warzone_level_1",
}

DIMENSION_DISPLAY_NAMES = {
    "city_level": "城市等级",
    "event_category": "事件类别",
    "faq_level_6": "六级FAQ",
    "store_category_level_1": "一级门店品类",
    "incoming_channel": "进线渠道",
    "warzone_level_1": "一级战区",
}


def _canonical_dimension_type(dim_type: str) -> str:
    return LEGACY_DIMENSION_ALIASES.get(dim_type, dim_type)


def anomaly_calc(
    current_data: List[Dict],
    compare_data: List[Dict],
    daily_current: List[Dict] = None,
    daily_compare: List[Dict] = None,
    dimension_availability: Dict[str, bool] = None,
    overall_base: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    体验异动分析核心计算工具

    Args:
        current_data: 本期明细数据
        compare_data: 对比期明细数据
        daily_current: 本期日粒度数据
        daily_compare: 对比期日粒度数据
        dimension_availability: 维度可用性清单

    Returns:
        计算结果JSON
    """
    # 初始化维度可用性
    if dimension_availability is None:
        dimension_availability = {dim: True for dim in STANDARD_DIMENSIONS}
    else:
        dimension_availability = {
            _canonical_dimension_type(dim): available
            for dim, available in dimension_availability.items()
        }

    # 初始化日数据
    if daily_current is None:
        daily_current = _generate_mock_daily(current_data, "current")
    if daily_compare is None:
        daily_compare = _generate_mock_daily(compare_data, "compare")

    # 1. 计算整体万服
    overall = _calculate_overall(current_data, compare_data, overall_base)

    # 确定性计算失败阻断：缺少有效订单基数（空数据/订单量为 0）时，禁止生成全 0 或虚构报告。
    # 由上层在收到 {"error": ...} 后阻断下游（文档 4.7 / F03 / F08）。
    if not current_data or overall.get("order_cnt", 0) <= 0:
        return {
            "error": "两期数据缺少有效订单量基数，无法计算万服，已阻断报告生成。请确认数据查询结果后重试。"
        }

    # 2. 计算各维度万服波动贡献，同时保留服务量变化占比作为辅助说明
    dim_result = _calculate_dimensions(current_data, compare_data, overall)

    # 保证固定 6 个维度始终出现在输出中：不可用/无数据的维度补空列表，交由「明细与告警」披露，
    # 不编造数据（文档 F04 / F05）。
    for dim_key in STANDARD_DIMENSIONS:
        dim_result["detail"].setdefault(dim_key, [])
        dim_result["dimension_tops"].setdefault(dim_key, {"top_up": [], "top_down": []})

    # 3. 生成日趋势数组
    daily_trend = _generate_daily_trend(daily_current, daily_compare)

    # 4. 生成告警
    alerts = _generate_alerts(current_data, compare_data, dim_result)

    # 不可用维度进入「明细与告警」，不编造数据（文档 F04 / F05）。
    for dim_key in STANDARD_DIMENSIONS:
        if dimension_availability.get(dim_key) is False:
            alerts.append({
                "type": "dimension_unavailable",
                "name": DIMENSION_DISPLAY_NAMES.get(dim_key, dim_key),
                "dimension_key": dim_key,
                "desc": "该维度当前不可用，已在明细与告警中披露，未做数据推断。",
            })

    return {
        "overall": overall,
        # 旧字段 dim，保留用于兼容旧前端/旧接口（文档要求可兼容，但建议优先使用 dimensions）
        "dim": {"top_up": dim_result["top_up"], "top_down": dim_result["top_down"], "detail": dim_result["detail"]},
        # 标准字段 dimensions：固定 6 维度的逐维度明细（文档 5.7 数据契约）
        "dimensions": dim_result["detail"],
        # 每个维度自动计算的 Top3 推高/压低项（文档 F04）
        "dimension_tops": dim_result["dimension_tops"],
        "daily_trend": daily_trend,
        "alerts": alerts,
        "dimension_availability": dimension_availability
    }


def _extract_overall_base(overall_base: Optional[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    """Normalize the independent overall base row from query_friday_data."""
    if not overall_base:
        return None

    current = overall_base.get("current", {})
    compare = overall_base.get("compare", {})
    normalized = {
        "current_service": int(current.get("total_service", current.get("service_count", 0)) or 0),
        "current_order": int(current.get("total_order", current.get("order_count", 0)) or 0),
        "compare_service": int(compare.get("total_service", compare.get("service_count", 0)) or 0),
        "compare_order": int(compare.get("total_order", compare.get("order_count", 0)) or 0),
    }
    if normalized["current_order"] > 0 and normalized["compare_order"] > 0:
        return normalized
    return None


def _derive_demo_overall_from_dimensions(current_data: List[Dict], compare_data: List[Dict]) -> Dict[str, int]:
    """Fallback for old callers that do not pass an independent overall row.

    Demo compromise: dimension rows are repeated breakdowns of the same business
    base, so summing every row would multiply the denominator by the number of
    dimensions. We aggregate one non-overlapping partition, preferring city
    level, and otherwise choose the partition with the largest order base. Real
    friday-mcp data must provide an independent overall row instead.
    """

    def aggregate(rows: List[Dict], service_key: str, order_key: str) -> Dict[str, int]:
        grouped = {}
        for row in rows:
            dim_type = _canonical_dimension_type(row.get("dimension_type", row.get("dim_type", "")))
            grouped.setdefault(dim_type, {"service": 0, "order": 0})
            grouped[dim_type]["service"] += int(row.get(service_key, 0) or 0)
            grouped[dim_type]["order"] += int(row.get(order_key, 0) or 0)

        for dim_type in ("city_level",):
            if dim_type in grouped:
                return grouped[dim_type]
        if grouped:
            return max(grouped.values(), key=lambda item: item["order"])
        return {"service": 0, "order": 0}

    current = aggregate(current_data, "current_service_count", "current_order_count")
    compare = aggregate(compare_data, "compare_service_count", "compare_order_count")
    return {
        "current_service": current["service"],
        "current_order": current["order"],
        "compare_service": compare["service"],
        "compare_order": compare["order"],
    }


def _calculate_overall(
    current_data: List[Dict],
    compare_data: List[Dict],
    overall_base: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """计算整体指标"""
    base = _extract_overall_base(overall_base) or _derive_demo_overall_from_dimensions(current_data, compare_data)
    current_service = base["current_service"]
    current_order = base["current_order"]
    compare_service = base["compare_service"]
    compare_order = base["compare_order"]

    # 计算万服
    current_wanfu = (current_service / current_order * 10000) if current_order > 0 else 0
    compare_wanfu = (compare_service / compare_order * 10000) if compare_order > 0 else 0

    # 计算YoY
    yoy = ((current_wanfu - compare_wanfu) / compare_wanfu * 100) if compare_wanfu > 0 else 0
    delta = current_wanfu - compare_wanfu

    # 服务量/订单量YoY
    service_yoy = ((current_service - compare_service) / compare_service * 100) if compare_service > 0 else 0
    order_yoy = ((current_order - compare_order) / compare_order * 100) if compare_order > 0 else 0

    return {
        "current": round(current_wanfu, 2),
        "compare": round(compare_wanfu, 2),
        "yoy": round(yoy, 2),
        "delta": round(delta, 2),
        "service_cnt": current_service,
        "order_cnt": current_order,
        "compare_service_cnt": compare_service,
        "compare_order_cnt": compare_order,
        "service_yoy": round(service_yoy, 2),
        "order_yoy": round(order_yoy, 2)
    }


def _calculate_dimensions(
    current_data: List[Dict],
    compare_data: List[Dict],
    overall: Dict[str, Any]
) -> Dict[str, Any]:
    """计算各维度万服波动贡献和服务量变化占比。

    service_change_ratio = 维度服务量变化 / 本期整体服务量。
    wanfu_contribution =
        维度项本期服务量 / 本期整体订单量 * 10000
        - 维度项对比期服务量 / 对比期整体订单量 * 10000。

    归因排序必须使用“万服波动贡献”而非“服务量变化占比”：前者使用整体
    订单量作分母，排除了订单量基数变化的干扰，能真正反映该维度项对每万单
    服务次数变好或变坏的推动。若只按服务量变化占比排序，可能把订单量同步
    扩张带来的服务量增长误判为体验恶化，从而误导业务把资源投向并非真正拉
    高万服的问题项。
    """
    # 按维度类型分组
    dim_groups = {}
    for item in current_data:
        dim_type = _canonical_dimension_type(item.get("dimension_type", item.get("dim_type", "未知")))
        if dim_type not in dim_groups:
            dim_groups[dim_type] = {"current": [], "compare": []}
        dim_groups[dim_type]["current"].append(item)

    for item in compare_data:
        dim_type = _canonical_dimension_type(item.get("dimension_type", item.get("dim_type", "未知")))
        if dim_type in dim_groups:
            dim_groups[dim_type]["compare"].append(item)

    # 计算各维度明细
    detail = {}
    all_contributions = []

    for dim_type, data in dim_groups.items():
        current_items = data["current"]
        compare_items = data["compare"]
        
        # 建立对比期索引
        compare_map = {item.get("dimension_value", item.get("name", "")): item for item in compare_items}

        detail[dim_type] = []
        for item in current_items:
            name = item.get("dimension_value", item.get("name", ""))
            curr_service = item.get("current_service_count", item.get("current_value", 0))
            prev_service = (
                compare_map.get(name, {}).get("compare_service_count")
                if name in compare_map else item.get("compare_service_count", item.get("compare_value", 0))
            )
            prev_service = int(prev_service or 0)
            
            delta = curr_service - prev_service
            yoy = (delta / prev_service * 100) if prev_service > 0 else 0
            
            # service_change_ratio 只用于辅助说明服务量规模变化，不能作为归因排序口径。
            total_service = overall.get("service_cnt", 1)
            service_change_ratio = (delta / total_service) if total_service > 0 else 0

            current_order = overall.get("order_cnt", 0)
            compare_order = overall.get("compare_order_cnt", 0)
            current_wanfu_part = (curr_service / current_order * 10000) if current_order > 0 else 0
            compare_wanfu_part = (prev_service / compare_order * 10000) if compare_order > 0 else 0
            wanfu_contribution = current_wanfu_part - compare_wanfu_part
            
            # 标签判定
            tags = []
            if prev_service == 0 and curr_service > 0:
                tags.append("new_added")
            elif curr_service == 0 and prev_service > 0:
                tags.append("disappeared")
            elif abs(yoy) > 500 and prev_service >= 10:
                tags.append("extreme_value")
            elif prev_service < 10 and curr_service > 100:
                tags.append("new_actual")

            record = {
                "name": name,
                "curr_service": curr_service,
                "prev_service": prev_service,
                "delta": delta,
                "yoy": round(yoy, 2),
                "contrib": round(yoy * (curr_service / max(overall.get("service_cnt", 1), 1)), 2),
                "service_change_ratio": round(service_change_ratio, 4),
                "wanfu_contribution": round(wanfu_contribution, 2),
                "contrib_wanfu": round(wanfu_contribution, 2),
                "tags": tags
            }
            detail[dim_type].append(record)
            all_contributions.append((
                name,
                dim_type,
                wanfu_contribution,
                service_change_ratio,
                delta,
                yoy,
                curr_service,
                prev_service,
                tags
            ))

    # 按万服波动贡献绝对值排序，Top3 正负方向分别展示。
    all_contributions.sort(key=lambda x: abs(x[2]), reverse=True)

    # Top推高/压低
    top_up = []
    top_down = []
    for name, dim_type, wanfu_contribution, service_change_ratio, delta, yoy, curr, prev, tags in all_contributions:
        record = {
            "name": name,
            "dim_type": dim_type,
            "delta": round(wanfu_contribution, 2),
            "yoy": round(yoy, 2),
            "contrib": round(yoy * (curr / max(overall.get("service_cnt", 1), 1)), 2),
            "wanfu_contribution": round(wanfu_contribution, 2),
            "service_change_ratio": round(service_change_ratio, 4),
            "contrib_wanfu": round(wanfu_contribution, 2),
            "service_delta": delta,
            "curr_service": curr,
            "prev_service": prev
        }
        if wanfu_contribution > 0 and len(top_up) < 3:
            top_up.append(record)
        elif wanfu_contribution < 0 and len(top_down) < 3:
            top_down.append(record)

    # 每个维度独立的 Top3 推高/压低（文档 F04：每个维度自动计算波动贡献度 Top3，
    # 不能只做全局 Top3 就当作 6 维度拆解）。
    dimension_tops: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for dim_type, items in detail.items():
        positive = [it for it in items if (it.get("wanfu_contribution", 0) or 0) > 0]
        negative = [it for it in items if (it.get("wanfu_contribution", 0) or 0) < 0]
        positive.sort(key=lambda x: abs(x.get("wanfu_contribution", 0)), reverse=True)
        negative.sort(key=lambda x: abs(x.get("wanfu_contribution", 0)), reverse=True)

        def _to_top(record: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "name": record.get("name", ""),
                "dim_type": dim_type,
                "wanfu_contribution": record.get("wanfu_contribution", 0),
                "service_change_ratio": record.get("service_change_ratio", 0),
                "service_delta": record.get("delta", 0),
                "curr_service": record.get("curr_service", 0),
                "prev_service": record.get("prev_service", 0),
                "yoy": record.get("yoy", 0),
                "tags": record.get("tags", []),
            }

        dimension_tops[dim_type] = {
            "top_up": [_to_top(r) for r in positive[:3]],
            "top_down": [_to_top(r) for r in negative[:3]],
        }

    return {
        "top_up": top_up,
        "top_down": top_down,
        "detail": detail,
        "dimension_tops": dimension_tops,
    }


def _generate_daily_trend(
    daily_current: List[Dict],
    daily_compare: List[Dict]
) -> List[Dict[str, Any]]:
    """生成日趋势数组"""
    if not daily_current:
        daily_current = _generate_mock_daily([], "current")
    if not daily_compare:
        daily_compare = _generate_mock_daily([], "compare")

    trend = []
    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    for i, (curr, prev) in enumerate(zip(daily_current[:7], daily_compare[:7])):
        curr_wanfu = curr.get("wanfu", curr.get("current_wanfu", 10))
        prev_wanfu = prev.get("wanfu", prev.get("compare_wanfu", 10))
        delta = curr_wanfu - prev_wanfu
        yoy = (delta / prev_wanfu * 100) if prev_wanfu > 0 else 0

        trend.append({
            "date": f"{days[i]} {curr.get('date', '')}",
            "curr_wanfu": round(curr_wanfu, 2),
            "prev_wanfu": round(prev_wanfu, 2),
            "yoy": round(yoy, 2),
            "delta": round(delta, 2)
        })

    return trend


def _generate_alerts(
    current_data: List[Dict],
    compare_data: List[Dict],
    dim_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """生成告警列表"""
    alerts = []

    # 检查新增维度
    curr_names = {item.get("dimension_value", item.get("name")) for item in current_data}
    prev_names = {item.get("dimension_value", item.get("name")) for item in compare_data}

    new_categories = curr_names - prev_names
    for name in new_categories:
        alerts.append({
            "type": "new_category",
            "name": name,
            "desc": "本期新增维度分类"
        })

    # 检查极端值
    for dim_type, items in dim_result.get("detail", {}).items():
        for item in items:
            if "extreme_value" in item.get("tags", []):
                alerts.append({
                    "type": "extreme_value",
                    "name": item["name"],
                    "yoy": item["yoy"],
                    "desc": f"变化幅度过大（YoY {item['yoy']}%）"
                })

    return alerts


def _generate_mock_daily(data: List[Dict], period: str) -> List[Dict[str, Any]]:
    """生成模拟日数据"""
    dates = ["3/16", "3/17", "3/18", "3/19", "3/20", "3/21", "3/22"]
    base_wanfu = 12.0 if period == "current" else 10.0

    result = []
    for i, date in enumerate(dates):
        wanfu = base_wanfu + random.uniform(-1.5, 1.5)
        result.append({
            "date": date,
            "wanfu": round(wanfu, 2),
            "service_count": random.randint(15000, 18000),
            "order_count": random.randint(1000000, 1200000)
        })
    return result


# 工具定义（用于Function Calling）
ANOMALY_CALC_TOOL = {
    "name": "anomaly_calc",
    "description": "体验异动分析核心计算工具。接收本期和对比期明细数据及整体基数，计算整体万服YoY、各维度万服波动贡献、服务量变化占比、异动打标、Top排序和日趋势。",
    "parameters": {
        "type": "object",
        "properties": {
            "current_data": {
                "type": "array",
                "description": "本期明细数据列表"
            },
            "compare_data": {
                "type": "array", 
                "description": "对比期明细数据列表"
            },
            "daily_current": {
                "type": "array",
                "description": "本期日粒度数据（可选）"
            },
            "daily_compare": {
                "type": "array",
                "description": "对比期日粒度数据（可选）"
            },
            "dimension_availability": {
                "type": "object",
                "description": "维度可用性清单（可选）",
                "properties": {
                    "city_level": {"type": "boolean"},
                    "event_category": {"type": "boolean"},
                    "faq_level_6": {"type": "boolean"},
                    "store_category_level_1": {"type": "boolean"},
                    "incoming_channel": {"type": "boolean"},
                    "warzone_level_1": {"type": "boolean"}
                }
            },
            "overall_base": {
                "type": "object",
                "description": "独立整体基数。包含本期/对比期 total_service 和 total_order，避免重复汇总维度行。",
                "properties": {
                    "current": {"type": "object"},
                    "compare": {"type": "object"}
                }
            }
        },
        "required": ["current_data", "compare_data"]
    }
}
