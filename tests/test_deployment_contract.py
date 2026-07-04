import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "backend", "app", "main.py")
RENDER = os.path.join(ROOT, "render.yaml")
REQUIREMENTS = os.path.join(ROOT, "backend", "requirements.txt")


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


if __name__ == "__main__":
    unittest.main()
