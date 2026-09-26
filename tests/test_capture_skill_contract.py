from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "capture" / "skill.md"


class CaptureSkillContractTest(unittest.TestCase):
    def test_skill_exists_with_required_sections(self) -> None:
        self.assertTrue(SKILL.exists(), "skills/capture/skill.md must exist")
        text = SKILL.read_text()
        for needle in [
            "name: capture",
            "user-invocable: true",
            "/capture",
            "for <project>",
            "auto-capture",
            "tasker",
            '"filed": false',
            '"filed": true',
        ]:
            self.assertIn(needle, text, f"skill.md missing: {needle}")

    def test_documents_branching_on_filed(self) -> None:
        text = SKILL.read_text()
        self.assertIn("Branch on `filed`", text,
                      "skill.md must instruct callers to branch on filed before reading other fields")


if __name__ == "__main__":
    unittest.main()
