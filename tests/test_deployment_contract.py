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
        self.assertIn('frontend_index = os.path.join(frontend_dir, "vibe_coding_prototype.html")', self.main_py)
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


if __name__ == "__main__":
    unittest.main()
