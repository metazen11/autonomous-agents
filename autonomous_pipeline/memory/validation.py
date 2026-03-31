from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from autonomous_pipeline.memory.agent_memory import AgentMemoryClient, AgentMemoryError


@dataclass(slots=True)
class ValidationCheck:
    name: str
    status: str
    detail: str


@dataclass(slots=True)
class ValidationReport:
    overall_status: str
    checks: list[ValidationCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_status": self.overall_status,
            "checks": [
                {"name": check.name, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
        }


def validate_agent_memory(client: AgentMemoryClient, *, project_path: str | Path) -> ValidationReport:
    checks: list[ValidationCheck] = []
    project = str(project_path)
    unique = uuid.uuid4().hex[:8]
    lesson_title = f"autonomous validation lesson {unique}"

    try:
        health = client.get_health()
        status = health.get("status", "unknown")
        check_status = "pass" if status in {"ok", "degraded"} else "fail"
        checks.append(
            ValidationCheck(
                name="health",
                status=check_status,
                detail=f"service status={status}",
            )
        )
    except AgentMemoryError as exc:
        checks.append(ValidationCheck(name="health", status="fail", detail=str(exc)))
        return ValidationReport(overall_status="fail", checks=checks)

    try:
        created = client.create_lesson(
            title=lesson_title,
            rule="Validation lesson for autonomous pipeline integration",
            project=project,
            severity="warning",
            trigger_tool="Bash",
            trigger_pattern="autonomous-sync",
        )
        checks.append(
            ValidationCheck(
                name="create_lesson",
                status="pass",
                detail=f"created lesson id={created.get('id')}",
            )
        )
    except AgentMemoryError as exc:
        checks.append(ValidationCheck(name="create_lesson", status="fail", detail=str(exc)))
        return ValidationReport(overall_status="fail", checks=checks)

    try:
        lessons = client.list_lessons(project=project, limit=25)
        found = any(lesson.get("title") == lesson_title for lesson in lessons)
        checks.append(
            ValidationCheck(
                name="list_lessons",
                status="pass" if found else "fail",
                detail="created lesson visible in scoped lesson list" if found else "created lesson not found",
            )
        )
    except AgentMemoryError as exc:
        checks.append(ValidationCheck(name="list_lessons", status="fail", detail=str(exc)))

    try:
        matched = client.match_lessons(
            tool_name="Bash",
            tool_input_preview="autonomous-sync --check",
            project=project,
        )
        found = any(lesson.get("title") == lesson_title for lesson in matched)
        checks.append(
            ValidationCheck(
                name="match_lessons",
                status="pass" if found else "fail",
                detail="lesson matched by tool and pattern" if found else "lesson did not match expected pattern",
            )
        )
    except AgentMemoryError as exc:
        checks.append(ValidationCheck(name="match_lessons", status="fail", detail=str(exc)))

    try:
        result = client.search_observations("autonomous pipeline", project=project, limit=3)
        total = result.get("total")
        checks.append(
            ValidationCheck(
                name="search_observations",
                status="pass" if isinstance(total, int) else "fail",
                detail=f"search total={total!r}",
            )
        )
    except AgentMemoryError as exc:
        checks.append(ValidationCheck(name="search_observations", status="fail", detail=str(exc)))

    overall = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return ValidationReport(overall_status=overall, checks=checks)
