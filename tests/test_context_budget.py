"""Issue #20: always-loaded instruction budget, rule drift, recency ordering, per-host agent selection.

The render-or-link check is per section (one §XX link covers every rule with that prefix); the frozen
per-prefix count in EXPECTED_RULE_COUNTS is the real guard against a dropped rule.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from autonomous_pipeline.host_sync import (
    HOST_AGENTS_CONFIG,
    IRON_RULES_HEADING,
    HostTarget,
    check_target,
    host_agent_sources,
    render_host_instructions,
    repo_agent_sources,
    sync_target,
)

REPO = Path(__file__).resolve().parents[1]
REFERENCE = REPO / "docs" / "contract-reference.md"
HOSTS = ("claude", "codex", "gemini", "anvil")
# Frozen rule inventory. Dropping a rule from the reference fails here; adding one means bumping its count.
EXPECTED_RULE_COUNTS = {
    "RC": 15, "DD": 4, "SEC": 2, "HG": 3, "OPT": 7, "OM": 13,
    "IN": 7, "BR": 10, "CR": 6, "IP": 11, "SS": 7,
}
RULE_ID = re.compile(r"^- \[([A-Z]+)-(\d+)\]", re.M)


def render(host: str) -> str:
    return render_host_instructions(
        REPO, HostTarget(name=host, skill_path=Path(f"/tmp/{host}/skill.md"), agents_dir=Path(f"/tmp/{host}/agents"))
    )


class RuleDriftTest(unittest.TestCase):
    def test_reference_holds_every_rule_id(self) -> None:
        ids = RULE_ID.findall(REFERENCE.read_text())
        self.assertEqual(len(ids), len(set(ids)), "duplicate rule ID in contract-reference.md")
        counts = Counter(prefix for prefix, _ in ids)
        self.assertEqual(dict(counts), EXPECTED_RULE_COUNTS)
        for prefix, total in EXPECTED_RULE_COUNTS.items():
            self.assertEqual(sorted(int(n) for p, n in ids if p == prefix), list(range(1, total + 1)), prefix)

    def test_every_rule_is_rendered_or_its_section_linked(self) -> None:
        text = REFERENCE.read_text()
        for prefix, _ in RULE_ID.findall(text):
            self.assertIn(f"## §{prefix} ", text, f"rule section §{prefix} missing a heading")
        for host in HOSTS:
            rendered = render(host)
            for prefix, number in RULE_ID.findall(text):
                self.assertTrue(
                    f"[{prefix}-{number}]" in rendered or f"§{prefix}" in rendered,
                    f"{host}: rule {prefix}-{number} neither rendered nor linked via §{prefix}",
                )


class OrderingAndBudgetTest(unittest.TestCase):
    def test_iron_rules_are_the_final_block_and_the_top_points_to_them(self) -> None:
        for host in HOSTS:
            rendered = render(host)
            headings = re.findall(r"(?m)^## .*$", rendered)
            self.assertEqual(headings[-1], IRON_RULES_HEADING, host)
            final = rendered[rendered.index(IRON_RULES_HEADING):]
            positions = [final.index(key) for key in ("Root cause", "Done =", "Secrets", "Human release gate", "OPTIMIZE EVERYTHING")]
            self.assertEqual(positions, sorted(positions), f"{host}: iron-rule order regressed")
            head = "\n".join(rendered.splitlines()[:4])
            self.assertIn("Iron Rules are the LAST section", head, host)

    def test_claude_and_codex_files_fit_budget(self) -> None:
        for host in ("claude", "codex"):
            self.assertLessEqual(len(render(host).encode()), 8 * 1024, host)

    def test_agent_descriptions_fit_budget(self) -> None:
        for source in repo_agent_sources(REPO):
            match = re.search(r"(?m)^description:\s*(.+)$", source.read_text())
            if match:
                self.assertLessEqual(len(match.group(1).strip()), 200, source.name)


class HostAgentSelectionTest(unittest.TestCase):
    def test_kyc_excluded_from_claude_and_codex_only(self) -> None:
        for host, expected in (("claude", False), ("codex", False), ("anvil", True), (None, True)):
            stems = {s.stem for s in host_agent_sources(REPO, host)}
            self.assertEqual("kyc-screener" in stems, expected, host)
        self.assertTrue((REPO / "agent_bundles/financial-services/agents/kyc-screener.md").exists())

    def _repo_copy(self, config: dict | None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for sub in ("agents", "agent_bundles", "pipeline"):
            shutil.copytree(REPO / sub, root / sub)
        if config is not None:
            (root / HOST_AGENTS_CONFIG).write_text(json.dumps(config))
        return root

    def test_missing_config_or_host_means_all(self) -> None:
        all_stems = {s.stem for s in repo_agent_sources(REPO)}
        self.assertEqual({s.stem for s in host_agent_sources(self._repo_copy(None), "claude")}, all_stems)
        self.assertEqual({s.stem for s in host_agent_sources(self._repo_copy({"codex": {"exclude": ["pm"]}}), "claude")}, all_stems)

    def test_unknown_stem_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown agents"):
            host_agent_sources(self._repo_copy({"claude": {"exclude": ["kyc-screenr"]}}), "claude")

    def test_sync_removes_excluded_agent_and_check_stays_green(self) -> None:
        root = self._repo_copy({"claude": {"include": "all", "exclude": ["kyc-screener"]}})
        dest = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dest)
        agents = dest / "agents"
        agents.mkdir()
        (agents / "aa_kyc_screener.md").write_text("stale copy")
        target = HostTarget(name="claude", skill_path=dest / "skill.md", agents_dir=agents)
        sync_target(root, target)
        self.assertFalse((agents / "aa_kyc_screener.md").exists())
        self.assertTrue((agents / "aa_pitch_agent.md").exists())
        self.assertEqual(check_target(root, target).missing_agents, [])


if __name__ == "__main__":
    unittest.main()
