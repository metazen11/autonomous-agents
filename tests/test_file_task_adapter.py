from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.file_task import FileTaskAdapter
from autonomous_pipeline.schemas import PromotionCandidate, TaskUpdate


class FileTaskAdapterTest(unittest.TestCase):
    def test_defaults_to_markdown_and_text_files_in_plans_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            plans_dir = repo_root / "plans"
            plans_dir.mkdir()
            (plans_dir / "b-task.txt").write_text("Second task\n\nLower alphabetical priority.\n")
            (plans_dir / "a-task.md").write_text("# First task\n\nPick this one first.\n")

            adapter = FileTaskAdapter(repo_root=repo_root)
            tasks = adapter.list_ready_tasks()

        self.assertEqual([task.metadata["source_label"] for task in tasks], ["plans/a-task.md", "plans/b-task.txt"])
        self.assertEqual(tasks[0].title, "First task")

    def test_reads_markdown_file_as_single_ready_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            task_file = repo_root / "planning.md"
            task_file.write_text("# Improve task intake\n\nAdd support for markdown and text prompts.\n")
            adapter = FileTaskAdapter(repo_root=repo_root, task_file=task_file)

            tasks = adapter.list_ready_tasks()

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Improve task intake")
        self.assertIn("markdown and text prompts", tasks[0].body)
        self.assertEqual(tasks[0].source, "file")

    def test_claim_and_update_inline_prompt_task_persist_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            adapter = FileTaskAdapter(
                repo_root=repo_root,
                prompt_text="Build support for inline prompts.\nCapture the plan in the task body.",
            )
            task = adapter.list_ready_tasks()[0]

            adapter.claim_task(task.id, worker_id="worker-7")
            updated = adapter.update_task(
                task.id,
                TaskUpdate(
                    status="blocked",
                    blockers=["Need decision on CLI flag naming"],
                    artifacts=["artifacts/plan.md"],
                    improvement_candidates=["Add reusable prompt parser"],
                    append_phase_log="Blocked during PLAN",
                ),
            )

            restored = FileTaskAdapter(repo_root=repo_root, prompt_text="Build support for inline prompts.\nCapture the plan in the task body.")
            restored_task = restored.get_task(task.id)

        self.assertEqual(updated.status, "blocked")
        self.assertEqual(restored_task.status, "blocked")
        self.assertEqual(restored_task.blockers, ["Need decision on CLI flag naming"])
        self.assertIn("artifacts/plan.md", restored_task.artifacts)
        self.assertIn("Add reusable prompt parser", restored_task.improvement_candidates)
        self.assertEqual(restored_task.metadata["claimed_by"], "worker-7")
        self.assertEqual(restored_task.metadata["phase_history"][0]["message"], "Blocked during PLAN")

    def test_create_follow_up_in_state_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            adapter = FileTaskAdapter(repo_root=repo_root, prompt_text="Turn this prompt into a task.")

            follow_up_id = adapter.create_follow_up(
                PromotionCandidate(
                    title="Package file intake flow",
                    description="Promote prompt ingestion into a reusable adapter",
                    candidate_type="adapter",
                )
            )
            payload = json.loads((repo_root / ".autonomous-file-task.json").read_text())

        self.assertEqual(follow_up_id, "follow-up-1")
        self.assertEqual(payload["follow_ups"][0]["candidate_type"], "adapter")
