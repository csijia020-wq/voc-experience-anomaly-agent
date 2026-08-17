import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT_ROUTER = os.path.join(ROOT, "backend", "app", "routers", "chat.py")
AGENT_CORE = os.path.join(ROOT, "backend", "app", "agent", "core.py")
MAIN_APP = os.path.join(ROOT, "backend", "app", "main.py")
FRONTEND = os.path.join(ROOT, "docs", "index.html")


class SseFrontendContractTest(unittest.TestCase):
    def test_backend_stream_uses_standard_sse_envelope(self):
        with open(CHAT_ROUTER, "r", encoding="utf-8") as f:
            source = f.read()

        self.assertIn('media_type="text/event-stream"', source)
        self.assertIn('"Cache-Control": "no-cache"', source)
        self.assertIn('"Connection": "keep-alive"', source)
        self.assertIn("def _sse_frame", source)
        self.assertRegex(source, re.compile(r'payload\s*=\s*\{\s*"event":\s*event', re.S))
        self.assertIn('return f"data: {json.dumps(payload, ensure_ascii=False)}\\n\\n"', source)

    def test_core_stream_emits_report_event_after_local_html_generation(self):
        with open(AGENT_CORE, "r", encoding="utf-8") as f:
            source = f.read()

        # 报告链路只落地到本地 HTML 生成，不触发分发/归档
        self.assertIn("html_result = self._run_local_html_report_delivery", source)
        self.assertIn('"event": "report"', source)
        self.assertIn('"report_url": (html_result or {}).get("report_url", "")', source)
        # SSE 阶段不应包含分发/发布/归档语义
        self.assertNotIn("publish_result = self._run_demo_mock_delivery", source)
        self.assertNotIn("run_demo_mock_delivery", source)

    def test_frontend_reads_sse_with_readable_stream(self):
        with open(FRONTEND, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("/api/chat/stream", html)
        self.assertIn("response.body.getReader()", html)
        self.assertIn("TextDecoder", html)
        self.assertIn("parseSseBuffer", html)
        self.assertIn("handleSseEvent", html)
        self.assertIn("通过 ReadableStream 逐帧解析 SSE 事件", html)
        self.assertIn("错误事件通过 SSE 通道向前端反馈", html)
        self.assertIn("report_url", html)
        self.assertIn("<iframe", html)
        # 前端不应展示分发/发布/归档语义
        self.assertNotIn("publish_result", html)
        self.assertNotIn("publishedReportFrameWrap", html)
        self.assertNotIn("已发送到", html)
        self.assertNotIn("已归档", html)

    def test_main_mounts_docs_static_frontend_with_open_cors(self):
        with open(MAIN_APP, "r", encoding="utf-8") as f:
            source = f.read()

        self.assertIn('frontend_dir = os.path.join(project_root, "docs")', source)
        self.assertIn('app.mount("/static", StaticFiles(directory=frontend_dir), name="static")', source)
        self.assertIn('allow_origins=["*"]', source)


if __name__ == "__main__":
    unittest.main()
