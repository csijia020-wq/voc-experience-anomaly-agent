import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "backend", "app", "main.py")
RENDER = os.path.join(ROOT, "render.yaml")
REQUIREMENTS = os.path.join(ROOT, "backend", "requirements.txt")
DOCKERFILE = os.path.join(ROOT, "Dockerfile")
DOCKERIGNORE = os.path.join(ROOT, ".dockerignore")
README = os.path.join(ROOT, "README.md")


class DeploymentContractTest(unittest.TestCase):
    def setUp(self):
        with open(MAIN, "r", encoding="utf-8") as f:
            self.main_py = f.read()

    def test_fastapi_serves_frontend_at_root(self):
        self.assertIn("FileResponse", self.main_py)
        self.assertIn('frontend_index = os.path.join(frontend_dir, "index.html")', self.main_py)
        self.assertIn("return FileResponse(frontend_index)", self.main_py)
        self.assertIn('@app.get("/vibe_coding_prototype.html"', self.main_py)

    def test_render_config_exists_for_one_link_demo(self):
        self.assertTrue(os.path.exists(RENDER))
        with open(RENDER, "r", encoding="utf-8") as f:
            render_yaml = f.read()
        self.assertIn("voc-experience-anomaly-agent", render_yaml)
        self.assertIn("uvicorn app.main:app", render_yaml)
        self.assertIn("backend", render_yaml)

    def test_backend_requirements_include_pydantic_settings(self):
        with open(REQUIREMENTS, "r", encoding="utf-8") as f:
            requirements = f.read()
        self.assertIn("pydantic-settings", requirements)

    def test_huggingface_space_docker_config_exists(self):
        self.assertTrue(os.path.exists(DOCKERFILE))
        with open(DOCKERFILE, "r", encoding="utf-8") as f:
            dockerfile = f.read()
        self.assertIn("FROM python:3.11-slim", dockerfile)
        self.assertIn("pip install --no-cache-dir -r /app/backend/requirements.txt", dockerfile)
        self.assertIn("EXPOSE 7860", dockerfile)
        self.assertIn("uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}", dockerfile)

        with open(README, "r", encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("sdk: docker", readme)
        self.assertIn("app_port: 7860", readme)

        self.assertTrue(os.path.exists(DOCKERIGNORE))
        with open(DOCKERIGNORE, "r", encoding="utf-8") as f:
            dockerignore = f.read()
        self.assertIn("backend/.env", dockerignore)
        self.assertIn(".env", dockerignore)
        self.assertIn(".git", dockerignore)

    def test_dockerfile_copies_docs_and_output_not_deleted_dir(self):
        """Dockerfile 不得引用已删除的 project_delivery，必须 COPY docs 并创建可写 output。"""
        with open(DOCKERFILE, "r", encoding="utf-8") as f:
            dockerfile = f.read()
        self.assertNotIn("project_delivery", dockerfile)
        self.assertIn("COPY docs /app/docs", dockerfile)
        self.assertIn("mkdir -p /app/output", dockerfile)

    def test_cors_whitelist_allows_github_pages_and_localhost(self):
        self.assertIn("csijia020-wq.github.io", self.main_py)
        self.assertIn("http://localhost:8000", self.main_py)
        # 实际中间件配置使用白名单变量（allow_origins=CORS_ORIGINS），而非通配符
        self.assertIn("allow_origins=CORS_ORIGINS", self.main_py)
        self.assertNotIn('allow_origins=["*"],', self.main_py)
        # 部署平台可通过 CORS_ORIGINS 环境变量覆盖
        self.assertIn("CORS_ORIGINS", self.main_py)
        self.assertIn('os.getenv("CORS_ORIGINS", "")', self.main_py)

    def test_frontend_supports_public_api_base_config(self):
        with open(os.path.join(ROOT, "docs", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("window.AGENT_API_BASE_URL", html)
        self.assertIn("if (window.AGENT_API_BASE_URL)", html)
        self.assertNotIn('AGENT_API_BASE_URL = "https://', html)

    def test_render_config_has_cors_envvar_and_no_api_key(self):
        with open(RENDER, "r", encoding="utf-8") as f:
            render_yaml = f.read()
        self.assertIn("CORS_ORIGINS", render_yaml)
        # DEEPSEEK_API_KEY 不应写入 render.yaml（敏感变量需在控制台配置）
        self.assertNotIn("DEEPSEEK_API_KEY:", render_yaml)

    def test_pages_workflow_injects_public_backend_url(self):
        """GitHub Pages workflow 支持 AGENT_API_BASE_URL 注入；未配置时前端保持「后端未连接」状态。"""
        workflow_path = os.path.join(ROOT, ".github", "workflows", "pages.yml")
        self.assertTrue(os.path.exists(workflow_path))
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = f.read()
        self.assertIn("AGENT_API_BASE_URL", workflow)
        self.assertIn("Inject public backend base URL", workflow)
        self.assertIn("window.AGENT_API_BASE_URL", workflow)
        # 未配置时明确保持空值（不注入任何地址）
        self.assertIn("AGENT_API_BASE_URL not set", workflow)
        self.assertIn("backend-unavailable", workflow)


if __name__ == "__main__":
    unittest.main()
