"""
Mock数据服务 - 模拟数据查询
"""
import pandas as pd
import os
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import random


class MockDataService:
    """Mock数据服务，模拟真实的数据查询"""

    # 历史问题：CSV 用中文列名（业务名称、本期服务量…），而 query_data 等
    # 方法按英文列名（business、current_service_count…）取值，导致 KeyError。
    # 这里在读取时统一做列名标准化，所有读取路径只需面对英文列名。
    COLUMN_MAP = {
        "业务名称": "business",
        "维度类型": "dimension_type",
        "维度值": "dimension_value",
        "本期服务量": "current_service_count",
        "对比期服务量": "compare_service_count",
        "本期订单量": "current_order_count",
        "对比期订单量": "compare_order_count",
        "本期万服": "current_wanfu",
        "对比期万服": "compare_wanfu",
        "YoY%": "yoy_change",
        "贡献度%": "contribution",
        "年份": "year",
        "周次": "week",
        "开始日期": "start_date",
        "结束日期": "end_date",
        "周类型": "week_type",
        "绝对差(delta)": "delta",
    }

    # 历史问题：之前所有 path 都写死成"上周"=W12，并硬编码 date_range。
    # 这里按 period 解析要使用的周次集合和日期标签，让"本月/上月"也能正常出月报。
    PERIOD_CONFIG = {
        "上周": {
            "current_weeks": [("2026", "W12")],
            "compare_weeks": [("2025", "W12")],
            "current_label": "2026W12 (2026-03-16 ~ 2026-03-22)",
            "compare_label": "2025W12 (2025-03-17 ~ 2025-03-23)",
            "trend_days": 7,
            "granularity": "weekly",
        },
        "本周": {
            "current_weeks": [("2026", "W12")],
            "compare_weeks": [("2025", "W12")],
            "current_label": "2026W12 (2026-03-16 ~ 2026-03-22)",
            "compare_label": "2025W12 (2025-03-17 ~ 2025-03-23)",
            "trend_days": 7,
            "granularity": "weekly",
        },
        "本月": {
            "current_weeks": [("2026", "W10"), ("2026", "W11"), ("2026", "W12"), ("2026", "W13")],
            "compare_weeks": [("2025", "W10"), ("2025", "W11"), ("2025", "W12"), ("2025", "W13")],
            "current_label": "2026-03 (本月)",
            "compare_label": "2025-03 (去年同期)",
            "trend_days": 30,
            "granularity": "monthly",
        },
        "上月": {
            "current_weeks": [("2026", "W5"), ("2026", "W6"), ("2026", "W7"), ("2026", "W8"), ("2026", "W9")],
            "compare_weeks": [("2025", "W5"), ("2025", "W6"), ("2025", "W7"), ("2025", "W8"), ("2025", "W9")],
            "current_label": "2026-02 (上月)",
            "compare_label": "2025-02 (去年同期)",
            "trend_days": 30,
            "granularity": "monthly",
        },
    }

    def __init__(self, data_path: str = None):
        self.data_path = data_path or "../mock_data_weekly_dimension_full.csv"
        self._data_cache = None

    def _demo_deterministic(self) -> bool:
        return os.getenv("DEMO_DETERMINISTIC", "true").lower() != "false"

    def _rng_for(self, business: str, period: str, purpose: str):
        if not self._demo_deterministic():
            return random
        seed_source = f"{business}|{period}|{purpose}|{os.getenv('DEMO_SEED', '20260702')}"
        seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:8], 16)
        return random.Random(seed)

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """将中文列名标准化为代码内部使用的英文列名。"""
        rename = {cn: en for cn, en in self.COLUMN_MAP.items() if cn in df.columns}
        if rename:
            df = df.rename(columns=rename)
        return df

    def _resolve_period(self, period: str) -> dict:
        """
        根据用户输入的 period 解析出要使用的数据范围。
        若 period 不在预置集合中（如自定义或YYYY-MM格式），动态计算。
        """
        if period in self.PERIOD_CONFIG:
            return self.PERIOD_CONFIG[period]

        import re
        year_month_match = re.match(r'(\d{4})-(\d{2})', period)
        if year_month_match:
            year = int(year_month_match.group(1))
            month = int(year_month_match.group(2))
            return self._build_monthly_period(year, month)

        return self.PERIOD_CONFIG["上周"]

    def _build_monthly_period(self, year: int, month: int) -> dict:
        """
        动态构建指定年月的周期配置。
        
        Args:
            year: 年份
            month: 月份
            
        Returns:
            周期配置字典
        """
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
        
        current_label = f"{year}-{str(month).zfill(2)}"
        compare_label = f"{compare_year}-{str(month).zfill(2)} (去年同期)"
        
        return {
            "current_weeks": current_weeks,
            "compare_weeks": compare_weeks,
            "current_label": current_label,
            "compare_label": compare_label,
            "trend_days": calendar.monthrange(year, month)[1],
            "granularity": "monthly",
        }

    def get_date_range(self, business: str, period: str) -> str:
        """返回报告头部的 date_range 文本，例如 "2026-03 (本月) vs 2025-03 (去年同期)"。"""
        cfg = self._resolve_period(period)
        return f"{cfg['current_label']} vs {cfg['compare_label']}"

    def _load_data(self) -> pd.DataFrame:
        """加载数据"""
        if self._data_cache is not None:
            return self._data_cache

        # 尝试加载CSV文件，如果不存在则生成模拟数据
        try:
            if os.path.exists(self.data_path):
                df = pd.read_csv(self.data_path)
                df = self._normalize_columns(df)
                self._data_cache = df
                return df
        except Exception:
            pass

        # 生成模拟数据
        return self._generate_mock_data()

    def _generate_mock_data(self) -> pd.DataFrame:
        """生成模拟数据"""
        businesses = ["到餐客服", "闪购客服", "企客业务"]
        dimensions = {
            "城市等级": ["一线城市", "二线城市", "三线城市", "四线城市", "五线城市"],
            "品类": ["到店", "外卖", "闪购", "酒旅", "优选"],
            "事件类别": ["支付问题", "退款问题", "质量问题", "账户问题", "配送问题", "会员服务"],
            "进线渠道": ["APP在线", "小程序", "电话热线"],
            "战区": ["华北战区", "华南战区", "华东战区", "华中战区", "西南战区", "西北战区"]
        }

        # 计算上周和去年同期
        today = datetime.now()
        # 上周周一
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_week_num = last_monday.isocalendar()[1]
        last_year = last_monday.year

        rng = self._rng_for("all", "generated", "mock_data")
        rows = []
        for business in businesses:
            for dim_type, dim_values in dimensions.items():
                for dim_value in dim_values:
                    # 生成随机但有合理范围的数据
                    base_service_count = rng.randint(2000, 20000)
                    yoy_change = rng.uniform(-0.15, 0.15)

                    current_count = base_service_count
                    compare_count = int(current_count / (1 + yoy_change))

                    # 计算万服
                    base_wanfu = rng.uniform(10, 15)
                    current_wanfu = base_wanfu + rng.uniform(-2, 2)
                    compare_wanfu = current_wanfu / (1 + yoy_change)

                    rows.append({
                        "business": business,
                        "dimension_type": dim_type,
                        "dimension_value": dim_value,
                        "current_period": f"{last_year}W{last_week_num}",
                        "compare_period": f"{last_year-1}W{last_week_num}",
                        "current_service_count": current_count,
                        "compare_service_count": compare_count,
                        "current_wanfu": round(current_wanfu, 2),
                        "compare_wanfu": round(compare_wanfu, 2),
                        "yoy_change": round(yoy_change * 100, 2),
                        "contribution": round(rng.uniform(-3, 3), 2)
                    })

        df = pd.DataFrame(rows)
        self._data_cache = df
        return df

    def query_data(
        self,
        business: str,
        dimension_type: Optional[str] = None,
        period: str = "上周"
    ) -> Dict[str, Any]:
        """
        查询数据

        Args:
            business: 业务名称
            dimension_type: 维度类型（可选）
            period: 时间周期

        Returns:
            查询结果
        """
        try:
            df = self._load_data()

            if "business" not in df.columns:
                raise KeyError("business")

            df_filtered = df[df["business"] == business]

            # 按 period 过滤：只保留本期 / 对比期需要聚合的周次
            cfg = self._resolve_period(period)
            cur_keys = {(str(y), str(w)) for y, w in cfg["current_weeks"]}
            cmp_keys = {(str(y), str(w)) for y, w in cfg["compare_weeks"]}
            keep_keys = cur_keys | cmp_keys
            has_year_week = {"year", "week"}.issubset(df_filtered.columns)
            if has_year_week and keep_keys:
                _yw = list(zip(df_filtered["year"].astype(str), df_filtered["week"].astype(str)))
                df_filtered = df_filtered[[k in keep_keys for k in _yw]]

            if dimension_type:
                df_filtered = df_filtered[df_filtered["dimension_type"] == dimension_type]

            if df_filtered.empty:
                return {"error": f"未找到业务 {business} 的数据"}

            total_current_service = df_filtered[df_filtered["dimension_type"] == "城市等级"]["current_service_count"].sum()
            total_compare_service = df_filtered[df_filtered["dimension_type"] == "城市等级"]["compare_service_count"].sum()

            wanfu_data = df_filtered[df_filtered["dimension_type"] == "城市等级"]
            if total_current_service > 0:
                total_current_wanfu = (wanfu_data["current_wanfu"] * wanfu_data["current_service_count"]).sum() / total_current_service
            else:
                total_current_wanfu = 0

            if total_compare_service > 0:
                total_compare_wanfu = (wanfu_data["compare_wanfu"] * wanfu_data["compare_service_count"]).sum() / total_compare_service
            else:
                total_compare_wanfu = 0

            if total_compare_wanfu != 0:
                yoy = ((total_current_wanfu - total_compare_wanfu) / total_compare_wanfu) * 100
            else:
                yoy = 0

            # 推导本期/对比期标签：直接使用 PERIOD_CONFIG 里的标准化标签。
            # 旧逻辑从 CSV 行里挑"本期重点分析"行，导致不管用户问什么，标签都固定为 W12。
            current_period_value = cfg["current_label"]
            compare_period_value = cfg["compare_label"]

            rng = self._rng_for(business, period, "query_data")
            return {
                "business": business,
                "period": period,
                "current_period": current_period_value,
                "compare_period": compare_period_value,
                "current_wanfu": round(total_current_wanfu, 2),
                "compare_wanfu": round(total_compare_wanfu, 2),
                "yoy": round(yoy, 2),
                "service_count": int(total_current_service),
                "service_yoy": round(((total_current_service - total_compare_service) / max(total_compare_service, 1)) * 100, 2),
                "order_count": rng.randint(3500000, 4000000),
                "order_yoy": round(rng.uniform(-5, 5), 2),
                "dimensions": self._get_dimensions_data(df_filtered)
            }
        except Exception as e:
            print(f"[ERROR] query_data failed: {e}")
            return {"error": str(e)}

    def _get_dimensions_data(self, df: pd.DataFrame) -> Dict[str, List[Dict]]:
        """获取各维度数据"""
        dimensions = {}
        dimension_types = df["dimension_type"].unique()

        for dim_type in dimension_types:
            dim_df = df[df["dimension_type"] == dim_type].copy()
            dim_df = dim_df.sort_values("yoy_change", ascending=False)

            dimensions[dim_type] = []
            for _, row in dim_df.iterrows():
                dimensions[dim_type].append({
                    "name": row["dimension_value"],
                    "current_value": row["current_service_count"],
                    "compare_value": row["compare_service_count"],
                    "delta": row["current_service_count"] - row["compare_service_count"],
                    "yoy": row["yoy_change"],
                    "contribution": row["contribution"]
                })

        return dimensions

    def get_daily_trend(self, business: str, period: str = "上周") -> List[Dict]:
        """
        获取日/周趋势数据。
        - 周期为"上周/本周/自定义"时：返回 7 天日趋势
        - 周期为"本月/上月"时：返回 4~5 个周聚合点（一个点对应一周），保证趋势图能看到完整的月度波动
        """
        cfg = self._resolve_period(period)
        n = cfg["trend_days"]
        granularity = cfg["granularity"]
        today = datetime.now()
        last_monday = today - timedelta(days=today.weekday() + 7)

        # 锚点：周报用上周一，月报用本期首周的周一
        if granularity == "weekly":
            anchor = last_monday
            n_points = 7
            label_fmt = lambda d: f"{d.month}/{d.day}"
        else:
            # 本月/上月：以"本期"第一周作为锚点
            anchor = last_monday  # 仍以 W12 周一为锚，趋势起点保持稳定
            n_points = max(4, len(cfg["current_weeks"]))
            label_fmt = lambda d: f"W{d.isocalendar()[1]}"

        rng = self._rng_for(business, period, "daily_trend")
        trend = []
        base_wanfu = rng.uniform(11, 13)
        # 每月/每周的"天"长度
        per_point = max(1, n // n_points)

        for i in range(n_points):
            date = anchor + timedelta(days=i * per_point)
            current_wanfu = base_wanfu + rng.uniform(-1.2, 1.2)
            compare_wanfu = current_wanfu - rng.uniform(0.5, 1.5)
            yoy = ((current_wanfu - compare_wanfu) / compare_wanfu) * 100
            trend.append({
                "date": label_fmt(date),
                "current_wanfu": round(current_wanfu, 2),
                "compare_wanfu": round(compare_wanfu, 2),
                "yoy": round(yoy, 2)
            })

        return trend

    def get_top_factors(self, business: str, top_n: int = 3) -> Dict[str, List[Dict]]:
        """获取推高/压低万服的主要因素"""
        df = self._load_data()
        df_filtered = df[df["business"] == business]

        # 按同比排序
        df_sorted = df_filtered.sort_values("yoy_change", ascending=False)

        # 推高因素
        top_up = []
        for _, row in df_sorted.head(top_n).iterrows():
            top_up.append({
                "name": row["dimension_value"],
                "dim_type": row["dimension_type"],
                "yoy": row["yoy_change"],
                "delta": int(row["current_service_count"] - row["compare_service_count"])
            })

        # 压低因素
        top_down = []
        for _, row in df_sorted.tail(top_n).iterrows():
            if row["yoy_change"] < 0:
                top_down.append({
                    "name": row["dimension_value"],
                    "dim_type": row["dimension_type"],
                    "yoy": abs(row["yoy_change"]),
                    "delta": int(row["current_service_count"] - row["compare_service_count"])
                })

        return {
            "top_up": top_up,
            "top_down": top_down
        }


# 单例实例
mock_data_service = MockDataService()
