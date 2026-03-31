from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.host_sync import (
    anacron_line,
    check_target,
    cron_line,
    discover_targets,
    feature_report,
    install_git_hooks,
    launchd_plist,
    load_dotenv,
    sync_target,
    windows_task_command,
    windows_task_xml,
)
from scripts.sync_prompt_pack import resolve_output_path


class HostSyncTest(unittest.TestCase):
    def test_load_dotenv_and_discover_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "CLAUDE_SKILL_PATH=~/fake/claude/skill.md\n"
                "CLAUDE_AGENTS_DIR=~/fake/claude/agents\n"
                "CLAUDE_INSTRUCTIONS_PATH=~/fake/claude/CLAUDE.md\n"
                "GEMINI_SKILL_PATH=/tmp/gemini/skill.md\n"
                "GEMINI_AGENTS_DIR=/tmp/gemini/agents\n"
                "GEMINI_INSTRUCTIONS_PATH=/tmp/gemini/GEMINI.md\n"
            )
            env = load_dotenv(env_path)
            targets = discover_targets(Path(tmpdir), env)
        self.assertEqual([target.name for target in targets], ["claude", "gemini"])
        self.assertTrue(all(target.instructions_path is not None for target in targets))

    def test_sync_and_check_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "pipeline").mkdir(parents=True)
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            (repo_root / "agents" / "one.md").write_text("agent one\n")
            (repo_root / "agents" / "two.md").write_text("agent two\n")

            target_root = Path(tmpdir) / "target"
            target = discover_targets(
                repo_root,
                {
                    "CLAUDE_SKILL_PATH": str(target_root / "skills" / "autonomous" / "skill.md"),
                    "CLAUDE_AGENTS_DIR": str(target_root / "agents"),
                    "CLAUDE_INSTRUCTIONS_PATH": str(target_root / "CLAUDE.md"),
                    "CLAUDE_CONFIG_SNIPPET_PATH": str(target_root / "claude-settings.snippet.json"),
                },
            )[0]

            sync_target(repo_root, target)
            status = check_target(repo_root, target)
        self.assertTrue(status.skill_in_sync)
        self.assertEqual(status.missing_agents, [])
        self.assertTrue(status.instructions_in_sync)
        self.assertTrue(status.config_snippet_in_sync)

    def test_sync_removes_stale_agent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "pipeline").mkdir(parents=True)
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            (repo_root / "agents" / "one.md").write_text("agent one\n")

            target_root = Path(tmpdir) / "target"
            target = discover_targets(
                repo_root,
                {
                    "CLAUDE_SKILL_PATH": str(target_root / "skills" / "autonomous" / "skill.md"),
                    "CLAUDE_AGENTS_DIR": str(target_root / "agents"),
                },
            )[0]
            target.agents_dir.mkdir(parents=True, exist_ok=True)
            (target.agents_dir / "stale.md").write_text("old\n")

            sync_target(repo_root, target)
            self.assertFalse((target.agents_dir / "stale.md").exists())

    def test_sync_supports_instruction_only_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "pipeline").mkdir(parents=True)
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            target = discover_targets(
                repo_root,
                {
                    "CODEX_INSTRUCTIONS_PATH": str(Path(tmpdir) / "AGENTS.md"),
                    "CODEX_CONFIG_SNIPPET_PATH": str(Path(tmpdir) / "codex-autonomous.toml"),
                },
            )[0]

            sync_target(repo_root, target)
            status = check_target(repo_root, target)

            self.assertIsNone(status.skill_in_sync)
            self.assertTrue(status.instructions_in_sync)
            self.assertTrue(status.config_snippet_in_sync)

    def test_feature_report_includes_primary_hosts(self) -> None:
        report = feature_report()
        self.assertIn("claude:", report)
        self.assertIn("codex:", report)
        self.assertIn("gemini:", report)

    def test_cron_line_contains_sync_script(self) -> None:
        line = cron_line(Path("/tmp/repo"))
        self.assertIn("sync_prompt_pack.py", line)
        self.assertIn("*/15 * * * *", line)

    def test_alternative_scheduler_lines(self) -> None:
        self.assertIn("autonomous-prompt-pack", anacron_line(Path("/tmp/repo")))
        self.assertIn("sync_prompt_pack.py", windows_task_command(Path("/tmp/repo")))
        self.assertIn("<plist version=\"1.0\">", launchd_plist(Path("/tmp/repo")))
        self.assertIn("<Task version=\"1.4\"", windows_task_xml(Path("/tmp/repo")))

    def test_install_git_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".git" / "hooks").mkdir(parents=True)
            (repo_root / "scripts").mkdir()
            (repo_root / "scripts" / "sync_prompt_pack.py").write_text("#!/usr/bin/env python3\n")
            written = install_git_hooks(repo_root)
            self.assertEqual(len(written), 2)
            for hook_path in written:
                self.assertTrue(hook_path.exists())
                self.assertIn("sync_prompt_pack.py", hook_path.read_text())

    def test_resolve_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            expected = cwd / "out.xml"
            old_cwd = Path.cwd()
            try:
                os.chdir(cwd)
                self.assertEqual(resolve_output_path("out.xml", cwd / "default").resolve(), expected.resolve())
                self.assertEqual(resolve_output_path(None, cwd / "default"), cwd / "default")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
