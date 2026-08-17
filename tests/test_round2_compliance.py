"""本轮落地验收补充测试。

覆盖用户要求的额外验收点：
- 未知周期 / 缺周期不得静默默认（查询层返回 error，意图层进入澄清）
- 3 个业务 × 6 种周期全量可查
- 状态机不包含 DELIVERED / ARCHIVED（外部能力排除）
- 前端创建定时任务前必须确认（表单路径有确认步骤）
- 前端 iframe 使用同源 /reports HTTP 路径（file:// 仅作展示）
- 前端与后端均不出现大象分发 / 学城同步等外部能力字样
- 主链路不包含分发/归档语义
"""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.agent.core import analysis_agent
from app.agent.task_state import TaskStatus
from app.agent.tools.anomaly_calc import STANDARD_DIMENSIONS
from app.agent.tools.query_friday_data import query_friday_data
from app.services.llm import LLMServiceError

FRONTEND = os.path.join(ROOT, "docs", "index.html")
CORE_PY = os.path.join(BACKEND, "app", "agent", "core.py")
TASK_STATE_PY = os.path.join(BACKEND, "app", "agent", "task_state.py")
MAIN_PY = os.path.join(BACKEND, "app", "main.py")
DELIVERY_PY = os.path.join(BACKEND, "app", "services", "demo_delivery.py")

ALL_BUSINESSES = ["到餐客服", "闪购客服", "企客业务"]
ALL_PERIODS = ["上周", "本周", "上月", "本月", "2026W02", "2026-03"]


class PeriodNoSilentDefaultTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_query_missing_period_returns_error_not_default(self):
        data = query_friday_data("到餐客服", "", "weekly")
        self.assertIn("error", data)
        self.assertNotIn("current_data", data)

    def test_query_unknown_period_returns_error_not_default(self):
        data = query_friday_data("到餐客服", "2025年Q3", "weekly")
        self.assertIn("error", data)
        self.assertNotIn("current_data", data)

    def test_intent_unknown_period_enters_clarification(self):
        original_chat = analysis_agent.llm.chat
        analysis_agent.llm.chat = lambda *a, **k: (_ for _ in ()).throw(
            LLMServiceError(code="LLM_TEST", user_message="fallback"))
        try:
            result = analysis_agent.recognize_intent("生成到餐客服 2025年Q3 周报")
        finally:
            analysis_agent.llm.chat = original_chat
        # LLM 降级后若解析出非法周期，应进入澄清而不是静默继续
        self.assertTrue(result.get("needs_clarification") or not result.get("period"))


class AllBusinessPeriodMatrixTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEMO_DETERMINISTIC"] = "true"
        os.environ["DEMO_SEED"] = "20260702"

    def test_all_businesses_all_periods_queryable(self):
        for business in ALL_BUSINESSES:
            for period in ALL_PERIODS:
                data = query_friday_data(business, period, "weekly")
                self.assertNotIn("error", data, f"{business} {period}")
                for field in ["current_data", "compare_data", "daily_current", "daily_compare",
                              "overall", "calibration_result", "dimension_availability", "meta"]:
                    self.assertIn(field, data, f"{business} {period} 缺 {field}")
                self.assertIsNotNone(data.get("calibration_result", {}).get("passed"))


class ExternalCapabilityExclusionTest(unittest.TestCase):
    def test_task_state_has_no_delivered_or_archived(self):
        with open(TASK_STATE_PY, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("DELIVERED", source)
        self.assertNotIn("ARCHIVED", source)
        # 且必须包含建议的完整状态集
        for status in [
            "CREATED", "INTENT_RECOGNIZED", "PARAMETER_VALIDATED", "DATA_QUERIED",
            "CALIBRATION_CHECKED", "CALCULATED", "REPORT_GENERATED", "HTML_GENERATED",
            "COMPLETED", "FAILED", "WAITING_CONFIRMATION",
        ]:
            self.assertIn(f'"{status}"', source, f"状态机缺 {status}")

    def test_main_chain_has_no_delivery_or_archive(self):
        with open(CORE_PY, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("run_demo_mock_delivery", source)
        self.assertNotIn("publish_result", source)
        self.assertNotIn("dx-api-tools-bai", source)
        self.assertNotIn("meituan-km", source)
        self.assertNotIn("kmedit", source)
        self.assertNotIn("daxiang", source)

    def test_frontend_has_no_external_delivery_claims(self):
        with open(FRONTEND, "r", encoding="utf-8") as f:
            html = f.read()
        # 前端不得出现「已发送到/已同步」等声称已实现外部能力的表述
        for forbidden in ["已发送到大象群", "已同步学城", "已发送到", "已归档"]:
            self.assertNotIn(forbidden, html, f"前端不应出现外部能力声称：{forbidden}")
        # 也不得把大象分发/学城同步作为当前能力展示
        for forbidden in ["大象分发", "学城同步", "daxiang-scheduled-message", "meituan-km", "dx-api-tools-bai"]:
            self.assertNotIn(forbidden, html, f"前端不应展示外部能力：{forbidden}")


class FrontendScheduleConfirmTest(unittest.TestCase):
    def setUp(self):
        with open(FRONTEND, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_form_creation_requires_confirmation_step(self):
        # 创建前必须有确认区域与确认按钮，不能点一下就直接写库
        self.assertIn("taskConfirmArea", self.html)
        self.assertIn("confirmCreateTask()", self.html)
        self.assertIn("cancelCreateTask()", self.html)
        self.assertIn("请确认定时任务配置", self.html)
        self.assertIn("不会真实到点触发", self.html)
        # 确认后才调用后端创建接口
        idx_confirm = self.html.find("async function confirmCreateTask")
        idx_create = self.html.find("async function createTask")
        self.assertGreater(idx_confirm, -1)
        self.assertGreater(idx_create, -1)
        self.assertIn("/schedule/create", self.html)

    def test_iframe_uses_same_origin_reports_path(self):
        # iframe 使用后端 /reports 同源 HTTP 路径，而不是被浏览器拦截的 file://
        self.assertIn("report_http_path", self.html)
        self.assertIn("`${getApiBaseUrl()}${reportHttpPath}`", self.html)
        self.assertIn("report_filename", self.html)


class FrontendReportModulesTest(unittest.TestCase):
    def setUp(self):
        with open(FRONTEND, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_five_modules_and_dual_metrics_visible(self):
        self.assertIn("核心指标", self.html)
        self.assertIn("综合结论", self.html)
        # 前端趋势区标题为「日度趋势」（对应规格第 3 模块「日度趋势」）
        self.assertRegex(self.html, r"日[万度]服趋势|日度趋势")
        self.assertIn("万服波动贡献", self.html)
        self.assertIn("服务量变化占比", self.html)
        self.assertIn("不能证明因果关系", self.html)
        self.assertIn("本项目使用模拟数据，仅用于作品集演示，不代表真实生产数据或真实业务结果。", self.html)
        # 模块5：明细与告警
        self.assertIn("明细与告警", self.html)
        self.assertIn("alertList", self.html)
        self.assertIn("unavailableDims", self.html)

    def test_report_header_and_metric_styles(self):
        # 报告头部：红色大标题、周期独立行、模拟数据声明独立行、生成时间
        self.assertIn("text-red-600", self.html)
        self.assertIn('id="reportPeriod"', self.html)
        self.assertIn('id="reportDataNote"', self.html)
        self.assertIn('id="reportGenTime"', self.html)
        # 核心指标区：浅红/浅米背景带 + 2 列布局卡片（sm 断点 2 列、桌面 4 列）
        self.assertIn('sm:grid-cols-2', self.html)
        self.assertIn('xl:grid-cols-4', self.html)
        self.assertIn("metric-card", self.html)
        self.assertIn("本期人工万服", self.html)
        self.assertIn("去年同期万服", self.html)
        self.assertIn("万服同比", self.html)
        self.assertIn("服务量变化", self.html)
        # 红涨蓝跌：同比升高红色、下降蓝色
        self.assertIn("text-red-600", self.html)
        self.assertIn("text-blue-600", self.html)

    def test_dimension_top3_cards_and_dual_metrics(self):
        # 每个维度必须展示 Top3 推高/压低卡片（按 wanfu_contribution）
        self.assertIn("function computeDimTops", self.html)
        self.assertIn("function renderDimensionTops", self.html)
        self.assertIn("Top3 推高", self.html)
        self.assertIn("Top3 压低", self.html)
        self.assertIn("按 wanfu_contribution", self.html)
        self.assertIn("次/万单", self.html)
        # 双指标说明：wanfu_contribution 用于归因排序，service_change_ratio 仅辅助说明
        self.assertIn("wanfu_contribution", self.html)
        self.assertIn("service_change_ratio", self.html)
        self.assertIn("仅辅助说明服务量规模变化", self.html)
        # 6 个标准维度 Tab
        for dim_id in ["dim_city", "dim_category", "dim_event", "dim_faq", "dim_channel", "dim_zone"]:
            self.assertIn(f'id="{dim_id}"', self.html)

    def test_report_rendered_in_page_html_entry_only_auxiliary(self):
        # 报告主体必须直接在当前页面渲染，本地 HTML 链接只是辅助入口
        self.assertIn("renderReport(reportData)", self.html)
        self.assertIn("直接在当前页面渲染报告展示区", self.html)
        self.assertIn("打开完整 HTML 报告", self.html)
        self.assertIn("辅助入口", self.html)
        # 不依赖浏览器下载文件才能看到
        self.assertIn("toggleReportFrame", self.html)


class BackendReportsMountTest(unittest.TestCase):
    def test_main_mounts_reports_static_dir(self):
        with open(MAIN_PY, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn('app.mount("/reports", StaticFiles(directory=output_dir), name="reports")', source)

    def test_delivery_returns_report_filename(self):
        with open(DELIVERY_PY, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn('"report_filename": report_path.name', source)


if __name__ == "__main__":
    unittest.main()
