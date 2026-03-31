from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.runner import PipelineRunner
from autonomous_pipeline.schemas import RuntimeConfig


class _MemoryClient:
    def list_lessons(self, project: str | None = None, limit: int = 20) -> list[dict]:
        return []

    def create_lesson(self, **kwargs) -> dict:
        return {"id": 11, "title": kwargs["title"]}


class DevAndSpecialistFlowTest(unittest.TestCase):
    def test_run_development_captures_artifact_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "Implement flow", "status": "ready", "source": "todo_json"}]}\n'
            )
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(development_command='python3 -c "print(\'dev ok\')"'),
                memory_client=_MemoryClient(),
            )
            runner.initialize()
            task = runner.pick_task()
            assert task is not None
            result = runner.run_development(task)
            updated = runner.adapter.get_task(task.id)

            self.assertEqual(result["status"], "pass")
            self.assertTrue(Path(result["artifact_path"]).exists())
            self.assertEqual(updated.metadata["development_result"]["status"], "pass")

    def test_run_development_preserves_existing_changed_files_when_git_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "Implement flow", "status": "ready", "source": "todo_json", "metadata": {"changed_files": ["autonomous_pipeline/runner.py"]}}]}\n'
            )
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(development_command='python3 -c "print(\'dev ok\')"'),
                memory_client=_MemoryClient(),
            )
            runner.initialize()
            task = runner.pick_task()
            assert task is not None
            result = runner.run_development(task)

            self.assertEqual(result["changed_files"], ["autonomous_pipeline/runner.py"])

    def test_run_review_uses_automated_code_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "Review flow", "status": "ready", "source": "todo_json", "metadata": {"verification_results": [{"category": "unit", "status": "pass", "command": "pytest", "artifact_path": "artifacts/unit.log"}], "changed_files": ["autonomous_pipeline/runner.py"]}}]}\n'
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
            result = runner.run_review(task)
            updated = runner.adapter.get_task(task.id)

            self.assertEqual(result["status"], "success")
            self.assertTrue(Path(result["artifact_path"]).exists())
            self.assertIn("review_result", updated.metadata)
            self.assertEqual(updated.metadata["review_result"]["agent_name"], "code-reviewer")
            self.assertEqual(updated.metadata["review_result"]["findings"], [])

    def test_run_code_review_runs_before_verification_evidence_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "Code review flow", "status": "ready", "source": "todo_json", "metadata": {"changed_files": ["autonomous_pipeline/runner.py", "autonomous_pipeline/schemas.py", "autonomous_pipeline/config.py"]}}]}\n'
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
            result = runner.run_code_review(task)
            updated = runner.adapter.get_task(task.id)

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["verdict"], "changes_requested")
            self.assertIn("code_review_result", updated.metadata)
            self.assertEqual(updated.metadata["code_review_result"]["agent_name"], "code-reviewer")
            self.assertTrue(updated.metadata["code_review_result"]["findings"])

    def test_run_improvement_promotes_follow_up_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "Improve flow", "status": "ready", "source": "todo_json", "metadata": {"development_result": {"status": "pass", "artifact_path": "artifacts/development.log"}, "verification_results": [{"category": "build", "status": "pass", "command": "npm run build", "artifact_path": "artifacts/build.log"}, {"category": "unit", "status": "pass", "command": "npm test", "artifact_path": "artifacts/test.log"}]}}]}\n'
            )
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(development_command="make dev"),
                memory_client=_MemoryClient(),
            )
            runner.initialize()
            task = runner.pick_task()
            assert task is not None
            result = runner.run_improvement(task)
            todo_payload = (repo_root / "todo.json").read_text()

            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["promotions"]), 2)
            self.assertIn("follow-up-1", todo_payload)
            self.assertIn("follow-up-2", todo_payload)

    def test_run_specialist_records_metadata_for_additional_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "Dependency review", "status": "ready", "source": "todo_json", "metadata": {"changed_files": ["package.json"]}}]}\n'
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
            result = runner.run_specialist(task, "dep-auditor")
            updated = runner.adapter.get_task(task.id)

            self.assertEqual(result["agent_name"], "dep-auditor")
            self.assertIn("specialist_results", updated.metadata)
            self.assertIn("dep-auditor", updated.metadata["specialist_results"])


if __name__ == "__main__":
    unittest.main()
