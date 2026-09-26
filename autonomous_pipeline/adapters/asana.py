from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from autonomous_pipeline.adapters._checklist import extract_checklist
from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.schemas import PromotionCandidate, Task, TaskUpdate

_API_BASE = "https://app.asana.com/api/1.0"

HttpTransport = Callable[[str, str, dict, "bytes | None"], dict]


class AsanaAdapter(TaskAdapter):
    """Task adapter backed by Asana via its REST API (PAT auth)."""

    def __init__(
        self,
        *,
        project_gid: str,
        token: str | None = None,
        workspace_gid: str | None = None,
        default_section_gid: str | None = None,
        http: HttpTransport | None = None,
    ) -> None:
        self.project_gid = project_gid
        self.token = token or os.environ.get("ASANA_ACCESS_TOKEN")
        self.workspace_gid = workspace_gid
        self.default_section_gid = default_section_gid
        self._http = http or _urllib_transport

    # ---- read path -------------------------------------------------------

    def list_ready_tasks(self) -> list[Task]:
        payload = self._request(
            "GET",
            f"/projects/{self.project_gid}/tasks",
            params={"opt_fields": "name,notes,completed"},
        )
        tasks = [self._normalize(item) for item in payload.get("data", [])]
        return [task for task in tasks if task.status == "ready"]

    def get_task(self, task_id: str) -> Task:
        payload = self._request(
            "GET",
            f"/tasks/{task_id}",
            params={"opt_fields": "name,notes,completed"},
        )
        return self._normalize(payload["data"])

    # ---- write path (implemented in Task 4) ------------------------------

    def claim_task(self, task_id: str, worker_id: str) -> None:
        self._request(
            "POST",
            f"/tasks/{task_id}/stories",
            body={"text": f"Autonomous pipeline claimed this task with worker `{worker_id}`."},
        )

    def update_task(self, task_id: str, update: TaskUpdate) -> Task:
        comments: list[str] = []
        if update.status is not None:
            comments.append(f"Status: `{update.status}`")
        if update.blockers:
            comments.append("Blockers:\n" + "\n".join(f"- {item}" for item in update.blockers))
        if update.artifacts:
            comments.append("Artifacts:\n" + "\n".join(f"- {item}" for item in update.artifacts))
        if update.append_phase_log:
            comments.append(update.append_phase_log)
        if comments:
            self._request("POST", f"/tasks/{task_id}/stories", body={"text": "\n\n".join(comments)})
        if update.status == "done":
            self._request("PUT", f"/tasks/{task_id}", body={"completed": True})
        return self.get_task(task_id)

    def create_follow_up(self, item: PromotionCandidate) -> str | None:
        body_parts = [item.description]
        if item.expected_benefit:
            body_parts.append(f"Expected benefit: {item.expected_benefit}")
        gid, _ = self.create_item(title=item.title, body="\n\n".join(body_parts), criteria=[], labels=[])
        return gid

    def create_item(
        self,
        *,
        title: str,
        body: str,
        criteria: list[str],
        labels: list[str],
    ) -> tuple[str, str]:
        notes = body
        if criteria:
            notes = notes + "\n\n" + "\n".join(f"- [ ] {c}" for c in criteria)
        if labels:
            notes = notes + "\n\nLanes: " + ", ".join(labels)
        data: dict[str, Any] = {"name": title, "notes": notes, "projects": [self.project_gid]}
        if self.default_section_gid:
            data["memberships"] = [{"project": self.project_gid, "section": self.default_section_gid}]
        payload = self._request("POST", "/tasks", body=data)
        gid = str(payload["data"]["gid"])
        return gid, f"https://app.asana.com/0/{self.project_gid}/{gid}"

    # ---- helpers ---------------------------------------------------------

    def _normalize(self, item: dict[str, Any]) -> Task:
        gid = str(item["gid"])
        notes = item.get("notes", "") or ""
        return Task(
            id=gid,
            title=item.get("name", ""),
            body=notes,
            status="done" if item.get("completed") else "ready",
            acceptance_criteria=extract_checklist(notes),
            source="asana",
            source_url=f"https://app.asana.com/0/{self.project_gid}/{gid}",
            metadata={"tracker_ref": gid},
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.token:
            raise TaskAdapterError("ASANA_ACCESS_TOKEN not set")
        url = _API_BASE + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        raw_body = json.dumps({"data": body}).encode() if body is not None else None
        return self._http(method, url, headers, raw_body)


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode(errors="replace")
        raise TaskAdapterError(f"Asana API {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise TaskAdapterError(f"Asana API unreachable: {exc.reason}") from None
