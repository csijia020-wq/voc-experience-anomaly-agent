import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "project_delivery", "vibe_coding_prototype.html")


class FrontendContractTest(unittest.TestCase):
    def setUp(self):
        with open(FRONTEND, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_uses_stream_api_and_current_project_title(self):
        self.assertIn("VoC 体验异动分析 Agent", self.html)
        self.assertIn("/api/chat/stream", self.html)

    def test_api_base_url_is_deployable_same_origin(self):
        self.assertNotIn("const API_BASE_URL = 'http://localhost:8000';", self.html)
        self.assertIn("window.location.origin", self.html)
        self.assertIn("window.location.protocol === 'file:'", self.html)

    def test_service_change_ratio_label_and_formatting(self):
        self.assertIn("服务量变化占比", self.html)
        self.assertNotIn("万服贡献度", self.html)
        self.assertNotIn("严格贡献", self.html)
        self.assertNotIn("因果贡献", self.html)
        self.assertIn("Number(value || 0)", self.html)
        self.assertRegex(self.html, re.compile(r"ratio\s*\*\s*100"))
        self.assertIn("service_change_ratio ?? f.contrib_wanfu", self.html)

    def test_report_summary_uses_markdown_renderer(self):
        self.assertIn('id="reportSummary"', self.html)
        self.assertIn("function renderReportMarkdown", self.html)
        self.assertIn("renderReportMarkdown(report.summary)", self.html)
        self.assertIn("report-table-wrap", self.html)

    def test_streaming_chat_text_uses_markdown_renderer(self):
        self.assertIn("chat-report-bubble", self.html)
        self.assertIn("textMessage.dataset.rawMarkdown", self.html)
        self.assertIn("renderReportMarkdown(textMessage.dataset.rawMarkdown)", self.html)
        self.assertNotIn("content.textContent += text", self.html)

    def test_metric_cards_have_stable_layout_selector(self):
        self.assertIn('id="metricCards"', self.html)
        self.assertIn("metric-card", self.html)
        self.assertIn("document.querySelectorAll('#metricCards .metric-card')", self.html)

    def test_dimension_tabs_use_dynamic_report_data(self):
        self.assertNotIn("网页端维度当前数据集暂不支持查询", self.html)
        self.assertIn("function renderDimensionSection", self.html)
        self.assertIn("function renderDimensionTable", self.html)
        self.assertIn("renderDimensionSection('dim_city', '城市等级', dimensions['城市等级'], true)", self.html)
        self.assertIn("renderDimensionSection('dim_category', '品类', dimensions['品类'])", self.html)
        self.assertIn("renderDimensionSection('dim_event', '事件类别', dimensions['事件类别'])", self.html)
        self.assertIn("renderDimensionSection('dim_channel', '进线渠道', dimensions['进线渠道'])", self.html)
        self.assertIn("renderDimensionSection('dim_zone', '战区', dimensions['战区'])", self.html)

    def test_daily_chart_is_initialized_when_report_is_visible(self):
        self.assertNotIn("setTimeout(initCharts, 500)", self.html)
        self.assertIn("function ensureDailyChart", self.html)
        self.assertIn("function resizeDailyChartSoon", self.html)
        self.assertIn("function calculateChartBounds", self.html)
        self.assertRegex(
            self.html,
            re.compile(r"initCharts\(\);\s*if \(currentReportData\) \{\s*renderReport\(currentReportData\);", re.S),
        )
        self.assertRegex(
            self.html,
            re.compile(r"function updateChart\(dailyTrend\) \{\s*ensureDailyChart\(\);", re.S),
        )
        self.assertIn("yAxis: calculateChartBounds(currentSeries, compareSeries)", self.html)


if __name__ == "__main__":
    unittest.main()
