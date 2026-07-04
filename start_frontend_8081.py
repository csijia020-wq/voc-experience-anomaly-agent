import http.server
import socketserver
import os

os.chdir(r"d:\桌面D盘文件\A有点东西\异动分析agent\project_delivery")

PORT = 8081

Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Frontend server started at http://localhost:{PORT}/vibe_coding_prototype.html")
    print(f"Backend API: http://localhost:8000")
    httpd.serve_forever()