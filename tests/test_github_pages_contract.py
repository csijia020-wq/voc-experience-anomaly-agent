import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_PAGE = os.path.join(ROOT, "docs", "index.html")
PAGES_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pages.yml")


class GitHubPagesContractTest(unittest.TestCase):
    def test_static_portfolio_page_exists_and_is_safe(self):
        self.assertTrue(os.path.exists(STATIC_PAGE))
        with open(STATIC_PAGE, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("VoC 体验异动分析 Agent", html)
        self.assertIn("实时联调版", html)
        self.assertIn("生成到餐客服上周周报", html)
        self.assertIn("本期人工万服", html)
        self.assertIn("服务量变化占比", html)
        self.assertNotIn("DEEPSEEK_API_KEY", html)
        self.assertNotIn("api.deepseek.com", html)
        # 页面为「本地后端联调 + 公网后端可配置」入口：本地 file: 回退 localhost，
        # 公网通过 window.AGENT_API_BASE_URL 注入，不硬编码具体后端地址。
        self.assertIn("getApiBaseUrl()", html)
        self.assertIn("window.AGENT_API_BASE_URL", html)
        self.assertNotIn('AGENT_API_BASE_URL = "https://', html)

    def test_no_static_report_fallback_data(self):
        """前端不得内置固定报告数据或静态流程，报告只能来自后端 report 事件。"""
        with open(STATIC_PAGE, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertNotIn("STATIC_REPORT_DATA", html)
        self.assertNotIn("STATIC_THINKING_STEPS", html)
        self.assertNotIn("runStaticDemo", html)
        self.assertNotIn("isStaticHosting", html)
        self.assertNotIn("renderReport(STATIC_REPORT_DATA)", html)
        # 不得内嵌可被误认为真实报告的固定指标数值
        self.assertNotIn("120.47", html)
        self.assertNotIn("126.72", html)
        self.assertNotIn("-4.94%", html)
        # 报告数据只能来自后端 report 事件
        self.assertIn("function handleReport(reportData)", html)
        self.assertIn("currentReportData = reportData", html)

    def test_backend_unavailable_shows_error_not_report(self):
        """后端不可达时前端必须明确报错并提示启动命令，不展示静态报告。"""
        with open(STATIC_PAGE, "r", encoding="utf-8") as f:
            html = f.read()

        # 页面加载时检查后端健康
        self.assertIn("function checkBackendHealth", html)
        self.assertIn("/health", html)
        # 后端不可达提示文案与启动命令
        self.assertIn("后端服务未连接", html)
        self.assertIn("请先启动后端服务", html)
        self.assertIn("python start_servers.py start", html)
        self.assertIn("showBackendUnavailable", html)
        # SSE 失败/接口失败时不生成静态报告，只报错
        self.assertIn("后端接口请求失败", html)
        self.assertIn("无法连接后端服务", html)
        # 不允许自动切换到静态演示
        self.assertNotIn("不调用真实 DeepSeek", html)
        self.assertNotIn("静态作品集演示版", html)

    def test_report_only_from_backend_report_event(self):
        """点击发送必须调用 /api/chat/stream；报告展示只能由后端 report 事件触发。"""
        with open(STATIC_PAGE, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("/api/chat/stream", html)
        self.assertIn("method: 'POST'", html)
        self.assertIn("handleSseEvent", html)
        # 只有 report 事件才会渲染报告
        self.assertIn("if (event === 'report')", html)
        self.assertIn("renderReport(reportData)", html)
        # 报告页无数据时显示空状态而非静态报告
        self.assertIn("showEmptyReportState", html)

    def test_full_report_page_structure(self):
        with open(STATIC_PAGE, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn('id="reportPanel"', html)
        self.assertIn('id="metricCards"', html)
        self.assertIn('id="reportSummary"', html)
        self.assertIn('id="factorCards"', html)
        self.assertIn('id="dailyTrendChart"', html)
        self.assertIn("function renderReportMarkdown", html)
        self.assertIn("function renderReport(report)", html)
        self.assertIn("function renderDimensionSection", html)
        self.assertIn("function renderDimensionTables", html)
        self.assertIn("function computeDimTops", html)
        self.assertIn("function renderDimensionTops", html)
        self.assertIn("function updateChart", html)
        # 6 维度 Top3 推高/压低卡片 + 明细表
        self.assertIn("Top3 推高", html)
        self.assertIn("Top3 压低", html)
        self.assertIn("renderDimensionSection('dim_city', '城市等级', getDimItems(dimensions, 'city_level'), true, getDimTops(dimensionTops, 'city_level'))", html)
        self.assertIn("renderDimensionSection('dim_category', '一级门店品类', getDimItems(dimensions, 'store_category_level_1'), false, getDimTops(dimensionTops, 'store_category_level_1'))", html)
        self.assertIn("renderDimensionSection('dim_event', '事件类别', getDimItems(dimensions, 'event_category'), false, getDimTops(dimensionTops, 'event_category'))", html)
        self.assertIn("renderDimensionSection('dim_faq', '六级FAQ', getDimItems(dimensions, 'faq_level_6'), false, getDimTops(dimensionTops, 'faq_level_6'))", html)
        self.assertIn("renderDimensionSection('dim_channel', '进线渠道', getDimItems(dimensions, 'incoming_channel'), false, getDimTops(dimensionTops, 'incoming_channel'))", html)
        self.assertIn("renderDimensionSection('dim_zone', '一级战区', getDimItems(dimensions, 'warzone_level_1'), false, getDimTops(dimensionTops, 'warzone_level_1'))", html)
        self.assertIn("getApiBaseUrl()", html)
        # 公网后端地址通过 window.AGENT_API_BASE_URL 配置（部署时注入），不硬编码具体域名
        self.assertIn("window.AGENT_API_BASE_URL", html)
        self.assertNotIn('AGENT_API_BASE_URL = "https://', html)

    def test_github_pages_workflow_exists(self):
        self.assertTrue(os.path.exists(PAGES_WORKFLOW))
        with open(PAGES_WORKFLOW, "r", encoding="utf-8") as f:
            workflow = f.read()

        self.assertIn("Deploy static portfolio demo to GitHub Pages", workflow)
        self.assertIn("actions/configure-pages", workflow)
        self.assertIn("actions/upload-pages-artifact", workflow)
        self.assertIn("actions/deploy-pages", workflow)
        self.assertIn("path: docs", workflow)


if __name__ == "__main__":
    unittest.main()
