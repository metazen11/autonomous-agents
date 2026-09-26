from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TODO = REPO / "todo.json"

_CANONICAL_PRIORITIES = {"low", "medium", "high", "urgent"}


class TodoJsonCanonicalShapeTest(unittest.TestCase):
    def test_no_legacy_keys_and_canonical_priority(self) -> None:
        document = json.loads(TODO.read_text())
        for task in document.get("tasks", []):
            self.assertNotIn("acceptance", task, f"legacy 'acceptance' key in task {task.get('id')}")
            self.assertNotIn("issue", task, f"legacy 'issue' key in task {task.get('id')}")
            self.assertIn(task.get("priority"), _CANONICAL_PRIORITIES,
                          f"non-canonical priority in task {task.get('id')}")


if __name__ == "__main__":
    unittest.main()
