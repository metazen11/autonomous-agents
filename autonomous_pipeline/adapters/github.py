from __future__ import annotations

import json
import subprocess
from pathlib import Path

from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.schemas import PromotionCandidate, Task, TaskUpdate


class GitHubAdapter(TaskAdapter):
    """Task adapter backed by GitHub Issues via the gh CLI."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        repo: str | None = None,
        label: str | None = None,
        skip_labels: list[str] | None = None,
        gh_command: list[str] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repo = repo
        self.label = label
        self.skip_labels = skip_labels or ["blocked", "human-only"]
        self.gh_command = gh_command or ["gh"]

    def list_ready_tasks(self) -> list[Task]:
        args = [
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,title,body,labels,url",
        ]
        if self.label:
            args.extend(["--label", self.label])
        issues = self._gh_json(args)
        tasks = []
        for issue in issues:
            label_names = [label["name"] for label in issue.get("labels", [])]
            if any(label in self.skip_labels for label in label_names):
                continue
            tasks.append(self._normalize_issue(issue))
        return tasks

    def get_task(self, task_id: str) -> Task:
        issue = self._gh_json(
            [
                "issue",
                "view",
                task_id,
                "--json",
                "number,title,body,labels,url",
            ]
        )
        return self._normalize_issue(issue)

    def claim_task(self, task_id: str, worker_id: str) -> None:
        self._gh(
            [
                "issue",
                "comment",
                task_id,
                "--body",
                f"Autonomous pipeline claimed this task with worker `{worker_id}`.",
            ]
        )

    def update_task(self, task_id: str, update: TaskUpdate) -> Task:
        comments: list[str] = []
        if update.status is not None:
            comments.append(f"Status: `{update.status}`")
        if update.blockers:
            comments.append("Blockers:\n" + "\n".join(f"- {item}" for item in update.blockers))
        if update.artifacts:
            comments.append("Artifacts:\n" + "\n".join(f"- {item}" for item in update.artifacts))
        if update.improvement_candidates:
            comments.append(
                "Improvement candidates:\n" + "\n".join(f"- {item}" for item in update.improvement_candidates)
            )
        if update.append_phase_log:
            comments.append(update.append_phase_log)

        if comments:
            self._gh(
                [
                    "issue",
                    "comment",
                    task_id,
                    "--body",
                    "\n\n".join(comments),
                ]
            )

        return self.get_task(task_id)

    def create_follow_up(self, item: PromotionCandidate) -> str | None:
        body_parts = [item.description]
        if item.expected_benefit:
            body_parts.append(f"Expected benefit: {item.expected_benefit}")
        if item.source_evidence:
            body_parts.append("Source evidence:\n" + "\n".join(f"- {entry}" for entry in item.source_evidence))

        issue = self._gh_json(
            [
                "issue",
                "create",
                "--title",
                item.title,
                "--body",
                "\n\n".join(body_parts),
                "--label",
                "autonomous:follow-up",
                "--json",
                "number,url",
            ]
        )
        return str(issue["number"])

    def create_or_update_pr(self, *, title: str, body: str, base: str) -> dict | None:
        existing = self._find_existing_pr()
        if existing is not None:
            number = str(existing["number"])
            self._gh(["pr", "edit", number, "--title", title, "--body", body, "--base", base])
            view = self._gh_json(["pr", "view", number, "--json", "number,url,title"])
            return {"status": "updated", "url": view.get("url"), "number": view.get("number"), "title": view.get("title")}

        created = self._gh_json(["pr", "create", "--base", base, "--title", title, "--body", body, "--json", "number,url,title"])
        return {"status": "created", "url": created.get("url"), "number": created.get("number"), "title": created.get("title")}

    def _normalize_issue(self, issue: dict) -> Task:
        labels = [label["name"] for label in issue.get("labels", [])]
        priority = _derive_priority(labels)
        acceptance_criteria = _extract_checklist(issue.get("body", ""))
        return Task(
            id=str(issue["number"]),
            title=issue["title"],
            body=issue.get("body", ""),
            status="ready",
            priority=priority,
            labels=labels,
            acceptance_criteria=acceptance_criteria,
            source="github",
            source_url=issue.get("url"),
            metadata={"issue_number": issue["number"]},
        )

    def _gh_json(self, args: list[str]) -> dict | list:
        result = self._gh(args)
        try:
            return json.loads(result)
        except json.JSONDecodeError as exc:
            raise TaskAdapterError(f"Invalid JSON from gh: {exc}") from exc

    def _gh(self, args: list[str]) -> str:
        command = [*self.gh_command, *args]
        if self.repo:
            command.extend(["--repo", self.repo])
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                check=True,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise TaskAdapterError("gh CLI not found") from exc
        except subprocess.CalledProcessError as exc:
            raise TaskAdapterError(exc.stderr.strip() or exc.stdout.strip()) from exc
        return completed.stdout

    def _find_existing_pr(self) -> dict | None:
        prs = self._gh_json(["pr", "list", "--state", "open", "--head", "HEAD", "--json", "number,url,title"])
        if isinstance(prs, list) and prs:
            return prs[0]
        return None


def _derive_priority(labels: list[str]) -> str:
    if "priority:urgent" in labels:
        return "urgent"
    if "priority:high" in labels:
        return "high"
    if "priority:low" in labels:
        return "low"
    return "medium"


def _extract_checklist(body: str) -> list[str]:
    lines = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("- [ ] "):
            lines.append(line[6:])
    return lines
