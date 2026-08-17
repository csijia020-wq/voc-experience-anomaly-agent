"""前端强依赖后端契约测试。

验证前端不再包含静态演示兜底：
- 不包含 STATIC_REPORT_DATA / STATIC_THINKING_STEPS / runStaticDemo
- 后端不可达时显示错误并提示启动命令，不展示静态报告
- 点击发送必须调用 /api/chat/stream
- 报告展示只能由后端 report 事件触发
- GitHub Pages 静态页面不会伪装成完整 Agent
"""

import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "docs", "index.html")


class NoStaticFallbackTest(unittest.TestCase):
    def setUp(self):
        with open(FRONTEND, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_no_static_report_data(self):
        self.assertNotIn("STATIC_REPORT_DATA", self.html)
        self.assertNotIn("STATIC_THINKING_STEPS", self.html)
        self.assertNotIn("STATIC_", self.html)
        # 不得包含可渲染的完整静态 report payload（指标卡数字+维度明细+summary 的组合）
        self.assertNotIn('"current_wanfu": 120.47', self.html)
        self.assertNotIn('"top_up_factors"', self.html)

    def test_no_static_text_claims(self):
        # 不得出现「无需后端/不调用后端/静态作品集版不调用真实 DeepSeek」等文案
        for phrase in ["无需后端", "不调用后端", "不调用真实 DeepSeek", "静态作品集版", "不需要后端"]:
            self.assertNotIn(phrase, self.html)

    def test_no_static_fallback_branches(self):
        self.assertNotIn("runStaticDemo", self.html)
        self.assertNotIn("isStaticHosting", self.html)
        self.assertNotIn("静态作品集演示版", self.html)
        self.assertNotIn("不调用真实 DeepSeek", self.html)
        self.assertNotIn("静态演示链路", self.html)
        self.assertNotIn("内置静态报告", self.html)

    def test_no_hardcoded_report_numbers(self):
        # 不得内嵌可被误认为真实报告的固定指标数值
        self.assertNotIn("120.47", self.html)
        self.assertNotIn("126.72", self.html)
        self.assertNotIn("-4.94%", self.html)

    def test_backend_unavailable_shows_error(self):
        self.assertIn("function checkBackendHealth", self.html)
        self.assertIn("/health", self.html)
        self.assertIn("后端服务未连接", self.html)
        self.assertIn("请先启动后端服务", self.html)
        self.assertIn("python start_servers.py start", self.html)

    def test_backend_unavailable_disables_send_and_blocks_report_tab(self):
        # 后端不可达时：禁用发送按钮/输入框、阻止报告展示 Tab、不展示指标卡/6维度
        self.assertIn("backendHealthy = false", self.html)
        self.assertIn("sendBtn.disabled = true", self.html)
        self.assertIn("chatInput.disabled = true", self.html)
        self.assertIn("else if (!backendHealthy)", self.html)
        self.assertIn("showBackendUnavailable(getApiBaseUrl())", self.html)
        # 未连接时 sendMessage 直接阻止，不进入报告生成路径
        self.assertIn("if (!backendHealthy)", self.html)

    def test_send_always_calls_backend_stream(self):
        self.assertIn("/api/chat/stream", self.html)
        self.assertIn("method: 'POST'", self.html)
        # 后端失败分支只报错，不降级
        self.assertIn("后端接口请求失败", self.html)
        self.assertIn("无法连接后端服务", self.html)

    def test_report_only_from_backend_report_event(self):
        self.assertIn("function handleReport(reportData)", self.html)
        self.assertIn("if (event === 'report')", self.html)
        self.assertIn("currentReportData = reportData", self.html)
        # 报告页无后端数据时显示空状态
        self.assertIn("function showEmptyReportState", self.html)
        # 没有后端 report 事件就没有报告渲染调用点
        report_render_calls = re.findall(r"renderReport\s*\(", self.html)
        self.assertTrue(report_render_calls)
        # 所有 renderReport 调用必须受后端数据保护（handleReport 内 或 currentReportData 条件内）
        self.assertIn("currentReportData && currentReportData.business", self.html)
        self.assertNotIn("renderReport(STATIC_REPORT_DATA)", self.html)

    def test_current_report_data_starts_empty(self):
        self.assertRegex(self.html, re.compile(r"let currentReportData = null;"))
        self.assertNotRegex(self.html, re.compile(r"let currentReportData = STATIC_REPORT_DATA"))

    def test_initial_load_health_checks_not_renders(self):
        # DOMContentLoaded 只做健康检查 + 切 Tab，不渲染任何静态报告
        self.assertIn("checkBackendHealth()", self.html)
        self.assertNotIn("renderReport(STATIC_REPORT_DATA)", self.html)
        # 报告渲染必须受「后端 report 数据存在」条件保护
        self.assertIn("if (currentReportData && currentReportData.business)", self.html)
        self.assertRegex(self.html, re.compile(r"let currentReportData = null;"))

    def test_backend_chain_structure_kept(self):
        # 后端可达时 5 模块 / 6 维度 / 双指标渲染逻辑仍完整
        self.assertIn("function renderReport(report)", self.html)
        self.assertIn("function renderDimensionTables", self.html)
        self.assertIn("function renderDimensionTops", self.html)
        self.assertIn("Top3 推高", self.html)
        self.assertIn("Top3 压低", self.html)
        self.assertIn("wanfu_contribution", self.html)
        self.assertIn("service_change_ratio", self.html)
        self.assertIn("仅辅助说明服务量规模变化", self.html)
        self.assertIn("本项目使用模拟数据，仅用于作品集演示", self.html)


if __name__ == "__main__":
    unittest.main()
