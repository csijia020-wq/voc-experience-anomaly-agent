"""
query_friday_data - 数据查询工具

模拟friday-mcp数据查询
"""
from typing import Dict, List, Any, Optional
import hashlib
import os
import random
from datetime import date, datetime, timedelta


def _demo_deterministic() -> bool:
    """Demo模式默认稳定；显式设置 DEMO_DETERMINISTIC=false 才允许随机。"""
    return os.getenv("DEMO_DETERMINISTIC", "true").lower() != "false"


def _demo_seed() -> str:
    return os.getenv("DEMO_SEED", "20260702")


def _stable_seed(seed_source: str) -> int:
    return int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:8], 16)


def _rng_for(
    business: str,
    cfg: Dict[str, Any],
    comparison_type: str,
    granularity: str,
    purpose: str
):
    if not _demo_deterministic():
        return random
    seed_source = "|".join([
        business,
        cfg.get("current_label", ""),
        cfg.get("compare_label", ""),
        comparison_type,
        granularity,
        purpose,
        _demo_seed(),
    ])
    return random.Random(_stable_seed(seed_source))


def _stable_timestamp(cfg: Dict[str, Any]) -> str:
    if not _demo_deterministic():
        return datetime.now().isoformat()
    return f"demo-seed-{_demo_seed()}::{cfg.get('current_label', '')}"


def query_friday_data(
    business: str,
    period: str = "上周",
    granularity: str = "weekly"
) -> Dict[str, Any]:
    """
    查询指定业务和时间周期的体验数据

    Args:
        business: 业务名称（到餐客服/闪购客服/企客业务）
        period: 时间周期（如：上周、本月、2025-01）
        granularity: 查询粒度（weekly/daily），默认weekly

    Returns:
        查询结果JSON
    """
    # 业务验证
    valid_businesses = ["到餐客服", "闪购客服", "企客业务"]
    if business not in valid_businesses:
        return {
            "error": f"不支持的业务：{business}",
            "supported_businesses": valid_businesses
        }

    # 解析周期
    cfg = _resolve_period_config(period)

    # 生成模拟数据
    current_rng = _rng_for(business, cfg, "yoy", granularity, "current_dimension")
    compare_rng = _rng_for(business, cfg, "yoy", granularity, "compare_dimension")
    current_data = _generate_dimension_data(business, cfg["current_weeks"], "current", current_rng)
    compare_data = _generate_dimension_data(business, cfg["compare_weeks"], "compare", compare_rng)

    # 生成日粒度数据
    daily_current = _generate_daily_data(
        cfg["current_weeks"],
        "current",
        _rng_for(business, cfg, "yoy", granularity, "current_daily")
    )
    daily_compare = _generate_daily_data(
        cfg["compare_weeks"],
        "compare",
        _rng_for(business, cfg, "yoy", granularity, "compare_daily")
    )

    # 口径校验
    calibration_result = _calibration_check(current_data, compare_data)

    return {
        "current_data": current_data,
        "compare_data": compare_data,
        "daily_current": daily_current,
        "daily_compare": daily_compare,
        "calibration_result": calibration_result,
        "dimension_availability": {
            "城市等级": True,
            "品类": True,
            "事件类别": True,
            "进线渠道": True,
            "战区": True,
            "FAQ": True
        },
        "meta": {
            "dataset_id": _get_dataset_id(business, granularity),
            "query_timestamp": _stable_timestamp(cfg),
            "current_date_range": cfg.get("current_label", ""),
            "compare_date_range": cfg.get("compare_label", ""),
            "current_week": cfg["current_weeks"][0] if cfg["current_weeks"] else "",
            "compare_week": cfg["compare_weeks"][0] if cfg["compare_weeks"] else "",
            "granularity": granularity
        }
    }


def _resolve_period_config(period: str) -> Dict[str, Any]:
    """解析周期配置"""
    import re

    explicit_week = _parse_explicit_week_period(period)
    if explicit_week:
        year, week = explicit_week
        return _build_weekly_period(year, week)

    # 检查是否是YYYY-MM格式
    year_month_match = re.match(r'(\d{4})-(\d{2})', period)
    if year_month_match:
        year = int(year_month_match.group(1))
        month = int(year_month_match.group(2))
        return _build_monthly_period(year, month)

    # 预置周期
    configs = {
        "上周": {"weeks": 1, "offset": 1},
        "本周": {"weeks": 1, "offset": 0},
        "本月": {"weeks": 4, "offset": 0},
        "上月": {"weeks": 4, "offset": -1}
    }

    if period in configs:
        cfg = configs[period]
        today = datetime.now()
        target_monday = today - timedelta(days=today.weekday() + 7 * cfg["offset"])
        week_num = target_monday.isocalendar()[1]
        year = target_monday.year
        month = target_monday.month

        current_weeks = [(str(year), f"W{week_num + i}") for i in range(cfg["weeks"])]
        compare_weeks = [(str(year - 1), f"W{week_num + i}") for i in range(cfg["weeks"])]

        return {
            "current_weeks": current_weeks,
            "compare_weeks": compare_weeks,
            "current_label": f"{year}W{week_num} ({period})",
            "compare_label": f"{year-1}W{week_num} (去年同期)"
        }

    # 默认返回上周
    return _resolve_period_config("上周")


def _parse_explicit_week_period(period: str) -> Optional[tuple]:
    """解析 YYYYWww、YYYY-Www、YYYY年Ww、YYYY年第w周 等显式ISO周格式。"""
    import re

    text = (period or "").strip()
    patterns = [
        r'^(\d{4})\s*年?\s*[Ww]\s*0*(\d{1,2})$',
        r'^(\d{4})\s*[-/]\s*[Ww]\s*0*(\d{1,2})$',
        r'^(\d{4})\s*年?\s*第\s*0*(\d{1,2})\s*周$',
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        year = int(match.group(1))
        week = int(match.group(2))
        if _is_valid_iso_week(year, week):
            return year, week
    return None


def _is_valid_iso_week(year: int, week: int) -> bool:
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return False
    return True


def _build_weekly_period(year: int, week: int) -> Dict[str, Any]:
    """构建显式ISO周周期配置。"""
    compare_year = year - 1
    compare_week = week
    if not _is_valid_iso_week(compare_year, compare_week):
        compare_week = date(compare_year, 12, 28).isocalendar()[1]

    current_week = f"W{week:02d}"
    compare_week_label = f"W{compare_week:02d}"

    return {
        "current_weeks": [(str(year), current_week)],
        "compare_weeks": [(str(compare_year), compare_week_label)],
        "current_label": f"{year}{current_week}",
        "compare_label": f"{compare_year}{compare_week_label} (去年同期)"
    }


def _build_monthly_period(year: int, month: int) -> Dict[str, Any]:
    """构建月周期配置"""
    import calendar
    from datetime import datetime, timedelta

    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, calendar.monthrange(year, month)[1])

    start_monday = first_day - timedelta(days=first_day.weekday())
    if start_monday.month != month:
        start_monday = start_monday + timedelta(days=7)

    end_sunday = last_day + timedelta(days=(6 - last_day.weekday()))
    if end_sunday.month != month:
        end_sunday = end_sunday - timedelta(days=7)

    current_weeks = []
    current_date = start_monday
    while current_date <= end_sunday:
        week_num = current_date.isocalendar()[1]
        current_weeks.append((str(year), f"W{week_num}"))
        current_date += timedelta(days=7)

    compare_year = year - 1
    compare_weeks = [(str(compare_year), w[1]) for w in current_weeks]

    return {
        "current_weeks": current_weeks,
        "compare_weeks": compare_weeks,
        "current_label": f"{year}-{str(month).zfill(2)}",
        "compare_label": f"{compare_year}-{str(month).zfill(2)} (去年同期)"
    }


def _generate_dimension_data(business: str, weeks: List[tuple], period: str, rng=None) -> List[Dict]:
    """生成维度明细数据"""
    rng = rng or random
    dimensions = {
        "城市等级": ["一线城市", "二线城市", "三线城市", "四线城市", "五线城市"],
        "品类": ["到店", "外卖", "闪购", "酒旅", "优选"],
        "事件类别": ["支付问题", "退款问题", "质量问题", "账户问题", "配送问题", "会员服务"],
        "进线渠道": ["APP在线", "小程序", "电话热线"],
        "战区": ["华北战区", "华南战区", "华东战区", "华中战区", "西南战区", "西北战区"],
        "FAQ": ["订单查询", "退款进度", "优惠券使用", "账户异常", "活动咨询"]
    }

    # 业务基础值
    base_values = {
        "到餐客服": 15000,
        "闪购客服": 8000,
        "企客业务": 5000
    }
    base = base_values.get(business, 10000)

    data = []
    for dim_type, dim_values in dimensions.items():
        for dim_value in dim_values:
            # 随机生成有差异的数据
            variation = rng.uniform(0.5, 1.5)
            current_service = int(base * variation * rng.uniform(0.1, 0.3))

            if period == "compare":
                current_service = int(current_service * rng.uniform(0.85, 1.15))

            compare_service = int(current_service * rng.uniform(0.9, 1.1))
            current_order = int(current_service * rng.uniform(60, 100))
            compare_order = int(compare_service * rng.uniform(60, 100))

            data.append({
                "business": business,
                "dimension_type": dim_type,
                "dimension_value": dim_value,
                "current_service_count": current_service,
                "compare_service_count": compare_service,
                "current_order_count": current_order,
                "compare_order_count": compare_order
            })

    return data


def _generate_daily_data(weeks: List[tuple], period: str, rng=None) -> List[Dict]:
    """生成日粒度数据"""
    rng = rng or random
    dates = _dates_for_weeks(weeks)
    base_wanfu = 12.0 if period == "current" else 10.0

    result = []
    for date in dates:
        wanfu = base_wanfu + rng.uniform(-1.5, 1.5)
        result.append({
            "date": date,
            "wanfu": round(wanfu, 2),
            "service_count": rng.randint(15000, 18000),
            "order_count": rng.randint(1000000, 1200000)
        })
    return result


def _dates_for_weeks(weeks: List[tuple]) -> List[str]:
    """根据ISO周生成周一到周日的展示日期。"""
    dates = []
    for year_value, week_value in weeks:
        try:
            week_num = int(str(week_value).upper().replace("W", ""))
            week_start = date.fromisocalendar(int(year_value), week_num, 1)
        except (TypeError, ValueError):
            continue
        for offset in range(7):
            current_day = week_start + timedelta(days=offset)
            dates.append(f"{current_day.month}/{current_day.day}")

    return dates or ["3/16", "3/17", "3/18", "3/19", "3/20", "3/21", "3/22"]


def _calibration_check(current_data: List[Dict], compare_data: List[Dict]) -> Dict[str, Any]:
    """口径校验"""
    current_order = sum(item.get("current_order_count", 0) for item in current_data)
    compare_order = sum(item.get("compare_order_count", 0) for item in compare_data)

    if compare_order > 0:
        change_rate = abs(current_order - compare_order) / compare_order
        return {
            "passed": change_rate <= 0.2,
            "current_order": current_order,
            "compare_order": compare_order,
            "change_rate": round(change_rate * 100, 2)
        }

    return {"passed": True, "current_order": current_order, "compare_order": compare_order}


def _get_dataset_id(business: str, granularity: str) -> str:
    """获取数据集ID"""
    mapping = {
        ("到餐客服", "weekly"): "dacan_cs_wanfu_weekly",
        ("到餐客服", "daily"): "dacan_cs_wanfu_daily",
        ("闪购客服", "weekly"): "shangou_cs_feedback_weekly",
        ("闪购客服", "daily"): "shangou_cs_feedback_daily",
        ("企客业务", "weekly"): "qike_cs_inbound_weekly",
        ("企客业务", "daily"): "qike_cs_inbound_daily"
    }
    return mapping.get((business, granularity), "unknown_dataset")


# 工具定义（用于Function Calling）
QUERY_FRIDAY_TOOL = {
    "name": "query_friday_data",
    "description": "从魔数数据平台查询体验数据。接收业务名称和时间周期，返回本期和对比期的明细数据、日趋势和维度可用性。",
    "parameters": {
        "type": "object",
        "properties": {
            "business": {
                "type": "string",
                "description": "业务名称（到餐客服/闪购客服/企客业务）"
            },
            "period": {
                "type": "string",
                "description": "时间周期（如：上周、本月、2025-01）",
                "default": "上周"
            },
            "granularity": {
                "type": "string",
                "description": "查询粒度（weekly/daily）",
                "enum": ["weekly", "daily"],
                "default": "weekly"
            }
        },
        "required": ["business"]
    }
}
