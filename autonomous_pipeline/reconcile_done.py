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
            # Per-task resilience boundary: a lookup failure for one task (API
            # error, missing ref, auth) skips only that task and does not abort
            # the whole reconcile. Narrow to TaskAdapterError if a common base
            # is formalized across adapters.
            continue
        if remote.status == "done":
            task["status"] = "done"
            transitioned.append(str(task.get("id")))

    if transitioned:
        todo_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return transitioned
