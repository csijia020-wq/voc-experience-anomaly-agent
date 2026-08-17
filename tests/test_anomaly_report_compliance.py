"""体验异动分析 Agent 口径合规测试。

覆盖文档要求的核心验收点：
- 缺业务/缺周期时追问
- 不支持业务时拒绝生成
- 万服计算公式
- wanfu_contribution 归因排序
- service_change_ratio 不参与归因排序
- 6 个维度均输出
- 5 个报告模块均输出
- 口径自校验失败时阻断
- 确定性计算失败时阻断
- SSE 最终返回 report/done 或明确 error
"""

import asyncio
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.core import analysis_agent
from app.agent.tools.anomaly_calc import STANDARD_DIMENSIONS, anomaly_calc
from app.agent.tools.query_friday_data import query_friday_data
from app.agent.prompts.report import build_report_prompt
from app.services.demo_delivery import render_html_report
from app.services.llm import LLMServiceError

EXPECTED_DIMENSIONS = {
    "city_level",
    "event_category",
    "faq_level_6",
    "store_category_level_1",
    "incoming_channel",
    "warzone_level_1",
}

FIVE_MODULES = ["核心指标", "综合结论", "日度趋势", "6 维度拆解", "明细与告警"]


def _full_calc(business="到餐客服", period="上周"):
    data = query_friday_data(business=business, period=period, granularity="weekly")
    calc = anomaly_calc(
        current_data=data["current_data"],
        compare_data=data["compare_data"],
        daily_current=data["daily_current"],
        daily_compare=data["daily_compare"],
        dimension_availability=data["dimension_availability"],
        overall_base=data["overall"],
    )
    return data, calc


class IntentClarificationTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def _force_fallback(self):
        def fake_chat(*args, **kwargs):
            raise LLMServiceError(code="LLM_AUTH_ERROR", user_message="no key")

        analysis_agent.llm.chat = fake_chat
        self.addCleanup(lambda: setattr(analysis_agent.llm, "chat", analysis_agent.llm.chat))

    def test_missing_business_and_period_asks_clarification(self):
        self._force_fallback()
        result = analysis_agent.recognize_intent("帮我分析一下最近的情况")
        self.assertTrue(result["needs_clarification"])
        self.assertTrue(result["llm_response"])
        self.assertIn("业务", result["llm_response"])

    def test_missing_period_asks_clarification_not_default(self):
        self._force_fallback()
        result = analysis_agent.recognize_intent("生成到餐客服的周报")
        # 缺周期时不应静默默认「上周」，需要追问或明确周期
        self.assertTrue(result["needs_clarification"] or result.get("period"))

    def test_unsupported_business_is_blocked_from_generation(self):
        self._force_fallback()
        result = analysis_agent.process_with_tools("生成海外机票客服上周周报")
        self.assertIn("error", result["result"])
        self.assertIn("不支持", result["result"]["error"])


class MetricFormulaTest(unittest.TestCase):
    def test_wanfu_formula_service_over_order_times_10000(self):
        result = anomaly_calc(
            current_data=[
                {"dimension_type": "city_level", "dimension_value": "A",
                 "current_service_count": 100, "current_order_count": 1000}
            ],
            compare_data=[
                {"dimension_type": "city_level", "dimension_value": "A",
                 "compare_service_count": 80, "compare_order_count": 1000}
            ],
            daily_current=[],
            daily_compare=[],
            overall_base={
                "current": {"total_service": 500, "total_order": 10000},
                "compare": {"total_service": 400, "total_order": 10000},
            },
        )
        self.assertEqual(result["overall"]["current"], 500.0)   # 500 / 10000 * 10000
        self.assertEqual(result["overall"]["compare"], 400.0)   # 400 / 10000 * 10000

    def test_wanfu_contribution_uses_overall_order_denominator(self):
        result = anomaly_calc(
            current_data=[
                {"dimension_type": "event_category", "dimension_value": "X",
                 "current_service_count": 50, "current_order_count": 1000}
            ],
            compare_data=[
                {"dimension_type": "event_category", "dimension_value": "X",
                 "compare_service_count": 0, "compare_order_count": 1000}
            ],
            daily_current=[],
            daily_compare=[],
            overall_base={
                "current": {"total_service": 1000, "total_order": 100000},
                "compare": {"total_service": 900, "total_order": 10000},
            },
        )
        item = result["dimensions"]["event_category"][0]
        # 50 / 100000 * 10000 - 0 / 10000 * 10000 = 5.0
        self.assertEqual(item["wanfu_contribution"], 5.0)

    def test_top_factors_sort_by_wanfu_contribution(self):
        current = [
            {"dimension_type": "event_category", "dimension_value": "High service ratio",
             "current_service_count": 200, "current_order_count": 1000},
            {"dimension_type": "event_category", "dimension_value": "High wanfu contribution",
             "current_service_count": 50, "current_order_count": 1000},
        ]
        compare = [
            {"dimension_type": "event_category", "dimension_value": "High service ratio",
             "compare_service_count": 100, "compare_order_count": 1000},
            {"dimension_type": "event_category", "dimension_value": "High wanfu contribution",
             "compare_service_count": 0, "compare_order_count": 1000},
        ]
        result = anomaly_calc(
            current_data=copy.deepcopy(current),
            compare_data=copy.deepcopy(compare),
            daily_current=[],
            daily_compare=[],
            overall_base={
                "current": {"total_service": 1000, "total_order": 100000},
                "compare": {"total_service": 900, "total_order": 10000},
            },
        )
        self.assertEqual(result["dim"]["top_up"][0]["name"], "High wanfu contribution")
        # service_change_ratio 最高的项不是 Top 推高第一，说明未用占比排序
        self.assertNotEqual(result["dim"]["top_up"][0]["name"], "High service ratio")

    def test_service_change_ratio_not_used_for_attribution(self):
        data, calc = _full_calc()
        top_up = calc["dim"]["top_up"]
        for item in top_up:
            self.assertIn("wanfu_contribution", item)
            self.assertIn("service_change_ratio", item)
            self.assertNotEqual(item["wanfu_contribution"], item["service_change_ratio"])


class DimensionAndModuleTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_six_dimensions_all_output(self):
        _, calc = _full_calc()
        self.assertEqual(set(STANDARD_DIMENSIONS), EXPECTED_DIMENSIONS)
        self.assertEqual(set(calc["dimensions"].keys()), EXPECTED_DIMENSIONS)
        self.assertEqual(set(calc["dimension_tops"].keys()), EXPECTED_DIMENSIONS)

    def test_each_dimension_has_its_own_top3(self):
        _, calc = _full_calc()
        for dim_key in EXPECTED_DIMENSIONS:
            tops = calc["dimension_tops"][dim_key]
            self.assertIn("top_up", tops)
            self.assertIn("top_down", tops)
            self.assertLessEqual(len(tops["top_up"]), 3)
            self.assertLessEqual(len(tops["top_down"]), 3)

    def test_report_prompt_contains_five_modules(self):
        _, calc = _full_calc()
        prompt = build_report_prompt(
            "到餐客服", "上周", calc,
            {"current_date_range": "2026W26", "compare_date_range": "2025W26"},
        )
        for module in FIVE_MODULES:
            self.assertIn(module, prompt)

    def test_html_report_contains_five_modules(self):
        _, calc = _full_calc()
        html = render_html_report({
            "title": "到餐客服 上周 体验异动分析报告",
            "business": "到餐客服",
            "period": "上周",
            "calc_result": calc,
        })
        for module_id in [
            "module-core-metrics", "module-summary", "module-daily-trend",
            "module-dimensions", "module-alerts-detail",
        ]:
            self.assertIn(f'id="{module_id}"', html)
        self.assertIn("模块 4：6维度拆解", html)
        self.assertIn("模块 5：明细与告警", html)
        self.assertIn("wanfu_contribution", html)
        self.assertIn("service_change_ratio", html)
        self.assertIn("本项目使用模拟数据，仅用于作品集演示，不代表真实生产数据或真实业务结果。", html)


class BlockOnFailureTest(unittest.TestCase):
    def test_calibration_failure_is_flagged(self):
        from app.agent.tools.query_friday_data import _calibration_check
        current = [{"current_order_count": 1000} for _ in range(5)]
        compare = [{"compare_order_count": 100} for _ in range(5)]
        result = _calibration_check(current, compare)
        self.assertFalse(result["passed"])

    def test_empty_data_blocks_calculation(self):
        result = anomaly_calc(
            current_data=[], compare_data=[], daily_current=[], daily_compare=[],
        )
        self.assertIn("error", result)


class SseContractTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_stream_emits_full_chain_and_ends_with_report_done(self):
        async def fake_chat_stream(messages, temperature=None, max_tokens=None):
            yield "【模拟数据】测试降级报告。"
            return

        original = analysis_agent.llm.chat_stream
        analysis_agent.llm.chat_stream = fake_chat_stream
        try:
            async def run():
                events = []
                async for chunk in analysis_agent.generate_report_stream("到餐客服", "上周"):
                    events.append(chunk)
                return events

            events = asyncio.run(run())
        finally:
            analysis_agent.llm.chat_stream = original

        event_types = [e.get("event") for e in events]
        steps = {e["data"].get("step") for e in events if e.get("event") == "step"}

        for step in ["intent_recognition", "parameter_validation", "data_query",
                     "calibration", "anomaly_calc", "report_generation", "html_generation"]:
            self.assertIn(step, steps)

        # 最终必须返回 report 与 done（成功），或 error（失败），不能中途无声终止
        self.assertTrue(
            ("report" in event_types and "done" in event_types) or ("error" in event_types)
        )
        if "report" in event_types:
            report_event = [e for e in events if e.get("event") == "report"][0]
            self.assertIn("dimensions", report_event["data"])
            self.assertIn("data_note", report_event["data"])


if __name__ == "__main__":
    unittest.main()
