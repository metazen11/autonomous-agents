from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import asdict
from pathlib import Path

from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.memory.agent_memory import AgentMemoryClient, AgentMemoryError
from autonomous_pipeline.schemas import (
    AgentResult,
    PhaseRecord,
    PromotionCandidate,
    PullRequestResult,
    RunState,
    RuntimeConfig,
    Task,
    TaskUpdate,
)
from autonomous_pipeline.specialists import execute_specialist, get_specialist_contract, list_specialist_contracts
from autonomous_pipeline.verification import resolve_verification_commands, run_command_with_retries, run_verification_commands


class PipelineRunner:
    """Minimal runtime skeleton for the autonomous pipeline."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        adapter: TaskAdapter,
        config: RuntimeConfig,
        memory_client: AgentMemoryClient | None = None,
        mode: str = "full",
    ) -> None:
        self.repo_root = Path(repo_root)
        self.adapter = adapter
        self.config = config
        self.memory_client = memory_client
        self.mode = mode
        self.run_state_path = self.repo_root / ".autonomous-state.json"
        self.run_state = self._restore_or_create_state(mode)
        self.artifacts_root = self.repo_root / self.config.artifacts_dir / str(uuid.uuid4())
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> RunState:
        memory_summary = self._load_memory_context()
        self._record_phase(
            "INIT",
            "success",
            f"Runtime skeleton initialized with task source {self.config.task_source}; {memory_summary}",
        )
        self._persist_state()
        return self.run_state

    def pick_task(self) -> Task | None:
        ready = self.adapter.list_ready_tasks()
        if not ready:
            self._record_phase("PICK", "needs_human", "No ready tasks found")
            self._persist_state()
            return None

        task = ready[0]
        self.adapter.claim_task(task.id, worker_id=self.run_state.session_id)
        self.run_state.selected_task_id = task.id
        self._record_phase("PICK", "success", f"Selected task {task.id}: {task.title}")
        self._persist_state()
        return self.adapter.get_task(task.id)

    def report_planning(self, task: Task, summary: str) -> Task:
        artifact_path = self._write_artifact("plan-summary.txt", summary + "\n")
        updated = self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[artifact_path],
                append_phase_log=summary,
                metadata_patch={"last_planning_summary": summary},
            ),
        )
        self._record_phase("PLAN", "success", summary, artifacts=[artifact_path])
        self._persist_state()
        return updated

    def run_verification(self, task: Task) -> list[dict]:
        commands = resolve_verification_commands(self.repo_root, self.config)
        if not commands:
            self._record_phase("TEST", "needs_human", "No verification commands resolved")
            self._persist_state()
            return []

        results = run_verification_commands(
            self.repo_root,
            self.artifacts_root,
            commands,
            retries=self.config.verification_retries,
        )
        artifact_paths = [result.artifact_path for result in results if result.artifact_path]
        status = "success" if all(result.status == "pass" for result in results) else "failed"
        summary = ", ".join(f"{result.category}:{result.status}" for result in results)
        self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[path for path in artifact_paths if path],
                append_phase_log=f"Verification results: {summary}",
                metadata_patch={
                    "verification_results": [
                        {
                            "category": result.category,
                            "status": result.status,
                            "command": result.command,
                            "artifact_path": result.artifact_path,
                        }
                        for result in results
                    ]
                },
            ),
        )
        self._record_phase("TEST", status, f"Verification results: {summary}", artifacts=[path for path in artifact_paths if path])
        self._persist_state()
        return [
            {
                "category": result.category,
                "status": result.status,
                "command": result.command,
                "artifact_path": result.artifact_path,
                "detail": result.detail,
            }
            for result in results
        ]

    def run_development(self, task: Task) -> dict:
        command = self.config.development_command or task.metadata.get("development_command")
        if not command:
            summary = "No development command configured"
            self._record_phase("DEV", "needs_human", summary)
            self._persist_state()
            return {"status": "needs_human", "summary": summary}

        existing_changed_files = list(task.metadata.get("changed_files", []))
        execution = run_command_with_retries(
            self.repo_root,
            self.artifacts_root,
            command=command,
            artifact_name="development.log",
            retries=self.config.development_retries,
        )
        changed_files = self._git_changed_files() or existing_changed_files
        result = {
            "status": execution["status"],
            "command": command,
            "artifact_path": execution["artifact_path"],
            "detail": execution["detail"],
            "attempts": execution["attempts"],
            "changed_files": changed_files,
        }
        phase_status = "success" if execution["status"] == "pass" else "failed"
        summary = f"Development command {execution['status']}: {command}"
        self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[str(execution["artifact_path"])],
                append_phase_log=summary,
                metadata_patch={"development_result": result, "changed_files": result["changed_files"]},
            ),
        )
        self._record_phase("DEV", phase_status, summary, artifacts=[str(execution["artifact_path"])])
        self._persist_state()
        return result

    def run_specialist(self, task: Task, name: str) -> dict:
        result = self._execute_specialist(task, name)
        artifact_path = result.artifacts[0] if result.artifacts else None
        metadata = dict(task.metadata.get("specialist_results", {}))
        metadata[name] = asdict(result)
        self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[artifact_path] if artifact_path else [],
                append_phase_log=result.summary,
                metadata_patch={"specialist_results": metadata},
            ),
        )
        phase_status = result.status if result.status in {"success", "failed", "needs_human"} else "needs_human"
        phase_name = "CODE_REVIEW" if name == "code-reviewer" else "REVIEW"
        self._record_phase(phase_name, phase_status, f"{name}: {result.summary}", artifacts=[artifact_path] if artifact_path else [])
        self._persist_state()
        return {
            "status": result.status,
            "artifact_path": artifact_path,
            "summary": result.summary,
            "findings": result.findings,
            "agent_name": result.agent_name,
        }

    def run_code_review(self, task: Task) -> dict:
        result = self._execute_specialist(task, "code-reviewer", stage="CODE_REVIEW")
        artifact_path = result.artifacts[0] if result.artifacts else None
        verdict = "approved" if not result.findings else "changes_requested"
        self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[artifact_path] if artifact_path else [],
                append_phase_log=result.summary,
                metadata_patch={
                    "code_review_artifact": artifact_path,
                    "code_review_summary": result.summary,
                    "code_review_verdict": verdict,
                    "code_review_result": asdict(result),
                },
            ),
        )
        self._record_phase("CODE_REVIEW", result.status, result.summary, artifacts=[artifact_path] if artifact_path else [])
        self._persist_state()
        return {
            "status": result.status,
            "verdict": verdict,
            "artifact_path": artifact_path,
            "summary": result.summary,
            "findings": result.findings,
        }

    def list_specialist_contracts(self) -> list[dict]:
        return [
            {
                "name": contract.name,
                "prompt_file": contract.prompt_file,
                "mode": contract.mode,
                "responsibilities": contract.responsibilities,
                "required_inputs": contract.required_inputs,
                "optional_inputs": contract.optional_inputs,
                "allowed_write_scope_required": contract.allowed_write_scope_required,
                "output_keys": contract.output_keys,
                "escalation_conditions": contract.escalation_conditions,
            }
            for contract in list_specialist_contracts()
        ]

    def get_specialist_contract(self, name: str) -> dict:
        contract = get_specialist_contract(name)
        return {
            "name": contract.name,
            "prompt_file": contract.prompt_file,
            "mode": contract.mode,
            "responsibilities": contract.responsibilities,
            "required_inputs": contract.required_inputs,
            "optional_inputs": contract.optional_inputs,
            "allowed_write_scope_required": contract.allowed_write_scope_required,
            "output_keys": contract.output_keys,
            "escalation_conditions": contract.escalation_conditions,
        }

    def report_result(self, task: Task, *, success: bool, summary: str, artifacts: list[str] | None = None) -> Task:
        new_status = "done" if success else "failed"
        updated = self.adapter.update_task(
            task.id,
            TaskUpdate(
                status=new_status,
                artifacts=artifacts or [],
                append_phase_log=summary,
                metadata_patch={"final_summary": summary},
            ),
        )
        if success:
            self.run_state.completed_tasks.append(task.id)
        else:
            self.run_state.failed_tasks.append(task.id)
        self._record_phase("REPORT", "success" if success else "failed", summary, artifacts=artifacts or [])
        self._persist_state()
        return updated

    def promote_candidate(self, candidate: PromotionCandidate) -> dict:
        if candidate.candidate_type == "memory":
            lesson = self.remember_lesson(title=candidate.title, rule=candidate.description)
            return {"type": "memory", "result": lesson}

        follow_up_id = self.adapter.create_follow_up(candidate)
        summary = f"Created follow-up for promotion candidate: {candidate.title}"
        self._record_phase("IMPROVE", "success", summary)
        self._persist_state()
        return {"type": "follow_up", "id": follow_up_id}

    def run_review(self, task: Task) -> dict:
        result = self._execute_specialist(task, "code-reviewer", stage="REVIEW")
        artifact_path = result.artifacts[0] if result.artifacts else None
        detail = result.summary
        verdict = "approved" if not result.findings else "changes_requested"
        self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[artifact_path] if artifact_path else [],
                append_phase_log=detail,
                metadata_patch={
                    "review_artifact": artifact_path,
                    "review_summary": detail,
                    "review_verdict": verdict,
                    "review_result": asdict(result),
                },
            ),
        )
        self._record_phase("REVIEW", result.status, detail, artifacts=[artifact_path] if artifact_path else [])
        self._persist_state()
        return {
            "status": result.status,
            "verdict": verdict,
            "artifact_path": artifact_path,
            "summary": detail,
            "findings": result.findings,
        }

    def run_improvement(self, task: Task) -> dict:
        result = self._execute_specialist(task, "skill-promoter")
        promotions: list[dict] = []
        improvement_titles: list[str] = []
        for finding in result.findings:
            if not isinstance(finding, dict) or "title" not in finding or "description" not in finding:
                continue
            candidate = PromotionCandidate(
                title=str(finding["title"]),
                description=str(finding["description"]),
                source_evidence=list(finding.get("source_evidence", [])),
                expected_benefit=str(finding.get("expected_benefit", "")),
                candidate_type=finding.get("candidate_type", "memory"),
            )
            promotions.append(self.promote_candidate(candidate))
            improvement_titles.append(candidate.title)

        artifact_path = result.artifacts[0] if result.artifacts else None
        self.adapter.update_task(
            task.id,
            TaskUpdate(
                artifacts=[artifact_path] if artifact_path else [],
                improvement_candidates=improvement_titles,
                append_phase_log=result.summary,
                metadata_patch={"improvement_result": asdict(result)},
            ),
        )
        self._record_phase("IMPROVE", result.status, result.summary, artifacts=[artifact_path] if artifact_path else [])
        self._persist_state()
        return {
            "status": result.status,
            "artifact_path": artifact_path,
            "summary": result.summary,
            "promotions": promotions,
        }

    def prepare_pr(self, task: Task) -> PullRequestResult:
        body_artifact = self._write_pr_body(task)
        title = self._default_pr_title(task)
        body = Path(body_artifact).read_text()
        try:
            result = self.adapter.create_or_update_pr(title=title, body=body, base=self.config.pr_base)
        except TaskAdapterError as exc:
            detail = f"PR integration unavailable: {exc}"
            self._record_phase("PR", "needs_human", detail, artifacts=[body_artifact])
            self._persist_state()
            return PullRequestResult(
                status="human_required",
                title=title,
                body_artifact_path=body_artifact,
                detail=detail,
            )

        status = result.get("status", "created")
        detail = f"PR {status}: {result.get('url') or 'no url'}"
        self._record_phase("PR", "success", detail, artifacts=[body_artifact])
        self._persist_state()
        return PullRequestResult(
            status=status,
            url=result.get("url"),
            title=result.get("title", title),
            body_artifact_path=body_artifact,
            detail=detail,
        )

    def get_selected_task(self) -> Task | None:
        if self.run_state.selected_task_id is None:
            return None
        return self.adapter.get_task(self.run_state.selected_task_id)

    def remember_lesson(self, *, title: str, rule: str) -> dict | None:
        if self.memory_client is None:
            self.run_state.memory_status = "unavailable"
            self._record_phase("IMPROVE", "needs_human", "Memory client not configured")
            self._persist_state()
            return None
        try:
            lesson = self.memory_client.create_lesson(
                title=title,
                rule=rule,
                project=str(self.repo_root),
            )
        except AgentMemoryError as exc:
            self.run_state.memory_status = "degraded"
            self._record_phase("IMPROVE", "needs_human", f"Memory write failed: {exc}")
            self._persist_state()
            return None
        self.run_state.memory_status = "ok"
        self._record_phase("IMPROVE", "success", f"Stored lesson: {title}")
        self._persist_state()
        return lesson

    def _record_phase(self, phase: str, status: str, summary: str, artifacts: list[str] | None = None) -> None:
        self.run_state.current_phase = phase
        self.run_state.phase_history.append(
            PhaseRecord(phase=phase, status=status, summary=summary, artifacts=artifacts or [])
        )

    def _persist_state(self) -> None:
        payload = self.run_state.to_dict()
        self.run_state_path.write_text(json.dumps(payload, indent=2) + "\n")

    def _write_artifact(self, filename: str, content: str) -> str:
        artifact_path = self.artifacts_root / filename
        artifact_path.write_text(content)
        return str(artifact_path)

    def _write_pr_body(self, task: Task) -> str:
        verification = task.metadata.get("verification_results", [])
        review_summary = task.metadata.get("review_summary", "No review summary recorded")
        body = (
            "## Summary\n"
            f"- {task.title}\n\n"
            "## Task\n"
            f"- Source: {task.source}\n"
            f"- Task ID: {task.id}\n\n"
            "## Verification\n"
            + "\n".join(
                f"- {item.get('category')}: {item.get('status')} ({item.get('command')})"
                for item in verification
            )
            + ("\n" if verification else "- No verification results recorded\n")
            + "\n## Review\n"
            f"- {review_summary}\n"
        )
        return self._write_artifact("pull-request-body.md", body)

    def _default_pr_title(self, task: Task) -> str:
        return f"feat: {task.title}"

    def _restore_or_create_state(self, mode: str) -> RunState:
        if self.run_state_path.exists():
            try:
                payload = json.loads(self.run_state_path.read_text())
                return RunState.from_dict(payload)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
        return RunState(
            session_id=str(uuid.uuid4()),
            repo_root=str(self.repo_root),
            mode=mode,
        )

    def _load_memory_context(self) -> str:
        if self.memory_client is None:
            self.run_state.memory_status = "unavailable"
            self.run_state.memory_lessons_loaded = 0
            return "memory unavailable"

        try:
            lessons = self.memory_client.list_lessons(project=str(self.repo_root), limit=25)
        except AgentMemoryError as exc:
            self.run_state.memory_status = "degraded"
            self.run_state.memory_lessons_loaded = 0
            return f"memory degraded ({exc})"

        self.run_state.memory_status = "ok"
        self.run_state.memory_lessons_loaded = len(lessons)
        return f"loaded {len(lessons)} scoped lessons"

    def _git_changed_files(self) -> list[str]:
        try:
            completed = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.repo_root,
                check=True,
                text=True,
                capture_output=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return []

        changed_files: list[str] = []
        for raw_line in completed.stdout.splitlines():
            line = raw_line.rstrip()
            if len(line) < 4:
                continue
            changed_files.append(line[3:])
        return changed_files

    def _execute_specialist(self, task: Task, name: str, *, stage: str | None = None) -> AgentResult:
        current_task = self.adapter.get_task(task.id)
        return execute_specialist(
            name,
            repo_root=self.repo_root,
            artifacts_root=self.artifacts_root,
            task=current_task,
            run_state=self.run_state,
            config=self.config,
            stage=stage,
        )
