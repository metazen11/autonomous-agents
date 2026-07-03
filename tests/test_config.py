from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.config import load_runtime_config, merge_cli_overrides


class RuntimeConfigTest(unittest.TestCase):
    def test_defaults_when_config_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_runtime_config(tmpdir)
        self.assertEqual(config.task_source, "todo_json")
        self.assertEqual(config.todo_path, "todo.json")

    def test_loads_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".autonomous.json"
            config_path.write_text(
                json.dumps(
                    {
                        "task_source": "github",
                        "github_repo": "owner/repo",
                        "github_label": "autonomous:ready",
                        "github_command": ["gh"],
                        "artifacts_dir": ".runs",
                    }
                )
            )
            config = load_runtime_config(tmpdir)
        self.assertEqual(config.task_source, "github")
        self.assertEqual(config.github_repo, "owner/repo")
        self.assertEqual(config.artifacts_dir, ".runs")

    def test_cli_overrides_take_precedence(self) -> None:
        config = merge_cli_overrides(load_runtime_config("."), todo_path="tasks/todo.json", memory_url="http://x")
        self.assertEqual(config.todo_path, "tasks/todo.json")
        self.assertEqual(config.memory_url, "http://x")

    def test_task_file_override_switches_task_source(self) -> None:
        config = merge_cli_overrides(load_runtime_config("."), task_file="plans/task.md")
        self.assertEqual(config.task_source, "file")
        self.assertEqual(config.task_file, "plans/task.md")
        self.assertIsNone(config.prompt_text)

    def test_prompt_text_override_switches_task_source(self) -> None:
        config = merge_cli_overrides(load_runtime_config("."), prompt_text="Ship the feature.")
        self.assertEqual(config.task_source, "prompt")
        self.assertEqual(config.prompt_text, "Ship the feature.")
        self.assertIsNone(config.task_file)


if __name__ == "__main__":
    unittest.main()
