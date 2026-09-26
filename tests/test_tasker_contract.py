from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "agents" / "tasker.md"


class TaskerContractTest(unittest.TestCase):
    def test_contract_exists_with_required_sections(self) -> None:
        self.assertTrue(CONTRACT.exists(), "agents/tasker.md must exist")
        text = CONTRACT.read_text()
        for needle in [
            "name: tasker",
            "AGENT_AGNOSTIC_GUIDE.md",
            "## Inputs",
            "## Procedure",
            "build_adapter",
            "acceptance_criteria",
            "aa_auditor",
            "tracker_ref",
            "filed",
            "## Forbidden Actions",
            "## Conflict and Failure Handling",
            "## Output",
            "source_url",
        ]:
            self.assertIn(needle, text, f"tasker.md missing: {needle}")


if __name__ == "__main__":
    unittest.main()
