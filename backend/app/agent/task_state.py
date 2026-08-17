"""轻量任务状态机与状态存储（Demo Mock，内存 + JSON 文件持久化）。

追踪一次报告生成的全过程：从 CREATED 到 COMPLETED/FAILED，
记录每个阶段、失败节点与可重试动作，支撑「失败节点恢复」。

不依赖数据库，仅用内存 dict + 本地 JSON 文件（output/task_states.json）。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskStatus:
    CREATED = "CREATED"
    INTENT_RECOGNIZED = "INTENT_RECOGNIZED"
    PARAMETER_VALIDATED = "PARAMETER_VALIDATED"
    DATA_QUERIED = "DATA_QUERIED"
    CALIBRATION_CHECKED = "CALIBRATION_CHECKED"
    CALCULATED = "CALCULATED"
    REPORT_GENERATED = "REPORT_GENERATED"
    HTML_GENERATED = "HTML_GENERATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"


# 状态推进顺序（用于判断「从哪个节点继续」）
STATUS_ORDER = [
    TaskStatus.CREATED,
    TaskStatus.INTENT_RECOGNIZED,
    TaskStatus.PARAMETER_VALIDATED,
    TaskStatus.DATA_QUERIED,
    TaskStatus.CALIBRATION_CHECKED,
    TaskStatus.CALCULATED,
    TaskStatus.REPORT_GENERATED,
    TaskStatus.HTML_GENERATED,
    TaskStatus.COMPLETED,
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_task_id() -> str:
    return "task_" + uuid.uuid4().hex[:12]


def _default_path() -> Path:
    # output/task_states.json（相对项目根）
    return Path(__file__).resolve().parents[3] / "output" / "task_states.json"


class TaskStore:
    """任务状态存储：内存 dict + 可选 JSON 文件持久化。"""

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

    def create(self, business: str, period: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        """创建一个新任务，返回初始任务记录。"""
        task_id = task_id or _new_task_id()
        record = {
            "task_id": task_id,
            "business": business,
            "period": period,
            "status": TaskStatus.CREATED,
            "current_step": "",
            "history": [],
            "failed_node": "",
            "fail_reason": "",
            "retry_action": "",
            "report_url": "",
            "report_path": "",
            "retry_payload": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._tasks[task_id] = record
            self._persist()
        return record

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._tasks.get(task_id)
            return dict(record) if record else None

    def update(
        self,
        task_id: str,
        status: str,
        step: Optional[str] = None,
        message: Optional[str] = None,
        **fields: Any,
    ) -> Optional[Dict[str, Any]]:
        """推进任务状态，追加历史记录，可选写入额外字段。"""
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return None
            record["status"] = status
            if step is not None:
                record["current_step"] = step
            record["updated_at"] = _now()
            for key, value in fields.items():
                record[key] = value
            record["history"].append({
                "status": status,
                "step": step or "",
                "message": message or "",
                "at": _now(),
            })
            self._persist()
            return dict(record)

    def fail(
        self,
        task_id: str,
        failed_node: str,
        reason: str,
        retry_action: str,
    ) -> Optional[Dict[str, Any]]:
        """标记任务失败，记录失败节点、原因与可重试动作。"""
        return self.update(
            task_id,
            status=TaskStatus.FAILED,
            step=failed_node,
            failed_node=failed_node,
            fail_reason=reason,
            retry_action=retry_action,
            message=reason,
        )

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._tasks.values())
        items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return items


# 全局单例
task_store = TaskStore()
