"""定时任务管理（Demo Mock，本地 JSON 持久化）。

支持创建/查看/暂停/恢复/删除本地定时任务，仅用于演示「定时任务」链路，
不接真实 cron 调度、大象机器人或生产系统。

持久化到 output/scheduled_tasks.json。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_task_id() -> str:
    return "sched_" + uuid.uuid4().hex[:12]


def _default_path() -> Path:
    return Path(__file__).resolve().parents[3] / "output" / "scheduled_tasks.json"


class ScheduledTaskStore:
    """本地定时任务存储（Demo Mock）。"""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or str(_default_path())
        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._tasks = data
        except Exception:
            self._tasks = {}

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._tasks, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def create(
        self,
        name: str,
        business: str,
        period_rule: str = "上一完整自然周",
        cron: str = "0 9 * * 1",
        receiver: str = "本地 Demo",
    ) -> Dict[str, Any]:
        task_id = _new_task_id()
        record = {
            "task_id": task_id,
            "name": name,
            "business": business,
            "period_rule": period_rule,
            "cron": cron,
            "receiver": receiver,
            "status": "running",
            "created_at": _now(),
            "last_run_at": "",
            "last_result": "",
            "demo_mock": True,
        }
        with self._lock:
            self._tasks[task_id] = record
            self._persist()
        return dict(record)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._tasks.get(task_id)
            return dict(record) if record else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._tasks.values())
        items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return items

    def pause(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._set_status(task_id, "paused")

    def resume(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._set_status(task_id, "running")

    def delete(self, task_id: str) -> bool:
        with self._lock:
            existed = task_id in self._tasks
            self._tasks.pop(task_id, None)
            self._persist()
        return existed

    def _set_status(self, task_id: str, status: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return None
            record["status"] = status
            self._persist()
            return dict(record)


# 全局单例
scheduled_task_store = ScheduledTaskStore()
