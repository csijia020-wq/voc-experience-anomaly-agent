@echo off
cd /d "d:\桌面D盘文件\A有点东西\异动分析agent\backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
