from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


TaskStatus = Literal["ready", "in_progress", "blocked", "done", "failed", "needs_human"]
TaskPriority = Literal["low", "medium", "high", "urgent"]
RunMode = Literal["dry_run", "full"]
PhaseName = Literal["INIT", "PICK", "PLAN", "DEV", "CODE_REVIEW", "TEST", "REVIEW", "PR", "REPORT", "IMPROVE"]
VerificationCategory = Literal["build", "lint", "unit", "integration", "ui", "security", "data", "performance"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Subtask:
    id: str
    title: str
    status: TaskStatus = "ready"
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Subtask":
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            status=payload.get("status", "ready"),
            dependencies=list(payload.get("dependencies", [])),
            acceptance_criteria=list(payload.get("acceptance_criteria", [])),
            blockers=list(payload.get("blockers", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class Task:
    id: str
    title: str
    body: str = ""
    status: TaskStatus = "ready"
    priority: TaskPriority = "medium"
    labels: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    subtasks: list[Subtask] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    source: str = "todo_json"
    source_url: str | None = None
    artifacts: list[str] = field(default_factory=list)
    improvement_candidates: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["subtasks"] = [subtask.to_dict() for subtask in self.subtasks]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Task":
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            body=str(payload.get("body", "")),
            status=payload.get("status", "ready"),
            priority=payload.get("priority", "medium"),
            labels=list(payload.get("labels", [])),
            acceptance_criteria=list(payload.get("acceptance_criteria", [])),
            dependencies=list(payload.get("dependencies", [])),
            subtasks=[Subtask.from_dict(item) for item in payload.get("subtasks", [])],
            blockers=list(payload.get("blockers", [])),
            source=str(payload.get("source", "todo_json")),
            source_url=payload.get("source_url"),
            artifacts=list(payload.get("artifacts", [])),
            improvement_candidates=list(payload.get("improvement_candidates", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class TaskUpdate:
    status: TaskStatus | None = None
    blockers: list[str] | None = None
    artifacts: list[str] | None = None
    improvement_candidates: list[str] | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)
    append_phase_log: str | None = None


@dataclass(slots=True)
class AgentResult:
    agent_name: str
    status: Literal["success", "needs_human", "failed"]
    summary: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    follow_up: list[str] = field(default_factory=list)
    memory_status: Literal["loaded", "skipped", "unavailable"] = "unavailable"


@dataclass(slots=True)
class PromotionCandidate:
    title: str
    description: str
    source_evidence: list[str] = field(default_factory=list)
    expected_benefit: str = ""
    candidate_type: Literal["memory", "playbook", "script", "skill", "adapter"] = "memory"


@dataclass(slots=True)
class PhaseRecord:
    phase: PhaseName
    status: Literal["success", "failed", "needs_human"]
    summary: str
    timestamp: str = field(default_factory=utc_now_iso)
    artifacts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunState:
    session_id: str
    repo_root: str
    started_at: str = field(default_factory=utc_now_iso)
    mode: RunMode = "full"
    current_phase: PhaseName = "INIT"
    selected_task_id: str | None = None
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    skipped_tasks: list[str] = field(default_factory=list)
    memory_status: str = "unknown"
    memory_lessons_loaded: int = 0
    phase_history: list[PhaseRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["phase_history"] = [asdict(record) for record in self.phase_history]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunState":
        return cls(
            session_id=str(payload["session_id"]),
            repo_root=str(payload["repo_root"]),
            started_at=payload.get("started_at", utc_now_iso()),
            mode=payload.get("mode", "full"),
            current_phase=payload.get("current_phase", "INIT"),
            selected_task_id=payload.get("selected_task_id"),
            completed_tasks=list(payload.get("completed_tasks", [])),
            failed_tasks=list(payload.get("failed_tasks", [])),
            skipped_tasks=list(payload.get("skipped_tasks", [])),
            memory_status=payload.get("memory_status", "unknown"),
            memory_lessons_loaded=int(payload.get("memory_lessons_loaded", 0)),
            phase_history=[
                PhaseRecord(
                    phase=item["phase"],
                    status=item["status"],
                    summary=item["summary"],
                    timestamp=item.get("timestamp", utc_now_iso()),
                    artifacts=list(item.get("artifacts", [])),
                )
                for item in payload.get("phase_history", [])
            ],
        )


@dataclass(slots=True)
class RuntimeConfig:
    task_source: Literal["todo_json", "github", "asana", "file", "prompt"] = "todo_json"
    todo_path: str = "todo.json"
    asana_project_gid: str | None = None
    asana_workspace_gid: str | None = None
    asana_default_section_gid: str | None = None
    task_file: str | None = None
    prompt_text: str | None = None
    artifacts_dir: str = "artifacts"
    memory_url: str = "http://127.0.0.1:3377"
    github_repo: str | None = None
    github_label: str | None = None
    github_skip_labels: list[str] = field(default_factory=lambda: ["blocked", "human-only"])
    github_command: list[str] = field(default_factory=lambda: ["gh"])
    pr_base: str = "main"
    max_tasks: int = 1
    development_command: str | None = None
    development_retries: int = 0
    build_command: str | None = None
    lint_command: str | None = None
    test_command: str | None = None
    ui_command: str | None = None
    verification_retries: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SpecialistContract:
    name: str
    prompt_file: str
    mode: Literal["read_only", "bounded_write"]
    responsibilities: list[str]
    required_inputs: list[str]
    optional_inputs: list[str] = field(default_factory=list)
    allowed_write_scope_required: bool = False
    output_keys: list[str] = field(default_factory=list)
    escalation_conditions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationCommand:
    category: VerificationCategory
    command: str
    source: Literal["config", "autodetect"]


@dataclass(slots=True)
class VerificationResult:
    category: VerificationCategory
    command: str
    status: Literal["pass", "fail", "skipped"]
    artifact_path: str | None = None
    detail: str = ""


@dataclass(slots=True)
class PullRequestResult:
    status: Literal["created", "updated", "human_required", "failed"]
    url: str | None = None
    title: str = ""
    body_artifact_path: str | None = None
    detail: str = ""
