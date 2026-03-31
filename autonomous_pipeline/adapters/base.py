from __future__ import annotations

from abc import ABC, abstractmethod

from autonomous_pipeline.schemas import PromotionCandidate, Task, TaskUpdate


class TaskAdapterError(RuntimeError):
    """Raised when a task adapter cannot fulfill its contract."""


class TaskAdapter(ABC):
    """Canonical task adapter interface for all task systems."""

    @abstractmethod
    def list_ready_tasks(self) -> list[Task]:
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: str) -> Task:
        raise NotImplementedError

    @abstractmethod
    def claim_task(self, task_id: str, worker_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_task(self, task_id: str, update: TaskUpdate) -> Task:
        raise NotImplementedError

    @abstractmethod
    def create_follow_up(self, item: PromotionCandidate) -> str | None:
        raise NotImplementedError

    def create_or_update_pr(self, *, title: str, body: str, base: str) -> dict | None:
        raise TaskAdapterError("Pull request integration is not supported for this task adapter")
