import http.server
import socketserver
import os

os.chdir(r"d:\桌面D盘文件\A有点东西\异动分析agent\project_delivery")

PORT = 8080

Handler = http.server.SimpleHTTPRequestHandler

try:
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Frontend server started at http://localhost:{PORT}/vibe_coding_prototype.html")
        print(f"Backend API: http://localhost:8000")
        httpd.serve_forever()
except OSError as e:
    print(f"Error: {e}")
    print("Port 8080 is already in use. Trying port 8081...")
    PORT = 8081
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Frontend server started at http://localhost:{PORT}/vibe_coding_prototype.html")
        print(f"Backend API: http://localhost:8000")
        httpd.serve_forever()