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
        self.assertIn("静态作品集演示版", html)
        self.assertIn("生成到餐客服上周周报", html)
        self.assertIn("本期万服", html)
        self.assertIn("120.47", html)
        self.assertIn("126.72", html)
        self.assertIn("-4.94%", html)
        self.assertIn("服务量变化占比", html)
        self.assertIn("不调用真实 DeepSeek", html)
        self.assertNotIn("DEEPSEEK_API_KEY", html)
        self.assertNotIn("api.deepseek.com", html)
        self.assertNotIn("localhost:8000", html)

    def test_static_portfolio_embeds_full_report_page(self):
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
        self.assertIn("function updateChart", html)
        self.assertIn("const STATIC_REPORT_DATA", html)
        self.assertIn("renderReport(STATIC_REPORT_DATA)", html)
        self.assertIn("renderDimensionSection('dim_city', '城市等级', dimensions['城市等级'], true)", html)
        self.assertIn("renderDimensionSection('dim_category', '品类', dimensions['品类'])", html)
        self.assertIn("renderDimensionSection('dim_event', '事件类别', dimensions['事件类别'])", html)
        self.assertIn("renderDimensionSection('dim_channel', '进线渠道', dimensions['进线渠道'])", html)
        self.assertIn("renderDimensionSection('dim_zone', '战区', dimensions['战区'])", html)
        self.assertIn("华南战区", html)
        self.assertIn("APP在线", html)
        self.assertNotIn("/api/chat/stream", html)
        self.assertNotIn("API_BASE_URL", html)

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
