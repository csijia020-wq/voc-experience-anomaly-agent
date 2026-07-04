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
