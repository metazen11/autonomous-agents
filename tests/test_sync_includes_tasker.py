from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class SyncIncludesTaskerTest(unittest.TestCase):
    def test_tasker_agent_present_in_source(self) -> None:
        # Agent discovery is directory-based; presence in agents/ is the contract.
        self.assertTrue((REPO / "agents" / "tasker.md").exists())

    def test_capture_skill_present_in_source(self) -> None:
        self.assertTrue((REPO / "skills" / "capture" / "skill.md").exists())


if __name__ == "__main__":
    unittest.main()
