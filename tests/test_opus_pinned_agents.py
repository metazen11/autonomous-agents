import re
import unittest
from pathlib import Path

from autonomous_pipeline.host_sync import render_agent_prompt

AGENTS = Path(__file__).resolve().parent.parent / "agents"


class OpusPinnedAgentsTest(unittest.TestCase):
    def test_gate_agents_pin_opus_and_survive_render(self) -> None:
        for name in ("auditor", "code-reviewer", "quality-gate"):
            rendered = render_agent_prompt(AGENTS / f"{name}.md", repo_root=AGENTS.parent)
            front = re.match(r"---\n(.*?)\n---\n", rendered, re.S).group(1)
            self.assertRegex(front, r"(?m)^model: opus$", name)

    def test_simple_roles_pin_haiku_and_gate_roles_never_do(self) -> None:
        root = AGENTS.parent
        simple = {
            "report": root / "agent_bundles/anvil-local/agents/report.md",
            "pr": root / "agent_bundles/anvil-local/agents/pr.md",
            "docs": root / "agent_bundles/anvil-local/agents/docs.md",
            "infra-checker": AGENTS / "infra-checker.md",
        }
        for name, path in simple.items():
            front = re.match(r"---\n(.*?)\n---\n", render_agent_prompt(path, repo_root=root), re.S).group(1)
            self.assertRegex(front, r"(?m)^model: haiku$", name)
        for name in ("quality-gate", "auditor", "code-reviewer", "tasker", "security-auditor", "security-fixer"):
            self.assertNotRegex(render_agent_prompt(AGENTS / f"{name}.md", repo_root=root), r"(?m)^model: haiku$", name)
        dev = root / "agent_bundles/anvil-local/agents/dev.md"
        self.assertNotRegex(render_agent_prompt(dev, repo_root=root), r"(?m)^model: haiku$", "dev")


if __name__ == "__main__":
    unittest.main()
