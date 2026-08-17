import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.tools.anomaly_calc import anomaly_calc
from app.agent.tools.query_friday_data import STANDARD_DIMENSIONS, query_friday_data


EXPECTED_DIMENSIONS = {
    "city_level",
    "event_category",
    "faq_level_6",
    "store_category_level_1",
    "incoming_channel",
    "warzone_level_1",
}


class StandardizedDataContractTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_query_friday_data_uses_only_standard_english_dimensions(self):
        data = query_friday_data("到餐客服", "上周", "weekly")
        current_dims = {row["dimension_type"] for row in data["current_data"]}
        compare_dims = {row["dimension_type"] for row in data["compare_data"]}

        self.assertEqual(set(STANDARD_DIMENSIONS), EXPECTED_DIMENSIONS)
        self.assertEqual(current_dims, EXPECTED_DIMENSIONS)
        self.assertEqual(compare_dims, EXPECTED_DIMENSIONS)
        self.assertEqual(set(data["dimension_availability"]), EXPECTED_DIMENSIONS)

    def test_anomaly_calc_preserves_standard_english_dimension_keys(self):
        data = query_friday_data("到餐客服", "上周", "weekly")
        result = anomaly_calc(
            current_data=data["current_data"],
            compare_data=data["compare_data"],
            daily_current=data["daily_current"],
            daily_compare=data["daily_compare"],
            dimension_availability=data["dimension_availability"],
            overall_base=data["overall"],
        )

        self.assertEqual(set(result["dim"]["detail"]), EXPECTED_DIMENSIONS)
        self.assertTrue(result["dim"]["top_up"] or result["dim"]["top_down"])
        for item in result["dim"]["top_up"] + result["dim"]["top_down"]:
            self.assertIn(item["dim_type"], EXPECTED_DIMENSIONS)
            self.assertIn("wanfu_contribution", item)
            self.assertIn("service_change_ratio", item)

    def test_report_router_does_not_use_deprecated_mock_data_service(self):
        report_path = os.path.join(BACKEND, "app", "routers", "report.py")
        with open(report_path, "r", encoding="utf-8") as f:
            report_source = f.read()

        self.assertNotIn("data_service", report_source)
        self.assertIn("query_friday_data", report_source)
        self.assertIn("anomaly_calc", report_source)

    def test_mock_data_service_is_marked_deprecated(self):
        mock_data_path = os.path.join(BACKEND, "app", "services", "mock_data.py")
        with open(mock_data_path, "r", encoding="utf-8") as f:
            mock_source = f.read()

        self.assertIn("@Deprecated", mock_source)
        self.assertIn("Use query_friday_data + anomaly_calc instead", mock_source)


if __name__ == "__main__":
    unittest.main()
