import http.server
import socketserver
import os
import sys

# 设置工作目录
os.chdir(r"d:\桌面D盘文件\A有点东西\异动分析agent\project_delivery")

PORT = 8082

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # 添加CORS头
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

try:
    with socketserver.TCPServer(("127.0.0.1", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Frontend server started at http://127.0.0.1:{PORT}/vibe_coding_prototype.html")
        print(f"Backend API: http://localhost:8000")
        print("Press Ctrl+C to stop the server")
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\nServer stopped.")
except OSError as e:
    print(f"Error: {e}")
    sys.exit(1)