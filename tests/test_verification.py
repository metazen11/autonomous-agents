from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.schemas import RuntimeConfig
from autonomous_pipeline.verification import resolve_verification_commands, run_verification_commands


class VerificationTest(unittest.TestCase):
    def test_resolve_commands_from_config(self) -> None:
        config = RuntimeConfig(
            build_command="echo build",
            lint_command="echo lint",
            test_command="echo test",
            ui_command="echo ui",
        )
        commands = resolve_verification_commands(".", config)
        self.assertEqual([command.category for command in commands], ["build", "lint", "unit", "ui"])

    def test_resolve_commands_from_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "package.json").write_text(
                json.dumps({"scripts": {"build": "vite build", "lint": "eslint .", "test": "vitest"}})
            )
            commands = resolve_verification_commands(repo_root, RuntimeConfig())
        self.assertEqual([command.category for command in commands], ["build", "lint", "unit"])

    def test_run_verification_commands_captures_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            artifacts = repo_root / "artifacts"
            results = run_verification_commands(
                repo_root,
                artifacts,
                commands=[
                    type("Cmd", (), {"category": "build", "command": "python3 -c \"print('ok')\"", "source": "config"})(),
                    type("Cmd", (), {"category": "lint", "command": "python3 -c \"import sys; sys.exit(1)\"", "source": "config"})(),
                ],
                retries=0,
            )
            self.assertEqual(results[0].status, "pass")
            self.assertEqual(results[1].status, "fail")
            self.assertTrue(Path(results[0].artifact_path).exists())
            self.assertTrue(Path(results[1].artifact_path).exists())


if __name__ == "__main__":
    unittest.main()
