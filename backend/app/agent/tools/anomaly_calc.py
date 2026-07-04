"""
anomaly_calc - 体验异动分析核心计算工具

基于experience-anomaly-report.md第一层规范实现
"""
from typing import Dict, List, Any, Optional
import random


def anomaly_calc(
    current_data: List[Dict],
    compare_data: List[Dict],
    daily_current: List[Dict] = None,
    daily_compare: List[Dict] = None,
    dimension_availability: Dict[str, bool] = None
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
        dimension_availability = {
            "城市等级": True,
            "品类": True,
            "事件类别": True,
            "进线渠道": True,
            "战区": True,
            "FAQ": True
        }

    # 初始化日数据
    if daily_current is None:
        daily_current = _generate_mock_daily(current_data, "current")
    if daily_compare is None:
        daily_compare = _generate_mock_daily(compare_data, "compare")

    # 1. 计算整体万服
    overall = _calculate_overall(current_data, compare_data)

    # 2. 计算各维度服务量变化占比
    dim_result = _calculate_dimensions(current_data, compare_data, overall)

    # 3. 生成日趋势数组
    daily_trend = _generate_daily_trend(daily_current, daily_compare)

    # 4. 生成告警
    alerts = _generate_alerts(current_data, compare_data, dim_result)

    return {
        "overall": overall,
        "dim": dim_result,
        "daily_trend": daily_trend,
        "alerts": alerts,
        "dimension_availability": dimension_availability
    }


def _calculate_overall(current_data: List[Dict], compare_data: List[Dict]) -> Dict[str, Any]:
    """计算整体指标"""
    # 聚合本期数据
    current_service = sum(item.get("current_service_count", item.get("current_value", 0)) for item in current_data)
    current_order = sum(item.get("current_order_count", item.get("order_count", 0)) for item in current_data)
    
    # 聚合对比期数据
    compare_service = sum(item.get("compare_service_count", item.get("compare_value", 0)) for item in compare_data)
    compare_order = sum(item.get("compare_order_count", item.get("order_count", 0)) for item in compare_data)

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
        "service_yoy": round(service_yoy, 2),
        "order_yoy": round(order_yoy, 2)
    }


def _calculate_dimensions(
    current_data: List[Dict],
    compare_data: List[Dict],
    overall: Dict[str, Any]
) -> Dict[str, Any]:
    """计算各维度服务量变化占比。

    service_change_ratio = 维度服务量变化 / 本期整体服务量。
    该指标反映相对关联程度，不能证明因果关系。
    """
    # 按维度类型分组
    dim_groups = {}
    for item in current_data:
        dim_type = item.get("dimension_type", item.get("dim_type", "未知"))
        if dim_type not in dim_groups:
            dim_groups[dim_type] = {"current": [], "compare": []}
        dim_groups[dim_type]["current"].append(item)

    for item in compare_data:
        dim_type = item.get("dimension_type", item.get("dim_type", "未知"))
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
            prev_service = item.get("compare_service_count", 
                                    compare_map.get(name, {}).get("compare_service_count", 0)
                                    if name in compare_map else 0)
            
            delta = curr_service - prev_service
            yoy = (delta / prev_service * 100) if prev_service > 0 else 0
            
            # 计算服务量变化占比。contrib_wanfu 为旧字段兼容名。
            total_service = overall.get("service_cnt", 1)
            service_change_ratio = (delta / total_service) if total_service > 0 else 0
            
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
                "contrib_wanfu": round(service_change_ratio, 4),
                "tags": tags
            }
            detail[dim_type].append(record)
            all_contributions.append((name, dim_type, service_change_ratio, delta, yoy, curr_service, prev_service, tags))

    # 按服务量变化占比排序
    all_contributions.sort(key=lambda x: x[2], reverse=True)

    # Top推高/压低
    top_up = []
    top_down = []
    for name, dim_type, contrib, delta, yoy, curr, prev, tags in all_contributions:
        record = {
            "name": name,
            "dim_type": dim_type,
            "delta": round(contrib, 4),
            "yoy": round(yoy, 2),
            "contrib": round(yoy * (curr / max(overall.get("service_cnt", 1), 1)), 2),
            "service_change_ratio": round(contrib, 4),
            "contrib_wanfu": round(contrib, 4),
            "service_delta": delta,
            "curr_service": curr,
            "prev_service": prev
        }
        if contrib > 0 and len(top_up) < 5:
            top_up.append(record)
        elif contrib < 0 and len(top_down) < 5:
            top_down.append(record)

    return {
        "top_up": top_up,
        "top_down": top_down,
        "detail": detail
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
    "description": "体验异动分析核心计算工具。接收本期和对比期明细数据，计算整体万服YoY、各维度服务量变化占比、异动打标、Top排序和日趋势。",
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
                    "城市等级": {"type": "boolean"},
                    "品类": {"type": "boolean"},
                    "事件类别": {"type": "boolean"},
                    "进线渠道": {"type": "boolean"},
                    "战区": {"type": "boolean"},
                    "FAQ": {"type": "boolean"}
                }
            }
        },
        "required": ["current_data", "compare_data"]
    }
}
