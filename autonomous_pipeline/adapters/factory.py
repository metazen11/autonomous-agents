from __future__ import annotations

from pathlib import Path

from autonomous_pipeline.adapters.asana import AsanaAdapter
from autonomous_pipeline.adapters.base import TaskAdapter, TaskAdapterError
from autonomous_pipeline.adapters.file_task import FileTaskAdapter
from autonomous_pipeline.adapters.github import GitHubAdapter
from autonomous_pipeline.adapters.todo_json import TodoJsonAdapter
from autonomous_pipeline.schemas import RuntimeConfig


def build_adapter(config: RuntimeConfig, repo_root: str | Path) -> TaskAdapter:
    root = Path(repo_root)
    source = config.task_source
    if source == "todo_json":
        return TodoJsonAdapter(root / config.todo_path)
    if source == "github":
        return GitHubAdapter(
            repo_root=root,
            repo=config.github_repo,
            label=config.github_label,
            skip_labels=config.github_skip_labels,
            gh_command=config.github_command,
        )
    if source == "asana":
        if not config.asana_project_gid:
            raise TaskAdapterError("task_source 'asana' requires asana_project_gid in .autonomous.json")
        return AsanaAdapter(
            project_gid=config.asana_project_gid,
            workspace_gid=config.asana_workspace_gid,
            default_section_gid=config.asana_default_section_gid,
        )
    if source in ("file", "prompt"):
        return FileTaskAdapter(
            repo_root=root,
            task_file=config.task_file,
            prompt_text=config.prompt_text,
        )
    raise TaskAdapterError(f"Unknown task_source: {source}")
