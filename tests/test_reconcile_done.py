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

    def test_adapter_exception_skips_task_not_abort(self) -> None:
        """A get_task failure for one task must skip only that task, and the
        reconcile must continue to the next (stated per-task isolation contract)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "todo.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {"id": "boom", "title": "raises", "status": "in_progress",
                             "source": "asana", "metadata": {"tracker_ref": "boom"}},
                            {"id": "ok", "title": "done-remote", "status": "in_progress",
                             "source": "asana", "metadata": {"tracker_ref": "ok"}},
                        ]
                    }
                )
            )

            from autonomous_pipeline.adapters.base import TaskAdapter
            from autonomous_pipeline.schemas import Task

            class FlakyAdapter(TaskAdapter):
                def list_ready_tasks(self): return []
                def get_task(self, task_id):
                    if task_id == "boom":
                        raise RuntimeError("simulated tracker API failure")
                    return Task(id=task_id, title="done-remote", status="done", source="asana")
                def claim_task(self, task_id, worker_id): ...
                def update_task(self, task_id, update): ...
                def create_follow_up(self, item): return None

            transitioned = reconcile_done(RuntimeConfig(), root, adapter=FlakyAdapter())
            # The failing task is skipped; the reconcile continues and transitions "ok".
            self.assertEqual(transitioned, ["ok"])
            data = json.loads((root / "todo.json").read_text())
            statuses = {t["id"]: t["status"] for t in data["tasks"]}
            self.assertEqual(statuses["boom"], "in_progress")
            self.assertEqual(statuses["ok"], "done")


if __name__ == "__main__":
    unittest.main()
