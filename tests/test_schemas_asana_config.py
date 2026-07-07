from __future__ import annotations

import unittest

from autonomous_pipeline.schemas import RuntimeConfig


class RuntimeConfigAsanaTest(unittest.TestCase):
    def test_asana_fields_default_to_none(self) -> None:
        config = RuntimeConfig()
        self.assertIsNone(config.asana_project_gid)
        self.assertIsNone(config.asana_workspace_gid)
        self.assertIsNone(config.asana_default_section_gid)

    def test_asana_task_source_roundtrips(self) -> None:
        config = RuntimeConfig(task_source="asana", asana_project_gid="123")
        data = config.to_dict()
        self.assertEqual(data["task_source"], "asana")
        self.assertEqual(data["asana_project_gid"], "123")


if __name__ == "__main__":
    unittest.main()
