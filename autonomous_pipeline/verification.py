from __future__ import annotations

import json
import subprocess
from pathlib import Path

from autonomous_pipeline.schemas import RuntimeConfig, VerificationCommand, VerificationResult


def resolve_verification_commands(repo_root: str | Path, config: RuntimeConfig) -> list[VerificationCommand]:
    repo_root_path = Path(repo_root)
    commands: list[VerificationCommand] = []

    if config.build_command:
        commands.append(VerificationCommand(category="build", command=config.build_command, source="config"))
    if config.lint_command:
        commands.append(VerificationCommand(category="lint", command=config.lint_command, source="config"))
    if config.test_command:
        commands.append(VerificationCommand(category="unit", command=config.test_command, source="config"))
    if config.ui_command:
        commands.append(VerificationCommand(category="ui", command=config.ui_command, source="config"))

    if commands:
        return commands

    package_json = repo_root_path / "package.json"
    if package_json.exists():
        payload = json.loads(package_json.read_text())
        scripts = payload.get("scripts", {})
        if "build" in scripts:
            commands.append(VerificationCommand(category="build", command="npm run build", source="autodetect"))
        if "lint" in scripts:
            commands.append(VerificationCommand(category="lint", command="npm run lint", source="autodetect"))
        if "test" in scripts:
            commands.append(VerificationCommand(category="unit", command="npm test", source="autodetect"))

    pyproject = repo_root_path / "pyproject.toml"
    requirements = repo_root_path / "requirements.txt"
    if not commands and (pyproject.exists() or requirements.exists()):
        commands.append(VerificationCommand(category="lint", command="python3 -m compileall .", source="autodetect"))

    playwright_files = ["playwright.config.ts", "playwright.config.js"]
    if any((repo_root_path / name).exists() for name in playwright_files):
        commands.append(VerificationCommand(category="ui", command="npx playwright test", source="autodetect"))

    return commands


def run_verification_commands(
    repo_root: str | Path,
    artifacts_root: str | Path,
    commands: list[VerificationCommand],
    retries: int = 1,
) -> list[VerificationResult]:
    repo_root_path = Path(repo_root)
    artifacts_root_path = Path(artifacts_root)
    artifacts_root_path.mkdir(parents=True, exist_ok=True)

    results: list[VerificationResult] = []
    for command in commands:
        execution = run_command_with_retries(
            repo_root_path,
            artifacts_root_path,
            command=command.command,
            artifact_name=f"verification-{command.category}.log",
            retries=retries,
        )
        result = VerificationResult(
            category=command.category,
            command=command.command,
            status="pass" if execution["status"] == "pass" else "fail",
            artifact_path=str(execution["artifact_path"]),
            detail=f"{command.source} command passed" if execution["status"] == "pass" else "command failed after retries",
        )
        results.append(result)
    return results


def run_command_with_retries(
    repo_root: Path,
    artifacts_root: Path,
    *,
    command: str,
    artifact_name: str,
    retries: int,
) -> dict[str, str | int]:
    artifact_path = artifacts_root / artifact_name
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            command,
            cwd=repo_root,
            shell=True,
            text=True,
            capture_output=True,
        )
        output = (
            f"$ {command}\n"
            f"attempt: {attempt}/{attempts}\n"
            f"exit_code: {completed.returncode}\n\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}\n"
        )
        artifact_path.write_text(output)
        if completed.returncode == 0:
            return {
                "status": "pass",
                "artifact_path": str(artifact_path),
                "detail": "command passed",
                "attempts": attempt,
            }

    return {
        "status": "fail",
        "artifact_path": str(artifact_path),
        "detail": "command failed after retries",
        "attempts": attempts,
    }
