import re
import unittest
from pathlib import Path

from autonomous_pipeline.host_sync import render_agent_prompt

AGENTS = Path(__file__).resolve().parent.parent / "agents"


class OpusPinnedAgentsTest(unittest.TestCase):
    def test_gate_agents_pin_opus_and_survive_render(self) -> None:
        for name in ("auditor", "code-reviewer", "quality-gate"):
            rendered = render_agent_prompt(AGENTS / f"{name}.md")
            front = re.match(r"---\n(.*?)\n---\n", rendered, re.S).group(1)
            self.assertRegex(front, r"(?m)^model: opus$", name)


if __name__ == "__main__":
    unittest.main()
