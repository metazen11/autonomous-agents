from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.schemas import PromotionCandidate, Task, TaskUpdate, utc_now_iso


class TodoJsonAdapter(TaskAdapter):
    """Local task adapter backed by a canonical todo.json document."""

    def __init__(self, todo_path: str | Path):
        self.todo_path = Path(todo_path)

    def list_ready_tasks(self) -> list[Task]:
        payload = self._load_document()
        tasks = [Task.from_dict(item) for item in payload["tasks"]]
        ready = [task for task in tasks if task.status == "ready"]
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(ready, key=lambda task: (priority_order.get(task.priority, 9), task.id))

    def get_task(self, task_id: str) -> Task:
        task = self._get_task_from_document(task_id)
        return Task.from_dict(task)

    def claim_task(self, task_id: str, worker_id: str) -> None:
        payload = self._load_document()
        task = self._find_task(payload, task_id)
        task["status"] = "in_progress"
        metadata = dict(task.get("metadata", {}))
        metadata["claimed_by"] = worker_id
        metadata["claimed_at"] = utc_now_iso()
        task["metadata"] = metadata
        self._write_document(payload)

    def update_task(self, task_id: str, update: TaskUpdate) -> Task:
        payload = self._load_document()
        task = self._find_task(payload, task_id)

        if update.status is not None:
            task["status"] = update.status
        if update.blockers is not None:
            task["blockers"] = list(update.blockers)
        if update.artifacts is not None:
            task["artifacts"] = self._merge_unique(task.get("artifacts", []), update.artifacts)
        if update.improvement_candidates is not None:
            task["improvement_candidates"] = self._merge_unique(
                task.get("improvement_candidates", []),
                update.improvement_candidates,
            )
        if update.metadata_patch:
            metadata = dict(task.get("metadata", {}))
            metadata.update(update.metadata_patch)
            task["metadata"] = metadata
        if update.append_phase_log:
            history = list(task.get("phase_history", []))
            history.append({"timestamp": utc_now_iso(), "message": update.append_phase_log})
            task["phase_history"] = history

        task["updated_at"] = utc_now_iso()
        self._write_document(payload)
        return Task.from_dict(task)

    def create_follow_up(self, item: PromotionCandidate) -> str | None:
        payload = self._load_document()
        follow_ups = payload.setdefault("follow_ups", [])
        follow_up_id = f"follow-up-{len(follow_ups) + 1}"
        follow_ups.append(
            {
                "id": follow_up_id,
                "title": item.title,
                "description": item.description,
                "candidate_type": item.candidate_type,
                "source_evidence": item.source_evidence,
                "expected_benefit": item.expected_benefit,
                "created_at": utc_now_iso(),
                "status": "ready",
            }
        )
        self._write_document(payload)
        return follow_up_id

    def _get_task_from_document(self, task_id: str) -> dict[str, Any]:
        payload = self._load_document()
        return self._find_task(payload, task_id)

    def _load_document(self) -> dict[str, Any]:
        if not self.todo_path.exists():
            raise TaskAdapterError(f"todo.json not found: {self.todo_path}")
        try:
            payload = json.loads(self.todo_path.read_text())
        except json.JSONDecodeError as exc:
            raise TaskAdapterError(f"Invalid todo.json: {exc}") from exc
        if "tasks" not in payload or not isinstance(payload["tasks"], list):
            raise TaskAdapterError("todo.json must contain a top-level 'tasks' array")
        return payload

    def _write_document(self, payload: dict[str, Any]) -> None:
        self.todo_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def _find_task(payload: dict[str, Any], task_id: str) -> dict[str, Any]:
        for item in payload["tasks"]:
            if str(item.get("id")) == task_id:
                return item
        raise TaskAdapterError(f"Task not found: {task_id}")

    @staticmethod
    def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
        merged = list(existing)
        for value in incoming:
            if value not in merged:
                merged.append(value)
        return merged

