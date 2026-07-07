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
