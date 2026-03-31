from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autonomous_pipeline.schemas import RuntimeConfig


def load_runtime_config(repo_root: str | Path) -> RuntimeConfig:
    repo_root_path = Path(repo_root)
    config_path = repo_root_path / ".autonomous.json"
    if not config_path.exists():
        return RuntimeConfig()

    payload = json.loads(config_path.read_text())
    return RuntimeConfig(
        task_source=payload.get("task_source", "todo_json"),
        todo_path=payload.get("todo_path", "todo.json"),
        artifacts_dir=payload.get("artifacts_dir", "artifacts"),
        memory_url=payload.get("memory_url", "http://127.0.0.1:3377"),
        github_repo=payload.get("github_repo"),
        github_label=payload.get("github_label"),
        github_skip_labels=list(payload.get("github_skip_labels", ["blocked", "human-only"])),
        github_command=list(payload.get("github_command", ["gh"])),
        pr_base=payload.get("pr_base", "main"),
        max_tasks=int(payload.get("max_tasks", 1)),
        development_command=payload.get("development_command"),
        development_retries=int(payload.get("development_retries", 0)),
        build_command=payload.get("build_command"),
        lint_command=payload.get("lint_command"),
        test_command=payload.get("test_command"),
        ui_command=payload.get("ui_command"),
        verification_retries=int(payload.get("verification_retries", 1)),
    )


def merge_cli_overrides(config: RuntimeConfig, *, todo_path: str | None = None, memory_url: str | None = None) -> RuntimeConfig:
    data = config.to_dict()
    if todo_path is not None:
        data["todo_path"] = todo_path
    if memory_url is not None:
        data["memory_url"] = memory_url
    return RuntimeConfig(**data)
