from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.host_sync import (
    HOST_SPECS,
    HostTarget,
    anacron_line,
    check_target,
    cron_line,
    discover_targets,
    feature_report,
    install_git_hooks,
    install_from_git_command,
    launchd_plist,
    load_dotenv,
    reconcile_agent_inventory,
    repo_agent_sources,
    rendered_agent_filename,
    render_agent_prompt,
    render_host_instructions,
    sync_agents_dir,
    sync_target,
    update_checkout_from_git,
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

            result = sync_target(repo_root, target)
            self.assertTrue(result, "sync_target should return True for a plain target")
            status = check_target(repo_root, target)
        self.assertTrue(status.skill_in_sync)
        self.assertEqual(status.missing_agents, [])
        self.assertTrue(status.instructions_in_sync)
        self.assertTrue(status.config_snippet_in_sync)

    def test_sync_skips_target_inside_git_worktree(self) -> None:
        """A host target whose paths sit inside a git checkout is owned by that
        repo, not by this sync. sync_target() must skip it and not create a
        dirty tree. Regression for project_opt_anvil_overlay_recurrence."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "pipeline").mkdir(parents=True)
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            (repo_root / "agents" / "one.md").write_text("agent one\n")

            # Mirror the real /opt/anvil case: the git target already has
            # committed copies of the sync-destination files (CLAUDE.md,
            # pipeline/autonomous.md, agents/*.md). Sync must NOT touch
            # them and create a dirty tree.
            git_target_root = Path(tmpdir) / "git_target"
            (git_target_root / "pipeline").mkdir(parents=True)
            (git_target_root / "agents").mkdir(parents=True)
            (git_target_root / "pipeline" / "autonomous.md").write_text("original\n")
            (git_target_root / "agents" / "one.md").write_text("original agent\n")
            (git_target_root / "CLAUDE.md").write_text("original instructions\n")
            subprocess.run(
                ["git", "init", "-q"], cwd=str(git_target_root), check=True
            )
            subprocess.run(
                ["git", "-C", str(git_target_root), "add", "-A"], check=True
            )
            subprocess.run(
                [
                    "git", "-C", str(git_target_root),
                    "-c", "user.email=test@test", "-c", "user.name=test",
                    "commit", "-q", "-m", "initial",
                ],
                check=True,
            )

            plain_target_root = Path(tmpdir) / "plain_target"

            targets = discover_targets(
                repo_root,
                {
                    "CLAUDE_SKILL_PATH": str(git_target_root / "pipeline" / "autonomous.md"),
                    "CLAUDE_AGENTS_DIR": str(git_target_root / "agents"),
                    "CLAUDE_INSTRUCTIONS_PATH": str(git_target_root / "CLAUDE.md"),
                    "CODEX_SKILL_PATH": str(plain_target_root / "skills" / "autonomous" / "skill.md"),
                    "CODEX_AGENTS_DIR": str(plain_target_root / "agents"),
                    "CODEX_INSTRUCTIONS_PATH": str(plain_target_root / "AGENTS.md"),
                },
            )

            sync_results = {target.name: sync_target(repo_root, target) for target in targets}

            # Git-managed target must be skipped (returns False)
            self.assertFalse(
                sync_results["claude"],
                "sync_target should return False for a git-managed target",
            )
            # Plain directory target must be synced (returns True)
            self.assertTrue(
                sync_results["codex"],
                "sync_target should return True for a plain target",
            )

            # The git-tracked target must be UNTOUCHED — the tracked files
            # retain their original content, sync did not overwrite them
            # (that would cause the dirty-tree state that blocks anvil update).
            self.assertEqual(
                (git_target_root / "pipeline" / "autonomous.md").read_text(),
                "original\n",
            )
            self.assertEqual(
                (git_target_root / "agents" / "one.md").read_text(),
                "original agent\n",
            )
            self.assertEqual(
                (git_target_root / "CLAUDE.md").read_text(),
                "original instructions\n",
            )
            # And the git repo must be clean (no modified/untracked files).
            status = subprocess.run(
                ["git", "-C", str(git_target_root), "status", "--porcelain"],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(status.stdout, "", f"Sync left git target dirty:\n{status.stdout}")

            # The plain-directory target must receive the full sync.
            self.assertTrue((plain_target_root / "skills" / "autonomous" / "skill.md").exists())
            self.assertTrue((plain_target_root / "agents").exists())
            self.assertTrue((plain_target_root / "AGENTS.md").exists())

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

    def test_sync_agents_dir_writes_rendered_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            target_dir = Path(tmpdir) / "target"
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "agents" / "core-agent.md").write_text("---\nname: core-agent\n---\n\nBody\n")
            target_dir.mkdir()
            (target_dir / "core-agent.md").write_text("legacy\n")

            sync_agents_dir(repo_root, target_dir)

            self.assertFalse((target_dir / "core-agent.md").exists())
            rendered = target_dir / "aa_core_agent.md"
            self.assertTrue(rendered.exists())
            self.assertIn("name: aa_core_agent", rendered.read_text())

    def test_agent_sources_include_curated_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "agent_bundles" / "financial-services" / "agents").mkdir(parents=True)
            (repo_root / "agents" / "core.md").write_text("core\n")
            bundle_agent = repo_root / "agent_bundles" / "financial-services" / "agents" / "earnings-reviewer.md"
            bundle_agent.write_text("financial\n")

            sources = repo_agent_sources(repo_root)

        self.assertEqual([source.name for source in sources], ["core.md", "earnings-reviewer.md"])

    def test_agents_install_with_aa_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "earnings-reviewer.md"
            source.write_text("---\nname: earnings-reviewer\ndescription: demo\n---\n\nBody\n")

            self.assertEqual(rendered_agent_filename(source), "aa_earnings_reviewer.md")
            self.assertIn("name: aa_earnings_reviewer", render_agent_prompt(source))
            self.assertIn("Body", render_agent_prompt(source))

    def test_reconcile_agent_inventory_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            target_dir = Path(tmpdir) / "target"
            (repo_root / "agents").mkdir(parents=True)
            target_dir.mkdir()
            (repo_root / "agents" / "core.md").write_text("---\nname: core\n---\n\nrepo\n")
            (target_dir / "aa_core.md").write_text("---\nname: aa_core\n---\n\ntarget\n")
            (target_dir / "host-only.md").write_text("host\n")

            report = reconcile_agent_inventory(repo_root, target_dir)

        self.assertEqual(report.repo_count, 1)
        self.assertEqual(report.target_count, 2)
        self.assertEqual(report.missing_from_repo, ["host-only.md"])
        self.assertEqual(report.missing_from_target, [])
        self.assertEqual(report.diverged, ["aa_core.md"])

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

    def test_primary_hosts_share_updated_global_protocols(self) -> None:
        repo_root = Path("/Users/mz/_CODING/autonomous_agents_mds")
        for host in ("claude", "codex", "gemini", "anvil"):
            spec = HOST_SPECS[host]
            instructions = render_host_instructions(
                repo_root,
                HostTarget(
                    name=host,
                    skill_path=Path(f"/tmp/{host}/skills/autonomous/skill.md"),
                    agents_dir=Path(f"/tmp/{host}/agents"),
                ),
            )

            self.assertIn(f"# {spec.instruction_filename}", instructions)
            self.assertIn("YOU ARE AN ORCHESTRATOR OF DEVELOPMENT TEAMS AND AGENTS.", instructions)
            self.assertIn("ALWAYS DISPATCH AGENTS IN PERSONAL WORKTREE", instructions)
            self.assertIn("Automate and make everything easier as you go", instructions)
            self.assertIn("if hooks are not present, create them", instructions)
            self.assertIn("Session-handoff markers (agent-agnostic)", instructions)
            self.assertIn("Git distribution source: `https://github.com/metazen11/autonomous-agents.git`", instructions)
            self.assertIn("Prompt pack source: `~/_CODING/autonomous_agents_mds/`", instructions)
            self.assertIn("Prompt pack sync: `cd ~/_CODING/autonomous_agents_mds", instructions)
            # Installed files live outside the repo; a relative docs/ pointer dangles there.
            self.assertNotIn("`docs/contract-reference.md`", instructions)
            self.assertIn("`~/_CODING/autonomous_agents_mds/docs/contract-reference.md`", instructions)

    def test_install_from_git_command_uses_repo_as_distribution_source(self) -> None:
        command = install_from_git_command(
            repo_url="https://github.com/metazen11/autonomous-agents.git",
            install_dir=Path("/Users/mz/_CODING/autonomous_agents_mds"),
        )

        self.assertIn("git clone", command)
        self.assertIn("https://github.com/metazen11/autonomous-agents.git", command)
        self.assertIn("git pull --ff-only origin", command)
        self.assertIn("main", command)
        self.assertIn("scripts/sync_prompt_pack.py sync", command)

    def test_update_checkout_from_git_clones_or_fast_forwards(self) -> None:
        calls: list[list[str]] = []

        def runner(command, **kwargs):
            calls.append(command)
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            install_dir = Path(tmpdir) / "autonomous_agents_mds"
            update_checkout_from_git(
                repo_url="https://github.com/metazen11/autonomous-agents.git",
                install_dir=install_dir,
                runner=runner,
            )

            self.assertEqual(
                calls,
                [
                    [
                        "git",
                        "clone",
                        "--branch",
                        "main",
                        "https://github.com/metazen11/autonomous-agents.git",
                        str(install_dir),
                    ]
                ],
            )

            calls.clear()
            (install_dir / ".git").mkdir(parents=True)
            update_checkout_from_git(
                repo_url="https://github.com/metazen11/autonomous-agents.git",
                install_dir=install_dir,
                runner=runner,
            )

        self.assertEqual(calls[0][:5], ["git", "-C", str(install_dir), "fetch", "origin"])
        self.assertIn(["git", "-C", str(install_dir), "checkout", "main"], calls)
        self.assertIn(["git", "-C", str(install_dir), "pull", "--ff-only", "origin", "main"], calls)

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
