import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.tools.anomaly_calc import anomaly_calc
from app.agent.tools.query_friday_data import STANDARD_DIMENSIONS, query_friday_data
from app.services.demo_delivery import render_html_report, run_local_html_report_delivery


def _sample_calc():
    query = query_friday_data("到餐客服", "上周", "weekly")
    calc = anomaly_calc(
        current_data=query["current_data"],
        compare_data=query["compare_data"],
        daily_current=query["daily_current"],
        daily_compare=query["daily_compare"],
        dimension_availability=query["dimension_availability"],
        overall_base=query["overall"],
    )
    calc["alerts"] = [{"type": "extreme_value", "name": "退款进度", "desc": "Demo alert"}]
    return calc


def _sample_modules_data():
    calc = _sample_calc()
    return {
        "title": "到餐客服 上周 体验异动分析报告",
        "summary": "## Summary\nDemo summary",
        "meta": query_friday_data("到餐客服", "上周", "weekly")["meta"],
        "calc_result": calc,
        "dimension_labels": {
            "city_level": "城市等级",
            "event_category": "事件类别",
            "faq_level_6": "六级FAQ",
            "store_category_level_1": "一级门店品类",
            "incoming_channel": "进线渠道",
            "warzone_level_1": "一级战区",
        },
    }


class LocalHtmlReportDeliveryTest(unittest.TestCase):
    def test_local_html_report_generation_only(self):
        """主链路只落地本地 HTML 报告生成，不触发分发/归档。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            calc = _sample_calc()
            result = run_local_html_report_delivery(
                business="到餐客服",
                period="上周",
                calc_result=calc,
                report_prompt="## Prompt\nDemo prompt",
                summary="## Summary\nDemo summary",
                output_dir=tmpdir,
                timestamp="20260816_120000",
            )

            self.assertEqual(result.get("demo_mock"), True)
            self.assertTrue(result["report_url"].startswith("file:///"))
            self.assertEqual(result["errors"], [])
            self.assertTrue(os.path.exists(result["report_path"]))

            with open(result["report_path"], "r", encoding="utf-8") as f:
                html = f.read()
            self.assertIn("Demo Mock", html)
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("https://cdn.jsdelivr.net/npm/chart.js", html)
            self.assertIn('id="module-core-metrics"', html)
            self.assertIn('id="module-summary"', html)
            self.assertIn('id="module-daily-trend"', html)
            self.assertIn('id="module-dimensions"', html)
            self.assertIn('id="module-alerts-detail"', html)
            self.assertIn("模拟数据", html)
            # 主链路只落地本地 HTML 生成，不应包含分发/归档等产物
            self.assertNotIn("已向 WBR 群发送", html)
            self.assertNotIn("knowledge_base", html)
            self.assertNotIn("大象", html)
            self.assertNotIn("学城", html)

    def test_core_main_flow_invokes_local_html_delivery(self):
        core_path = os.path.join(BACKEND, "app", "agent", "core.py")
        with open(core_path, "r", encoding="utf-8") as f:
            source = f.read()

        self.assertIn("run_local_html_report_delivery", source)
        self.assertIn("html_result", source)
        # 不应残留旧的分发/发布函数或字段
        self.assertNotIn("run_demo_mock_delivery", source)
        self.assertNotIn("publish_result", source)

    def test_render_html_report_contains_visual_five_module_layout(self):
        modules_data = _sample_modules_data()
        html = render_html_report(modules_data)

        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<head>", html)
        self.assertIn("<style>", html)
        self.assertIn("<body>", html)
        self.assertIn("https://cdn.jsdelivr.net/npm/chart.js", html)
        self.assertIn("display: grid", html)
        self.assertIn("display: flex", html)
        self.assertIn('class="metrics-grid"', html)
        self.assertIn('class="metric-card"', html)
        self.assertIn('class="summary-panel', html)
        self.assertIn('class="alert-box"', html)
        self.assertIn('class="dimension-card"', html)
        self.assertIn('class="detail-table zebra"', html)
        self.assertIn('canvas id="trendChart"', html)
        self.assertIn('id="trendFallback"', html)
        self.assertIn("new Chart(", html)
        self.assertIn("pointRadius", html)
        for dim in STANDARD_DIMENSIONS:
            self.assertIn(f'data-dimension="{dim}"', html)
        self.assertIn("bar-positive", html)
        self.assertIn("bar-negative", html)
        self.assertIn('class="dimension-split"', html)
        self.assertIn('class="dimension-column positive-column"', html)
        self.assertIn('class="dimension-column negative-column"', html)
        self.assertIn("🔺 主要推高", html)
        self.assertIn("🔻 主要压降", html)
        # 推高/压低项必须按实际 wanfu_contribution 值渲染（mock 数据可动态变化，不写死具体数值）
        top_up = modules_data["calc_result"]["dim"]["top_up"]
        top_down = modules_data["calc_result"]["dim"]["top_down"]
        self.assertTrue(top_up, "应存在推高项")
        self.assertTrue(top_down, "应存在压降项")
        for item in top_up[:3] + top_down[:3]:
            contrib = item["wanfu_contribution"]
            sign = "+" if contrib >= 0 else "-"
            self.assertIn(f"{item['name']} ({sign}{abs(contrib):.2f} 次/万单)", html)
        self.assertIn("*按万服波动贡献排序（正值=推高，负值=压降）*", html)
        self.assertIn("wanfu_contribution", html)
        self.assertIn("<table", html)
        self.assertIn("不可用维度", html)
        self.assertIn("Demo alert", html)
        self.assertNotIn("Demo summary", html)
        self.assertNotIn("<pre", html.lower())

    def test_render_html_report_filters_tiny_dimension_impacts_only_in_module_four(self):
        modules_data = {
            "title": "过滤测试报告",
            "summary": "## Summary\nDemo summary",
            "calc_result": {
                "overall": {
                    "current": 100,
                    "compare": 98,
                    "yoy": 2.04,
                    "service_cnt": 1000,
                    "order_cnt": 100000,
                },
                "dim": {
                    "top_up": [],
                    "top_down": [],
                    "detail": {
                        "event_category": [
                            {
                                "name": "HighUp",
                                "curr_service": 20,
                                "prev_service": 5,
                                "wanfu_contribution": 1.25,
                                "service_change_ratio": 0.015,
                                "yoy": 300,
                            },
                            {
                                "name": "TinyUp",
                                "curr_service": 9,
                                "prev_service": 8,
                                "wanfu_contribution": 0.2,
                                "service_change_ratio": 0.001,
                                "yoy": 12.5,
                            },
                            {
                                "name": "HighDown",
                                "curr_service": 3,
                                "prev_service": 20,
                                "wanfu_contribution": -0.8,
                                "service_change_ratio": -0.017,
                                "yoy": -85,
                            },
                            {
                                "name": "TinyDown",
                                "curr_service": 10,
                                "prev_service": 11,
                                "wanfu_contribution": -0.3,
                                "service_change_ratio": -0.001,
                                "yoy": -9.09,
                            },
                        ],
                        "incoming_channel": [
                            {
                                "name": "OnlyTiny",
                                "curr_service": 10,
                                "prev_service": 9,
                                "wanfu_contribution": 0.1,
                                "service_change_ratio": 0.001,
                                "yoy": 11.11,
                            }
                        ],
                    },
                },
                "daily_trend": [],
                "alerts": [],
                "dimension_availability": {},
            },
        }

        html = render_html_report(modules_data)

        self.assertIn("HighUp (+1.25 次/万单)", html)
        self.assertIn("HighDown (-0.80 次/万单)", html)
        self.assertNotIn("TinyUp (+0.20 次/万单)", html)
        self.assertNotIn("TinyDown (-0.30 次/万单)", html)
        self.assertIn("波动幅度极小，建议关注其他维度。", html)
        self.assertIn("<td>TinyUp</td>", html)
        self.assertIn("<td>TinyDown</td>", html)
        self.assertNotIn("Demo summary", html)

    def test_render_html_report_keeps_dashboard_shell_for_empty_data(self):
        html = render_html_report({})

        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("暂无数据", html)
        self.assertIn('id="module-core-metrics"', html)
        self.assertIn('id="module-daily-trend"', html)
        self.assertIn('canvas id="trendChart"', html)
        self.assertIn("*基于模拟数据生成*", html)
        self.assertNotIn("<pre", html.lower())

        renderer_path = os.path.join(BACKEND, "app", "services", "demo_delivery.py")
        with open(renderer_path, "r", encoding="utf-8") as f:
            renderer_source = f.read()
        self.assertIn("为什么报告生成必须依赖于已经计算好的 modules_data", renderer_source)


if __name__ == "__main__":
    unittest.main()
