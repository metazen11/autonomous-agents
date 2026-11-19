"""Issue #23: excluded agents go to `<host>/agents-bench/`; `bench play|sit` moves one; non-agent files never render."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.host_sync import (
    HOST_AGENTS_CONFIG,
    HostTarget,
    check_target,
    host_agent_sources,
    repo_agent_sources,
    sync_target,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sync_prompt_pack.py"
BENCH = {
    "earnings-reviewer", "gl-reconciler", "kyc-screener", "market-researcher", "meeting-prep-agent",
    "model-builder", "month-end-closer", "pitch-agent", "statement-auditor", "valuation-reviewer",
    "anvil-qa", "anvil-qa-ui", "regime-filter-tuner", "strategy-honesty-checker",
}


def repo_copy(test: unittest.TestCase) -> Path:
    root = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, root)
    for sub in ("agents", "agent_bundles", "pipeline"):
        shutil.copytree(REPO / sub, root / sub)
    shutil.copy(REPO / HOST_AGENTS_CONFIG, root / HOST_AGENTS_CONFIG)
    return root


def temp_target(test: unittest.TestCase, host: str = "claude") -> HostTarget:
    dest = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, dest)
    return HostTarget(name=host, skill_path=dest / "skill.md", agents_dir=dest / "agents")


def names(path: Path) -> set[str]:
    return {p.name for p in path.glob("*.md")}


class NonAgentFilesTest(unittest.TestCase):
    def test_spec_without_frontmatter_is_not_an_agent_source(self) -> None:
        self.assertNotIn("secret_rotator.SPEC", {s.stem for s in repo_agent_sources(REPO)})
        self.assertTrue((REPO / "agents/secret_rotator.SPEC.md").exists(), "source is kept")

    def test_non_agent_md_never_rendered_into_agent_dir(self) -> None:
        root = repo_copy(self)
        (root / "agents/notes.md").write_text("# Notes\nno frontmatter\n")
        (root / "agents/half.md").write_text("---\nname: half\n---\nno description\n")
        target = temp_target(self)
        sync_target(root, target)
        rendered = names(target.agents_dir)
        for bad in ("aa_notes.md", "aa_half.md", "aa_secret_rotator.SPEC.md"):
            self.assertNotIn(bad, rendered)
        self.assertIn("aa_auditor.md", rendered)


class BenchSyncTest(unittest.TestCase):
    def test_issue_exclusion_list_applied_to_claude_and_codex(self) -> None:
        for host in ("claude", "codex"):
            self.assertEqual(BENCH & {s.stem for s in host_agent_sources(REPO, host)}, set(), host)
        self.assertTrue(BENCH <= {s.stem for s in host_agent_sources(REPO, "anvil")})

    def test_excluded_agents_land_in_bench_not_active(self) -> None:
        target = temp_target(self)
        sync_target(repo_copy(self), target)
        bench = target.agents_dir.parent / "agents-bench"
        expected = {f"aa_{stem.replace('-', '_')}.md" for stem in BENCH}
        self.assertEqual(names(bench), expected)
        self.assertEqual(names(target.agents_dir) & expected, set())

    def test_check_fails_when_bench_agent_is_also_active(self) -> None:
        root = repo_copy(self)
        target = temp_target(self)
        sync_target(root, target)
        status = check_target(root, target)
        self.assertEqual(status.bench_problems, [])
        self.assertIn("aa_pitch_agent.md", status.bench)
        shutil.copy(target.agents_dir.parent / "agents-bench/aa_pitch_agent.md", target.agents_dir)
        self.assertIn("aa_pitch_agent.md(active)", check_target(root, target).bench_problems)


class BenchCliTest(unittest.TestCase):
    def cli(self, root: Path, env_file: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(REPO)}
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--repo-root", str(root), "--env-file", str(env_file)],
            capture_output=True, text=True, env=env, check=False,
        )

    def test_play_then_sit_round_trip(self) -> None:
        root = repo_copy(self)
        target = temp_target(self)
        env_file = root / ".env"
        env_file.write_text(f"CLAUDE_SKILL_PATH={target.skill_path}\nCLAUDE_AGENTS_DIR={target.agents_dir}\n")
        active, bench = target.agents_dir, target.agents_dir.parent / "agents-bench"
        self.assertEqual(self.cli(root, env_file, "sync").returncode, 0)

        played = self.cli(root, env_file, "bench", "play", "pitch-agent", "--host", "claude")
        self.assertEqual(played.returncode, 0, played.stderr)
        self.assertIn("aa_pitch_agent.md", names(active))
        self.assertNotIn("aa_pitch_agent.md", names(bench))
        config = json.loads((root / HOST_AGENTS_CONFIG).read_text())
        self.assertNotIn("pitch-agent", config["claude"]["exclude"])
        self.assertIn("pitch-agent", config["codex"]["exclude"], "--host claude must leave codex alone")
        checked = self.cli(root, env_file, "check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

        sat = self.cli(root, env_file, "bench", "sit", "pitch-agent")  # default: every host in the config
        self.assertEqual(sat.returncode, 0, sat.stderr)
        self.assertIn("sat pitch-agent: claude", sat.stdout)
        self.assertNotIn("codex", sat.stdout, "codex already had it benched; nothing to change or re-sync")
        self.assertNotIn("aa_pitch_agent.md", names(active))
        self.assertIn("aa_pitch_agent.md", names(bench))
        self.assertEqual(self.cli(root, env_file, "check").returncode, 0)
        self.assertIn("pitch-agent", self.cli(root, env_file, "bench", "list").stdout)

    def test_unknown_agent_fails_without_touching_config(self) -> None:
        root = repo_copy(self)
        before = (root / HOST_AGENTS_CONFIG).read_text()
        result = self.cli(root, root / ".env", "bench", "play", "pitch-agnt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown agent", result.stderr)
        self.assertEqual((root / HOST_AGENTS_CONFIG).read_text(), before)


if __name__ == "__main__":
    unittest.main()
