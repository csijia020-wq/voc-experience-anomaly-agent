"""
后端稳定启动入口（解决两类历史崩溃）

修复点1：强制关闭日志颜色输出。
    uvicorn 的 DefaultFormatter 在 use_colors 未显式指定时，会调用
    sys.stdout.isatty() 来判断是否着色；当 stdout 为 None（pythonw / 某些
    后台重定向场景）时会抛 AttributeError: 'NoneType' object has no
    attribute 'isatty'，进而导致 ValueError: Unable to configure formatter。
    显式置 use_colors=False 即可彻底绕开 isatty 调用。

修复点2：强制 UTF-8 输出，避免 Windows GBK 控制台无法编码 emoji 等
    字符（如 \U0001f60a）导致 UnicodeEncodeError。

用法：python run.py
"""
import os
import sys

# 1) 兜底：若 stdout/stderr 被设为 None（pythonw 场景），重定向到 devnull，
#    避免后续 isatty() / write() 崩溃。
for _name in ("stdout", "stderr"):
    if getattr(sys, _name, None) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

# 2) 强制 UTF-8，解决 GBK 无法编码 emoji 等字符的问题。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 切换工作目录到 backend，使 app.* 可被正确导入。
_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)
sys.path.insert(0, _HERE)

import uvicorn
from uvicorn.config import LOGGING_CONFIG

# 3) 关键修复：强制关闭颜色，绕开 DefaultFormatter 内的 isatty 调用。
for _fmt in LOGGING_CONFIG["formatters"].values():
    _fmt["use_colors"] = False

from app.config import settings


def main():
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_config=LOGGING_CONFIG,
    )


if __name__ == "__main__":
    main()
