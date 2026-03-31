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
        return {"id": 1}


class PRFlowTest(unittest.TestCase):
    def test_prepare_pr_falls_back_to_human_required_for_todo_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text(
                '{"tasks": [{"id": "task-1", "title": "PR task", "status": "ready", "source": "todo_json"}]}\n'
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
            result = runner.prepare_pr(task)
            self.assertEqual(result.status, "human_required")
            self.assertTrue(Path(result.body_artifact_path).exists())


if __name__ == "__main__":
    unittest.main()
