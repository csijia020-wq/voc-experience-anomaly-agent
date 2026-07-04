import copy
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.tools.anomaly_calc import anomaly_calc
from app.agent.tools.query_friday_data import query_friday_data
from app.agent.core import analysis_agent


def _summary_for(business, period):
    data = query_friday_data(business=business, period=period, granularity="weekly")
    calc = anomaly_calc(
        current_data=data["current_data"],
        compare_data=data["compare_data"],
        daily_current=data["daily_current"],
        daily_compare=data["daily_compare"],
        dimension_availability=data["dimension_availability"],
    )
    return {
        "query": data,
        "overall": calc["overall"],
        "top_up": calc["dim"]["top_up"],
        "top_down": calc["dim"]["top_down"],
    }


class DemoStabilityTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_same_request_is_fully_deterministic(self):
        first = _summary_for("到餐客服", "上周")
        second = _summary_for("到餐客服", "上周")
        self.assertEqual(first, second)

    def test_reimport_like_fresh_call_keeps_same_result(self):
        first = _summary_for("到餐客服", "上周")
        third = _summary_for("到餐客服", "上周")
        self.assertEqual(first["overall"], third["overall"])
        self.assertEqual(first["top_up"], third["top_up"])

    def test_business_and_period_change_data(self):
        base = _summary_for("到餐客服", "上周")
        other_business = _summary_for("闪购客服", "上周")
        other_period = _summary_for("到餐客服", "本周")
        self.assertNotEqual(base["overall"], other_business["overall"])
        self.assertNotEqual(base["overall"], other_period["overall"])

    def test_intent_keeps_this_week_period(self):
        result = analysis_agent.recognize_intent("生成到餐客服本周周报")
        self.assertEqual(result["intent"], "generate_report")
        self.assertEqual(result["business"], "到餐客服")
        self.assertEqual(result["period"], "本周")

    def test_intent_parses_explicit_iso_week_period(self):
        result = analysis_agent.recognize_intent("帮我提取2026年W2的周报")
        self.assertEqual(result["intent"], "generate_report")
        self.assertEqual(result["business"], "到餐客服")
        self.assertEqual(result["period"], "2026W02")

    def test_query_uses_explicit_iso_week_period(self):
        data = query_friday_data(business="到餐客服", period="2026W02", granularity="weekly")
        self.assertEqual(data["meta"]["current_week"], ("2026", "W02"))
        self.assertEqual(data["meta"]["compare_week"], ("2025", "W02"))
        self.assertEqual(data["meta"]["current_date_range"], "2026W02")
        self.assertEqual(data["meta"]["compare_date_range"], "2025W02 (去年同期)")

    def test_query_daily_dates_follow_explicit_iso_week_period(self):
        data = query_friday_data(business="到餐客服", period="2026W02", granularity="weekly")
        self.assertEqual(data["daily_current"][0]["date"], "1/5")
        self.assertEqual(data["daily_current"][-1]["date"], "1/11")
        self.assertEqual(data["daily_compare"][0]["date"], "1/6")
        self.assertEqual(data["daily_compare"][-1]["date"], "1/12")


class MetricNamingTest(unittest.TestCase):
    def test_service_change_ratio_alias_keeps_old_field(self):
        current = [
            {
                "dimension_type": "品类",
                "dimension_value": "A",
                "current_service_count": 100,
                "current_order_count": 1000,
            }
        ]
        compare = [
            {
                "dimension_type": "品类",
                "dimension_value": "A",
                "compare_service_count": 80,
                "compare_order_count": 1000,
            }
        ]
        result = anomaly_calc(
            current_data=copy.deepcopy(current),
            compare_data=copy.deepcopy(compare),
            daily_current=[],
            daily_compare=[],
        )
        item = result["dim"]["top_up"][0]
        self.assertEqual(item["service_change_ratio"], 0.2)
        self.assertEqual(item["contrib_wanfu"], item["service_change_ratio"])


if __name__ == "__main__":
    unittest.main()
