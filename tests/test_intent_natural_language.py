import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.core import analysis_agent


class NaturalLanguageIntentTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def _assert_no_llm_call(self, message):
        called = False
        original_chat = analysis_agent.llm.chat

        def fake_chat(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("intent recognition should not need LLM for demo-safe expressions")

        analysis_agent.llm.chat = fake_chat
        try:
            result = analysis_agent.recognize_intent(message)
        finally:
            analysis_agent.llm.chat = original_chat

        self.assertFalse(called)
        return result

    def test_report_synonyms_parse_without_llm(self):
        result = self._assert_no_llm_call("复盘企客业务2026年3月体验指标")
        self.assertEqual(result["intent"], "generate_report")
        self.assertEqual(result["business"], "企客业务")
        self.assertEqual(result["business_source"], "explicit_user_input")
        self.assertEqual(result["period"], "2026-03")
        self.assertEqual(result["period_source"], "explicit_user_input")
        self.assertEqual(result["comparison_type"], "yoy")
        self.assertEqual(result["granularity"], "weekly")
        self.assertFalse(result["needs_clarification"])

    def test_query_synonyms_parse_explicit_week(self):
        result = self._assert_no_llm_call("查一下闪购客服2026W2数据")
        self.assertEqual(result["intent"], "query_data")
        self.assertEqual(result["business"], "闪购客服")
        self.assertEqual(result["period"], "2026W02")
        self.assertEqual(result["period_source"], "explicit_user_input")

    def test_unsupported_business_is_explainable(self):
        result = self._assert_no_llm_call("生成海外机票客服上周周报")
        self.assertEqual(result["intent"], "generate_report")
        self.assertEqual(result["business"], "海外机票客服")
        self.assertIn("不支持", result["unsupported_reason"])


class PromptModuleTest(unittest.TestCase):
    def test_intent_prompt_contains_natural_language_examples(self):
        from app.agent.prompts.intent import build_intent_messages

        messages = build_intent_messages("帮我提取2026年W2的周报")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("拉一下", messages[1]["content"])
        self.assertIn("2026年W2", messages[1]["content"])
        self.assertIn("business_source", messages[1]["content"])
        self.assertIn("只返回 JSON", messages[1]["content"])

    def test_report_prompt_keeps_metric_constraints(self):
        from app.agent.prompts.report import build_report_prompt

        prompt = build_report_prompt(
            "到餐客服",
            "2026W02",
            {
                "overall": {"current": 1, "compare": 2, "yoy": -50, "delta": -1},
                "dim": {"top_up": [], "top_down": []},
                "daily_trend": [],
                "alerts": [],
                "dimension_availability": {},
            },
            {"current_date_range": "2026W02", "compare_date_range": "2025W02 (去年同期)"},
        )
        self.assertIn("服务量变化占比", prompt)
        self.assertIn("不能证明因果关系", prompt)
        self.assertIn("所有数字必须来自", prompt)


if __name__ == "__main__":
    unittest.main()
