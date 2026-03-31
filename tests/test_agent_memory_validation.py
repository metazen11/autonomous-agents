from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.memory.validation import validate_agent_memory
from autonomous_pipeline.runner import PipelineRunner
from autonomous_pipeline.schemas import RuntimeConfig


class _StubMemoryClient:
    def __init__(self) -> None:
        self.lessons: list[dict] = []

    def get_health(self) -> dict:
        return {"status": "ok"}

    def create_lesson(self, **kwargs) -> dict:
        lesson = {
            "id": len(self.lessons) + 1,
            "title": kwargs["title"],
            "rule": kwargs["rule"],
            "severity": kwargs.get("severity", "warning"),
            "active": True,
        }
        self.lessons.insert(0, lesson)
        return lesson

    def list_lessons(self, project: str | None = None, limit: int = 20) -> list[dict]:
        return list(self.lessons)

    def match_lessons(self, *, tool_name: str, tool_input_preview: str = "", project: str | None = None) -> list[dict]:
        return list(self.lessons)

    def search_observations(self, query: str, project: str, limit: int = 5) -> dict:
        return {"observations": [], "mode": "hybrid", "total": 0}


class _FailingMemoryClient:
    def list_lessons(self, project: str | None = None, limit: int = 20) -> list[dict]:
        raise RuntimeError("unavailable")

    def create_lesson(self, **kwargs) -> dict:
        raise RuntimeError("unavailable")


class AgentMemoryValidationTest(unittest.TestCase):
    def test_validation_report_passes_against_stub_contract(self) -> None:
        report = validate_agent_memory(_StubMemoryClient(), project_path=Path("/tmp/project"))
        self.assertEqual(report.overall_status, "pass")
        self.assertEqual([check.status for check in report.checks], ["pass", "pass", "pass", "pass", "pass"])

    def test_runner_loads_memory_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "todo.json").write_text('{"tasks": []}\n')
            runner = PipelineRunner(
                repo_root=repo_root,
                adapter=TodoJsonAdapter(repo_root / "todo.json"),
                config=RuntimeConfig(),
                memory_client=_StubMemoryClient(),
            )
            state = runner.initialize()
        self.assertEqual(state.memory_status, "ok")
        self.assertEqual(state.memory_lessons_loaded, 0)


if __name__ == "__main__":
    unittest.main()
