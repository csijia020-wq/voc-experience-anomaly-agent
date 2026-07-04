"""
后端稳定后台启动脚本

解决问题：
  1. `AttributeError: 'NoneType' object has no attribute 'isatty'`
     —— uvicorn 的日志格式化器在 stdout 被重定向为 None 时崩溃
  2. `UnicodeEncodeError: 'gbk' codec can't encode character`
     —— Windows 控制台 GBK 编码无法打印 emoji/中文字符

原理：
  - 不使用 shell 的 `> log 2>&1` 重定向（会把 sys.stdout 替换为 None）
  - 改在 Python 进程内打开真实文件对象作为 stdout/stderr，并强制 UTF-8
  - 显式构造 uvicorn.Config 并传 use_colors=False，跳过 isatty() 分支
  - 绑定进程退出码到脚本，便于 .bat / 外壳判断成败
"""
import os
import sys
import time
import signal
import threading
from pathlib import Path

# ---- 路径常量 ----
ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
LOG_DIR = ROOT
STDOUT_LOG = LOG_DIR / "backend.log"
STDERR_LOG = LOG_DIR / "backend.err.log"

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))


def _open_log(path: Path):
    """以 UTF-8、行缓冲、unbuffered 错误友好方式打开日志文件"""
    return open(path, "a", encoding="utf-8", buffering=1)


def main():
    # 切换到 backend 目录，使 `app.main:app` 可被正确导入
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))

    # 把真实 stdout/stderr 指向文件对象（而非 shell 重定向产生的 None）
    out_fp = _open_log(STDOUT_LOG)
    err_fp = _open_log(STDERR_LOG)
    sys.stdout = out_fp
    sys.stderr = err_fp

    # 兜底：若环境依旧想用 GBK，强制改成 UTF-8（避免 emoji/中文崩溃）
    for name in ("PYTHONIOENCODING",):
        os.environ[name] = "utf-8"

    # 延迟导入，确保上面的 chdir / path 生效
    import uvicorn
    from uvicorn.config import Config
    from uvicorn.server import Server

    print(f"\n{'=' * 60}", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动后端服务", flush=True)
    print(f"  Host: {HOST}", flush=True)
    print(f"  Port: {PORT}", flush=True)
    print(f"  App : app.main:app", flush=True)
    print(f"  CWD : {BACKEND_DIR}", flush=True)
    print(f"  日志: {STDOUT_LOG}", flush=True)
    print(f"{'=' * 60}", flush=True)

    # 显式构造 Config：
    #   - use_colors=False 关键！跳过 DefaultFormatter 中 sys.stdout.isatty() 调用
    #   - log_level 用默认 info
    config = Config(
        app="app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        use_colors=False,
        log_level="info",
        timeout_graceful_shutdown=10,
    )
    server = Server(config=config)

    # 优雅处理 Ctrl+C / 终止信号，保证日志刷新落盘
    def _shutdown(signum, frame):
        print(f"\n[{time.strftime('%H:%M:%S')}] 收到退出信号 {signum}，正在关闭...", flush=True)
        server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.run()
    except Exception as e:
        print(f"[FATAL] 后端启动失败: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            out_fp.flush()
            err_fp.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
