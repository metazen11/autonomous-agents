from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.schemas import PromotionCandidate, Task, TaskUpdate, utc_now_iso


class FileTaskAdapter(TaskAdapter):
    """Task adapter backed by local markdown/text files or inline prompt text."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        task_file: str | Path | None = None,
        prompt_text: str | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.task_file = Path(task_file) if task_file is not None else None
        self.prompt_text = prompt_text
        self.default_plans_dir = self.repo_root / "plans"
        self.state_path = Path(state_path) if state_path is not None else self.repo_root / ".autonomous-file-task.json"

    def list_ready_tasks(self) -> list[Task]:
        ready = [task for task in self._current_tasks() if task.status == "ready"]
        return sorted(ready, key=lambda task: (task.metadata.get("source_label", ""), task.id))

    def get_task(self, task_id: str) -> Task:
        for task in self._current_tasks():
            if task.id == task_id:
                return task
        raise TaskAdapterError(f"Task not found: {task_id}")

    def claim_task(self, task_id: str, worker_id: str) -> None:
        task = self.get_task(task_id)
        metadata = dict(task.metadata)
        metadata["claimed_by"] = worker_id
        metadata["claimed_at"] = utc_now_iso()
        task.status = "in_progress"
        task.metadata = metadata
        self._write_state(task)

    def update_task(self, task_id: str, update: TaskUpdate) -> Task:
        task = self.get_task(task_id)

        if update.status is not None:
            task.status = update.status
        if update.blockers is not None:
            task.blockers = list(update.blockers)
        if update.artifacts is not None:
            task.artifacts = self._merge_unique(task.artifacts, update.artifacts)
        if update.improvement_candidates is not None:
            task.improvement_candidates = self._merge_unique(task.improvement_candidates, update.improvement_candidates)
        if update.metadata_patch:
            metadata = dict(task.metadata)
            metadata.update(update.metadata_patch)
            task.metadata = metadata
        if update.append_phase_log:
            phase_history = list(task.metadata.get("phase_history", []))
            phase_history.append({"timestamp": utc_now_iso(), "message": update.append_phase_log})
            task.metadata["phase_history"] = phase_history

        task.metadata["updated_at"] = utc_now_iso()
        self._write_state(task)
        return task

    def create_follow_up(self, item: PromotionCandidate) -> str | None:
        payload = self._load_state_payload()
        follow_ups = list(payload.get("follow_ups", []))
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
        payload["follow_ups"] = follow_ups
        self._write_state_payload(payload)
        return follow_up_id

    def _current_tasks(self) -> list[Task]:
        base_tasks = self._build_base_tasks()
        payload = self._load_state_payload()
        stored_tasks = self._stored_task_map(payload)
        merged_tasks: list[Task] = []
        for base_task in base_tasks:
            stored_task = stored_tasks.get(base_task.id)
            if stored_task is None:
                merged_tasks.append(base_task)
                continue
            if stored_task.metadata.get("source_fingerprint") != base_task.metadata.get("source_fingerprint"):
                merged_tasks.append(base_task)
                continue

            payload = base_task.to_dict()
            payload.update(
                {
                    "status": stored_task.status,
                    "blockers": stored_task.blockers,
                    "artifacts": stored_task.artifacts,
                    "improvement_candidates": stored_task.improvement_candidates,
                    "metadata": stored_task.metadata,
                }
            )
            merged_tasks.append(Task.from_dict(payload))
        return merged_tasks

    def _build_base_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for source_text, source_label, source_url, source_kind in self._resolve_sources():
            normalized = source_text.strip()
            if not normalized:
                continue

            lines = [line.strip() for line in normalized.splitlines()]
            title_index = next((index for index, line in enumerate(lines) if line), 0)
            raw_title = lines[title_index] if lines else "Prompt task"
            title = self._normalize_title(raw_title)
            body_lines = normalized.splitlines()
            if title_index < len(body_lines):
                body_lines = body_lines[title_index + 1 :]
            body = "\n".join(body_lines).strip()
            if not body:
                body = normalized

            metadata = {
                "source_fingerprint": hashlib.sha1(normalized.encode("utf-8")).hexdigest(),
                "source_kind": source_kind,
                "source_label": source_label,
            }
            if source_kind == "file" and source_url is not None:
                metadata["task_file"] = source_url

            tasks.append(
                Task(
                    id=self._task_id(source_kind, source_label),
                    title=title,
                    body=body,
                    source=source_kind,
                    source_url=source_url,
                    metadata=metadata,
                )
            )

        if not tasks:
            raise TaskAdapterError("No prompt sources found")
        return tasks

    def _resolve_sources(self) -> list[tuple[str, str, str | None, str]]:
        if self.task_file is not None:
            task_path = self.task_file if self.task_file.is_absolute() else self.repo_root / self.task_file
            if not task_path.exists():
                raise TaskAdapterError(f"Task file not found: {task_path}")
            if task_path.is_dir():
                return [self._file_source(path) for path in self._discover_task_files(task_path)]
            return [self._file_source(task_path)]
        if self.prompt_text is not None:
            return [(self.prompt_text, "inline prompt", None, "prompt")]
        if self.default_plans_dir.exists():
            return [self._file_source(path) for path in self._discover_task_files(self.default_plans_dir)]
        raise TaskAdapterError("No task file, inline prompt, or /plans directory configured")

    def _load_state_payload(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text())
        except json.JSONDecodeError as exc:
            raise TaskAdapterError(f"Invalid file task state: {exc}") from exc
        if not isinstance(payload, dict):
            raise TaskAdapterError("File task state must be a JSON object")
        return payload

    def _write_state(self, task: Task) -> None:
        payload = self._load_state_payload()
        tasks = dict(payload.get("tasks", {}))
        tasks[task.id] = task.to_dict()
        payload["tasks"] = tasks
        self._write_state_payload(payload)

    def _write_state_payload(self, payload: dict) -> None:
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def _merge_unique(existing: list[str], incoming: list[str]) -> list[str]:
        merged = list(existing)
        for value in incoming:
            if value not in merged:
                merged.append(value)
        return merged

    @staticmethod
    def _normalize_title(raw_title: str) -> str:
        stripped = raw_title.lstrip("#").strip()
        stripped = re.sub(r"^\*\s+", "", stripped)
        stripped = re.sub(r"^-\s+", "", stripped)
        return stripped or "Prompt task"

    @staticmethod
    def _task_id(source_kind: str, source_label: str) -> str:
        digest = hashlib.sha1(f"{source_kind}:{source_label}".encode("utf-8")).hexdigest()[:12]
        return f"{source_kind}-{digest}"

    def _discover_task_files(self, directory: Path) -> list[Path]:
        files = [path for path in sorted(directory.iterdir()) if path.is_file() and path.suffix.lower() in {".md", ".txt"}]
        if not files:
            raise TaskAdapterError(f"No markdown or text task files found in: {directory}")
        return files

    def _file_source(self, path: Path) -> tuple[str, str, str, str]:
        resolved = path.resolve()
        try:
            source_label = str(resolved.relative_to(self.repo_root))
        except ValueError:
            source_label = str(resolved)
        return (resolved.read_text(), source_label, str(resolved), "file")

    @staticmethod
    def _stored_task_map(payload: dict) -> dict[str, Task]:
        stored_tasks = payload.get("tasks", {})
        if isinstance(stored_tasks, dict):
            return {
                str(task_id): Task.from_dict(task_payload)
                for task_id, task_payload in stored_tasks.items()
                if isinstance(task_payload, dict)
            }
        stored_task = payload.get("task")
        if isinstance(stored_task, dict):
            task = Task.from_dict(stored_task)
            return {task.id: task}
        return {}
