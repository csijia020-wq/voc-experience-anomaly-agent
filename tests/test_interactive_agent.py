"""可交互、可追踪、可恢复 Agent 能力测试。

覆盖：
- 多轮澄清（history 槽位继承，不静默默认）
- 任务状态机（task_id、失败节点、可重试动作）
- 定时任务（确认前不创建、确认后创建、CRUD、cron 提取）
- 失败恢复（retry 从 html_generation 节点继续）
- SSE 阶段携带 task_id
"""

import asyncio
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.core import analysis_agent, _pending_schedules
from app.agent.task_state import TaskStatus, task_store
from app.services.scheduled_tasks import ScheduledTaskStore, scheduled_task_store
from app.services.llm import LLMServiceError
from app.agent.tools.query_friday_data import query_friday_data
from app.agent.tools.anomaly_calc import anomaly_calc


def _patch_llm_to_fail():
    """让 LLM 调用抛异常，强制降级到规则解析（保证测试确定性）。"""
    original = analysis_agent.llm.chat

    def fake(*args, **kwargs):
        raise LLMServiceError(code="LLM_TEST_FALLBACK", user_message="test")

    analysis_agent.llm.chat = fake
    return original


def _restore_llm(original):
    analysis_agent.llm.chat = original


class MultiTurnClarificationTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_missing_business_and_period_asks(self):
        original = _patch_llm_to_fail()
        try:
            result = analysis_agent.recognize_intent("帮我生成周报")
        finally:
            _restore_llm(original)
        self.assertTrue(result["needs_clarification"])
        self.assertIn("业务", result["llm_response"])

    def test_supplement_business_still_missing_period(self):
        original = _patch_llm_to_fail()
        try:
            result = analysis_agent.recognize_intent(
                "到餐客服",
                history=[{"role": "user", "content": "帮我生成周报"}],
            )
        finally:
            _restore_llm(original)
        self.assertEqual(result["business"], "到餐客服")
        self.assertTrue(result["needs_clarification"])  # 仍缺周期
        self.assertIn("周期", result["llm_response"])

    def test_full_slots_after_multi_turn_continue(self):
        original = _patch_llm_to_fail()
        try:
            result = analysis_agent.recognize_intent(
                "上周",
                history=[
                    {"role": "user", "content": "帮我生成周报"},
                    {"role": "user", "content": "到餐客服"},
                ],
            )
        finally:
            _restore_llm(original)
        self.assertEqual(result["business"], "到餐客服")
        self.assertEqual(result["business_source"], "inherited_from_history")
        self.assertEqual(result["period"], "上周")
        self.assertFalse(result["needs_clarification"])

    def test_no_silent_default_when_history_empty(self):
        original = _patch_llm_to_fail()
        try:
            result = analysis_agent.recognize_intent("帮我生成周报", history=None)
        finally:
            _restore_llm(original)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["business"], "")


class TaskStateMachineTest(unittest.TestCase):
    def test_state_machine_and_failure_record(self):
        record = task_store.create("到餐客服", "上周")
        task_id = record["task_id"]
        self.assertEqual(record["status"], TaskStatus.CREATED)

        task_store.update(task_id, TaskStatus.CALCULATED, step="anomaly_calc", message="计算完成")
        self.assertEqual(task_store.get(task_id)["status"], TaskStatus.CALCULATED)

        task_store.fail(task_id, "html_generation", "渲染失败", "可调用 retry 重试")
        r = task_store.get(task_id)
        self.assertEqual(r["status"], TaskStatus.FAILED)
        self.assertEqual(r["failed_node"], "html_generation")
        self.assertEqual(r["retry_action"], "可调用 retry 重试")

    def test_stream_emits_task_id_per_step(self):
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

        step_events = [e for e in events if e.get("event") == "step"]
        self.assertTrue(step_events)
        task_ids = {e["data"].get("task_id") for e in step_events}
        self.assertTrue(task_ids)
        self.assertNotIn(None, task_ids)

        steps = [e["data"].get("step") for e in step_events]
        for expected in ["intent_recognition", "parameter_validation", "data_query",
                         "calibration", "anomaly_calc", "report_generation", "html_generation"]:
            self.assertIn(expected, steps)

        event_types = [e.get("event") for e in events]
        self.assertIn("report", event_types)
        self.assertIn("done", event_types)


class ScheduleTaskTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"
        _pending_schedules.clear()

    def test_extract_cron(self):
        self.assertEqual(analysis_agent._extract_cron("每周一上午9点自动生成到餐客服周报"), "0 9 * * 1")
        self.assertEqual(analysis_agent._extract_cron("每天下午3点"), "0 15 * * *")

    def test_schedule_requires_confirmation_before_create(self):
        original = _patch_llm_to_fail()
        try:
            result = analysis_agent.process_with_tools("每周一上午9点自动生成到餐客服周报")
        finally:
            _restore_llm(original)
        self.assertTrue(result["result"].get("needs_confirmation"))
        self.assertNotIn("schedule_created", result["result"])
        self.assertEqual(result["intent"]["intent"], "schedule_task")

    def test_confirmation_creates_task(self):
        original = _patch_llm_to_fail()
        try:
            analysis_agent.process_with_tools("每周一上午9点自动生成到餐客服周报")
            result = analysis_agent.process_with_tools("确认")
        finally:
            _restore_llm(original)
        self.assertIn("schedule_created", result["result"])
        task = result["result"]["schedule_created"]
        self.assertEqual(task["business"], "到餐客服")
        self.assertEqual(task["cron"], "0 9 * * 1")
        self.assertEqual(task["status"], "running")
        # 清理
        scheduled_task_store.delete(task["task_id"])

    def test_has_pending_schedule_helper_tracks_pending(self):
        from app.agent.core import has_pending_schedule
        original = _patch_llm_to_fail()
        try:
            # 尚无待确认任务时返回 False
            before = has_pending_schedule()
            analysis_agent.process_with_tools("每周一上午9点自动生成闪购客服周报")
            after_request = has_pending_schedule()
            self.assertTrue(after_request)
            # 确认后待确认队列被消费
            analysis_agent.process_with_tools("确认")
            after_confirm = has_pending_schedule()
            self.assertFalse(after_confirm)
        finally:
            _restore_llm(original)
        # 清理
        from app.services.scheduled_tasks import scheduled_task_store
        for task in scheduled_task_store.list():
            if task.get("business") == "闪购客服":
                scheduled_task_store.delete(task["task_id"])

    def test_schedule_crud(self):
        # 使用临时目录避免沙箱回收站删除拦截，也不污染 output/
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ScheduledTaskStore(file_path=os.path.join(tmpdir, "scheduled_tasks.json"))
            task = store.create(name="测试周报", business="到餐客服", cron="0 9 * * 1")
            self.assertEqual(task["status"], "running")

            self.assertTrue(any(t["task_id"] == task["task_id"] for t in store.list()))

            self.assertEqual(store.pause(task["task_id"])["status"], "paused")
            self.assertEqual(store.resume(task["task_id"])["status"], "running")
            self.assertTrue(store.delete(task["task_id"]))
            self.assertFalse(store.delete(task["task_id"]))


class RetryRecoveryTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_retry_from_html_generation_failure(self):
        data = query_friday_data("到餐客服", "上周", "weekly")
        calc = anomaly_calc(
            current_data=data["current_data"],
            compare_data=data["compare_data"],
            daily_current=data["daily_current"],
            daily_compare=data["daily_compare"],
            dimension_availability=data["dimension_availability"],
            overall_base=data["overall"],
        )

        record = task_store.create("到餐客服", "上周")
        task_id = record["task_id"]
        task_store.update(task_id, TaskStatus.REPORT_GENERATED, step="report_generation", retry_payload={
            "calc_result": calc,
            "summary": "测试摘要",
            "report_prompt": "测试 prompt",
        })
        task_store.fail(task_id, "html_generation", "模拟渲染失败", "可调用 retry 重试")

        result = analysis_agent.retry_task(task_id)
        self.assertTrue(result.get("success"))
        self.assertEqual(result["status"], TaskStatus.COMPLETED)
        self.assertTrue(result["report_url"].startswith("file:///"))
        self.assertEqual(task_store.get(task_id)["status"], TaskStatus.COMPLETED)

    def test_retry_rejects_non_failed_task(self):
        record = task_store.create("到餐客服", "上周")
        result = analysis_agent.retry_task(record["task_id"])
        self.assertIn("error", result)

    def test_calc_failure_blocks(self):
        result = anomaly_calc(current_data=[], compare_data=[], daily_current=[], daily_compare=[])
        self.assertIn("error", result)


class SkillContractTest(unittest.TestCase):
    """friday-mcp-query 与 experience-anomaly-report 的落地契约。"""

    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_query_supported_business_and_fields(self):
        data = query_friday_data("到餐客服", "上周", "weekly")
        for field in ["current_data", "compare_data", "daily_current", "daily_compare",
                      "overall", "calibration_result", "dimension_availability", "meta"]:
            self.assertIn(field, data)

    def test_query_rejects_unsupported_business(self):
        data = query_friday_data("海外机票客服", "上周", "weekly")
        self.assertIn("error", data)

    def test_query_period_parsing(self):
        for period in ["上周", "本周", "上月", "本月", "2026W02", "2026-03"]:
            data = query_friday_data("到餐客服", period, "weekly")
            self.assertNotIn("error", data)
            self.assertIn("meta", data)

    def test_anomaly_six_dimensions_and_tops(self):
        from app.agent.tools.anomaly_calc import STANDARD_DIMENSIONS
        data = query_friday_data("到餐客服", "上周", "weekly")
        calc = anomaly_calc(
            current_data=data["current_data"], compare_data=data["compare_data"],
            daily_current=data["daily_current"], daily_compare=data["daily_compare"],
            dimension_availability=data["dimension_availability"], overall_base=data["overall"],
        )
        self.assertEqual(set(calc["dimensions"].keys()), set(STANDARD_DIMENSIONS))
        self.assertEqual(set(calc["dimension_tops"].keys()), set(STANDARD_DIMENSIONS))
        for dim_key, tops in calc["dimension_tops"].items():
            self.assertLessEqual(len(tops["top_up"]), 3)
            self.assertLessEqual(len(tops["top_down"]), 3)


if __name__ == "__main__":
    unittest.main()
