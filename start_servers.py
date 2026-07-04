"""
异动分析 Agent —— 前后端一键启动控制脚本

用法:
    python start_servers.py start     启动后端(8000) + 前端(8080)
    python start_servers.py stop      停止当前项目记录的服务
    python start_servers.py restart   重启当前项目服务
    python start_servers.py status    查看记录的进程状态（默认）
    python start_servers.py check     检查端口、项目身份、前端和Demo配置

安全约束:
    - 8000 被占用时必须校验 /openapi.json 的项目标题和 /api/chat/stream。
    - 若端口属于其他项目，明确报错，不自动接管或结束未知进程。
    - stop/restart 只停止 .runtime 记录的 PID，或经 OpenAPI 验证为当前项目的后端。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
FRONTEND_DIR = os.path.join(ROOT, "project_delivery")
RUNTIME_DIR = os.path.join(ROOT, ".runtime")
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(RUNTIME_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

STATE_FILE = os.path.join(RUNTIME_DIR, "start_servers.json")
BACKEND_PID_FILE = os.path.join(RUNTIME_DIR, "backend.pid")
FRONTEND_PID_FILE = os.path.join(RUNTIME_DIR, "frontend.pid")

BACKEND_LOG = os.path.join(LOG_DIR, "backend.out.log")
BACKEND_ERR = os.path.join(LOG_DIR, "backend.err.log")
FRONTEND_LOG = os.path.join(LOG_DIR, "frontend.out.log")
FRONTEND_ERR = os.path.join(LOG_DIR, "frontend.err.log")

PROJECT_TITLE = "VoC 体验异动分析 Agent"
LEGACY_PROJECT_TITLES = {"VoC回声系统 - 体验异动分析Agent"}
BACKEND_PORT = 8000
FRONTEND_PORT = 8080
FRONTEND_PAGE = "vibe_coding_prototype.html"
BACKEND_BASE = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}/{FRONTEND_PAGE}"

CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


def _utf8_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _proc_alive(pid):
    if not pid:
        return False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        return str(pid) in r.stdout
    except Exception:
        return False


def _kill(pid):
    if not pid:
        return
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )


def _port_pid(port):
    try:
        r = subprocess.run(
            f'netstat -ano | findstr ":{port}"',
            shell=True,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        for line in r.stdout.splitlines():
            parts = line.split()
            if "LISTENING" in line and len(parts) >= 5:
                return parts[-1]
    except Exception:
        pass
    return None


def _read_url(url, timeout=3):
    with urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body


def _read_json(url, timeout=3):
    status, body = _read_url(url, timeout=timeout)
    return status, json.loads(body)


def _openapi_matches_project(openapi):
    return (
        openapi.get("info", {}).get("title") == PROJECT_TITLE
        and "/api/chat/stream" in openapi.get("paths", {})
    )


def _openapi_belongs_to_project(openapi):
    title = openapi.get("info", {}).get("title")
    return (
        title in ({PROJECT_TITLE} | LEGACY_PROJECT_TITLES)
        and "/api/chat/stream" in openapi.get("paths", {})
    )


def _inspect_backend():
    info = {
        "listening": bool(_port_pid(BACKEND_PORT)),
        "reachable": False,
        "title": None,
        "matches": False,
        "belongs": False,
        "has_stream": False,
        "health_ok": False,
        "error": "",
    }
    try:
        status, health = _read_json(f"{BACKEND_BASE}/health")
        info["health_ok"] = status == 200 and health.get("status") == "healthy"
    except Exception as exc:
        info["error"] = f"health: {type(exc).__name__}: {exc}"

    try:
        status, openapi = _read_json(f"{BACKEND_BASE}/openapi.json")
        info["reachable"] = status == 200
        info["title"] = openapi.get("info", {}).get("title")
        info["has_stream"] = "/api/chat/stream" in openapi.get("paths", {})
        info["matches"] = _openapi_matches_project(openapi)
        info["belongs"] = _openapi_belongs_to_project(openapi)
    except Exception as exc:
        if not info["error"]:
            info["error"] = f"openapi: {type(exc).__name__}: {exc}"
    return info


def _frontend_ready():
    try:
        status, body = _read_url(FRONTEND_URL)
        return status == 200 and (PROJECT_TITLE in body or "体验异动分析Agent" in body)
    except Exception:
        return False


def _wait_until(predicate, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
    return False


def _backend_ready():
    inspected = _inspect_backend()
    return inspected["matches"] and inspected["health_ok"] and inspected["has_stream"]


def _load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if data.get("backend"):
        with open(BACKEND_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(data["backend"]))
    if data.get("frontend"):
        with open(FRONTEND_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(data["frontend"]))


def _clear_state():
    for path in (STATE_FILE, BACKEND_PID_FILE, FRONTEND_PID_FILE):
        try:
            os.remove(path)
        except OSError:
            pass


def _spawn(args, cwd, out_path, err_path):
    out = open(out_path, "ab")
    err = open(err_path, "ab")
    try:
        p = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=out,
            stderr=err,
            env=_utf8_env(),
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            close_fds=True,
        )
        return p.pid
    finally:
        out.close()
        err.close()


def _start_backend(data):
    recorded = data.get("backend")
    if recorded and _proc_alive(recorded):
        inspected = _inspect_backend()
        if inspected["matches"]:
            print(f"[=] 当前项目后端已在运行 (PID {recorded})")
            return recorded

    existing = _port_pid(BACKEND_PORT)
    if existing:
        inspected = _inspect_backend()
        if inspected["matches"]:
            print(f"[=] 当前项目后端已在运行 (PID {existing})")
            return existing
        print("启动失败：端口 8000 已被其他服务占用。")
        print(f"检测到的应用：{inspected.get('title') or '未知/无法读取 OpenAPI'}")
        print(f"期望的应用：{PROJECT_TITLE}")
        print("请关闭占用进程，或为当前项目配置其他端口。")
        raise SystemExit(1)

    print("[>] 启动 backend ...")
    pid = _spawn([sys.executable, os.path.join(BACKEND_DIR, "run.py")], BACKEND_DIR, BACKEND_LOG, BACKEND_ERR)
    ready = _wait_until(_backend_ready, timeout=45)
    if not ready:
        inspected = _inspect_backend()
        print(f"[!!] 后端启动后项目身份检查失败：{inspected}")
        raise SystemExit(1)
    print("VoC 体验异动分析 Agent 后端启动成功。")
    return pid


def _start_frontend(data):
    recorded = data.get("frontend")
    if recorded and _proc_alive(recorded) and _frontend_ready():
        print(f"[=] 前端已在运行 (PID {recorded})")
        return recorded

    existing = _port_pid(FRONTEND_PORT)
    if existing:
        if _frontend_ready():
            print(f"[=] 前端页面已可访问 (PID {existing})")
            return existing
        print("启动失败：端口 8080 已被其他服务占用，且不是当前前端页面。")
        raise SystemExit(1)

    print("[>] 启动 frontend ...")
    pid = _spawn(
        [sys.executable, "-m", "http.server", str(FRONTEND_PORT), "--directory", FRONTEND_DIR],
        FRONTEND_DIR,
        FRONTEND_LOG,
        FRONTEND_ERR,
    )
    if not _wait_until(_frontend_ready, timeout=20):
        print(f"[!!] 前端页面未就绪，请查看 {FRONTEND_ERR}")
        raise SystemExit(1)
    print("前端启动成功。")
    return pid


def _env_value(name, default=""):
    env_path = os.path.join(BACKEND_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(f"{name}="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get(name, default)


def _print_check():
    backend = _inspect_backend()
    frontend = _frontend_ready()
    key = _env_value("DEEPSEEK_API_KEY")
    deterministic = _env_value("DEMO_DETERMINISTIC", "true").lower() != "false"
    print(f"[后端端口] {BACKEND_PORT}：{'已监听' if backend['listening'] else '未监听'}")
    print(f"[应用标题] {backend.get('title') or '-'}：{'匹配' if backend['matches'] else '不匹配'}")
    print(f"[健康检查] {'通过' if backend['health_ok'] else '未通过'}")
    print(f"[流式接口] /api/chat/stream：{'存在' if backend['has_stream'] else '缺失'}")
    print(f"[前端端口] {FRONTEND_PORT}：{'已监听' if _port_pid(FRONTEND_PORT) else '未监听'}")
    print(f"[前端页面] {'可访问' if frontend else '不可访问'}")
    print(f"[DeepSeek] {'已配置' if key and not key.startswith('your_') else '未配置'} / 降级可用")
    print(f"[模拟数据] 稳定 Demo 模式{'已开启' if deterministic else '已关闭'}")
    return backend["matches"] and backend["health_ok"] and backend["has_stream"] and frontend


def cmd_start():
    data = _load_state()
    backend_pid = _start_backend(data)
    frontend_pid = _start_frontend(data)
    _save_state({"backend": backend_pid, "frontend": frontend_pid, "started_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    print()
    print("=" * 60)
    print(f"[OK] 后端  PID {backend_pid:<8} http://localhost:{BACKEND_PORT}/docs")
    print(f"[OK] 前端  PID {frontend_pid:<8} http://localhost:{FRONTEND_PORT}/{FRONTEND_PAGE}")
    print(f"[i] 检查命令  python start_servers.py check")
    print(f"[i] 停止命令  python start_servers.py stop")
    print("=" * 60)


def cmd_stop():
    data = _load_state()
    killed = False
    backend_pid = data.get("backend")
    if backend_pid and _proc_alive(backend_pid):
        print(f"[>] 停止 backend (PID {backend_pid}) ...")
        _kill(backend_pid)
        killed = True
    else:
        inspected = _inspect_backend()
        existing = _port_pid(BACKEND_PORT)
        if existing and inspected["belongs"]:
            print(f"[>] 停止已验证属于当前项目的 backend (PID {existing}) ...")
            _kill(existing)
            killed = True
        else:
            print("[=] backend 未运行或端口不属于当前项目，跳过")

    frontend_pid = data.get("frontend")
    if frontend_pid and _proc_alive(frontend_pid):
        print(f"[>] 停止 frontend (PID {frontend_pid}) ...")
        _kill(frontend_pid)
        killed = True
    else:
        print("[=] frontend 未运行或未由当前项目记录，跳过")

    _clear_state()
    print("[OK] 已停止" if killed else "[i] 无当前项目记录的运行服务")


def cmd_status():
    data = _load_state()
    print("=" * 60)
    print("异动分析 Agent 服务状态")
    print("=" * 60)
    for key, name, port in (("backend", "后端", BACKEND_PORT), ("frontend", "前端", FRONTEND_PORT)):
        pid = data.get(key)
        alive = _proc_alive(pid) if pid else False
        mark = "[运行]" if alive else "[停止]"
        print(f"{mark} {name}  PID={str(pid or '-'):<8} 端口 {port}")
    print("-" * 60)
    print(f"运行态目录: {RUNTIME_DIR}")
    print(f"日志目录: {LOG_DIR}")


def cmd_check():
    ok = _print_check()
    raise SystemExit(0 if ok else 1)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "restart":
        cmd_stop()
        time.sleep(1)
        cmd_start()
    elif cmd == "status":
        cmd_status()
    elif cmd == "check":
        cmd_check()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
