from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.runner import PipelineRunner
from autonomous_pipeline.schemas import PromotionCandidate, RuntimeConfig


class _MemoryClient:
    def list_lessons(self, project: str | None = None, limit: int = 20) -> list[dict]:
        return []

    def create_lesson(self, **kwargs) -> dict:
        return {"id": 99, "title": kwargs["title"]}


class RunnerFlowTest(unittest.TestCase):
    def test_report_result_marks_task_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "x", "status": "ready", "source": "todo_json"}]}\n'
            )
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(),
                memory_client=_MemoryClient(),
            )
            runner.initialize()
            task = runner.pick_task()
            assert task is not None
            updated = runner.report_result(task, success=True, summary="done")
        self.assertEqual(updated.status, "done")

    def test_promote_candidate_creates_follow_up_for_non_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text('{"tasks": []}\n')
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(),
                memory_client=_MemoryClient(),
            )
            runner.initialize()
            result = runner.promote_candidate(
                PromotionCandidate(
                    title="Automate repeated step",
                    description="Turn repeated command sequence into script",
                    candidate_type="script",
                )
            )
        self.assertEqual(result["type"], "follow_up")

    def test_runner_restores_selected_task_from_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "x", "status": "in_progress", "source": "todo_json"}]}\n'
            )
            (repo_root / ".autonomous-state.json").write_text(
                '{"session_id":"abc","repo_root":"%s","mode":"full","current_phase":"PLAN","selected_task_id":"task-1","completed_tasks":[],"failed_tasks":[],"skipped_tasks":[],"memory_status":"ok","memory_lessons_loaded":0,"phase_history":[]}\n'
                % repo_root
            )
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(),
                memory_client=_MemoryClient(),
            )
            task = runner.get_selected_task()
        assert task is not None
        self.assertEqual(task.id, "task-1")


if __name__ == "__main__":
    unittest.main()
