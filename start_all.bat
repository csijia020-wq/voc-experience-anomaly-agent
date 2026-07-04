@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM  VoC回声系统 - 体验异动分析Agent  一键启动 (后端+前端)
REM  解决: uvicorn 后台重定向 NoneType isatty 崩溃
REM        Windows GBK 编码无法打印 emoji/中文
REM ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

REM --- 端口配置 ---
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=8080"

echo ==========================================================
echo  VoC回声系统 - 体验异动分析Agent 启动
echo ==========================================================
echo.

REM --- 1. 检查端口占用，已占用则提示 ---
echo [1/4] 检查端口 %BACKEND_PORT% / %FRONTEND_PORT% ...
netstat -ano | findstr "LISTENING" | findstr ":%BACKEND_PORT% " >nul
if %errorlevel%==0 (
    echo     [!] 端口 %BACKEND_PORT% 已被占用，可能后端已在运行。
    echo         如需重启，请先运行 stop_all.bat
    echo.
    goto :start_frontend
)
echo     [OK] 端口空闲
echo.

REM --- 2. 检查 backend 目录 ---
echo [2/4] 检查后端目录 ...
if not exist "%ROOT%\backend\app\main.py" (
    echo     [X] 未找到 backend\app\main.py
    pause
    exit /b 1
)
echo     [OK] 后端目录存在
echo.

REM --- 3. 启动后端 (后台) ---
echo [3/4] 启动后端服务 http://localhost:%BACKEND_PORT% ...
REM  关键: 用 pythonw 或 start /b 启动 run_backend.py，
REM  在 Python 内部完成 stdout 重定向，避免 shell 重定向产生 None。
start "VOC-Backend" /b "" "D:\Python39\python.exe" "%ROOT%\run_backend.py"

REM  等待后端就绪 (最多 15 秒)
set "ready=0"
for /l %%i in (1,1,30) do (
    if "!ready!"=="0" (
        curl -s -o nul http://localhost:%BACKEND_PORT%/health 2>nul
        if !errorlevel!==0 (
            set "ready=1"
            echo     [OK] 后端已就绪
        ) else (
            ping 127.0.0.1 -n 2 >nul
        )
    )
)
if "!ready!"=="0" (
    echo     [!] 后端未在 15 秒内就绪，请查看 backend.err.log
)
echo.

:start_frontend
REM --- 4. 启动前端 (后台) ---
echo [4/4] 启动前端服务 http://localhost:%FRONTEND_PORT% ...
netstat -ano | findstr "LISTENING" | findstr ":%FRONTEND_PORT% " >nul
if %errorlevel%==0 (
    echo     [!] 端口 %FRONTEND_PORT% 已被占用，前端可能已在运行。
    goto :show_info
)
start "VOC-Frontend" /b "" "D:\Python39\python.exe" "%ROOT%\start_frontend_simple.py"
echo     [OK] 前端已启动
echo.

:show_info
echo ==========================================================
echo  启动完成！
echo.
echo  前端页面: http://localhost:%FRONTEND_PORT%/vibe_coding_prototype.html
echo  后端 API: http://localhost:%BACKEND_PORT%
echo  API 文档: http://localhost:%BACKEND_PORT%/docs
echo  健康检查: http://localhost:%BACKEND_PORT%/health
echo.
echo  后端日志: %ROOT%\backend.log
echo  后端错误: %ROOT%\backend.err.log
echo.
echo  停止服务: 运行 stop_all.bat
echo ==========================================================
echo.
echo  此窗口可保持打开，关闭窗口不会停止服务。
echo  按任意键退出本启动窗口...
pause >nul
endlocal
