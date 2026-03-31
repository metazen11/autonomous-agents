from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.schemas import PromotionCandidate, TaskUpdate


class TodoJsonAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.todo_path = Path(self.tmpdir.name) / "todo.json"
        self.todo_path.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "task-2",
                            "title": "Lower priority task",
                            "status": "ready",
                            "priority": "medium",
                        },
                        {
                            "id": "task-1",
                            "title": "Highest priority task",
                            "status": "ready",
                            "priority": "urgent",
                            "artifacts": [],
                            "improvement_candidates": [],
                        },
                    ]
                },
                indent=2,
            )
            + "\n"
        )
        self.adapter = TodoJsonAdapter(self.todo_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_list_ready_tasks_sorts_by_priority(self) -> None:
        tasks = self.adapter.list_ready_tasks()
        self.assertEqual([task.id for task in tasks], ["task-1", "task-2"])

    def test_claim_and_update_task(self) -> None:
        self.adapter.claim_task("task-1", worker_id="worker-123")
        task = self.adapter.update_task(
            "task-1",
            TaskUpdate(
                status="blocked",
                blockers=["Missing credentials"],
                artifacts=["artifacts/run-1/log.txt"],
                improvement_candidates=["Add preflight auth check"],
                append_phase_log="Blocked during TEST",
            ),
        )
        self.assertEqual(task.status, "blocked")
        self.assertEqual(task.blockers, ["Missing credentials"])
        self.assertIn("artifacts/run-1/log.txt", task.artifacts)
        self.assertIn("Add preflight auth check", task.improvement_candidates)

    def test_create_follow_up(self) -> None:
        follow_up_id = self.adapter.create_follow_up(
            PromotionCandidate(
                title="Automate repeated lint/test chain",
                description="Promote repeated verification command sequence into a script",
                candidate_type="script",
            )
        )
        payload = json.loads(self.todo_path.read_text())
        self.assertEqual(follow_up_id, "follow-up-1")
        self.assertEqual(payload["follow_ups"][0]["candidate_type"], "script")


if __name__ == "__main__":
    unittest.main()
