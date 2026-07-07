from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.config import load_runtime_config


class LoadAsanaConfigTest(unittest.TestCase):
    def test_loads_asana_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".autonomous.json").write_text(
                json.dumps(
                    {
                        "task_source": "asana",
                        "asana_project_gid": "1215642525150297",
                        "asana_workspace_gid": "9999",
                        "asana_default_section_gid": "8888",
                    }
                )
            )
            config = load_runtime_config(root)
            self.assertEqual(config.task_source, "asana")
            self.assertEqual(config.asana_project_gid, "1215642525150297")
            self.assertEqual(config.asana_workspace_gid, "9999")
            self.assertEqual(config.asana_default_section_gid, "8888")

    def test_absent_config_defaults_to_todo_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_runtime_config(Path(tmp))
            self.assertEqual(config.task_source, "todo_json")
            self.assertIsNone(config.asana_project_gid)


if __name__ == "__main__":
    unittest.main()
