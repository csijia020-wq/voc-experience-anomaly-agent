import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "docs", "index.html")


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
        self.assertIn("getApiBaseUrl()", self.html)

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
        self.assertIn("response.body.getReader()", self.html)
        self.assertIn("handleSseEvent", self.html)

    def test_metric_cards_have_stable_layout_selector(self):
        self.assertIn('id="metricCards"', self.html)
        self.assertIn("metric-card", self.html)
        self.assertIn("document.querySelectorAll('#metricCards .metric-card')", self.html)

    def test_dimension_tabs_use_dynamic_report_data(self):
        self.assertNotIn("网页端维度当前数据集暂不支持查询", self.html)
        self.assertIn("function renderDimensionSection", self.html)
        self.assertIn("function renderDimensionTable", self.html)
        self.assertIn("function getDimItems", self.html)
        self.assertIn("function getDimTops", self.html)
        self.assertIn("function computeDimTops", self.html)
        self.assertIn("function renderDimensionTops", self.html)
        # 每个维度必须渲染 Top3 推高/压低卡片 + 明细表
        self.assertIn("Top3 推高", self.html)
        self.assertIn("Top3 压低", self.html)
        self.assertIn("renderDimensionSection('dim_city', '城市等级', getDimItems(dimensions, 'city_level'), true, getDimTops(dimensionTops, 'city_level'))", self.html)
        self.assertIn("renderDimensionSection('dim_category', '一级门店品类', getDimItems(dimensions, 'store_category_level_1'), false, getDimTops(dimensionTops, 'store_category_level_1'))", self.html)
        self.assertIn("renderDimensionSection('dim_event', '事件类别', getDimItems(dimensions, 'event_category'), false, getDimTops(dimensionTops, 'event_category'))", self.html)
        self.assertIn("renderDimensionSection('dim_faq', '六级FAQ', getDimItems(dimensions, 'faq_level_6'), false, getDimTops(dimensionTops, 'faq_level_6'))", self.html)
        self.assertIn("renderDimensionSection('dim_channel', '进线渠道', getDimItems(dimensions, 'incoming_channel'), false, getDimTops(dimensionTops, 'incoming_channel'))", self.html)
        self.assertIn("renderDimensionSection('dim_zone', '一级战区', getDimItems(dimensions, 'warzone_level_1'), false, getDimTops(dimensionTops, 'warzone_level_1'))", self.html)
        # 报告渲染必须直接在当前页面绘制（不依赖 HTML 下载/链接）
        self.assertIn("renderReport(reportData)", self.html)
        self.assertIn("renderDimensionTables(report.dimensions, report.dimension_tops)", self.html)

    def test_daily_chart_is_initialized_when_report_is_visible(self):
        self.assertNotIn("setTimeout(initCharts, 500)", self.html)
        self.assertIn("function ensureDailyChart", self.html)
        self.assertIn("function resizeDailyChartSoon", self.html)
        self.assertIn("function calculateChartBounds", self.html)
        self.assertRegex(
            self.html,
            re.compile(r"renderReport\(currentReportData\);\s*initCharts\(\);", re.S),
        )
        self.assertRegex(
            self.html,
            re.compile(r"function updateChart\(dailyTrend\) \{\s*ensureDailyChart\(\);", re.S),
        )
        self.assertIn("yAxis: calculateChartBounds(currentSeries, compareSeries)", self.html)


if __name__ == "__main__":
    unittest.main()
