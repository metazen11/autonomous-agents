# Capture Buffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the operator barrages a session mid-task, every real request is auto-filed as a well-formed item in the project's canonical tracker (todo.json / GitHub / Asana) and mirrored as a `ready` task in the local task file, so nothing is dropped and the pipeline can drain it.

**Architecture:** Extend the existing `autonomous_pipeline` adapter pattern. Add an Asana `TaskAdapter` (REST via PAT, mirroring how `github.py` shells to `gh`), a single `build_adapter()` factory that resolves the per-project canonical tracker from `.autonomous.json`, a `tasker` specialist agent that authors tracker items + mirrors them into the local task file, and a `/capture` skill that invokes the tasker. Done is signaled only when `aa_auditor` verifies acceptance criteria and closes the tracker item.

**Tech Stack:** Python 3 (stdlib only — `urllib`, `json`, `subprocess`, `unittest`), Markdown agent/skill contracts, `sync_prompt_pack.py` for distribution.

## Global Constraints

- Adapters implement the `TaskAdapter` ABC in `autonomous_pipeline/adapters/base.py`: `list_ready_tasks`, `get_task`, `claim_task`, `update_task`, `create_follow_up` (and optional `create_or_update_pr`). Copy this interface verbatim.
- `Task`/`TaskUpdate`/`PromotionCandidate` come from `autonomous_pipeline/schemas.py`. Do NOT redefine them. `utc_now_iso()` is the only timestamp source.
- `TaskStatus = Literal["ready","in_progress","blocked","done","failed","needs_human"]`; `TaskPriority = Literal["low","medium","high","urgent"]`. Use these exact values.
- Python is **stdlib only** — no `requests`, no third-party HTTP. Use `urllib.request`.
- Secrets never appear in code, tests, transcript, or committed files. The Asana PAT is read from env var `ASANA_ACCESS_TOKEN` only.
- Commits omit any Claude/AI attribution and `Co-Authored-By` lines.
- Tests run with `python3 -m unittest <module> -v` from repo root `/Users/mz/_CODING/autonomous_agents_mds`.
- `source` values are exactly `"todo_json"`, `"github"`, `"asana"`. Tracker refs live in `metadata["tracker_ref"]`.

---

## File Structure

- `autonomous_pipeline/adapters/asana.py` — **new.** `AsanaAdapter(TaskAdapter)`, REST via PAT.
- `tests/test_asana_adapter.py` — **new.** Unit tests with a fake HTTP transport (no network).
- `autonomous_pipeline/adapters/factory.py` — **new.** `build_adapter(config, repo_root)` → the right `TaskAdapter`.
- `tests/test_adapter_factory.py` — **new.** Factory resolution tests.
- `autonomous_pipeline/schemas.py` — **modify.** Add `"asana"` to `RuntimeConfig.task_source` Literal + Asana config fields.
- `autonomous_pipeline/config.py` — **modify.** Load the new Asana fields from `.autonomous.json`.
- `tests/test_config.py` — **new/modify.** Assert Asana config loads.
- `agents/tasker.md` — **new.** The tasker specialist contract.
- `skills/capture/skill.md` — **new.** The `/capture` skill.
- `agents/aa_auditor.md` OR its existing contract — **verify only** (agent already exists as `aa_auditor` type); no code change, referenced by the tasker/done convention.

---

## Task 1: Add Asana fields to RuntimeConfig

**Files:**
- Modify: `autonomous_pipeline/schemas.py` (the `RuntimeConfig` dataclass, ~line 178)
- Test: `tests/test_schemas_asana_config.py` (create)

**Interfaces:**
- Produces: `RuntimeConfig.task_source` now accepts `"asana"`; new fields `asana_project_gid: str | None`, `asana_workspace_gid: str | None`, `asana_default_section_gid: str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schemas_asana_config.py`:
```python
from __future__ import annotations

import unittest

from autonomous_pipeline.schemas import RuntimeConfig


class RuntimeConfigAsanaTest(unittest.TestCase):
    def test_asana_fields_default_to_none(self) -> None:
        config = RuntimeConfig()
        self.assertIsNone(config.asana_project_gid)
        self.assertIsNone(config.asana_workspace_gid)
        self.assertIsNone(config.asana_default_section_gid)

    def test_asana_task_source_roundtrips(self) -> None:
        config = RuntimeConfig(task_source="asana", asana_project_gid="123")
        data = config.to_dict()
        self.assertEqual(data["task_source"], "asana")
        self.assertEqual(data["asana_project_gid"], "123")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_schemas_asana_config -v`
Expected: FAIL — `TypeError: RuntimeConfig() got an unexpected keyword argument 'asana_project_gid'` (or AttributeError on the default test).

- [ ] **Step 3: Write minimal implementation**

In `autonomous_pipeline/schemas.py`, change the `task_source` type and add fields. Find:
```python
class RuntimeConfig:
    task_source: Literal["todo_json", "github", "file", "prompt"] = "todo_json"
    todo_path: str = "todo.json"
```
Replace with:
```python
class RuntimeConfig:
    task_source: Literal["todo_json", "github", "asana", "file", "prompt"] = "todo_json"
    todo_path: str = "todo.json"
    asana_project_gid: str | None = None
    asana_workspace_gid: str | None = None
    asana_default_section_gid: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_schemas_asana_config -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the existing suite to confirm no regression**

Run: `python3 -m unittest discover -s tests -v`
Expected: all existing tests still PASS (asdict roundtrip unaffected because new fields have defaults).

- [ ] **Step 6: Commit**

```bash
git add autonomous_pipeline/schemas.py tests/test_schemas_asana_config.py
git commit -m "feat(schemas): add asana task_source and project/workspace/section config fields"
```

---

## Task 2: Load Asana config from .autonomous.json

**Files:**
- Modify: `autonomous_pipeline/config.py` (`load_runtime_config`, ~line 16)
- Test: `tests/test_config_asana.py` (create)

**Interfaces:**
- Consumes: `RuntimeConfig` Asana fields from Task 1.
- Produces: `load_runtime_config(repo_root)` populates `asana_project_gid`, `asana_workspace_gid`, `asana_default_section_gid` from `.autonomous.json`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_asana.py`:
```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.config import load_runtime_config


class LoadAsanaConfigTest(unittest.TestCase):
    def test_loads_asana_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".autonomous.json").write_text(
                json.dumps(
                    {
                        "task_source": "asana",
                        "asana_project_gid": "1215642525150297",
                        "asana_workspace_gid": "9999",
                        "asana_default_section_gid": "8888",
                    }
                )
            )
            config = load_runtime_config(root)
            self.assertEqual(config.task_source, "asana")
            self.assertEqual(config.asana_project_gid, "1215642525150297")
            self.assertEqual(config.asana_workspace_gid, "9999")
            self.assertEqual(config.asana_default_section_gid, "8888")

    def test_absent_config_defaults_to_todo_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_runtime_config(Path(tmp))
            self.assertEqual(config.task_source, "todo_json")
            self.assertIsNone(config.asana_project_gid)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_config_asana -v`
Expected: FAIL — `test_loads_asana_fields` asserts `asana_project_gid == "1215642525150297"` but gets `None` (loader ignores the keys).

- [ ] **Step 3: Write minimal implementation**

In `autonomous_pipeline/config.py`, inside `load_runtime_config`, in the `return RuntimeConfig(...)` call, add these three lines after `todo_path=payload.get("todo_path", "todo.json"),`:
```python
        asana_project_gid=payload.get("asana_project_gid"),
        asana_workspace_gid=payload.get("asana_workspace_gid"),
        asana_default_section_gid=payload.get("asana_default_section_gid"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_config_asana -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add autonomous_pipeline/config.py tests/test_config_asana.py
git commit -m "feat(config): load asana project/workspace/section gids from .autonomous.json"
```

---

## Task 3: AsanaAdapter — list/get/normalize (read path)

**Files:**
- Create: `autonomous_pipeline/adapters/asana.py`
- Test: `tests/test_asana_adapter.py`

**Interfaces:**
- Consumes: `TaskAdapter`, `TaskAdapterError` from `adapters/base.py`; `Task`, `TaskUpdate`, `PromotionCandidate`, `utc_now_iso` from `schemas.py`.
- Produces: `AsanaAdapter(*, project_gid, token=None, workspace_gid=None, default_section_gid=None, http=None)`. The `http` param is an injectable callable `http(method, url, headers, body) -> dict` for testing; defaults to a real `urllib` transport. Methods: `list_ready_tasks() -> list[Task]`, `get_task(task_id) -> Task`, plus private `_normalize(task_dict) -> Task`, `_request(method, path, params=None, body=None) -> dict`.
- Normalization mapping: Asana `gid` → `Task.id`; `name` → `title`; `notes` → `body`; `completed=False` → `status="ready"`, `completed=True` → `status="done"`; `Task.source="asana"`; `Task.source_url=f"https://app.asana.com/0/{project_gid}/{gid}"`; `metadata={"tracker_ref": gid}`. Priority + acceptance criteria parsed from `notes` (checklist lines `- [ ] ...`) mirroring `github.py`'s `_extract_checklist`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_asana_adapter.py`:
```python
from __future__ import annotations

import unittest

from autonomous_pipeline.adapters.asana import AsanaAdapter


class FakeHttp:
    """Records requests, returns queued responses."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None) -> dict:
        self.calls.append((method, url, headers))
        return self.responses.pop(0)


class AsanaAdapterReadTest(unittest.TestCase):
    def test_list_ready_tasks_normalizes_incomplete(self) -> None:
        http = FakeHttp(
            [
                {
                    "data": [
                        {"gid": "111", "name": "Fix centroid", "notes": "do it", "completed": False},
                        {"gid": "222", "name": "Done thing", "notes": "", "completed": True},
                    ]
                }
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        tasks = adapter.list_ready_tasks()
        self.assertEqual([t.id for t in tasks], ["111"])
        task = tasks[0]
        self.assertEqual(task.title, "Fix centroid")
        self.assertEqual(task.source, "asana")
        self.assertEqual(task.metadata["tracker_ref"], "111")
        self.assertIn("111", task.source_url)

    def test_list_ready_tasks_sends_bearer_token(self) -> None:
        http = FakeHttp([{"data": []}])
        adapter = AsanaAdapter(project_gid="proj1", token="secret-token", http=http)
        adapter.list_ready_tasks()
        _, url, headers = http.calls[0]
        self.assertIn("proj1", url)
        self.assertEqual(headers["Authorization"], "Bearer secret-token")

    def test_get_task_extracts_acceptance_criteria(self) -> None:
        http = FakeHttp(
            [
                {
                    "data": {
                        "gid": "333",
                        "name": "Task with criteria",
                        "notes": "Intro\n- [ ] first crit\n- [ ] second crit",
                        "completed": False,
                    }
                }
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        task = adapter.get_task("333")
        self.assertEqual(task.acceptance_criteria, ["first crit", "second crit"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_asana_adapter -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autonomous_pipeline.adapters.asana'`.

- [ ] **Step 3: Write minimal implementation**

Create `autonomous_pipeline/adapters/asana.py`:
```python
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

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
        raise NotImplementedError

    def update_task(self, task_id: str, update: TaskUpdate) -> Task:
        raise NotImplementedError

    def create_follow_up(self, item: PromotionCandidate) -> str | None:
        raise NotImplementedError

    # ---- helpers ---------------------------------------------------------

    def _normalize(self, item: dict[str, Any]) -> Task:
        gid = str(item["gid"])
        notes = item.get("notes", "") or ""
        return Task(
            id=gid,
            title=item.get("name", ""),
            body=notes,
            status="done" if item.get("completed") else "ready",
            acceptance_criteria=_extract_checklist(notes),
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


def _extract_checklist(body: str) -> list[str]:
    lines = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("- [ ] "):
            lines.append(line[6:])
    return lines


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode(errors="replace")
        raise TaskAdapterError(f"Asana API {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise TaskAdapterError(f"Asana API unreachable: {exc.reason}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_asana_adapter -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add autonomous_pipeline/adapters/asana.py tests/test_asana_adapter.py
git commit -m "feat(adapters): AsanaAdapter read path (list/get/normalize) via REST PAT"
```

---

## Task 4: AsanaAdapter — write path (claim/update/create_follow_up)

**Files:**
- Modify: `autonomous_pipeline/adapters/asana.py`
- Test: `tests/test_asana_adapter.py` (add cases)

**Interfaces:**
- Consumes: `_request`, `_normalize` from Task 3; `TaskUpdate`, `PromotionCandidate` from schemas.
- Produces: `claim_task(task_id, worker_id)` posts a story (comment); `update_task(task_id, update)` posts a story and, when `update.status == "done"`, PUTs `completed=true`, returns the re-fetched `Task`; `create_follow_up(item)` POSTs a new task to the project and returns its gid string. A convenience `create_item(title, body, criteria, labels) -> tuple[str, str]` returning `(gid, url)` used by the tasker path.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_asana_adapter.py`:
```python
class AsanaAdapterWriteTest(unittest.TestCase):
    def test_update_task_marks_completed_when_done(self) -> None:
        http = FakeHttp(
            [
                {"data": {"gid": "444"}},  # story comment POST
                {"data": {"gid": "444"}},  # completed PUT
                {"data": {"gid": "444", "name": "T", "notes": "", "completed": True}},  # re-fetch
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        task = adapter.update_task("444", TaskUpdate(status="done", append_phase_log="audited PASS"))
        self.assertEqual(task.status, "done")
        methods = [call[0] for call in http.calls]
        self.assertIn("PUT", methods)

    def test_create_item_returns_gid_and_url(self) -> None:
        http = FakeHttp([{"data": {"gid": "555"}}])
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        gid, url = adapter.create_item(
            title="New captured task",
            body="intent",
            criteria=["crit one", "crit two"],
            labels=["lane:etl"],
        )
        self.assertEqual(gid, "555")
        self.assertIn("555", url)
        # last call is the create POST to /tasks
        method, called_url, _ = http.calls[-1]
        self.assertEqual(method, "POST")
        self.assertTrue(called_url.endswith("/tasks"))
```

Add this import at the top of the test file if not present: `from autonomous_pipeline.schemas import TaskUpdate` (add alongside existing imports).

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_asana_adapter -v`
Expected: FAIL — `update_task` raises `NotImplementedError`; `create_item` `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

In `autonomous_pipeline/adapters/asana.py`, replace the three `raise NotImplementedError` stub methods with:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_asana_adapter -v`
Expected: PASS (5 tests total).

- [ ] **Step 5: Commit**

```bash
git add autonomous_pipeline/adapters/asana.py tests/test_asana_adapter.py
git commit -m "feat(adapters): AsanaAdapter write path (claim/update/create) + create_item helper"
```

---

## Task 5: build_adapter() factory

**Files:**
- Create: `autonomous_pipeline/adapters/factory.py`
- Test: `tests/test_adapter_factory.py`

**Interfaces:**
- Consumes: `RuntimeConfig` (Task 1/2); `TodoJsonAdapter`, `GitHubAdapter`, `AsanaAdapter`, `FileTaskAdapter`.
- Produces: `build_adapter(config: RuntimeConfig, repo_root: str | Path) -> TaskAdapter`. Resolution: `task_source=="todo_json"` → `TodoJsonAdapter(repo_root/config.todo_path)`; `"github"` → `GitHubAdapter(repo_root=..., repo=config.github_repo, label=config.github_label, skip_labels=config.github_skip_labels, gh_command=config.github_command)`; `"asana"` → `AsanaAdapter(project_gid=config.asana_project_gid, workspace_gid=config.asana_workspace_gid, default_section_gid=config.asana_default_section_gid)`; `"file"`/`"prompt"` → `FileTaskAdapter(...)`. Raises `TaskAdapterError` if `asana` selected with no `asana_project_gid`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_adapter_factory.py`:
```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.asana import AsanaAdapter
from autonomous_pipeline.adapters.base import TaskAdapterError
from autonomous_pipeline.adapters.factory import build_adapter
from autonomous_pipeline.adapters.github import GitHubAdapter
from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.schemas import RuntimeConfig


class BuildAdapterTest(unittest.TestCase):
    def test_todo_json_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = build_adapter(RuntimeConfig(), Path(tmp))
            self.assertIsInstance(adapter, TodoJsonAdapter)

    def test_github(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = RuntimeConfig(task_source="github", github_repo="owner/name")
            adapter = build_adapter(config, Path(tmp))
            self.assertIsInstance(adapter, GitHubAdapter)
            self.assertEqual(adapter.repo, "owner/name")

    def test_asana(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = RuntimeConfig(task_source="asana", asana_project_gid="123")
            adapter = build_adapter(config, Path(tmp))
            self.assertIsInstance(adapter, AsanaAdapter)
            self.assertEqual(adapter.project_gid, "123")

    def test_asana_without_project_gid_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = RuntimeConfig(task_source="asana")
            with self.assertRaises(TaskAdapterError):
                build_adapter(config, Path(tmp))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_adapter_factory -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autonomous_pipeline.adapters.factory'`.

- [ ] **Step 3: Write minimal implementation**

Create `autonomous_pipeline/adapters/factory.py`:
```python
from __future__ import annotations

from pathlib import Path

from autonomous_pipeline.adapters.asana import AsanaAdapter
from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.adapters.file_task import FileTaskAdapter
from autonomous_pipeline.adapters.github import GitHubAdapter
from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.schemas import RuntimeConfig


def build_adapter(config: RuntimeConfig, repo_root: str | Path) -> TaskAdapter:
    root = Path(repo_root)
    source = config.task_source
    if source == "todo_json":
        return TodoJsonAdapter(root / config.todo_path)
    if source == "github":
        return GitHubAdapter(
            repo_root=root,
            repo=config.github_repo,
            label=config.github_label,
            skip_labels=config.github_skip_labels,
            gh_command=config.github_command,
        )
    if source == "asana":
        if not config.asana_project_gid:
            raise TaskAdapterError("task_source 'asana' requires asana_project_gid in .autonomous.json")
        return AsanaAdapter(
            project_gid=config.asana_project_gid,
            workspace_gid=config.asana_workspace_gid,
            default_section_gid=config.asana_default_section_gid,
        )
    if source in ("file", "prompt"):
        return FileTaskAdapter(
            repo_root=root,
            task_file=config.task_file,
            prompt_text=config.prompt_text,
        )
    raise TaskAdapterError(f"Unknown task_source: {source}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_adapter_factory -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add autonomous_pipeline/adapters/factory.py tests/test_adapter_factory.py
git commit -m "feat(adapters): build_adapter() factory resolving todo_json/github/asana/file"
```

---

## Task 6: tasker specialist agent contract

**Files:**
- Create: `agents/tasker.md`
- Test: `tests/test_tasker_contract.py` (structural assertions on the contract file)

**Interfaces:**
- Consumes: nothing at runtime (Markdown contract). Referenced by the `/capture` skill (Task 7).
- Produces: an agent contract with a documented Inputs section (`request`, `project`, `priority?`, `lane?`), a Procedure that resolves the tracker via `build_adapter`, authors a well-formed item with auditor-verifiable acceptance criteria, creates it through the adapter, mirrors a `ready` task into the local task file with `source`/`source_url`/`metadata.tracker_ref`, and a Return shape `{filed, tracker, ref, title, url}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tasker_contract.py`:
```python
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "agents" / "tasker.md"


class TaskerContractTest(unittest.TestCase):
    def test_contract_exists_with_required_sections(self) -> None:
        self.assertTrue(CONTRACT.exists(), "agents/tasker.md must exist")
        text = CONTRACT.read_text()
        for needle in [
            "name: tasker",
            "AGENT_AGNOSTIC_GUIDE.md",
            "## Inputs",
            "## Procedure",
            "build_adapter",
            "acceptance_criteria",
            "aa_auditor",
            "tracker_ref",
            "filed",
        ]:
            self.assertIn(needle, text, f"tasker.md missing: {needle}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tasker_contract -v`
Expected: FAIL — `agents/tasker.md must exist`.

- [ ] **Step 3: Write the contract**

Create `agents/tasker.md`:
```markdown
---
name: tasker
description: "Agent-agnostic capture specialist. Turns a raw operator request into a well-formed item in the project's canonical tracker (todo.json / GitHub / Asana) with auditor-verifiable acceptance criteria, and mirrors it as a ready task in the local task file. The front-door quality gate of the capture buffer."
---

# Tasker

Read [AGENT_AGNOSTIC_GUIDE.md](./AGENT_AGNOSTIC_GUIDE.md) before starting.

## Role

You are the capture specialist. When the operator fires a request mid-session,
you convert it — without the operator stopping to hand-write a ticket — into a
durable, well-formed tracker item plus a local mirror task the pipeline can drain.
You are the front-door quality gate: garbage-in (a hurried one-liner) becomes a
well-formed-item-out.

You do NOT implement the work. You do NOT push code. You author and file.

## Inputs

- `request` — the raw operator request text.
- `project` — target project root. Defaults to the session's current project;
  overridden when the request names another (e.g. `for etrade: ...`).
- `priority` — optional; infer `urgent|high|medium|low` from urgency language if omitted.
- `lane` — optional; infer the lane/label from content if omitted.

## Procedure

1. **Classify.** Is this work (code change / investigation) or a pure question?
   A pure question → return `{"filed": false, "reason": "question — answer inline"}`
   and file nothing.
2. **Resolve the canonical tracker.** Read the project's `.autonomous.json` and
   build the adapter with `autonomous_pipeline.adapters.factory.build_adapter`.
   The declared `task_source` (`todo_json` default, else `github`/`asana`) picks
   the backend. `todo.json` is always the local mirror regardless.
3. **Author the item.** Write a scoped title and a body containing intent,
   constraints, and **acceptance criteria that are testable and auditor-verifiable
   against a live end state** (these are the exact checklist `aa_auditor` verifies
   before the item may be closed). Add testing requirements when the work warrants
   them. Choose a priority and lane label.
4. **Create the item through the adapter.** For `github` use the adapter's issue
   creation; for `asana` use `AsanaAdapter.create_item(...)`; for `todo_json` the
   local task itself is the canonical item (no external create). Capture the
   tracker `ref` (issue number / Asana gid) and `url`.
5. **Mirror into the local task file** (`todo.json`, or `tasks.json` where that is
   the project's existing name) as a `ready` task in the `Task` schema shape:
   `{id, title, body, status:"ready", priority, labels:[lane], acceptance_criteria,
   source:"github|asana|todo_json", source_url, metadata:{captured_at, captured_by:"capture-buffer", tracker_ref}}`.
6. **Return** `{"filed": true, "tracker": "...", "ref": "...", "title": "...", "url": "..."}`.

## Definition of Done linkage

The acceptance criteria you author are the contract the `aa_auditor` checks at the
back door. Done is only reached when `aa_auditor` verifies every criterion against
the live end state with evidence and closes the tracker item. You never mark work
done — you set it up so done is verifiable.

## Allowed Actions

- Read project files and `.autonomous.json`.
- Create/list items through the resolved `TaskAdapter` (GitHub `gh`, Asana REST,
  or local task file).
- Read/write the project's local task file.
- No code edits. No pushes.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tasker_contract -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/tasker.md tests/test_tasker_contract.py
git commit -m "feat(agents): tasker capture specialist contract"
```

---

## Task 7: /capture skill

**Files:**
- Create: `skills/capture/skill.md`
- Test: `tests/test_capture_skill_contract.py`

**Interfaces:**
- Consumes: the `tasker` agent (Task 6).
- Produces: a user-invocable skill contract documenting `/capture <text>`, `/capture for <project>: <text>`, and the auto-capture default; host-agnostic invocation like `/reconcile`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_capture_skill_contract.py`:
```python
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "capture" / "skill.md"


class CaptureSkillContractTest(unittest.TestCase):
    def test_skill_exists_with_required_sections(self) -> None:
        self.assertTrue(SKILL.exists(), "skills/capture/skill.md must exist")
        text = SKILL.read_text()
        for needle in [
            "name: capture",
            "user-invocable: true",
            "/capture",
            "for <project>",
            "auto-capture",
            "tasker",
        ]:
            self.assertIn(needle, text, f"skill.md missing: {needle}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_capture_skill_contract -v`
Expected: FAIL — `skills/capture/skill.md must exist`.

- [ ] **Step 3: Write the skill**

Create `skills/capture/skill.md`:
```markdown
---
name: capture
description: "Capture an operator request as a well-formed item in the project's canonical tracker (todo.json / GitHub / Asana) and mirror it as a ready task locally, so nothing is dropped during a barrage. Invokes the tasker specialist."
argument-hint: "[for <project>:] <request text>"
user-invocable: true
---

# /capture — request capture buffer

Runs the `tasker` specialist to turn a request into a durable, well-formed tracker
item plus a local mirror task, without the active session stopping its current
work. Front door of the capture buffer; `aa_auditor` is the back door that closes
the item once acceptance criteria are verified.

## Usage

- **`/capture <text>`** — capture the text against the **current project**, routed
  to whatever tracker that project declares in `.autonomous.json`.
- **`/capture for <project>: <text>`** — capture against a named project.

## Auto-capture (default)

The session auto-invokes the `tasker` for any barraged request that implies a code
change — the operator does not need to type `/capture`. Pure questions are answered
inline and not filed. `/capture` is only needed to force-file something the
heuristic would otherwise skip.

## Invocation

Dispatch the `tasker` specialist (host-specific: Claude `Agent(subagent_type:
"tasker")`, Codex/Anvil subagent, etc.), passing `request`, `project` (default:
current), and optional `priority`/`lane`. Surface the returned
`{filed, tracker, ref, title, url}` to the operator as a one-line confirmation,
and mirror a `#<ref> <title>` item into the live TodoWrite list.

This skill is the inline counterpart of the `tasker` specialist, matching the
`/reconcile` ↔ `reconciler` pattern.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_capture_skill_contract -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/capture/skill.md tests/test_capture_skill_contract.py
git commit -m "feat(skills): /capture skill invoking the tasker specialist"
```

---

## Task 8: Wire tasker + capture into sync, verify distribution

**Files:**
- Verify/modify: `.env` host targets are unchanged; confirm `agents/tasker.md` is discovered.
- Test: `tests/test_sync_includes_tasker.py`

**Interfaces:**
- Consumes: `agents/tasker.md` (Task 6); the existing `sync_prompt_pack.py` agent discovery.
- Produces: confirmation the tasker agent is in the synced agent inventory (no script change expected — discovery is directory-based).

- [ ] **Step 1: Write the failing test**

Create `tests/test_sync_includes_tasker.py`:
```python
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class SyncIncludesTaskerTest(unittest.TestCase):
    def test_tasker_agent_present_in_source(self) -> None:
        # Agent discovery is directory-based; presence in agents/ is the contract.
        self.assertTrue((REPO / "agents" / "tasker.md").exists())

    def test_capture_skill_present_in_source(self) -> None:
        self.assertTrue((REPO / "skills" / "capture" / "skill.md").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python3 -m unittest tests.test_sync_includes_tasker -v`
Expected: PASS if Tasks 6–7 landed (this is a guard test). If it fails, the prior tasks are incomplete.

- [ ] **Step 3: Run the real sync check (evidence, not just unit test)**

Run: `python3 scripts/sync_prompt_pack.py check`
Expected: output lists each target with an `agents=` field. Confirm `tasker` is NOT reported under a `missing_agents` list. If it is reported missing, run `python3 scripts/sync_prompt_pack.py reconcile-agents` and read the report to see whether the target needs `sync`.

- [ ] **Step 4: If a target reports tasker missing, sync it**

Run: `python3 scripts/sync_prompt_pack.py sync`
Expected: prints `synced <target>: <path>` lines. Re-run `check`; `tasker` no longer missing.

- [ ] **Step 5: Commit any sync-driven changes**

```bash
git add -A
git commit -m "chore(sync): distribute tasker agent and capture skill across hosts"
```

(If `git status` shows nothing to commit because discovery is purely directory-based and no tracked file changed, skip this commit and note it.)

---

## Task 9: Done-reconcile — local mirror follows auditor-closed tracker items

**Files:**
- Create: `autonomous_pipeline/reconcile_done.py`
- Test: `tests/test_reconcile_done.py`

**Interfaces:**
- Consumes: `build_adapter` (Task 5); `TodoJsonAdapter` for the local mirror; `Task`/`TaskUpdate`.
- Produces: `reconcile_done(config, repo_root) -> list[str]` — for each local `todo.json` task whose canonical tracker item is closed/complete, set the local task `status="done"`; returns the list of task ids transitioned. Uses the adapter's `get_task` and treats `status=="done"` (Asana `completed`, GitHub closed) as the done signal. Only the auditor closes tracker items; this function merely propagates that fact to the local mirror.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reconcile_done.py`:
```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.reconcile_done import reconcile_done
from autonomous_pipeline.schemas import RuntimeConfig


class ReconcileDoneTest(unittest.TestCase):
    def test_local_task_marked_done_when_tracker_item_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "todo.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {"id": "1", "title": "open work", "status": "in_progress",
                             "source": "todo_json"},
                        ]
                    }
                )
            )
            # todo_json tracker: closing = local task itself is 'done'.
            # Simulate the auditor having set the canonical item done by writing done.
            data = json.loads((root / "todo.json").read_text())
            data["tasks"][0]["status"] = "done"
            (root / "todo.json").write_text(json.dumps(data))

            transitioned = reconcile_done(RuntimeConfig(), root)
            # Already done → no transition needed; returns empty.
            self.assertEqual(transitioned, [])

    def test_returns_ids_when_transitioning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "todo.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {"id": "7", "title": "mirror", "status": "in_progress",
                             "source": "asana", "source_url": "https://app.asana.com/0/p/7",
                             "metadata": {"tracker_ref": "7"}},
                        ]
                    }
                )
            )

            # Inject a fake adapter that reports the tracker item as done.
            from autonomous_pipeline.adapters.base import TaskAdapter
            from autonomous_pipeline.schemas import Task

            class DoneAdapter(TaskAdapter):
                def list_ready_tasks(self): return []
                def get_task(self, task_id): return Task(id=task_id, title="mirror", status="done", source="asana")
                def claim_task(self, task_id, worker_id): ...
                def update_task(self, task_id, update): ...
                def create_follow_up(self, item): return None

            transitioned = reconcile_done(RuntimeConfig(), root, adapter=DoneAdapter())
            self.assertEqual(transitioned, ["7"])
            data = json.loads((root / "todo.json").read_text())
            self.assertEqual(data["tasks"][0]["status"], "done")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_reconcile_done -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autonomous_pipeline.reconcile_done'`.

- [ ] **Step 3: Write minimal implementation**

Create `autonomous_pipeline/reconcile_done.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from autonomous_pipeline.adapters.base import TaskAdapter
from autonomous_pipeline.adapters.factory import build_adapter
from autonomous_pipeline.schemas import RuntimeConfig


def reconcile_done(
    config: RuntimeConfig,
    repo_root: str | Path,
    adapter: TaskAdapter | None = None,
) -> list[str]:
    """Mark local mirror tasks done when their canonical tracker item is closed.

    Only the auditor closes tracker items; this propagates that to the local file.
    """
    root = Path(repo_root)
    todo_path = root / config.todo_path
    if not todo_path.exists():
        return []
    document = json.loads(todo_path.read_text())
    tracker = adapter if adapter is not None else build_adapter(config, root)

    transitioned: list[str] = []
    for task in document.get("tasks", []):
        if task.get("status") == "done":
            continue
        ref = (task.get("metadata") or {}).get("tracker_ref") or task.get("id")
        try:
            remote = tracker.get_task(str(ref))
        except Exception:
            continue
        if remote.status == "done":
            task["status"] = "done"
            transitioned.append(str(task.get("id")))

    if transitioned:
        todo_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return transitioned
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_reconcile_done -v`
Expected: PASS (2 tests). Note: the first test uses the real `todo_json` adapter — the already-`done` task is skipped by the `status == "done"` guard, so no transition and no adapter lookup, returning `[]`.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add autonomous_pipeline/reconcile_done.py tests/test_reconcile_done.py
git commit -m "feat(pipeline): reconcile_done propagates auditor-closed tracker items to local mirror"
```

---

## Task 10: fire-map / DailyDispatch enablement docs (evidence-based)

**Files:**
- Create: `docs/capture-buffer-enablement.md`

**Interfaces:**
- Consumes: everything above.
- Produces: an operator runbook for turning on Asana capture in a real project (fire-map's `.autonomous.json` template with the Fire Map Tech project gid slot, PAT env var, and the `tasks.json` filename note).

- [ ] **Step 1: Write the runbook**

Create `docs/capture-buffer-enablement.md`:
```markdown
# Capture Buffer — Enablement Runbook

## Enable for a project

1. Set the tracker in the project's `.autonomous.json`:
   - todo.json (default): omit `task_source` or set `"task_source": "todo_json"`.
   - GitHub: `"task_source": "github"`, `"github_repo": "owner/name"`.
   - Asana: `"task_source": "asana"`, `"asana_project_gid": "<gid>"`,
     optionally `"asana_default_section_gid": "<gid>"`.
2. For Asana, export the PAT (never commit it):
   `export ASANA_ACCESS_TOKEN=...` (from the operator's Asana developer console).
3. Confirm the local mirror filename. New projects use `todo.json`. fire-map uses
   `tasks.json` — set `"todo_path": "tasks.json"` in `.autonomous.json` so the
   mirror writes to the existing file.

## fire-map (Fire Map Tech, Asana canonical)

`.autonomous.json` template:
```json
{
  "task_source": "asana",
  "asana_project_gid": "REPLACE_WITH_FIRE_MAP_TECH_GID",
  "todo_path": "tasks.json"
}
```
Fire Map Tech project + task gids are referenced in `fire-map.wfca.com/handoff.md`
and ADRs (e.g. task gid 1215642525150297). Confirm the *project* gid from the Asana
project URL before filling the template.

## Verify end state (Definition of Done)

- `/capture test capture — please ignore` → a new Asana task appears in Fire Map
  Tech AND a `ready` task appears in `tasks.json` with `source: "asana"` and a
  matching `metadata.tracker_ref`. Delete the test task afterward.
- The captured task is NOT `done` until `aa_auditor` verifies its acceptance
  criteria and closes the Asana task; `reconcile_done` then flips the local mirror.
```

- [ ] **Step 2: Commit**

```bash
git add docs/capture-buffer-enablement.md
git commit -m "docs: capture-buffer enablement runbook (fire-map Asana / todo.json / github)"
```

---

## Task 11: Migrate legacy todo.json tasks to canonical shape

**Files:**
- Modify: `todo.json` (the prompt-pack repo's own task list — 2 legacy tasks)
- Test: `tests/test_todo_json_canonical_shape.py`

**Interfaces:**
- Consumes: `Task.from_dict` (tolerant of legacy keys) and the canonical shape from the spec.
- Produces: the repo's `todo.json` tasks use `priority` in `low/medium/high/urgent` (not `P1/P2`), `acceptance_criteria` (not `acceptance`), and `source_url` (not `issue`). Additive: `Task.from_dict` already defaults missing fields, so this is a data migration, not a code change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_todo_json_canonical_shape.py`:
```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TODO = REPO / "todo.json"

_CANONICAL_PRIORITIES = {"low", "medium", "high", "urgent"}


class TodoJsonCanonicalShapeTest(unittest.TestCase):
    def test_no_legacy_keys_and_canonical_priority(self) -> None:
        document = json.loads(TODO.read_text())
        for task in document.get("tasks", []):
            self.assertNotIn("acceptance", task, f"legacy 'acceptance' key in task {task.get('id')}")
            self.assertNotIn("issue", task, f"legacy 'issue' key in task {task.get('id')}")
            self.assertIn(task.get("priority"), _CANONICAL_PRIORITIES,
                          f"non-canonical priority in task {task.get('id')}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_todo_json_canonical_shape -v`
Expected: FAIL — the two legacy tasks use `priority: "P1"/"P2"`, `acceptance`, `issue`.

- [ ] **Step 3: Migrate the two legacy tasks**

Edit `todo.json`. For each task: rename `acceptance` → `acceptance_criteria`; move the GitHub issue URL from `issue` → `source_url` and add `"source": "github"`; map priority `P1` → `"high"`, `P2` → `"medium"` (P0 → `"urgent"`, P3 → `"low"` if present). Preserve all other fields (`fold_in_files`, `description`, `owner`, `created`). Example for task id 1:
```json
{
  "id": 1,
  "title": "Migrate prompt-pack source out of ~/Dropbox/_CODING/ → ~/_CODING/",
  "status": "open",
  "priority": "high",
  "source": "github",
  "source_url": "https://github.com/metazen11/autonomous-agents/issues/11",
  "created": "2026-05-21",
  "owner": "mz@wfca.com",
  "description": "... (unchanged) ...",
  "acceptance_criteria": [ "... (unchanged list) ..." ],
  "fold_in_files": [ "... (unchanged) ..." ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_todo_json_canonical_shape -v`
Expected: PASS.

- [ ] **Step 5: Confirm the adapter still parses the migrated file**

Run: `python3 -c "from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter; print([t.id for t in TodoJsonAdapter('todo.json').list_ready_tasks()])"`
Expected: runs without error (prints `[]` because the two tasks are `status: "open"`, not `"ready"` — that is fine; the point is no parse error).

- [ ] **Step 6: Commit**

```bash
git add todo.json tests/test_todo_json_canonical_shape.py
git commit -m "chore(todo): migrate legacy tasks to canonical Task shape (priority/source_url/acceptance_criteria)"
```

---

## Task 12: Full-suite green + spec-coverage evidence

**Files:** none (verification task).

- [ ] **Step 1: Run the entire test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: ALL tests PASS, including the pre-existing suite.

- [ ] **Step 2: Confirm no secret leaked into tracked files**

Run: `git grep -nI "ASANA_ACCESS_TOKEN" -- ':!docs' ':!*.md' || echo "clean (only referenced in docs/code as env var name)"`
Expected: only the env-var *name* appears (in `asana.py` and docs), never a token value.

- [ ] **Step 3: Confirm the sync check is green for the new agent**

Run: `python3 scripts/sync_prompt_pack.py check`
Expected: no target reports `tasker` under missing agents.

- [ ] **Step 4: Final commit if anything is uncommitted**

```bash
git status
# commit only if there are pending intended changes
```
```
