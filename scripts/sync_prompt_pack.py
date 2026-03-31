#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync prompt pack into configured host directories")
    parser.add_argument(
        "action",
        choices=[
            "sync",
            "check",
            "print-cron",
            "print-anacron",
            "print-launchd",
            "print-windows-task",
            "print-windows-xml",
            "write-launchd",
            "write-windows-xml",
            "install-git-hooks",
            "print-host-features",
        ],
        nargs="?",
        default="check",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--env-file", default=".env", help="Path to .env file relative to repo root or absolute")
    parser.add_argument("--python-bin", default=None, help="Python executable to use in generated commands/hooks")
    parser.add_argument("--output", default=None, help="Output path for write-* actions")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = repo_root / env_path

    env = load_dotenv(env_path)
    targets = discover_targets(repo_root, env)
    python_bin = args.python_bin or sys.executable or "python3"

    if args.action == "print-host-features":
        print(feature_report())
        return 0

    if args.action == "print-cron":
        print(cron_line(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-anacron":
        print(anacron_line(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-launchd":
        print(launchd_plist(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-windows-task":
        print(windows_task_command(repo_root, python_bin=python_bin))
        return 0

    if args.action == "print-windows-xml":
        print(windows_task_xml(repo_root, python_bin=python_bin))
        return 0

    if args.action == "write-launchd":
        output = resolve_output_path(
            args.output,
            repo_root / ".runs" / "com.metazen11.autonomous-prompt-pack-sync.plist",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(launchd_plist(repo_root, python_bin=python_bin))
        print(output)
        return 0

    if args.action == "write-windows-xml":
        output = resolve_output_path(
            args.output,
            repo_root / ".runs" / "autonomous-prompt-pack-sync.xml",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(windows_task_xml(repo_root, python_bin=python_bin), encoding="utf-16")
        print(output)
        return 0

    if args.action == "install-git-hooks":
        written = install_git_hooks(repo_root, python_bin=python_bin)
        for hook_path in written:
            print(f"installed {hook_path}")
        return 0

    if not targets:
        print("No host targets configured in .env", file=sys.stderr)
        return 1

    if args.action == "sync":
        for target in targets:
            sync_target(repo_root, target)
            print(f"synced {target.name}: {target.skill_path}")
        return 0

    failed = False
    for target in targets:
        status = check_target(repo_root, target)
        agents_status = "ok" if not status.missing_agents else ",".join(status.missing_agents)
        skill_status = format_status(status.skill_in_sync)
        instructions_status = format_status(status.instructions_in_sync)
        config_status = format_status(status.config_snippet_in_sync)
        print(
            f"{target.name}: skill={skill_status} instructions={instructions_status} "
            f"config={config_status} agents={agents_status}"
        )
        if (
            status.skill_in_sync is False
            or status.instructions_in_sync is False
            or status.config_snippet_in_sync is False
            or status.missing_agents
        ):
            failed = True
    return 1 if failed else 0


def resolve_output_path(raw_output: str | None, default_path: Path) -> Path:
    if raw_output is None:
        return default_path
    output = Path(raw_output)
    if not output.is_absolute():
        return Path.cwd() / output
    return output


def format_status(status: bool | None) -> str:
    if status is None:
        return "n/a"
    return "ok" if status else "stale"


if __name__ == "__main__":
    raise SystemExit(main())
