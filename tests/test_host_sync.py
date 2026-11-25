from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autonomous_pipeline.host_sync import (
    HOST_SPECS,
    HostTarget,
    _host_sync_lock,
    _host_sync_lock_available,
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
    def test_render_embeds_and_refreshes_contract_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "agents").mkdir()
            guide = root / "agents/AGENT_AGNOSTIC_GUIDE.md"
            guide.write_text("# Shared rules\nFIRST CONTRACT\n")
            source = root / "bundled.md"
            source.write_text("---\nname: bundled\ndescription: demo\nmodel: local\n---\n# Agent\nROLE BODY\n")
            rendered = render_agent_prompt(source, repo_root=root)
            self.assertIn("model: local", rendered)
            self.assertIn("ROLE BODY", rendered)
            self.assertIn(guide.read_text().strip(), rendered)
            source = root / rendered_agent_filename(source)
            source.write_text(rendered)
            self.assertEqual(rendered_agent_filename(source), "aa_bundled.md")
            self.assertEqual(render_agent_prompt(source, repo_root=root), rendered)
            guide.write_text("# Shared rules\nREVISED CONTRACT\n")
            refreshed = render_agent_prompt(source, repo_root=root)
            self.assertNotIn("FIRST CONTRACT", refreshed)
            self.assertEqual(refreshed.count("REVISED CONTRACT"), 1)
            self.assertEqual(refreshed.count("BEGIN GENERATED AGENT CONTRACT"), 1)

    def test_render_uses_canonical_guide_for_every_real_specialist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        guide = root / "agents/AGENT_AGNOSTIC_GUIDE.md"
        for source in repo_agent_sources(root):
            with self.subTest(source=source):
                rendered = render_agent_prompt(source, repo_root=root)
                if source == guide:
                    self.assertEqual(rendered, guide.read_text())
                else:
                    self.assertIn(guide.read_text().strip(), rendered)
                    self.assertEqual(rendered.count("BEGIN GENERATED AGENT CONTRACT"), 1)

    def test_missing_contract_fails_before_agent_directory_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/core.md").write_text("---\nname: core\ndescription: demo\n---\nBody\n")
            target = Path(tmpdir) / "installed"
            target.mkdir()
            previous = target / "old.md"
            previous.write_text("preserve me")
            with self.assertRaisesRegex(ValueError, "missing canonical"):
                sync_agents_dir(root, target)
            self.assertEqual(previous.read_text(), "preserve me")
            self.assertEqual(list(target.iterdir()), [previous])

    def test_bundle_local_contract_cannot_override_canonical_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "agents").mkdir()
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("CANONICAL")
            bundle = root / "agent_bundles/example/agents"
            bundle.mkdir(parents=True)
            (bundle / "AGENT_AGNOSTIC_GUIDE.md").write_text("WRONG GUIDE")
            source = bundle / "example.md"
            source.write_text("---\nname: example\ndescription: demo\n---\nBody")
            rendered = render_agent_prompt(source, repo_root=root)
            self.assertIn("CANONICAL", rendered)
            self.assertNotIn("WRONG GUIDE", rendered)

    def test_malformed_generated_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "agents").mkdir()
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("CANONICAL")
            source = root / "agent.md"
            for block in (
                "<!-- BEGIN GENERATED AGENT CONTRACT -->",
                "<!-- END GENERATED AGENT CONTRACT -->",
                "<!-- BEGIN GENERATED AGENT CONTRACT -->\nx\n<!-- END GENERATED AGENT CONTRACT -->\nafter",
            ):
                source.write_text("---\nname: agent\ndescription: demo\n---\n" + block)
                with self.assertRaises(ValueError):
                    render_agent_prompt(source, repo_root=root)

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
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            (repo_root / "skills" / "extra").mkdir(parents=True)
            (repo_root / "skills" / "extra" / "skill.md").write_text("extra skill\n")
            (repo_root / "skills" / "reconcile").mkdir(parents=True)
            (repo_root / "skills" / "reconcile" / "skill.md").write_text("reuse existing checkout\n")
            (repo_root / "skills" / "reconcile" / "scripts").mkdir()
            (repo_root / "skills" / "reconcile" / "scripts" / "reconcile_lock.sh").write_text("#!/bin/sh\n")
            (repo_root / "agents" / "one.md").write_text("---\nname: one\ndescription: demo\n---\nagent one\n")
            (repo_root / "agents" / "two.md").write_text("---\nname: two\ndescription: demo\n---\nagent two\n")

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
            self.assertEqual((target.skill_path.parent.parent / "extra" / "skill.md").read_text(), "extra skill\n")
            self.assertEqual(
                (target.skill_path.parent.parent / "reconcile" / "skill.md").read_text(),
                "reuse existing checkout\n",
            )
            self.assertTrue((target.skill_path.parent.parent / "reconcile/scripts/reconcile_lock.sh").is_file())
            status = check_target(repo_root, target)
        self.assertTrue(status.skill_in_sync)
        self.assertEqual(status.missing_agents, [])
        self.assertEqual(status.missing_skill_files, [])
        self.assertTrue(status.instructions_in_sync)
        self.assertTrue(status.config_snippet_in_sync)

    def test_benched_legacy_toml_moves_byte_for_byte_and_unrelated_profiles_stay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            (root / "agents/quiet-agent.md").write_text("---\nname: quiet-agent\ndescription: demo\n---\nbody\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["quiet-agent"]}}))
            active = Path(tmpdir) / "host/agents"
            active.mkdir(parents=True)
            legacy_bytes = b"# legacy profile\r\n[model]\r\nname = 'old'\x00\xff"
            (active / "quiet-agent.toml").write_bytes(legacy_bytes)
            unrelated_bytes = b"[model]\nname = 'keep'\n"
            (active / "unrelated.toml").write_bytes(unrelated_bytes)

            sync_agents_dir(root, active, "codex")

            self.assertFalse((active / "quiet-agent.toml").exists())
            self.assertEqual((Path(tmpdir) / "host/agents-bench/quiet-agent.toml").read_bytes(), legacy_bytes)
            self.assertEqual((active / "unrelated.toml").read_bytes(), unrelated_bytes)

    def test_check_reports_active_legacy_toml_and_sync_conflict_is_preflighted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            (root / "agents/quiet-agent.md").write_text("---\nname: quiet-agent\ndescription: demo\n---\nbody\n")
            (root / "pipeline").mkdir()
            (root / "pipeline/autonomous.md").write_text("new skill\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["quiet-agent"]}}))
            host = Path(tmpdir) / "host"
            agents = host / "agents"
            agents.mkdir(parents=True)
            active_toml = agents / "quiet-agent.toml"
            active_toml.write_text("legacy")
            destination = host / "agents-bench/quiet-agent.toml"
            destination.parent.mkdir()
            destination.write_text("collision")
            skill = host / "skill.md"
            skill.write_text("preserve")
            target = HostTarget(name="codex", agents_dir=agents, skill_path=skill)

            status = check_target(root, target)
            self.assertIn("quiet-agent.toml(active)", status.bench_problems)
            with self.assertRaisesRegex(ValueError, "destination already exists"):
                sync_target(root, target)
            self.assertEqual(skill.read_text(), "preserve")
            self.assertEqual(active_toml.read_text(), "legacy")
            self.assertEqual(destination.read_text(), "collision")

    def test_benched_legacy_toml_symlink_fails_before_other_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            (root / "agents/quiet-agent.md").write_text("---\nname: quiet-agent\ndescription: demo\n---\nbody\n")
            (root / "pipeline").mkdir()
            (root / "pipeline/autonomous.md").write_text("new skill\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["quiet-agent"]}}))
            host = Path(tmpdir) / "host"
            agents = host / "agents"
            agents.mkdir(parents=True)
            outside = Path(tmpdir) / "outside.toml"
            outside.write_text("preserve")
            (agents / "quiet-agent.toml").symlink_to(outside)
            skill = host / "skill.md"
            skill.write_text("preserve")

            with self.assertRaisesRegex(ValueError, "regular file"):
                sync_target(root, HostTarget(name="codex", agents_dir=agents, skill_path=skill))
            self.assertEqual(skill.read_text(), "preserve")
            self.assertTrue((agents / "quiet-agent.toml").is_symlink())
            self.assertEqual(outside.read_text(), "preserve")

    def test_benched_legacy_toml_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            (root / "agents/quiet-agent.md").write_text("---\nname: quiet-agent\ndescription: demo\n---\nbody\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["quiet-agent"]}}))
            agents = Path(tmpdir) / "host/agents"
            (agents / "quiet-agent.toml").mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "regular file"):
                sync_agents_dir(root, agents, "codex")
            self.assertTrue((agents / "quiet-agent.toml").is_dir())

    def test_benched_legacy_tomls_reject_symlink_destination_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            (root / "agents/quiet-agent.md").write_text("---\nname: quiet-agent\ndescription: demo\n---\nbody\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["quiet-agent"]}}))
            host = Path(tmpdir) / "host"
            agents = host / "agents"
            agents.mkdir(parents=True)
            (agents / "quiet-agent.toml").write_text("legacy")
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            (host / "agents-bench").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "destination parent"):
                sync_agents_dir(root, agents, "codex")
            self.assertEqual((agents / "quiet-agent.toml").read_text(), "legacy")
            self.assertEqual(list(outside.iterdir()), [])

    def test_benched_legacy_toml_moves_roll_back_after_later_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            for name in ("first", "second"):
                (root / f"agents/{name}.md").write_text(f"---\nname: {name}\ndescription: demo\n---\nbody\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["first", "second"]}}))
            agents = Path(tmpdir) / "host/agents"
            agents.mkdir(parents=True)
            expected = {}
            for name in ("first", "second"):
                expected[name] = f"{name} profile\n".encode()
                (agents / f"{name}.toml").write_bytes(expected[name])

            original_unlink = Path.unlink

            def fail_second_source(path: Path, *args, **kwargs):
                if path == agents / "second.toml":
                    (agents / "first.toml").write_bytes(b"concurrent replacement\n")
                    raise OSError("simulated source unlink failure")
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_second_source):
                with self.assertRaisesRegex(OSError, "rollback conflict"):
                    sync_agents_dir(root, agents, "codex")

            self.assertEqual((agents / "first.toml").read_bytes(), b"concurrent replacement\n")
            self.assertEqual((agents.parent / "agents-bench/first.toml").read_bytes(), expected["first"])
            self.assertEqual((agents / "second.toml").read_bytes(), expected["second"])
            self.assertFalse((agents.parent / "agents-bench/second.toml").exists())

    def test_benched_legacy_toml_source_symlink_replacement_fails_identity_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            (root / "agents").mkdir(parents=True)
            (root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("canonical\n")
            (root / "agents/quiet-agent.md").write_text("---\nname: quiet-agent\ndescription: demo\n---\nbody\n")
            (root / "host_agents.json").write_text(json.dumps({"codex": {"include": "all", "exclude": ["quiet-agent"]}}))
            agents = Path(tmpdir) / "host/agents"
            agents.mkdir(parents=True)
            active = agents / "quiet-agent.toml"
            active.write_text("original profile\n")
            original = Path(tmpdir) / "original.toml"
            target = Path(tmpdir) / "target.toml"
            target.write_text("do not link this target\n")
            real_link = os.link

            def replace_with_symlink(source, destination, *, follow_symlinks=True):
                active.rename(original)
                active.symlink_to(target)
                return real_link(source, destination, follow_symlinks=follow_symlinks)

            with patch("autonomous_pipeline.host_sync.os.link", replace_with_symlink):
                with self.assertRaisesRegex(OSError, "rollback conflict"):
                    sync_agents_dir(root, agents, "codex")

            self.assertEqual(original.read_text(), "original profile\n")
            self.assertTrue(active.is_symlink())
            self.assertEqual(target.read_text(), "do not link this target\n")

    def test_host_sync_lock_serializes_independent_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "host/agents"
            probe = (
                "from pathlib import Path; "
                "from autonomous_pipeline.host_sync import _host_sync_lock_available; "
                "print(_host_sync_lock_available(Path(__import__('sys').argv[1])))"
            )
            with _host_sync_lock(target):
                child = subprocess.run(
                    [sys.executable, "-c", probe, str(target)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(child.stdout.strip(), "False")
            child = subprocess.run(
                [sys.executable, "-c", probe, str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(child.stdout.strip(), "True")

    def test_sync_skips_target_inside_git_worktree(self) -> None:
        """A host target whose paths sit inside a git checkout is owned by that
        repo, not by this sync. sync_target() must skip it and not create a
        dirty tree. Regression for project_opt_anvil_overlay_recurrence."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "pipeline").mkdir(parents=True)
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            (repo_root / "agents" / "one.md").write_text("---\nname: one\ndescription: demo\n---\nagent one\n")

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
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
            (repo_root / "pipeline" / "autonomous.md").write_text("skill content\n")
            (repo_root / "agents" / "one.md").write_text("---\nname: one\ndescription: demo\n---\nagent one\n")

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
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
            (repo_root / "agents" / "core-agent.md").write_text("---\nname: core-agent\ndescription: demo\n---\n\nBody\n")
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
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
            (repo_root / "agent_bundles" / "financial-services" / "agents").mkdir(parents=True)
            (repo_root / "agents" / "core.md").write_text("---\nname: core\ndescription: demo\n---\ncore\n")
            bundle_agent = repo_root / "agent_bundles" / "financial-services" / "agents" / "earnings-reviewer.md"
            bundle_agent.write_text("---\nname: earnings-reviewer\ndescription: demo\n---\nfinancial\n")

            sources = repo_agent_sources(repo_root)

        self.assertEqual([source.name for source in sources], ["AGENT_AGNOSTIC_GUIDE.md", "core.md", "earnings-reviewer.md"])

    def test_agents_install_with_aa_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "agents").mkdir()
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("CONTRACT")
            source = repo_root / "earnings-reviewer.md"
            source.write_text("---\nname: earnings-reviewer\ndescription: demo\n---\n\nBody\n")

            self.assertEqual(rendered_agent_filename(source), "aa_earnings_reviewer.md")
            self.assertIn("name: aa_earnings_reviewer", render_agent_prompt(source, repo_root=repo_root))
            self.assertIn("Body", render_agent_prompt(source, repo_root=repo_root))

    def test_reconcile_agent_inventory_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            target_dir = Path(tmpdir) / "target"
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
            target_dir.mkdir()
            (repo_root / "agents" / "core.md").write_text("---\nname: core\ndescription: demo\n---\n\nrepo\n")
            (target_dir / "aa_core.md").write_text("---\nname: aa_core\ndescription: demo\n---\n\ntarget\n")
            (target_dir / "host-only.md").write_text("host\n")

            report = reconcile_agent_inventory(repo_root, target_dir)

        self.assertEqual(report.repo_count, 2)
        self.assertEqual(report.target_count, 2)
        self.assertEqual(report.missing_from_repo, ["host-only.md"])
        self.assertEqual(report.missing_from_target, ["AGENT_AGNOSTIC_GUIDE.md"])
        self.assertEqual(report.diverged, ["aa_core.md"])

    def test_sync_supports_instruction_only_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            (repo_root / "pipeline").mkdir(parents=True)
            (repo_root / "agents").mkdir(parents=True)
            (repo_root / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\nfixture rules\n")
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

    def test_installed_reconcile_helper_runs_from_a_different_target_repository(self) -> None:
        pack_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "pack"
            (source / "pipeline").mkdir(parents=True)
            (source / "agents").mkdir()
            (source / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Shared contract\n")
            (source / "pipeline/autonomous.md").write_text("skill content\n")
            reconcile = source / "skills/reconcile"
            (reconcile / "scripts").mkdir(parents=True)
            (reconcile / "skill.md").write_text("bundled lock helper\n")
            for name in ("reconcile_lock.sh", "reconcile_lock.py"):
                (reconcile / "scripts" / name).write_bytes(
                    (pack_root / "skills/reconcile/scripts" / name).read_bytes()
                )
            target_home = root / "installed"
            target = HostTarget(
                name="codex",
                skill_path=target_home / "skills/autonomous/skill.md",
                agents_dir=target_home / "agents",
            )

            sync_target(source, target)
            helper = target_home / "skills/reconcile/scripts/reconcile_lock.sh"
            self.assertEqual(check_target(source, target).missing_skill_files, [])

            other_repo = root / "other-repo"
            other_repo.mkdir()
            subprocess.run(["git", "init", "-b", "work/reconcile-helper-test"], cwd=other_repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=other_repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=other_repo, check=True)
            (other_repo / "README.md").write_text("fixture\n")
            subprocess.run(["git", "add", "README.md"], cwd=other_repo, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=other_repo, check=True, capture_output=True)

            acquired = subprocess.run(
                [str(helper), "acquire", "fixture-task", str(other_repo), "work/reconcile-helper-test"],
                cwd=other_repo, check=True, capture_output=True, text=True,
            )
            self.assertIn("LOCK ACQUIRED", acquired.stdout)
            released = subprocess.run(
                [str(helper), "release", "fixture-task", str(other_repo), "work/reconcile-helper-test"],
                cwd=other_repo, check=True, capture_output=True, text=True,
            )
            self.assertIn("LOCK RELEASED", released.stdout)

    def test_sync_skips_when_bundled_helper_destination_is_git_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "pack"
            (source / "pipeline").mkdir(parents=True)
            (source / "agents").mkdir()
            (source / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Contract\n")
            (source / "pipeline/autonomous.md").write_text("skill content\n")
            reconcile = source / "skills/reconcile"
            (reconcile / "scripts").mkdir(parents=True)
            (reconcile / "skill.md").write_text("reconcile\n")
            (reconcile / "scripts/reconcile_lock.py").write_text("canonical helper\n")

            target_repo = root / "target-repo"
            target_repo.mkdir()
            support = target_repo / "skills/reconcile/scripts/reconcile_lock.py"
            support.parent.mkdir(parents=True)
            support.write_text("target-owned helper\n")
            subprocess.run(["git", "init", "-q", "-b", "work/target"], cwd=target_repo, check=True)
            subprocess.run(["git", "add", "skills/reconcile/scripts/reconcile_lock.py"], cwd=target_repo, check=True)
            subprocess.run(
                ["git", "-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "-q", "-m", "target helper"],
                cwd=target_repo, check=True,
            )
            target = HostTarget(
                name="codex",
                skill_path=target_repo / "skills/autonomous/skill.md",
                agents_dir=target_repo / "agents",
            )

            self.assertFalse(sync_target(source, target))
            self.assertEqual(support.read_text(), "target-owned helper\n")
            self.assertFalse(target.skill_path.exists())

    def test_sync_rejects_bundled_helper_symlink_before_any_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "pack"
            (source / "pipeline").mkdir(parents=True)
            (source / "agents").mkdir()
            (source / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Contract\n")
            (source / "pipeline/autonomous.md").write_text("skill content\n")
            reconcile = source / "skills/reconcile"
            (reconcile / "scripts").mkdir(parents=True)
            (reconcile / "skill.md").write_text("reconcile\n")
            (reconcile / "scripts/reconcile_lock.py").write_text("canonical helper\n")

            host = root / "host"
            installed = host / "skills/reconcile/scripts"
            installed.mkdir(parents=True)
            outside = root / "outside.py"
            outside.write_text("preserve\n")
            (installed / "reconcile_lock.py").symlink_to(outside)
            target = HostTarget(
                name="codex",
                skill_path=host / "skills/autonomous/skill.md",
                agents_dir=host / "agents",
            )

            with self.assertRaisesRegex(ValueError, "non-regular destination"):
                sync_target(source, target)
            self.assertEqual(outside.read_text(), "preserve\n")
            self.assertFalse(target.skill_path.exists())
            self.assertFalse(target.agents_dir.exists())

    def test_sync_rejects_bundled_helper_parent_symlink_before_any_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "pack"
            (source / "pipeline").mkdir(parents=True)
            (source / "agents").mkdir()
            (source / "agents/AGENT_AGNOSTIC_GUIDE.md").write_text("# Contract\n")
            (source / "pipeline/autonomous.md").write_text("skill content\n")
            reconcile = source / "skills/reconcile"
            (reconcile / "scripts").mkdir(parents=True)
            (reconcile / "skill.md").write_text("reconcile\n")
            (reconcile / "scripts/reconcile_lock.py").write_text("canonical helper\n")

            host = root / "host"
            skill_root = host / "skills"
            (skill_root / "reconcile").mkdir(parents=True)
            outside_dir = root / "outside"
            outside_dir.mkdir()
            (outside_dir / "reconcile_lock.py").write_text("canonical helper\n")
            (skill_root / "reconcile/scripts").symlink_to(outside_dir, target_is_directory=True)
            target = HostTarget(
                name="codex",
                skill_path=Path("host/skills/autonomous/skill.md"),
                agents_dir=Path("host/agents"),
            )

            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                self.assertEqual(
                    check_target(source, target).missing_skill_files,
                    ["reconcile/scripts/reconcile_lock.py"],
                )
                with self.assertRaisesRegex(ValueError, "unsafe parent"):
                    sync_target(source, target)
                self.assertFalse(target.skill_path.exists())
                self.assertFalse(target.agents_dir.exists())
            finally:
                os.chdir(previous_cwd)

    def test_feature_report_includes_primary_hosts(self) -> None:
        report = feature_report()
        self.assertIn("claude:", report)
        self.assertIn("codex:", report)
        self.assertIn("gemini:", report)

    def test_primary_hosts_share_updated_global_protocols(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
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
            self.assertIn("prioritize only within the owner's approved queue", instructions)
            self.assertIn("Reuse the assigned existing worktree; do not create a new one by default", instructions)
            self.assertIn("carry the latest explicit owner instruction across sessions and worktrees", instructions)
            self.assertIn("Continue only through the already approved queue", instructions)
            self.assertIn("Stop when it is empty, at a decision fork, or on a concrete blocker", instructions)
            self.assertIn("Queue membership alone does not authorize live, money, production-deploy, or credential actions", instructions)
            self.assertIn("Automate and make everything easier as you go", instructions)
            self.assertIn("if hooks are not present, create them", instructions)
            self.assertIn("Session-handoff markers (agent-agnostic)", instructions)
            self.assertIn("Git distribution source: `https://github.com/metazen11/autonomous-agents.git`", instructions)
            self.assertIn("Prompt pack source: `~/_CODING/autonomous_agents_mds/`", instructions)
            self.assertIn("Prompt pack sync: `cd ~/_CODING/autonomous_agents_mds", instructions)
            # Single-trunk is a positive per-repo opt-in; fail closed; no dev creation.
            self.assertIn('.reconcile-gate.json', instructions)
            self.assertIn("review: APPROVE <sha>", instructions)
            self.assertIn("audit: PASS <sha>", instructions)
            self.assertIn("required_approving_review_count == 0", instructions)
            self.assertIn("never creates `dev`", instructions)
            self.assertIn("The ORCHESTRATING agent", instructions)
            self.assertNotIn("permissions.admin", instructions)
            self.assertIn("--match-head-commit", instructions)
            self.assertIn("An unprotected trunk is human-gated", instructions)
            rule = instructions[instructions.index("**Self-merge permission"):].split("\n")[0]
            self.assertIn("agent-gate", rule)
            self.assertIn(".github/rulesets/**", instructions)
            self.assertIn("Operator approval is still required", instructions)
            self.assertNotIn("= fast-path", instructions)
            self.assertNotIn("counts as", instructions.split("**Self-merge permission")[1].split("**MUST NOT")[0])
            self.assertNotIn("reconciler MUST create `dev`", instructions)
            self.assertNotIn("Pre-live delivery mode", instructions)
            # Installed files live outside the repo; a relative docs/ pointer dangles.
            self.assertNotIn("`docs/contract-reference.md`", instructions)
            self.assertIn("`~/_CODING/autonomous_agents_mds/docs/contract-reference.md`", instructions)

    def test_host_agnostic_pipeline_carries_bounded_autonomy(self) -> None:
        root = Path(__file__).resolve().parents[1]
        prompt = (root / "pipeline/autonomous-spec-host-agnostic.md").read_text()
        for rule in (
            "Work through approved tasks in sequence without asking for the same approval again",
            "Stop when the approved queue is empty, at a real decision fork, or at a concrete blocker",
            "Do not invent adjacent tasks",
            "Queue membership alone does not authorize work touching live systems, money, production deployments, or credentials",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, prompt)

    def test_specialists_do_not_require_fresh_worktrees(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in (
            root / "agents/regime-filter-tuner.md",
            root / "agents/strategy-honesty-checker.md",
        ):
            prompt = path.read_text()
            with self.subTest(path=path.name):
                self.assertIn("Use the task's assigned existing checkout", prompt)
                self.assertNotIn("Each research session gets its own worktree. Never reuse.", prompt)
                self.assertNotIn("Each verification session gets its own worktree. Never reuse.", prompt)

    def test_reconcile_skill_never_creates_a_worktree_by_default(self) -> None:
        root = Path(__file__).resolve().parents[1]
        prompt = (root / "skills/reconcile/skill.md").read_text()
        self.assertIn("Do not automatically run `git worktree add`", prompt)
        self.assertIn("explicit owner request", prompt)
        self.assertIn("hard cap of five", prompt)
        self.assertIn("bundled `scripts/reconcile_lock.sh acquire <task-id> <assigned-checkout> <assigned-branch>`", prompt)
        self.assertIn("bundled helper using `scripts/reconcile_lock.sh release <task-id> <assigned-checkout> <assigned-branch>`", prompt)
        self.assertIn("does not authenticate the prompt author", prompt)
        self.assertIn("The originating issue or dispatch must name the exact checkout and working branch", prompt)
        self.assertIn("If the assigned checkout is dirty, ownership is unclear", prompt)
        autonomous = (root / "pipeline/autonomous.md").read_text()
        self.assertIn("Reconcile checkout and lock assigned", autonomous)
        self.assertIn("bundled `scripts/reconcile_lock.sh acquire <task-id> <assigned-checkout> <assigned-branch>`", autonomous)
        self.assertTrue((root / "scripts/reconcile_lock.sh").is_file())

    def test_no_hardcoded_dev_ref_in_agent_docs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for sub in ("agents", "pipeline", "docs"):
            for f in (root / sub).rglob("*.md"):
                # Dispatches are dated audit records and may name the then-current
                # integration ref; this guard applies to reusable agent guidance.
                if "superpowers" in f.parts or (sub == "docs" and "dispatches" in f.parts):
                    continue
                self.assertNotIn("origin/dev", f.read_text(), str(f))

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
